#!/bin/env python3

from daemon import Daemon
from zbackupapp import ZBackupApp
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

argcomplete.autocomplete(parser)
args = parser.parse_args()
appArgs = {}
dir_name = os.path.dirname(os.path.realpath(sys.argv[0]))

if args.logLevel:
    appArgs['logLevel'] = logging.DEBUG

if args.configFile:
    appArgs['configFile'] = args.configFile
else:
    appArgs['configFile'] = '{}/config.yml'.format(dir_name)

if args.daemon:
    appArgs['daemon'] = args.daemon

if args.logFile:
    appArgs['logFile'] = args.logFile

if args.pidFile:
    appArgs['pidFile'] = args.pidFile


if __name__ == '__main__':

    mainApp = ZBackupApp()
    appArgs['target'] = mainApp.main
    AppContainer = Daemon(**appArgs)
    mainApp.set_app_container(AppContainer)
    AppContainer.run()
