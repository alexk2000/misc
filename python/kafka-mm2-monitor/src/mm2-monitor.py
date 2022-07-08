#!/usr/bin/env python

from kafka import KafkaConsumer, KafkaAdminClient, TopicPartition
from kafka.structs import OffsetAndMetadata
from kafka.cluster import ClusterMetadata
from urllib.parse import quote_plus, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import start_http_server, Summary, Counter, Gauge, MetricsHandler
import argparse
import logging
import time
import os
import sys
import yaml
import signal
import threading
import re
import json
import copy
from datetime import datetime

# Prevent generating unneeded logs from python kafka module
log_kafka = logging.getLogger("kafka")
log_kafka.setLevel(logging.ERROR)

# Prometheus metrics
TOPICS = Gauge("mm2_monitor_topics", "Number of topics from source under monitoring", ["mm_instance"])
ITER_DURATION = Gauge("mm2_monitor_iter_duration", "Time spent in last loop iteration (seconds)", ["mm_instance"])
ITER_START = Gauge("mm2_monitor_iter_start", "Time last loop iteration started (timestamp)", ["mm_instance"])
ITER_FAILED = Counter("mm2_monitor_iter_failed_total", "Number of failed loop iterations", ["mm_instance"])
ITER_LAST_SUCCESS = Gauge("mm2_monitor_iter_last_success", "Time of last successful loop iteration (timestamp)", ["mm_instance"])
ITER_LAST_STATUS = Gauge("mm2_monitor_iter_last_status", "Status of last loop iteration (0 - failed, 1 success)", ["mm_instance"])
NUMBER_OF_PERIOD_DIFF_TOPICS = Gauge("mm2_monitor_number_of_period_diff_topics", 
    "Number of topics with different number of messages for particular period of time in the past", ["mm_instance"])
NUMBER_OF_LAG_TOPICS = Gauge("mm2_monitor_number_of_lag_topics", 
    "Number of topics with lag more the lag_threshold parameter in config", ["mm_instance"])

def get_args():
    parser = argparse.ArgumentParser(description="Sync Kafka consumers group")
    parser.add_argument("-c", "--config", dest="config", 
                        help="config file, yaml format", default="config.yaml")
    return parser.parse_args() 

class Topics(object):
    def __init__(self, bservers, group_id, topics_bl=None, topics=None):
        self.bservers = bservers
        self.group_id = group_id
        self.topics_bl = topics_bl
        self.topics = topics

    def get(self):
        topics = KafkaConsumer(group_id=self.group_id, bootstrap_servers=self.bservers).topics()
        if self.topics:
            # Only topics from the list
            topics_ = []
            for topic in self.topics:
                if topic in topics:
                    topics_.append(topic)
                else:
                    logging.error(f"Topic {topic} doesn't exist on source, excluded from processing")
            return topics_
        else:
            # All topics 
            if self.topics_bl:
                topics_ = []
                for topic in topics:
                    for regexp in self.topics_bl:
                        if re.search(regexp, topic):
                            break
                    else:
                        topics_.append(topic)
                return topics_
            else:
                return topics

