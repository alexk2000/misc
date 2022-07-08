#!/bin/env python3

from daemon import Daemon
from trestoreapp import TestRestoreApp
import argparse
import logging
import os
import sys
import time
import yaml
import argcomplete
PYTHON_ARGCOMPLETE_OK = True



parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", dest="logLevel", action="store_true",
                    help="increase output verbosity")
parser.add_argument("-c", "--config", dest="configFile", help="config file")
parser.add_argument("-d", "--daemon", dest="daemon", action="store_true", help="run as background daemon")
parser.add_argument("-l", "--log", dest="logFile", help="path to log file")
parser.add_argument("-p", "--pid", dest="pidFile", help="path to pid file")
parser.add_argument("-n", "--name", dest="appName", help="name of this session", required=True)
parser.add_argument("-r", "--repo", dest="borgRepo", help="path borg repos")
parser.add_argument("-t", "--type", dest="restoreType", help="currently fs or mysql")
parser.add_argument("-b", "--prefix", dest="borgPrefix", help="borg prefix")
parser.add_argument("-s", "--skip-borg-check", dest="borgCheck", action="store_true", help="skip repository borg check")
parser.add_argument("-f", "--skip-system_mysql", dest="skipSystemMysql", action="store_true", help="skip restore of system mysql db")

argcomplete.autocomplete(parser)
args = parser.parse_args()
appArgs = {}
dir_name = os.path.dirname(os.path.realpath(sys.argv[0]))
log_dir = "logs"

# trestore.py -n stagdbs11 -r /backup_storage/borgbackup/repos/stagdbs11 -t mysql -b stagdbs11-mysql
if args.borgRepo:
    appArgs['borgRepo'] = args.borgRepo
else:
    appArgs['borgRepo'] = '/backup_storage/borgbackup/repos/{}'.format(args.appName)

if args.restoreType:
    appArgs['restoreType'] = args.restoreType
else:
    appArgs['restoreType'] = 'mysql'

if args.skipSystemMysql:
    appArgs['skipSystemMysql'] = True
else:
    appArgs['skipSystemMysql'] = False

if args.borgPrefix:
    appArgs['borgPrefix'] = args.borgPrefix
else:
    appArgs['borgPrefix'] = "{}-{}".format(args.appName, appArgs['restoreType'])
    # in case of mysql restore prefix for myslq system db needed
    if appArgs['restoreType'] == 'mysql':
        appArgs['borgPrefixSystemMysql'] = "{}-system-{}".format(args.appName, appArgs['restoreType'])

if args.logLevel:
    appArgs['logLevel'] = logging.DEBUG

if args.configFile:
    appArgs['configFile'] = args.configFile
else:
    if os.path.isfile('{}/config.yml'.format(dir_name)):
        appArgs['configFile'] = '{}/config.yml'.format(dir_name)

if args.daemon:
    appArgs['daemon'] = args.daemon

if args.appName:
    appArgs['appName'] = args.appName

if args.logFile:
    appArgs['logFile'] = args.logFile
else:
    appArgs['logFile'] = '{}/{}/{}_{}.log'.format(dir_name, log_dir, args.appName, appArgs['restoreType'])

if args.pidFile:
    appArgs['pidFile'] = args.pidFile
else:
    appArgs['pidFile'] = '{}/{}/{}_{}.pid'.format(dir_name, log_dir, args.appName, appArgs['restoreType'])

if args.borgCheck:
    appArgs['borgCheck'] = False
else:
    appArgs['borgCheck'] = True



if __name__ == '__main__':


    os.environ['BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK'] = 'yes'
    os.environ['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'

    mainApp = TestRestoreApp()
    appArgs['target'] = mainApp.main
    AppContainer = Daemon(**appArgs)
    mainApp.set_app_container(AppContainer)
    sys.exit(AppContainer.run())
