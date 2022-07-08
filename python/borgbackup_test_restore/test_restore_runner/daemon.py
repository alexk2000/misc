import logging
import time
import os
import sys
import socket
import psutil
import signal
import yaml



class Daemon(object):

    def __init__(self, **kwargs):

        # set configuration defaults
        self.__config = {'daemon': False, 'target': None, 'configFile': None, 'appName': 'myapp', 'pidFile': None,
                         'logFile': '/tmp/myapp.log', 'logLevel': 10}

        # import configuration from yaml config file
        if 'configFile' in kwargs:
            self.config_load_yaml(kwargs['configFile'])

        self.__config.update(kwargs)

        if self.__config['pidFile'] is None:
            self.__config['pidFile'] = '/tmp/{appName}.pid'.format(appName=self.__config['appName'])

        if os.path.exists(self.__config['pidFile']):
            print("Error: pid file {pidFile} exists, exiting".format(pidFile=self.__config['pidFile']))
            sys.exit(1)

        getLock, pid = self.__get_start_lock()
        if not getLock:
            print('Error: already running, pid is {pid}'.format(pid=pid))
            sys.exit(1)

        # verify if we able to open files
        for file in [self.__config['logFile'], self.__config['pidFile']]:
            self.__verify_file(file)

        #print('log file is {logFile}, pid file is {pidFile}'.format(logFile=self.__config['logFile'],
        #                                                            pidFile=self.__config['pidFile']))
        # becoming daemon
        if self.__config['daemon']:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)

        self.__config['pid'] = os.getpid()

        # saving pid
        with open(self.__config['pidFile'], "w") as fd:
            fd.write(str(self.__config['pid']))

        # logging
        self.__config['logFormat'] = '%(asctime)s {appName}({pid}) %(levelname)s: %(message)s'.format(
            appName=self.__config['appName'], pid=self.__config['pid'])
#        logging.basicConfig(filename=self.__config['logFile'], level=self.__config['logLevel'],
#                            format=self.__config['logFormat'])

        logging.basicConfig(level=self.__config['logLevel'],
                            format=self.__config['logFormat'],
                            handlers=[
        logging.FileHandler(self.__config['logFile']),
        logging.StreamHandler()
    ]
)
        # handle signals
        for sgn in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
            signal.signal(sgn, self.__signal_handler)

        # [signal.signal(sgn, self.__signal_handler) for sgn in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]]
        # list(map(signal.signal, [signal.SIGHUP, signal.SIGTERM, signal.SIGINT], [self.__signal_handler]*3))

    def get_config_item(self, option=None):
        
        if option is not None:
            return self.__config[option]
        else:
            return self.__config

    def config_load_yaml(self, configFile):

        try:
            with open(configFile, 'r') as ymlfile:
                cfg = yaml.load(ymlfile)
        except Exception as e:
            print("Wrong configuration file:\n", e)
            sys.exit(1)

        self.__config.update(cfg)

        # try:
        #     with open(self.__config['configFile'], 'r') as ymlfile:
        #         cfg = yaml.load(ymlfile)
        # except Exception as e:
        #     print("Wrong configuration file:\n", e)
        #     sys.exit(1)

    def __get_start_lock(self):
        # get all unix sockets and verify if already opened
        for sock in psutil.net_connections(kind="unix"):
            if sock.laddr == '@{appName}_{restoreType}'.format(appName=self.__config['appName'], restoreType=self.__config['restoreType']):
                return False, sock.pid

        # socket not found so application is not running, getting lock
        self.__applock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.__applock.bind('\0{appName}_{restoreType}'.format(appName=self.__config['appName'], restoreType=self.__config['restoreType']))

        return True, 0

    def __verify_file(self, file):

        try:
            f = open(file, 'a')
            f.close()
        except Exception as e:
            print(e)
            sys.exit(1)

    def run(self):

        # for i in range(0, 20):
        # while True:
        #     logging.info('log message')
        #     time.sleep(1)

        if self.__config['target'] is not None:
            ret = self.__config['target']()

        self.shutdown()
        return ret

    def __signal_handler(self, signum, frame):
        logging.info('got {} signal'.format(signal.Signals(signum).name))
        if signum == 1:
            # reload
            pass
        elif signum in [2, 15]:
            # keyboardinterrupt or sigterm
            self.shutdown()

    def shutdown(self):
        # logging.info('shutdown')
        try:
            os.remove(self.__config['pidFile'])
        except Exception as e:
            logging.error("can't remove pid file {pidFile} {error}".format(pidFile=self.__config['pidFile'],
                                                                           error=e))
        #sys.exit(0)

if __name__ == "__main__":

    class myclass():

        def __init__(self):
            self.a=5
        def worker2(self):
            self.worker()

        def worker(self):
            # for i in range(0, 20):
            while True:
                logging.info('doing something ' + str(self.a))
                time.sleep(1)


    inst = myclass()

    myApp = Daemon(daemon=False, target=inst.worker2, appName="Kate",  logFile="/tmp/myapp.log", logLevel=logging.INFO)
    myApp.run()