class TopicsStats(object):
    def __init__(self, source, target, monitor_period, monitor_shift,
                 lag_threshold, group_id):
        self.source = source
        self.target = target
        self.monitor_period = monitor_period
        self.monitor_shift = monitor_shift
        self.group_id = group_id
        self.lag_threshold = lag_threshold

        self.metrics = {
            "number_of_lag_topics": None,
            "number_of_period_diff_topics": None
        }

    def collect(self, topics):
        clusters = {
            self.source["name"]: self.source["bservers"],
            self.target["name"]: self.target["bservers"]
        }
        clusters_con = {}
        for cl_name, cl_bservers in clusters.items():
            clusters_con[cl_name] = KafkaConsumer(
                group_id=self.group_id, bootstrap_servers=cl_bservers)

        ts_cur = int(time.time()*1000)
        ts_start = ts_cur - self.monitor_period * 1000
        ts_stop = ts_cur - self.monitor_shift  * 1000

        result = {}
        for topic in topics:
            logging.debug(f"Processing topic {topic}")
            result[topic] = {}
            for cl_name, cl_consumer in clusters_con.items():
                result[topic][cl_name] = {}
                result[topic][cl_name]["partitions"] = {}
                result[topic][cl_name]["diff_period_total"] = 0
                result[topic][cl_name]["diff_end_total"] = 0
                partitions = cl_consumer.partitions_for_topic(topic)
                p_end_offsets = cl_consumer.end_offsets([TopicPartition(topic, p) for p in partitions])

                for p in partitions:
                    result[topic][cl_name]["partitions"][p] = {
                        "offset_start": None,
                        "offset_stop": None,
                        "offset_latest": None
                    }
                    tp = TopicPartition(topic, p)
                    result[topic][cl_name]["partitions"][p]["offset_latest"] = p_end_offsets[tp]
                    offset_start = cl_consumer.offsets_for_times({tp: ts_start})[tp]
                    if offset_start:
                        result[topic][cl_name]["partitions"][p]["offset_start"] = offset_start.offset
                        offset_stop = cl_consumer.offsets_for_times({tp: ts_stop})[tp]
                        if offset_stop:
                            result[topic][cl_name]["partitions"][p]["offset_stop"] = offset_stop.offset
                        else:
                            # Get the latest offset
                            offset_stop = p_end_offsets[tp]-1
                            result[topic][cl_name]["partitions"][p]["offset_stop"] = offset_stop
                        result[topic][cl_name]["partitions"][p]["diff_period"] = result[topic][cl_name]["partitions"][p]["offset_stop"] - \
                            result[topic][cl_name]["partitions"][p]["offset_start"]
                        result[topic][cl_name]["partitions"][p]["diff_end"] = result[topic][cl_name]["partitions"][p]["offset_latest"] - \
                            result[topic][cl_name]["partitions"][p]["offset_start"]
                        result[topic][cl_name]["diff_period_total"] += result[topic][cl_name]["partitions"][p]["diff_period"]
                        result[topic][cl_name]["diff_end_total"] += result[topic][cl_name]["partitions"][p]["diff_end"]
        self.result = result
        self.calc_metrics()
        return self.metrics

    def print_result(self):
        print(json.dumps(self.result, sort_keys=True, indent=4))

    def calc_metrics(self):
        self.metrics["number_of_period_diff_topics"] = 0
        self.metrics["number_of_lag_topics"] = 0

        for t_name, t_stats in self.result.items():
            s_diff_period_total = t_stats[self.source["name"]]["diff_period_total"]
            t_diff_period_total = t_stats[self.target["name"]]["diff_period_total"]
            s_diff_end_total = t_stats[self.source["name"]]["diff_end_total"]
            t_diff_end_total = t_stats[self.target["name"]]["diff_end_total"]

            if s_diff_period_total != t_diff_period_total:
                self.metrics["number_of_period_diff_topics"] += 1
                logging.warning(f"number of messages different in topic {t_name} for period in past (" + 
                                f"{s_diff_period_total} {t_diff_period_total})")
            lag = s_diff_end_total - t_diff_end_total
            if lag > self.lag_threshold:
                self.metrics["number_of_lag_topics"] += 1
                logging.warning(f"{t_name} lag is {lag} (>{self.lag_threshold})")

