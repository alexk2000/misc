#!/bin/env python3


import shlex
import subprocess
import sys
import time
import os
import glob
import logging
import json
import datetime
import inspect
import pymysql


class TRunnerApp():

    def __init__(self):

        self.start = time.time()

    def set_app_container(self, app_container):

        self.app_container = app_container
        self.__config = self.app_container.get_config_item()

        self.db_container = "{}-db".format(self.__config['appName'])
        self.script_dir = "/opt/scripts/test_restore/test_restore_script"

    def run_command(self, cmd_str, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=None):

        logging.info(cmd_str)
        #cmd_list = shlex.split(cmd_str)
        with subprocess.Popen(cmd_str, shell=True, stdout=stdout, stderr=stderr, env=env) as proc:
            try:
                outs, errs = proc.communicate()
                ret = proc.returncode
            except subprocess.TimeoutExpired as e:
                pass

        return {'ret': ret, 'stdout': outs, 'stderr': errs}

    def start_db_container(self):
    
        cmd_str = "docker run --rm -d -v /opt/scripts/test_restore/mysql_config/custom.cnf:/etc/mysql/conf.d/custom.cnf --name {} -e MYSQL_ROOT_PASSWORD=skdWpel33Psd mariadb".format(self.db_container)
        net = "--net container:{}".format(self.db_container)
        return self.run_command(cmd_str)

    def stop_db_container(self):

        cmd_str = "docker rm -f -v {}".format(self.db_container)
        result = self.run_command(cmd_str)
        if result['ret'] != 0:
            logging.error("deleting db container failed: {}, {}".format(result['stdout'], result['stderr']))
        else:
            logging.info("db container deleted successfully")
        
    def main(self):

        ret = 0
        logging.info("------ test restore started")
        borgCheck = "-s"
        if self.__config['borgCheck']:
            borgCheck = ""

        logs_dir = "{}/logs/{}".format(self.script_dir, self.__config['appName'])
        os.makedirs(logs_dir, exist_ok=True)
        tests_dir = "{}/tests/{}".format(self.script_dir, self.__config['appName'])
        os.makedirs(tests_dir, exist_ok=True)
        cmd_restore_template = "docker run --privileged=true --rm --name {appName}_{restoreType}_restore {net} -v nfs_volume1:/backup_storage -v {script_dir}/app:/usr/src/myapp -v {logs_dir}:/usr/src/myapp/logs -v {tests_dir}:/usr/src/myapp/tests -w /usr/src/myapp custom_python:3.5 python trestore.py -n {appName} -t {restoreType} {borgCheck}".format(appName=self.__config['appName'], restoreType=self.__config['restoreType'], net="{net}", logs_dir=logs_dir, tests_dir=tests_dir, script_dir=self.script_dir, borgCheck=borgCheck)        

        if self.__config['restoreType'] == "mysql":


            start_db_container = self.start_db_container()
            if start_db_container['ret'] != 0:
                logging.critical("docker db container not started: {}, {}".format(start_db_container['stdout'], start_db_container['stderr']))
                ret = 3
            else:

                logging.info("docker db container started")
                time.sleep(10)
                net = "--net container:{}".format(self.db_container)
                cmd_str = cmd_restore_template.format(net=net)
                restore = self.run_command(cmd_str)
                if restore['ret'] != 0:
                    logging.critical("test restore failed: {}, {}".format(restore['stdout'], restore['stderr']))
                    ret = 4
                else:
                    logging.info("{}".format(restore['stdout'].decode()))
                    logging.info("test restore completed successfully")
                self.stop_db_container()

        elif self.__config['restoreType'] == "fs":

            net = ""
            cmd_str = cmd_restore_template.format(net=net)
            restore = self.run_command(cmd_str)
            if restore['ret'] != 0:
                logging.critical("test restore failed: {}, {}".format(restore['stdout'], restore['stderr']))
                ret = 4
            else:
                logging.info("{}".format(restore['stdout'].decode()))
                logging.info("test restore completed successfully")

        else:
            logging.critical("restore type {} not implemented".format(self.__config['restoreType']))
            ret = 2

        return ret
