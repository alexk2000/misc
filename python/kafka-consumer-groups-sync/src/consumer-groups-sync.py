#!/usr/bin/env python

from kafka import KafkaConsumer, KafkaAdminClient, TopicPartition
from kafka.structs import OffsetAndMetadata
from kafka.cluster import ClusterMetadata
import argparse
import logging
import time
import os
import sys
import yaml
import signal
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

# Prevent generating unneeded logs from python kafka module
log_kafka = logging.getLogger('kafka')
log_kafka.setLevel(logging.ERROR)

def get_args():
    parser = argparse.ArgumentParser(description="Sync Kafka consumers group")
    parser.add_argument("-c", "--config", dest="config", 
                        help="config file, yaml format", default="config.yaml")
    return parser.parse_args() 

class ConsumerGroups(object):
    def __init__(self, bootstrap_servers):
        self.bootstrap_servers = bootstrap_servers
        self.admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)

    def get_groups(self):
        # tp - topic->partitions
        tp = {}
        for group in self.admin.list_consumer_groups():
            tp[group[0]] = self.admin.list_consumer_group_offsets(group_id=group[0])
        return tp

class SyncConsumerGroups(object):
    def __init__(self, src_grps, dst_grps):
        self.src_grps = src_grps
        self.dst_grps = dst_grps

    def sync(self):
        src_grps = self.src_grps.get_groups()
        dst_grps = self.dst_grps.get_groups()
        for group_id in src_grps.keys():
            logging.debug(f"Processing {group_id}")
            if len(src_grps[group_id].keys()) == 0:
                logging.debug(f"Number of partitions is 0 for {group_id}, skipping")
            elif group_id not in dst_grps:
                consumer = KafkaConsumer(group_id=group_id, auto_offset_reset='earliest',
                                          bootstrap_servers=self.dst_grps.bootstrap_servers, 
                                          enable_auto_commit=True)
                # TODO: add handling case when number of topic partitions is different
                consumer.commit(src_grps[group_id])
                logging.info(f"Group {group_id} created")
            elif len(src_grps[group_id].keys()) != len(dst_grps[group_id].keys()):
                # TODO: need to handle this
                logging.warning(f"Number of partitions is different")
            else:
                logging.debug(f"Group {group_id} is already in sync, no action needed")
            logging.debug(f"Processing {group_id} finished")

class MainApp(object):
    def __init__(self, conf):
        try:
            with open(conf, "r") as config_f:
                self.conf = yaml.safe_load(config_f)
        except Exception as e:
            print(f"FATAL: wrong format of config file: {e}")
            sys.exit(1)

        # logging
        self.conf["log_format"] = "%(asctime)s %(levelname)s: %(message)s"
        logging.basicConfig(level=self.conf['log_level'], format=self.conf["log_format"])
        logging.info("Started")

        # handle signals
        for sgn in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
            signal.signal(sgn, self.__signal_handler)

        self.watch_dog = None
        self.max_watch_dog_diff = 300
        # Run health check web handler in seperate thread
        self.health_check = HTTPServer(('', self.conf["health_check_port"]), 
                                       self.health_check_class_creator())
        self.health_check_thread = threading.Thread(target = self.health_check.serve_forever, 
                                                    daemon=True).start()
        # Main app loop 
        self.main()

    def __signal_handler(self, signum, frame):
        logging.info('Got {} signal'.format(signal.Signals(signum).name))
        if signum == 1:
            # reload
            logging.info("Reload not implemented so far")
        elif signum in [2, 15]:
            # keyboardinterrupt or sigterm
            logging.info("Exit")
            sys.exit(0)

    def main(self):
        src_grps = ConsumerGroups(self.conf["source"]["bootstrap_servers"])
        dst_grps = ConsumerGroups(self.conf["destination"]["bootstrap_servers"])
        sync = SyncConsumerGroups(src_grps, dst_grps)
        while True:
            self.watch_dog = int(time.time())
            logging.info("Sync started")
            sync.sync()
            logging.info("Sync finished")
            logging.info(f"Sleep for {self.conf['interval']}s")
            time.sleep(self.conf['interval'])

    def health_check_class_creator(self):
        class HealthCheckHandler(SimpleHTTPRequestHandler):
            _main = self
            def do_GET(self_):
                cur_ts = int(time.time())
                if (cur_ts - self_._main.watch_dog) < self_._main.max_watch_dog_diff:
                    self_.send_response(200)
                else:
                    self_.send_response(500)
                self_.end_headers()
                return
        # Return class definition
        return HealthCheckHandler

if __name__ == "__main__":   
    args = get_args()
    if not os.path.isfile(args.config):
        print(f"FATAL: config file doesn't exist {args.config}")
        sys.exit(1)
    else:
        MainApp(conf=args.config)