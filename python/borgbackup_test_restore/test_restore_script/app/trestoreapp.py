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
import re

LAST_BACKUP_AGE = 60*60*24*2
MYSQL_USER = "root"
MYSQL_PASSWORD = "skdWpel33Psd"
MYSQL_HOST = "127.0.0.1"
# borg --lock-wait 
LOCK_WAIT = 3600
FS_RESTORE_PATH = "/tmp/restore"
FS_RESTORE_LIST = "tests/fs_retore_list.json"

class TestRestoreApp():

    def __init__(self):

        self.start = time.time()
        #self.__config = self.app_container.__config

    def set_app_container(self, app_container):

        self.app_container = app_container
        self.__config = self.app_container.get_config_item()
        #self.log_file_handler = open(self.app_container.get_config_item('logFile'), "at")
#        self.lock_file_name = self.app_container.get_config_item('lock_file')

    def run_command(self, cmd_str, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=None):

#        if stdout is None:
#            stdout = self.log_file_handler
#        if stderr is None:
#            stderr=self.log_file_handler
#
        logging.info(cmd_str)
        #cmd_list = shlex.split(cmd_str)
        with subprocess.Popen(cmd_str, shell=True, stdout=stdout, stderr=stderr, env=env) as proc:
            try:
                outs, errs = proc.communicate()
                ret = proc.returncode
            except subprocess.TimeoutExpired as e:
                pass

        return {'ret': ret, 'stdout': outs, 'stderr': errs}

    def read_last_backup(self, borgPrefix, borgRepo):

        # default
        ret = {'ret': 0, 'stdout': None, 'stderr': None}
        cmd_str = "borg list --lock-wait {} --prefix {} --json --last 1 {}".format(LOCK_WAIT, borgPrefix, borgRepo)
        result = self.run_command(cmd_str)
        # error on running borg 
        if result['ret'] != 0:
            return result

        self.last_backup_json = json.loads(bytes.decode((result['stdout'])))
        # error if no archives found in repo
        if len(self.last_backup_json['archives']) == 0:
            return {'ret': 1, 'stdout': None, 'stderr': 'no archives with prefix {} found in repo {}'.format(borgPrefix, borgRepo)}

        return ret        


    def verify_backup_age(self, last_backup_json):

        date_start = datetime.datetime.strptime(last_backup_json['archives'][0]['start'], '%Y-%m-%dT%H:%M:%S.%f')
        if (datetime.datetime.now().timestamp()-date_start.timestamp()) > LAST_BACKUP_AGE:
            return 2
        else:
            return 0
        
    def test(self, restoreType):

        test_pattern = 'test_{}_'.format(restoreType)
        for test in dir(self):
            if callable(getattr(self, test)) and test.find(test_pattern) == 0:
                ret = getattr(self, test)()
                if ret != 0:
                    return 1

        return 0

    def test_mysql_test1(self):
        
        test_name = "tests/{}".format(inspect.stack()[0][3]) 
        #print(test_name)
        logging.info("running test {}".format(test_name)) 
        if os.path.isfile(test_name) and os.path.getsize(test_name) > 0:

            ret = 0
            try:
                with open(test_name, 'r') as f:
                    test = json.load(f)
                conn = pymysql.connect(host='127.0.0.1', user='root', passwd='skdWpel33Psd', cursorclass=pymysql.cursors.DictCursor)
                cur = conn.cursor()
                for ge in test['ge']:
                    cur.execute(ge['sql'])
                    count = cur.fetchone()
                    if count['count'] < ge['count']:
                        ret = 1       
                        logging.error('test {} query failed: {}, {} < {}'.format(test_name, ge['sql'], count['count'], ge['count']))
                        break
                    else:
                        logging.info('test {} query completed successfully: {}, {} > {}'.format(test_name, ge['sql'], count['count'], ge['count']))

                for eq in test['eq']:
                    cur.execute(eq['sql'])
                    count = cur.fetchone()
                    if not eq['in'].items() <= count.items():
                        ret = 1
                        logging.error('test {} query failed: {}'.format(test_name, eq['sql']))
                        break
                    else:
                        logging.info('test {} query completed successfully: {}'.format(test_name, eq['sql']))

            except Exception as e:
                logging.error(e)
                ret = 1
            else:
                cur.close()
                conn.close()

            return ret                


        else:
            logging.warning('config file is missing, test skipped')
            return 0

    def test_fs_test1(self):

        test_name = "tests/{}".format(inspect.stack()[0][3])
        logging.info("running test {}".format(test_name))
        if os.path.isfile(test_name) and os.path.getsize(test_name) > 0:

            ret = 0
            try:
                with open(test_name, 'r') as f:
                    test = json.load(f)

                for check in test:
                    file_path = "{}/{}".format(FS_RESTORE_PATH, check['file'])
                    if not os.path.isfile(file_path):
                        logging.error('test {} failed: no such file {}'.format(test_name, file_path))
                    exp = re.compile(check['regexp'])
                    found = False
                    with open(file_path, 'r') as f:
                        for line in f:
                            if exp.search(line) is not None:
                                found = True
                                break
                        if not found:
                            logging.error('test {} failed: regexp "{}" not found in {}'.format(test_name, check['regexp'], check['file']))    
                            return 2
                        else:
                            logging.info('test {} completed successfully: regexp "{}" found in {}'.format(test_name, check['regexp'], check['file']))


            except Exception as e:
                logging.error(e)
                ret = 1

            return ret


        else:
            logging.warning('config file {} is missing or empty, test skipped'.format(test_name))
            return 0


    def check_repo(self, borgRepo):

        cmd_str = "borg check --lock-wait {} {}".format(LOCK_WAIT, borgRepo)
        return self.run_command(cmd_str)

    def restore_mysql(self, last_backup_json, db=''):

        logging.info('mysql restore started')
        cmd_str = "borg extract --nobsdflags --lock-wait {} --stdout {borgRepo}::{name} | mysql -h {host} -u {user} -p{password} {db}".format(LOCK_WAIT, borgRepo=self.__config['borgRepo'], name=last_backup_json['archives'][0]['name'], host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, db=db)
        return self.run_command(cmd_str)

    def restore_fs(self, last_backup_json):

        logging.info('fs restore started') 
        os.makedirs(FS_RESTORE_PATH, exist_ok=True)
        extract_list = ""
        borg_extract = "borg extract --nobsdflags --lock-wait {LOCK_WAIT} {borgRepo}::{name}".format(LOCK_WAIT=LOCK_WAIT, borgRepo=self.__config['borgRepo'], name=last_backup_json['archives'][0]['name'])
        if os.path.isfile(FS_RESTORE_LIST) and os.path.getsize(FS_RESTORE_LIST) > 0:

            try:
                with open(FS_RESTORE_LIST, 'r') as f:
                    restore_json = json.load(f)
                extract_list = " ".join(restore_json)
            except Exception as e:
                return {'ret': 1, 'stdout': '', 'stderr': e}

        cmd_str = "(cd {FS_RESTORE_PATH} && {borg_extract} {extract_list})".format(borg_extract=borg_extract, extract_list=extract_list, FS_RESTORE_PATH=FS_RESTORE_PATH)
        return self.run_command(cmd_str) 

    def main(self):

        logging.info("------ test restore script started")
        # verify repo by 'borg check'
        if self.__config['borgCheck']:
            borg_check = self.check_repo(self.__config['borgRepo'])
            if borg_check['ret'] != 0:
                logging.critical('borg repository check failed: {}'.format(borg_check['stderr']))
                return 6
            else:
                logging.info('borg repository check completed successfully')
        else:
            logging.info('borg repository check skipped')

        last_backup = self.read_last_backup(self.__config['borgPrefix'], self.__config['borgRepo'])
        if last_backup['ret'] != 0:
            logging.critical('can\'t read information about last backup: {}'.format(last_backup['stderr']))
            return last_backup['ret']
        
        backup_age = self.verify_backup_age(self.last_backup_json)
        if backup_age != 0:
            logging.critical('last backup age is more than {} seconds'.format(LAST_BACKUP_AGE))
            return backup_age 

        if self.__config['restoreType'] == 'mysql':

            # restore of system db
            main_last_backup_json = self.last_backup_json

            if not self.__config['skipSystemMysql']:

                last_backup = self.read_last_backup(self.__config['borgPrefixSystemMysql'], self.__config['borgRepo'])
                if last_backup['ret'] != 0:
                    logging.critical('can\'t read information about last system mysql backup: {}'.format(last_backup['stderr']))
                    return last_backup['ret']

                backup_age = self.verify_backup_age(self.last_backup_json)
                if backup_age != 0:
                    logging.critical('last mysql system backup age is more than {} seconds'.format(LAST_BACKUP_AGE))
                    return backup_age

                restore_result = self.restore_mysql(self.last_backup_json, db='mysql')
                if restore_result['ret'] != 0:
                    logging.critical('system mysqldump import failed: {},{}'.format(restore_result['stderr'], restore_result['stdout']))
                    return 3
                else:
                    logging.info('system mysqldump imported successfully')
 
                # flush privileges
                logging.info('mysqladmin reload')
                add_user = "echo \"GRANT ALL ON *.* TO 'root'@'127.0.0.1' IDENTIFIED BY '{password}'\"".format(password=MYSQL_PASSWORD)
                cmd_str = "{add_user} | mysql -h {host} -u {user} -p{password}".format(add_user=add_user, host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD)
                self.run_command(cmd_str)

                cmd_str = "echo 'flush privileges' | mysql -h {host} -u {user} -p{password}".format(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD)
                self.run_command(cmd_str)

            # main restore
            self.last_backup_json = main_last_backup_json
            restore_result = self.restore_mysql(self.last_backup_json)
            if restore_result['ret'] != 0:
                logging.critical('mysqldump import failed: {},{}'.format(restore_result['stderr'], restore_result['stdout']))
                return 3
            else:
                logging.info('mysqldump imported successfully')            
            
        elif self.__config['restoreType'] == 'fs':

            restore_result = self.restore_fs(self.last_backup_json)
            if restore_result['ret'] != 0:
                logging.critical('fs restore failed: {},{}'.format(restore_result['stderr'], restore_result['stdout']))
                return 3
            else:
                logging.info('fs restore completed successfully')

        else:
            logging.critical('restore type {} not implemented'.format(self.__config['restoreType']))
            return 5

        # testing
        ret = self.test(self.__config['restoreType'])
        if ret != 0:
            return 4

        logging.info("test restore completed successfully")
        return 0
