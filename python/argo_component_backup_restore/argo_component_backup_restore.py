#!/usr/bin/env python

# Backup/restore of Argo component information for specific environment.
# This is part of Argo component decommission solution.
#
# Example:
# $ argo_component_backup_restore.py backup --environment staging --component testappnetscaler -f staging_testappnetscaler.json
# Backup successfully saved to staging_testappnetscaler.json
#
# $ ansible-playbook -i inventory/staging/argo.py component_decommission.yml --limit "testappnetscaler" --tags "remove_from_argo"
# $ argo_component_backup_restore.py restore staging_testappnetscaler.json
# Component staging/testappnetscaler has been successfully restored


import argparse
import sys
import json
import httplib2
import os
import time
from getpass import getpass

try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

# constants declaration
ARGO_URL_DEFAULT = "https://argo"
REQUEST_HEADER_JSON = {
    'Accept': 'application/json',
    'Content-Type': 'application/json;charset=UTF-8'
}
REQUEST_HEADER_PLAIN = {
    'Content-Type': 'text/plain;charset=UTF-8'
}

def get_args():
    parser = argparse.ArgumentParser()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="backup or restore")

    parser_backup = subparsers.add_parser("backup", help="backup argo component in particular environment")
    parser_backup.add_argument("-e", "--environment", required=True, help="argo environment")
    parser_backup.add_argument("-c", "--component", required=True, help="argo component")
    parser_backup.add_argument("-f", "--file", help="file to save backup")
    parser_backup.add_argument("-s", "--stdout", action="store_true", help="print backup to console")
    parser_backup.set_defaults(func=do_backup)

    parser_restore = subparsers.add_parser("restore", help="restore argo component in particular environment")
    parser_restore.add_argument("file", help="file to restore")
    parser_restore.set_defaults(func=do_restore)

    return parser.parse_args()

def do_backup(args):
    backup_file = None
    if not args.file:
        backup_file = "{0}_{1}_{2}.json".format(args.environment, args.component, int(time.time()))
    else:
        backup_file = args.file

    if os.path.exists(backup_file):
        print("Error: file {0} exists".format(backup_file))
        sys.exit(1)

    url = "{0}/inventory?environment={1}&component={2}".format(argo_url, args.environment, args.component)
    response_obj, content_str =  http_request(url=url)
    content_dict = json.loads(content_str)
    # json verification, if "environments" is empty then component doesn't exist and we can't take backup
    if not content_dict["environments"]:
        print("Error: looks like component {0}/{1} doesn't exist\n{2}".format(
            args.environment, args.component, content_dict))
        sys.exit(1)   

    # make json prettier with indents
    content_str_ident = json.dumps(content_dict, indent=2)

    try:
        f = open(backup_file, "w")
    except Exception as e:
        print("Error: failed to open backup file: {0}".format(e))
    else:
        try:
            f.write(content_str_ident)
        except Exception as e2:
            print("Error: failed to save backup to file: {0}".format(e2))
        else:
            print("Backup successfully saved to {0}".format(backup_file))
        f.close()

    if args.stdout:
        print(content_str_ident)

