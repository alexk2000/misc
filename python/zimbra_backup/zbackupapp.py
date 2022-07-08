#!/bin/env python3


import shlex
import subprocess
import sys
import time
import os
import glob
import logging
from multiprocessing import Process
from multiprocessing import JoinableQueue as Queue

class ZBackupApp():

    def __init__(self):

        self.start = time.time()
        self.start_message = "zimbra backup started"
        self.backup_status_list = {
            'success': 'zimbra backup completed successfully',
            'failed': 'zimbra backup failed',
            'success_error': 'zimbra backup completed successfully with errors'

        }
        # backup is failed by default
        self.backup_status = 'failed'

        self.backup_steps_status = {'mount': False,
                                    'processes': False,
                                    'mailbox_error': False,
                                    'umount': False}

        # related to mailbox backup
        self.mb_worker_number = 1
        self.mb_workers = []
        # input queue with mailboxes to be backed up
        self.mbq_in = Queue()
        # output queue with status for backup each mailbox
        self.mbq_out = Queue()
	    # input queue for borgbackup 
        self.borgq_in = Queue()
        # output queue for borgbackup
        self.borgq_out = Queue()	
        # list of worker processes ldap, mysql, files, mailbox
        self.proc = []
        #self.status_list = {}

    # log final status of backup
    def log_backup_status(self):

        self.end = time.time()

        logger = logging.info
        self.backup_status = 'success'
        if not self.backup_steps_status['mount'] or not self.backup_steps_status['processes']:
            logger = logging.critical
            self.backup_status = 'failed'

        else:
            if not self.backup_steps_status['mailbox_error'] or not self.backup_steps_status['umount']:
                logger = logging.error
                self.backup_status = 'success_error'

        logger('{} ({}s)'.format(self.backup_status_list[self.backup_status], int(self.end-self.start)))

    def set_app_container(self, app_container):
        self.app_container = app_container
        self.log_file_handler = open(self.app_container.get_config_item('logFile'), "at")
        self.lock_file_name = self.app_container.get_config_item('lock_file')

    # run command and return exit code of the command
    def run_command(self, cmd_str, stdout=None, stderr=None, env=None):

        if stdout is None:
            stdout = self.log_file_handler
        if stderr is None:
            stderr=self.log_file_handler
 
        logging.info(cmd_str)
        cmd_list = shlex.split(cmd_str)
        with subprocess.Popen(cmd_list, stdout=stdout, stderr=stderr, env=env) as proc:
            try:
                outs, errs = proc.communicate()
                ret = proc.returncode
            except subprocess.TimeoutExpired as e:
                pass
            return ret

    def mount(self):

        nfs_list = self.app_container.get_config_item('nfs_list')
        
        for nfs in nfs_list: 
            cmd_str = "/usr/bin/sudo /bin/mount -o vers=3 {} {}".format(nfs['url'], nfs['mp'])
            ret = self.run_command(cmd_str)

            if not ret:
                logging.info("nfs mounted successfully {}".format(nfs['mp']))
            else:
                logging.critical("failed to mount nfs {}".format(nfs['mp']))
                return False

        fsname = ':'.join(list(item['mp'] for item in nfs_list))
        merge_mp = self.app_container.get_config_item('merge_mp')
        cmd_str = "/usr/bin/sudo /bin/mergerfs -o minfreespace=500G,defaults,uid=996,allow_other,use_ino,direct_io,fsname='{}' {} {}".format(fsname, fsname, merge_mp) 
        ret = self.run_command(cmd_str)
        if not ret:
            logging.info("mergefs mounted successfully {}".format(merge_mp))
        else:
            logging.critical("failed to mount mergefs {}".format(merge_mp))
            return False


        self.backup_steps_status['mount'] = True
        return True

    # if dirs exist and have write permission
    def check_access(self):
        
        def check_dir(self, dir):

            path = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'), 
                                                self.app_container.get_config_item('backup_dir'), dir)
            if not os.access(path,os.W_OK): 
                logging.critical('No access to {}'.format(path))
                return False
            else:
                return True
        
        for dir in [self.app_container.get_config_item('mailbox_save_to'), self.app_container.get_config_item('files_save_to'), 
                    self.app_container.get_config_item('mysql_save_to'), self.app_container.get_config_item('ldap_save_to')]:
            if not check_dir(self,dir):
                return False
        
        return True

    def umount(self):

        merge_mp = self.app_container.get_config_item('merge_mp')
        cmd_str = "/usr/bin/sudo /bin/umount {}".format(merge_mp)
        ret = self.run_command(cmd_str)

        if not ret:
            logging.info("mergefs unmounted successfully {}".format(merge_mp))
        else:
            logging.error("failed to unmount mergefs {}".format(merge_mp))
            return False

        nfs_list = self.app_container.get_config_item('nfs_list')

        for nfs in nfs_list:
            cmd_str = "/usr/bin/sudo /bin/umount {}".format(nfs['mp'])
            ret = self.run_command(cmd_str)

            if not ret:
                logging.info("nfs unmounted successfully {}".format(nfs['mp']))
            else:
                logging.critical("failed to unmount nfs {}".format(nfs['mp']))
                return False

        self.backup_steps_status['umount'] = True
        return True

    # run as separate process to backup mailboxes, 4 workers, 4 processes to speedup backup, number - worker id, q_in - queue with list of mailnboxes, 
    # q_out - backup result per each mailbox
    def worker_mailbox(self, number, q_in, q_out, borg_out):

        worker_info = 'id {} pid {}'.format(number, os.getpid())
        logging.info('Mailbox worker started {}'.format(worker_info))

        while True:
            mailbox = q_in.get()

            if mailbox is None:
                break

            cmd_str = "/opt/zimbra/bin/zmmailbox -z -t 0 -m {} getRestURL -u 'https://127.0.0.1' '//?fmt=tar'".format(mailbox)
            cmd_list = shlex.split(cmd_str)
            mailbox_path = '{}/{}/{}/{}.tar'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('mailbox_save_to'), mailbox)
            with open(mailbox_path, "wb") as mailbox_file:
                with subprocess.Popen(cmd_list, stdout=mailbox_file, stderr=self.log_file_handler) as proc:
                    try:
                        outs, errs = proc.communicate()
                        ret = proc.returncode
                    except subprocess.TimeoutExpired as e:
                        pass

            if ret != 0:
                logging.error('worker {} mailbox {} return code {}'.format(worker_info, mailbox, ret))
            else:
                # send to borgbackup
                logging.info('worker {} mailbox {} return code {}'.format(worker_info, mailbox, ret))
                borg_out.put(mailbox)

            q_out.put({'mailbox': mailbox, 'ret': ret})
            q_in.task_done()
        # put None if worker finisged its wirk and exits, used in worker_mailbox_status
        q_out.put(None)
        borg_out.put(None)
        logging.info('Mailbox worker stopped {}'.format(worker_info))
        sys.exit(0)

    # extra process to collect though queue q_in backup status for each mailbox from workers worker_mailbox
    def worker_mailbox_status(self, mb_worker_number, q_in):

        count = 0
        status_list = []
        # waiting until all worker_mailbox exit
        while True:
            status = q_in.get()
            if status is None:
                count += 1
                if count >= mb_worker_number:
                    break
            else:
                status_list.append(status)
        # count completed and failed mailboxes backup
        result = {'completed': 0, 'failed': 0}
        for item in status_list:
            if item['ret'] == 0:
                result['completed'] += 1
            else:
                result['failed'] += 1

        exit_code = 0
        logger = logging.info
        if result['failed'] > 0:
            exit_code = 1
            logger = logging.error

        logger('mailbox backup completed: successful={} failed={}'.format(result['completed'], result['failed']))
        sys.exit(exit_code)

    # run as separate process to backup mysql
    def worker_mysql(self):

        pid =  os.getpid()
        exit_code = 0
        mysql_path = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('mysql_save_to'))
       
        logging.info('MySQL backup started (worker pid {})'.format(pid))
        cmd_str = "source ~/bin/zmshutil && zmsetvars && mysqldump -S ${mysql_socket} -u ${zimbra_mysql_user} --password=${zimbra_mysql_password} --all-databases --single-transaction --routines --hex-blob > " + "{}/zimbra.sql".format(mysql_path)
        with subprocess.Popen(cmd_str, shell=True) as proc:
            try:
                outs, errs = proc.communicate()
                ret = proc.returncode
            except subprocess.TimeoutExpired as e:
                pass

        if ret != 0:
            exit_code = 1

        logger = logging.info
        message = "MySQL backup completed successfully"

        if exit_code == 1:
            logger = logging.critical
            message = "MySQL backup failed"
        else:

            borg_mysql_repo = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('borg_mysql_save_to'))
            mysql_dir = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('mysql_save_to'))
            backup_date = "{now:%Y-%m-%dT%H:%M:%S}"
            cmd_str = "/usr/bin/borg create --lock-wait {} -C zlib {}::mysql-{} {}".format(self.app_container.get_config_item('lock_wait'), borg_mysql_repo, backup_date, mysql_dir)
            ret = self.run_command(cmd_str)
            if ret != 0:
                logging.error('borg mysql failed')
                logger = logging.critical
                message = "MySQL backup failed"
                exit_code = 1
            else:
                keep = self.app_container.get_config_item('borg_mysql_retention')
                cmd_str = "/usr/bin/borg prune --lock-wait {} -v --list --keep-daily={} --keep-weekly={} --keep-monthly={} --keep-yearly={} --prefix mysql {}".format(self.app_container.get_config_item('lock_wait'), keep['daily'], keep['weekly'], keep['monthly'], keep['yearly'], borg_mysql_repo)
                ret = self.run_command(cmd_str)
                if ret != 0:
                    logging.error('borgbackup mysql prune failed (pid {}) return code {}'.format(pid, ret))
                # remove mysql dump after saving into borg repo
                for f in glob.glob("{}/*".format(mysql_dir)):
                    os.remove(f)
        
        logger('{} (worker pid {})'.format(message, pid))
        sys.exit(exit_code)

    # run as separate process to backup ldap
    def worker_ldap(self):

        pid =  os.getpid()
        exit_code = 0
        #ldap_path = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
        #                                        self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('ldap_save_to'))
        ldap_path = "/mnt/nfs1/zimbra_backup/ldap" 
        logging.info('LDAP backup started (worker pid {})'.format(pid))

        cmd_template = '/opt/zimbra/libexec/zmslapcat {} {}'
        # zmslapcat runs 3 times: '', '-c', '-a' 
        cmd_list = list(map(cmd_template.format, ['', '-c', '-a'], [ldap_path]*3))
        result_list = list(map(self.run_command, cmd_list))

        # if all 3 invokes of zmslapcat returns 0 then ldap backup successful
        if sum(result_list) != 0:
            exit_code = 1

        logger = logging.info
        message = "LDAP backup completed successfully"

        if exit_code == 1:
            logging.error('zmslapcat failed')
            logger = logging.critical
            message = "LDAP backup failed"
        else:
            #borg_ldap_repo = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
            #                                    self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('borg_ldap_save_to'))
            borg_ldap_repo = "/mnt/nfs1/zimbra_backup/ldap_borg"
            #ldap_dir = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
            #                                    self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('ldap_save_to'))            
            ldap_dir = ldap_path 
            backup_date = "{now:%Y-%m-%dT%H:%M:%S}"
            cmd_str = "/usr/bin/borg create --lock-wait {} -C zlib -e '*.bak.[0-9]*' {}::ldap-{} {}".format(self.app_container.get_config_item('lock_wait'), borg_ldap_repo, backup_date, ldap_dir)
            ret = self.run_command(cmd_str)
            if ret != 0:
                logging.error('borg ldap failed')
                logger = logging.critical
                message = "LDAP backup failed"
                exit_code = 1
            else:
                keep = self.app_container.get_config_item('borg_ldap_retention')
                cmd_str = "/usr/bin/borg prune --lock-wait {} -v --list --keep-daily={} --keep-weekly={} --keep-monthly={} --keep-yearly={} --prefix ldap {}".format(self.app_container.get_config_item('lock_wait'), keep['daily'], keep['weekly'], keep['monthly'], keep['yearly'], borg_ldap_repo)
                ret = self.run_command(cmd_str)
                if ret != 0:
                    logging.error('borgbackup ldap prune failed (pid {}) return code {}'.format(pid, ret))
                # remove ldap files after saving them in borg repo
                for f in glob.glob("{}/*".format(ldap_dir)):
                    os.remove(f)
    

        logger('{} (worker pid {})'.format(message, pid))
        sys.exit(exit_code)


    # run as separate process to dirs/files backup
    def worker_files(self):

        pid =  os.getpid()
        exit_code = 0
        files_path = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('files_save_to'))
        logging.info('Files backup started ({})'.format(pid))
        cmd_str = '/bin/sudo /bin/tar chf {}/files.tar {}'.format(files_path, ' '.join(self.app_container.get_config_item('files_to_backup')))
        ret = self.run_command(cmd_str)
        # tar exit codes
        # 0 `Successful termination'. 
        # 1 `Some files differ'.  If tar was given `--create', `--append' or `--update' option, this exit code means that some files were changed while being arch        # ived and so the resulting archive does not contain the exact copy of the file set 
        # 2 `Fatal error'. This means that some fatal, unrecoverable error occurred. 
        if ret == 2:
           exit_code = 1
        
        logger = logging.info
        message = "Files backup completed successfully" 

        if exit_code == 1:
            logger = logging.critical
            message = "Files backup failed"
        else:
            borg_files_repo = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('borg_files_save_to'))
            files_dir = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('files_save_to'))
            backup_date = "{now:%Y-%m-%dT%H:%M:%S}"
            cmd_str = "/usr/bin/borg create --lock-wait {} -C zlib {}::files-{} {}".format(self.app_container.get_config_item('lock_wait'), borg_files_repo, backup_date, files_dir)
            ret = self.run_command(cmd_str)
            if ret != 0:
                logging.error('borg files failed')
                logger = logging.critical
                message = "Files backup failed"
                exit_code = 1
            else:
                keep = self.app_container.get_config_item('borg_files_retention')
                cmd_str = "/usr/bin/borg prune --lock-wait {} -v --list --keep-daily={} --keep-weekly={} --keep-monthly={} --keep-yearly={} --prefix files {}".format(self.app_container.get_config_item('lock_wait'), keep['daily'], keep['weekly'], keep['monthly'], keep['yearly'], borg_files_repo)

                ret = self.run_command(cmd_str)
                if ret != 0:
                    logging.error('borgbackup files prune failed (pid {}) return code {}'.format(pid, ret))
                # remove tarball with files after saving them into borg repo
                for f in glob.glob("{}/*".format(files_dir)):
                    os.remove(f)


        logger('{} (worker pid {}, tar exit code {})'.format(message, pid, ret))
        sys.exit(exit_code)

    def worker_borgbackup(self, mb_worker_number, q_in, q_out):

