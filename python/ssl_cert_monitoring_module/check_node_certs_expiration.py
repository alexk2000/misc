#!/usr/bin/python3
"""
Before using this module it's strongly recommended to read documentation:
https://anchorfree.atlassian.net/wiki/spaces/~746991856/pages/950993346/Monitoring+expiration+of+TLS+Certificate+on+hosts#Implementation
"""

import os
import glob
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import pem
from concurrent.futures import ThreadPoolExecutor
import trafaret as t
from trafaret.constructor import construct
from checks.check_base import CheckBase

# Read environment variables
TTL_THRESHOLD_RATIO = float(os.environ.get("TTL_THRESHOLD_RATIO", 0.333))  # TTL/3
TTL_THRESHOLD_MAX = int(os.environ.get("TTL_THRESHOLD_MAX", 2592000))  # 30 days


class Check(CheckBase):
    label_list = ["cn", "file", "issuer", "sn", "counter",
                  "hint", "notAfter", "notBefore", "mode"]
    cert_uniq_combination = ("cn", "issuer", "sn", "mode")
    worker_num = 10
    date_format = "%Y-%m-%dT%H:%M:%S"
    file_csv = "/var/log/certs.csv"
    file_csv_format = "{file};{cn};{issuer};{sn};{notBefore};" + \
                      "{notAfter};{hint};{ts_diff}"
    arg_structure = t.Dict(
        t.Key("path", trafaret=t.String),
        t.Key("file_extension", trafaret=t.Or(t.List(t.String), t.String),
              default="crt", optional=True),
        t.Key("recursive_search", trafaret=t.ToBool,
              optional=True, default=False),
        t.Key("hint", trafaret=t.String(allow_blank=True),
              optional=True, default=""),
        t.Key("mode", trafaret=t.Enum("all", "alert", ""),
              optional=True, default="alert"),
        t.Key("ttl_threshold_ratio", trafaret=t.Float,
              optional=True, default=TTL_THRESHOLD_RATIO),
        t.Key("ttl_threshold_max", trafaret=t.Int,
              optional=True, default=TTL_THRESHOLD_MAX)
    )

    def __init__(self, metric, args, label_hostname,
                 self_health_state, log_level):
        super().__init__(metric, args, label_hostname,
                         self_health_state, log_level)
        self.arg_validator = construct(self.arg_structure)
        # Validate args one time on object creation.
        # self.paths contains only valid item from self.args list.
        self.paths = []
        if self.args and type(self.args) is list:
            for arg in self.args:
                try:
                    arg = self.arg_validator(arg)
                except t.dataerror.DataError as e:
                    self.logger.error(e.as_dict(True))
                else:
                    self.paths.append(arg)
        else:
            self.logger.error("No args or args is not a list")

    def get_certs_from_file(self, cert_file):
        """Return list of certs from single cert file."""
        try:
            cert_chain = pem.parse_file(cert_file)
        except Exception as e:
            self.logger.error(
                "failed to process {} ({})".format(cert_file, e))
            return []

        certs = []
        for cert in cert_chain:
            if isinstance(cert, pem.Certificate):
                cert_loaded = x509.load_pem_x509_certificate(
                    cert.as_bytes(), default_backend())

                cn = cert_loaded.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                # if subject doesn't contain CN - use whole subject string as 'cn' label
                cn_or_subject = cn[0].value if len(cn) == 1 else cert_loaded.subject.rfc4514_string()

                certs.append({
                    "cn": cn_or_subject,
                    "file": cert_file,
                    "issuer": cert_loaded.issuer.rfc4514_string(),
                    "sn": cert_loaded.serial_number,
                    "notAfter": cert_loaded.not_valid_after.strftime(self.date_format),
                    "notBefore": cert_loaded.not_valid_before.strftime(self.date_format),
                    "ts_diff": int(cert_loaded.not_valid_after.timestamp() -
                                   self.date_cur.timestamp()),
                })

        return certs

    def get_files_by_ext(self, path, file_extension, recursive_search):
        """Return set of uniq files with particular extension(s)."""
        # create extensions list and remove . at the beginning
        exts = map(lambda ext: ext.lstrip("."),
                   [file_extension] if type(file_extension) is str else file_extension)
        if recursive_search:
            return set(sum(map(lambda ext: glob.glob("{}/**/*.{}".format(path, ext), recursive=True), exts), []))
        else:
            return set(sum(map(lambda ext: glob.glob("{}/*.{}".format(path, ext), recursive=False), exts), []))

    def get_certs_from_path(self, p):
        """Return list of all certs in all file in particular path."""
        cert_files = []
        if os.path.exists(p["path"]):
            # get all cert files from path
            if os.path.isdir(p["path"]):
                cert_files = self.get_files_by_ext(
                    p["path"], p["file_extension"], p["recursive_search"])
            elif os.path.isfile(p["path"]):
                cert_files = [p["path"], ]
            else:
                return []

            # run threads for parallel processing cert files in the path
            with ThreadPoolExecutor(self.worker_num) as executor:
                certs = sum(
                    executor.map(self.get_certs_from_file, cert_files), [])

            # always export special metric per path which indicates that path
            # is under monitoring and how many certs found
            self.wrapper.set({
                "cn": "", "file": p['path'], "issuer": "", "sn": "",
                "counter": "", "hint": str(p), "notAfter": "", "notBefore": "",
                "mode": ""
            }, len(certs))

            # add path related attributes (hint, mode etc) and return found certs
            return list(map(lambda cert: dict(
                cert, hint=p["hint"], mode=p["mode"],
                ttl_threshold_ratio=p["ttl_threshold_ratio"],
                ttl_threshold_max=p["ttl_threshold_max"],), certs))
        else:
            self.logger.error(
                "{} doesn't exist ".format(p["path"]))
            return []

    def get_uniq_certs(self, certs):
        """Return list of unique certificates.

        Unique cert is unique labels combination defined
        in self.cert_uniq_combination
        """
        uniq = {}
        for cert in sorted(certs, key=lambda cert_: cert_["file"]):
            uniq_item = tuple(
                (value for label, value in cert.items() if label in self.cert_uniq_combination))
            if uniq_item in uniq:
                uniq[uniq_item]["counter"] += 1
            else:
                uniq[uniq_item] = cert.copy()
                uniq[uniq_item]["counter"] = 1
        return list(uniq.values())

    def will_be_expired(self, cert):
        """Return True if cert expires soon, False - not"""
        date_not_before = datetime.strptime(cert["notBefore"], self.date_format)
        date_not_after = datetime.strptime(cert["notAfter"], self.date_format)
        ttl = date_not_after - date_not_before

        ttl_threshold_max_td = timedelta(seconds=cert["ttl_threshold_max"])
        ttl_threshold = ttl * cert["ttl_threshold_ratio"]
        ttl_threshold = ttl_threshold if ttl_threshold < ttl_threshold_max_td else ttl_threshold_max_td

        if self.date_cur > (date_not_after - ttl_threshold):
            return True
        else:
            return False

    def export_prometheus(self, certs):
        """Exports certs in Prometheus format"""
        for cert in certs:
            if cert["mode"] == "all" or cert["ts_diff"] <= 0 \
               or self.will_be_expired(cert):
                self.wrapper.set({
                    "cn": cert["cn"],
                    "file": cert["file"],
                    "issuer": cert["issuer"],
                    "sn": cert["sn"],
                    "counter": cert["counter"],
                    "hint": cert["hint"],
                    "notAfter": cert["notAfter"],
                    "notBefore": cert["notBefore"],
                    "mode": cert["mode"]
                }, cert["ts_diff"])

    def export_csv(self, certs):
        """Exports certs in CSV format"""
        try:
            os.makedirs(os.path.dirname(self.file_csv), exist_ok=True)
            with open(self.file_csv, 'w') as f:
                # remove duplicates and save to file
                for cert in self.get_list_of_uniq_dicts(
                        data=certs,
                        exclude_fields=["mode", "ttl_threshold_ratio", "ttl_threshold_max"]):
                    f.write(self.file_csv_format.format(**cert) + os.linesep)
        except Exception as e:
            self.logger.error("Error occurred on saving certs to csv file: {}".format(e))

    def get_list_of_uniq_dicts(self, data, exclude_fields=[]):
        """Input: list of dicts, return: list of uniq dicts"""
        data_ = data.copy()
        # optionally remove fields in each dict before form uniq list
        if exclude_fields:
            data_ = [{k: v for k, v in item.items() if k not in exclude_fields} for item in data_]

        return list(map(dict, set(tuple(sorted(item.items())) for item in data_)))

    def run_check(self):
        """Main"""
        # self.args validation is in __init__
        if self.paths:
            self.date_cur = datetime.utcnow()
            # get certs from all paths/files, run thread per path
            with ThreadPoolExecutor(len(self.paths)) as executor:
                certs = self.get_list_of_uniq_dicts(sum(executor.map(
                    self.get_certs_from_path, self.paths), []))

            self.export_prometheus(self.get_uniq_certs(certs))
            self.export_csv(certs)
        else:
            self.logger.error("Nothing to check")