def do_restore(args):
    if not os.path.exists(args.file):
        print("Error: file {0} doesn't exist".format(args.file))
        sys.exit(1)

    f = open(args.file, "r")
    backup_dict = json.load(f)
    f.close()

    # some basic backup json verification 
    for key in ["instances", "environments"]:
        if key not in backup_dict:
            print("Error: '{0}' missing in backup file {1}".format(key, args.file))
            sys.exit(1)

    envs = list(backup_dict["environments"].keys())
    if len(envs) > 1:
        print("Error: there should be only one environment in {0}, found {1}".format(args.file, envs))
        sys.exit(1)
    component_env = envs[0]

    components = list(backup_dict["environments"][component_env]["components"].keys())
    if len(components) > 1:
        print("Error: there should be only one component in {0}, found {1}".format(args.file, components))
        sys.exit(1)
    component_name = components[0]

    component_dict = backup_dict["environments"][component_env]["components"][component_name]

    # verification if component exists
    url = "{0}/environment/{1}/component/{2}".format(argo_url, component_env, component_name)
    response_obj, content_str = http_request(url=url)
    # 404 meaning component doesn't exist so we can do restore
    response_obj.status = 404
    if response_obj.status == 404:
        argo_user = os.getenv("argo_user")
        argo_pass = os.getenv("argo_pass")
        if not argo_user:
            argo_user = raw_input("Argo user: ")
        if not argo_pass:
            argo_pass = getpass("Argo password: ")

        # component creation
        url = "{0}/environment/{1}/component/{2}".format(argo_url, component_env, component_name)
        body = {"longName": component_dict["longName"]}
        response_obj, content_str =  http_request(
            url=url, method="PUT", body=body, user=argo_user, password=argo_pass)
        if response_obj.status != 200:
            print("Error: failed component creation {0}/{1}:\n{2}\n{3}".format(
                component_env, component_name, response_obj, content_str))
            sys.exit(1)

        # adding component metadata
        component_metadata = component_dict["metadata"]
        for key, value in component_metadata.items():
            url = "{0}/environment/{1}/component/{2}/metadata/{3}".format(
                argo_url, component_env, component_name, key)
            response_obj, content_str = http_request(
                url=url, method="PUT", body=value, headers=REQUEST_HEADER_PLAIN, user=argo_user, password=argo_pass)
            if response_obj.status != 200:
                print("Error: failed to add metadata '{2}:{3}' for {0}/{1}:\n{4}\n{5}".format(
                    component_env, component_name, key, value, response_obj, content_str))
                sys.exit(1)

        # instances creation
        component_instances = component_dict["instances"]
        for instance, attrs in component_instances.items():
            url = "{0}/environment/{1}/component/{2}/instance/{3}".format(
                argo_url, component_env, component_name, instance)
            response_obj, content_str = http_request(
                url=url, method="PUT", body=attrs, user=argo_user, password=argo_pass)
            if response_obj.status != 200:
                print("Error: failed to add instance {2} for {0}/{1}:\n{3}\n{4}".format(
                    component_env, component_name, instance, response_obj, content_str))
                sys.exit(1)
            # adding instance metadata
            instance_metadata = attrs["metadata"]
            for key, value in instance_metadata.items():
                url = "{0}/environment/{1}/component/{2}/instance/{3}/metadata/{4}".format(
                    argo_url, component_env, component_name, instance, key)
                response_obj, content_str = http_request(
                    url=url, method="PUT", body=value, headers=REQUEST_HEADER_PLAIN, user=argo_user, password=argo_pass)
                if response_obj.status != 200:
                    print("Error: failed to add instance '{4}' metadata '{2}:{3}' for {0}/{1}:\n{5}\n{6}".format(
                        component_env, component_name, key, value, instance, response_obj, content_str))
                    sys.exit(1)

        # artifact creation
        artifact = component_dict["artifact"]
        artifact_metadata = artifact.pop("metadata")
        url = "{0}/environment/{1}/component/{2}/artifact".format(argo_url, component_env, component_name)
        response_obj, content_str =  http_request(
            url=url, method="PUT", body=artifact, user=argo_user, password=argo_pass)
        if response_obj.status != 200:
            print("Error: failed to add artifact {4} for {0}/{1}:\n{2}\n{3}".format(
                component_env, component_name, response_obj, content_str, artifact))
            sys.exit(1)

        # adding artifact metadata
        for key, value in artifact_metadata.items():
            url = "{0}/environment/{1}/component/{2}/artifact/metadata/{3}".format(
                argo_url, component_env, component_name, key)
            response_obj, content_str = http_request(
                url=url, method="PUT", body=value, headers=REQUEST_HEADER_PLAIN, user=argo_user, password=argo_pass)
            if response_obj.status != 200:
                print("Error: failed to add artifact metadata '{2}:{3}' for {0}/{1}:\n{4}\n{5}".format(
                    component_env, component_name, key, value, response_obj, content_str))
                sys.exit(1)

        print("Component {0}/{1} has been successfully restored".format(component_env, component_name))
    # 200 - component exists, exiting 
    elif response_obj.status == 200:
        print("Error: component '{0}' exists in env '{1}'".format(component_name, component_env))
        sys.exit(1)
    else:
        print("Error: request to {0} returns unhandled http response code {1}".format(url, response_obj.status))
        sys.exit(1)

# wrapper for httplib2 or any other http lib
# returns tuple (response, content)
def http_request(url=None, method="GET", body="", headers=REQUEST_HEADER_JSON, user=None, password=None):
    if url:
        target = urlparse(url)
        http = httplib2.Http(disable_ssl_certificate_validation=True, timeout=120)
        if user and password:
            http.add_credentials(user, password)
        body_ = body
        if type(body) == dict:
            body_ = json.dumps(body)
        return http.request(target.geturl(), method, body_, headers)

# program starts here
if __name__ == "__main__":
    argo_url = os.getenv('argo', ARGO_URL_DEFAULT)
    args = get_args()
    args.func(args)
    sys.exit(0)