class MainApp(object):
    DEFAULT_CONFIG = {
        "group_id": "mm2_monitoring",
        "interval": 30,
        "log_format": "%(asctime)s %(levelname)s: %(message)s",
        "log_level": "INFO",
        "topics": "ALL",
        "web_port": 80,
        "watch_dog_diff": 600,
        "topics_bl": ["[-.]internal$", "^_", "\.replica$"],
        "monitor_period": 21600,
        "monitor_shift": 10
    }

    def __init__(self, conf):
        self.conf = copy.copy(self.DEFAULT_CONFIG)
        try:
            with open(conf, "r") as config_f:
                conf_file = yaml.safe_load(config_f)
        except Exception as e:
            print(f"FATAL: wrong format of config file: {e}")
            sys.exit(1)

        self.conf.update(conf_file)
        # logging
        logging.basicConfig(level=self.conf["log_level"], format=self.conf["log_format"])
        logging.info("Started")

        # handle signals
        for sgn in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
            signal.signal(sgn, self.__signal_handler)

        self.watch_dog = None
        # Run health check web handler in seperate thread
        self.web = HTTPServer(("", self.conf["web_port"]), 
                              self.web_class_creator())
        self.web_thread = threading.Thread(target = self.web.serve_forever, 
                                           daemon=True).start()

        if isinstance(self.conf["topics"], str) and self.conf["topics"] == "ALL":
            self.source_topics = Topics(self.conf["source"]["bservers"], 
                                        self.conf["group_id"], topics_bl=self.conf["topics_bl"])
        elif isinstance(self.conf["topics"], list):
            self.source_topics = Topics(self.conf["source"]["bservers"], 
                                        self.conf["group_id"], topics=self.conf["topics"])
        else:
            logging.fatal("No topics list defined")
            self.shutdown(1)
        
        self.topics_stats = TopicsStats(self.conf["source"], self.conf["target"], 
                                        self.conf["monitor_period"], self.conf["monitor_shift"],
                                        self.conf["lag_threshold"], self.conf["group_id"])

        self.main()

    def __signal_handler(self, signum, frame):
        logging.info("Got {} signal".format(signal.Signals(signum).name))
        if signum == 1:
            # reload
            logging.info("Reload not implemented so far")
        elif signum in [2, 15]:
            # keyboardinterrupt or sigterm
            self.shutdown()

    def main(self):
        s_name = self.conf["source"]["name"]
        ITER_FAILED.labels(s_name).inc(0)
        while True:
            iter_start = time.time()
            ITER_START.labels(s_name).set(iter_start)
            self.watch_dog = int(iter_start)
            try:
                topics = self.source_topics.get()
                TOPICS.labels(s_name).set(len(topics))
                metrics = self.topics_stats.collect(topics)
            except Exception as e:
                logging.error(f"metrics collection failed, raised exception {e}")
                ITER_FAILED.labels(s_name).inc()
                ITER_LAST_STATUS.labels(s_name).set(0)
                NUMBER_OF_PERIOD_DIFF_TOPICS.labels(s_name).set(-1)
                NUMBER_OF_LAG_TOPICS.labels(s_name).set(-1)
            else:
                ITER_LAST_SUCCESS.labels(s_name).set(time.time())
                ITER_LAST_STATUS.labels(s_name).set(1)
                NUMBER_OF_PERIOD_DIFF_TOPICS.labels(s_name).set(metrics["number_of_period_diff_topics"])
                NUMBER_OF_LAG_TOPICS.labels(s_name).set(metrics["number_of_lag_topics"])
                logging.debug(metrics)
            ITER_DURATION.labels(s_name).set(time.time() - iter_start)
            logging.info(f"Sleep for {self.conf['interval']}s")
            time.sleep(self.conf["interval"])

    def web_class_creator(self):
        class WebHandler(MetricsHandler):
            _main = self
            def do_GET(self_):
                if self_.path in ["/healthcheck", "/status", "/health"]:
                    self_.handle_health_check()
                elif self_.path == "/metrics":
                    logging.debug("Metrics triggered")
                    super().do_GET()
                else:
                    self_.not_implemented()
            def handle_health_check(self_):
                logging.debug("Health check triggered")
                cur_ts = int(time.time())
                message = ""
                if (cur_ts - self_._main.watch_dog) < self_._main.conf["watch_dog_diff"]:
                    self_.send_response(200)
                    message = "SUCCESS"
                else:
                    self_.send_response(500)
                    message = "FAILED"
                self_.send_header("Content-Type",
                                "text/plain; charset=utf-8")
                self_.end_headers()
                self_.wfile.write(message.encode("utf-8"))

            def not_implemented(self_):
                logging.debug(f"Not implemented url triggered {self_.path}")
                self_.send_response(500)
                self_.send_header("Content-Type",
                                  "text/plain; charset=utf-8")
                self_.end_headers()
                self_.wfile.write("NOT IMPLEMENTED".encode("utf-8"))

        return WebHandler

    def shutdown(self, exit_code=0):
        logging.info("Exit")
        exit(exit_code)

if __name__ == "__main__":   
    args = get_args()
    if not os.path.isfile(args.config):
        print(f"FATAL: config file doesn't exist {args.config}")
        sys.exit(1)
    else:
        MainApp(conf=args.config)