#        os.environ['BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK'] = 'yes'
#        os.environ['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'
        pid =  os.getpid()
        exit_code = 0
        #logging.info('Borgbackup backup started ({})'.format(pid))
        borg_mailbox_repo = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('borg_mailbox_save_to'))
        mailbox_dir = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                                self.app_container.get_config_item('backup_dir'), self.app_container.get_config_item('mailbox_save_to'))  
        count = 0
        status_list = []
        while True:
            mailbox = q_in.get()
            if mailbox is None:
                count += 1
                if count >= mb_worker_number:
                    break
            else:
                # do backup by borg
                backup_date = "{now:%Y-%m-%dT%H:%M:%S}"
                mailbox_file = "{}/{}.tar".format(mailbox_dir, mailbox)
                cmd_str = "/usr/bin/borg create --lock-wait {} -C zlib {}::{}-{} {}".format(self.app_container.get_config_item('lock_wait'), borg_mailbox_repo, mailbox, backup_date, mailbox_file)
                #logging.info(cmd_str)
                #cmd_str = "echo $BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"
                #cmd_str = "env"
                #ret = self.run_command(cmd_str, env={'BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK': 'yes'})
                ret = self.run_command(cmd_str)
                if ret != 0:
                    logging.error('borgbackup (pid {}) mailbox {} return code {}'.format(pid, mailbox, ret))
                else:
                    logging.info('borgbackup (pid {}) mailbox {} return code {}'.format(pid, mailbox, ret))
                    # purge old backups
                    keep = self.app_container.get_config_item('borg_mailbox_retention')
                    cmd_str = "/usr/bin/borg prune --lock-wait {} -v --list --keep-daily={} --keep-weekly={} --keep-monthly={} --keep-yearly={} --prefix {} {}".format(self.app_container.get_config_item('lock_wait'), keep['daily'], keep['weekly'], keep['monthly'], keep['yearly'], mailbox, borg_mailbox_repo)
                ret = self.run_command(cmd_str)
                if ret != 0:
                    logging.error('borgbackup prune {} failed (pid {}) return code {}'.format(mailbox, pid, ret))
                os.remove(mailbox_file) 

        #logging.info('Borgbackup backup exited ({})'.format(pid))
        sys.exit(exit_code)
    # doing some preperations and run 4(self.mb_worker_number) worker processes of worker_mailbox
    def run_mailbox_workers(self):

        # put list of mailboxes to input queue q_in for worker_mailbox
        cmd_str = "/opt/zimbra/bin/zmprov -l gaa"
        #cmd_str = "cat testlist.txt"
        cmd_list = shlex.split(cmd_str)
        zmprov = subprocess.Popen(cmd_list, universal_newlines=True, stdout=subprocess.PIPE)
        for mailbox in iter(zmprov.stdout.readline, ''):
            self.mbq_in.put(mailbox.rsplit()[0])

        # send signal to process to exit after processing all mailboxes 
        for i in range(self.mb_worker_number):
            self.mbq_in.put(None)
        # create and run worker_mailbox processes
        for number in range(self.mb_worker_number):
            self.proc.append(Process(target=self.worker_mailbox, daemon=True, name='mailbox{}'.format(number),
                                     args=(number, self.mbq_in, self.mbq_out, self.borgq_in)))
            self.proc[number].start()

        # run process to get status from all mailbox workers
        proc = Process(target=self.worker_mailbox_status, daemon=True, name='worker_mailbox_status',
                       args=(self.mb_worker_number, self.mbq_out))
        self.proc.append(proc)
        proc.start()

		# run borgbackup process
        proc = Process(target=self.worker_borgbackup, daemon=True, name='borgbackup', args=(self.mb_worker_number, self.borgq_in, self.borgq_out))
        self.proc.append(proc)
        proc.start()

    # runs ldap, files, mysql workers
    def run_worker(self, worker):

        proc = Process(target=worker['target'], daemon=True, name=worker['name'])
        self.proc.append(proc)
        proc.start()

    # runs all workers
    def run_background_tasks(self):

        os.environ['BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK'] = 'yes'
        os.environ['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'
        self.run_mailbox_workers()

#        self.run_worker({'target': self.worker_mysql, 'name': 'mysql'})
#        self.run_worker({'target': self.worker_ldap, 'name': 'ldap'})
#        self.run_worker({'target': self.worker_files, 'name': 'files'})
        
        workers = [{'target': self.worker_mysql, 'name': 'mysql'},
                   {'target': self.worker_ldap, 'name': 'ldap'},
                   {'target': self.worker_files, 'name': 'files'}
                   ]
        list(map(self.run_worker, workers))

#        for worker in workers:
#            self.run_worker(worker)

    # waiting for all processes completed, based on exit code set status in self.backup_steps_status
    def wait_for_result(self):

        sum_exit_code = 0
        for task in self.proc:
            task.join()
            if task.name == 'worker_mailbox_status':
                if task.exitcode == 0:
                    self.backup_steps_status['mailbox_error'] = True
            else:
                sum_exit_code += task.exitcode

        if sum_exit_code == 0:
            self.backup_steps_status['processes'] = True

    # create/remove lock file, used by external scripts to verify if backup still in progress
    def lock(self, unlock=False):

        lock_file_path = '{}/{}/{}'.format(self.app_container.get_config_item('merge_mp'),
                                            self.app_container.get_config_item('backup_dir'), self.lock_file_name)

        if not unlock:
            if os.path.exists(lock_file_path):
                logging.error('lock file {} exists'.format(lock_file_path))
            try:
                with open(lock_file_path, 'w') as file_handler:
                    file_handler.write(str(os.getpid()))
            except Exception as e:
                logging.error('write lock file {} {}'.format(lock_file_path, e))
                return 1
        else:
            try:
                os.remove(lock_file_path)
            except Exception as e:
                logging.error('remove lock file {} {}'.format(lock_file_path, e))
                return 1

        return 0


    def main(self):

        logging.info("-----------------------------")
        logging.info(self.start_message)

#        print(self.app_container.get_config_item('borg_mailbox_retention'))
#        return True
#        if True:
        if self.mount():
            if self.check_access():
                self.lock()
                self.run_background_tasks()
                self.wait_for_result()
                self.lock(unlock=True)
            self.umount()

        self.log_backup_status()
