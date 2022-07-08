import os
import sys
import datetime
import logging
import subprocess
import yum
from yum.update_md import UpdateMetadata

# middleware list
middleware = ['httpd', 'java-1.6.0-openjdk', 'java-1.7.0-openjdk', 'java-1.8.0-openjdk']
archs = ['i386', 'i686', 'noarch', 'x86_64']
# form final middleware list based on archs
for p in middleware[:]:
    middleware.remove(p)
    for arch in archs:
        middleware.append('%s.%s' % (p, arch))

log_format = '%(asctime)s %(levelname)s: %(message)s'
log_general = '/var/opt/microsoft/omsagent/log/updates_system_general.log'

def set_logging(log_file, log_format, log_to_stdout=False, level=logging.DEBUG):
    logging.basicConfig(filename=log_file, level=logging.DEBUG, format=log_format)
    log = logging.getLogger('')
    log.setLevel(level)
    format = logging.Formatter(log_format)
    # log to stdout
    if log_to_stdout:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(format)
        log.addHandler(ch)
    return 0


def run_command(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=None):
    proc = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr, env=env)
    outs, errs = proc.communicate()
    ret = proc.returncode
    return {'ret': ret, 'stdout': outs, 'stderr': errs}

# argument parser
class ArgParse:
    def __init__(self):
        self.args = sys.argv[1:]
        self.arg_packages = []
        self.flags = False
        self.unknown_flag = []
        self.err = {'arg_err': 'Error parsing arguments'}
        self.arg_flags = {'--all': False, '--middleware': False, '--security': False, '--securitycritical': False, '--securityimportant': False, '--securitymoderate': False, '--securitylow': False, '--enhancement': False, '--bugfix': False}
        for arg in self.args:
            if arg in self.arg_flags:
                self.arg_flags[arg] = True
                self.flags = True
            elif arg[0] <> '-':
                self.arg_packages.append(arg)
            else:
                self.unknown_flag.append(arg)

    def print_help(self):
        print "Usage: %s [OPTIONS]... [PACKAGE]... " % sys.argv[0]
        print """
        --all           update all packages
        --security      update packages with security updates
        --securitycritical      update packages with security critical updates 
        --securityimportant     update packages with security important updates
        --securitymoderate      update packages with security moderate updates
        --securitylow           update packages with security low updates
        --bugfix        update packages with bugfixes
        --enhancement   update packages with enhancements 

        --middleware    include middleware (excluded by default)
        """

    def verify(self):
        if len(sys.argv) == 1:
            print '%s: no argument specified' % self.err['arg_err']
            return False

        if '--help' in self.args or '-h' in self.args:
            return False
 
        if len(self.arg_packages) > 0 and self.flags:
            print '%s: specified both packages and groups all/security/enhancement/bugfix' % self.err['arg_err']
            return False
        
        if len(self.unknown_flag) > 0:
            print 'unknown argument: %s' % ' '.join(self.unknown_flag) 
            return False

        if self.arg_flags['--all'] and (self.arg_flags['--security'] or self.arg_flags['--securitycritical'] or self.arg_flags['--securityimportant'] or self.arg_flags['--securitymoderate'] or self.arg_flags['--securitylow'] or self.arg_flags['--enhancement'] or self.arg_flags['--bugfix']):
            print '%s: --all can\'t be specified with update types' % self.err['arg_err']
            return False

        if self.arg_flags['--security'] and (self.arg_flags['--securitycritical'] or self.arg_flags['--securityimportant'] or self.arg_flags['--securitymoderate'] or self.arg_flags['--securitylow']):
            print '%s: --security can\'t be specified with --securitycritical/--securityimportant/--securitymoderate/--securitylow' % self.err['arg_err']
            return False                  

        return True

    def get_args(self):
        result = {}
        if self.flags:
            result['flags'] = []
            for flag, value in self.arg_flags.items():
                if value:
                    result['flags'].append(flag) 

        if len(self.arg_packages) > 0:
            result['packages'] = self.arg_packages
        
        return result

# from OMSPackageInventory.py, getting info about available updates
class YumUpdates:

    def __init__(self, log=False):
        self.yb = yum.YumBase()
        self.yb.doConfigSetup(errorlevel=0, debuglevel=0)
        self.stats = {'packages': 0, 'updates':0 }
        self.md_info = self._get_md()
        self.updates = {}
        self._get_updates()
        if log:
            logging.info('packages: %s, updates: %s' % (str(self.stats['packages']), str(self.stats['updates'])))

    def _get_md(self):
        md_info = UpdateMetadata()
        for repo in self.yb.repos.listEnabled():
            if not repo.enabled:
                continue
            try: # attempt to grab the updateinfo.xml.gz from the repodata
                md_info.add(repo)
            except yum.Errors.RepoMDError:
                continue # No metadata found for this repo
        return md_info

    def _get_updateinfo(self, md_info, p):
        result = {'moderate': [], 'critical': [], 'bugfix':[], 'important': [], 'enhancement': [], 'low': []}
        update_info = md_info.get_applicable_notices((p.name, p.arch, p.epoch, p.version, p.release))
        for item in update_info:
            self.stats['updates'] += 1
            info = item[1].get_metadata()
            if info['type'] == 'bugfix':
                result['bugfix'].append(info['update_id'])
            elif info['type'] == 'enhancement':
                result['enhancement'].append(info['update_id'])
            elif info['type'] == 'security':
                if info['severity'] == 'Critical':
                    result['critical'].append(info['update_id'])
                elif info['severity'] == 'Important':
                    result['important'].append(info['update_id'])
                elif info['severity'] == 'Moderate':
                    result['moderate'].append(info['update_id'])
                elif info['severity'] == 'Low':
                    result['low'].append(info['update_id'])
        return result

    def _get_updates(self):
        self._get_updates_packages()
        self._get_updates_updateinfo()

    def _get_updates_packages(self):
        # get updates
        pu = self.yb.doPackageLists(pkgnarrow='updates')
        if pu.updates:
            for item in pu.updates:
                self.stats['packages'] += 1
                self.updates[item.name] = {'new': item}

        # get installed
        pi = self.yb.doPackageLists(pkgnarrow='installed')
        installed = {}
        if pi.installed:
            for item in pi.installed:
                installed[item.name] = {'cur': item}

        # add current version to packages in updates
        for p in self.updates.keys():
            cur = installed.get(p)
            self.updates[p]['cur'] = cur['cur']

    def _get_updates_updateinfo(self):
        for package, info in self.updates.items():
            p = info['cur']
            self.updates[package]['updateinfo'] = self._get_updateinfo(md_info=self.md_info, p=p)

    def export_simple(self):
        for package, info in self.updates.items():
            print package, info, '\n'

    def _export_csv_line(self, updateinfo):
        result = []
        trans = {'critical': '--securitycritical', 'important': 'securityimportant', 'moderate': 'securitymoderate', 'low': 'securitylow', 'bugfix': 'bugfix', 'enhancement': 'enhancement'}        
        for u_type in updateinfo.keys():
           for update_id in updateinfo[u_type]:
                result.append([trans[u_type], update_id]) 
        return result

    def export_csv(self, log_updates, stdout=False, s=';'):
        ts = datetime.datetime.now().strftime('%s')
        f = open(log_updates, 'w')
        for package, info in self.updates.items():
            critical = len(info['updateinfo']['critical'])
            important = len(info['updateinfo']['important'])
            moderate = len(info['updateinfo']['moderate'])
            low = len(info['updateinfo']['low'])
            bugfix = len(info['updateinfo']['bugfix'])
            enhancement = len(info['updateinfo']['enhancement'])
            cur = '%s-%s' % (info['cur'].version, info['cur'].release)
            new = '%s-%s' % (info['new'].version, info['new'].release)
            uinfo = self._export_csv_line(updateinfo=info['updateinfo'])
            for item in uinfo:
                output = '%s%s%s%s%s%s%s%s%s%s%s%s%s\n' % (ts, s, package, s, cur, s, new, s, item[0], s, 1, s, item[1])
                f.write(output)
                if stdout:
                    print output
        f.close()

# install only those updates which specified in script arguments, inherits class YumUpdates to get info about availabe updates
class InstallUpdates(YumUpdates):
    def __init__(self, log=False, middleware=None, args=None):
        YumUpdates.__init__(self)

        self.p_list = None
        self.middleware = middleware        
        self.update_middleware = False
        self.args_orig = args

        self.args = {'flags': None, 'packages': None}
        if 'flags' in self.args_orig:
            self.args['flags'] = self.normalize_args(self.args_orig['flags'])
            if '--middleware' in self.args['flags']:
               self.update_middleware = True
               self.args['flags'].remove('--middleware')
            self.p2update()
        elif 'packages' in self.args_orig:
            self.p_list = self.args_orig['packages']
            # remove package from self.middleware (exclude list)
            for p in self.p_list:
                if p in self.middleware:
                    self.middleware.remove(p)

    def normalize_args(self, flags):
        flags_new = flags
        flags_all = ['--securitycritical', '--securityimportant', '--securitymoderate', '--securitylow', '--enhancement', '--bugfix']
        flags_security = ['--securitycritical', '--securityimportant', '--securitymoderate', '--securitylow']

        if '--all' in flags_new:
            flags_new.remove('--all')
            flags_new = flags_new + flags_all
        elif '--security' in flags_new:
            flags_new.remove('--security')
            flags_new = flags_new + flags_security

        return flags_new

    def p2update(self):
        # input data: packages in self.updates, update flags in self.args['flags']
        p_list = []
        p_types = {'--securitycritical': [], '--securityimportant': [], '--securitymoderate': [], '--securitylow': [], '--enhancement': [], '--bugfix': []}
        type_map = {'critical':'--securitycritical', 'important':'--securityimportant', 'moderate':'--securitymoderate', 'low':'--securitylow', 'enhancement':'--enhancement', 'bugfix':'--bugfix'}
#        for key in p_types.keys():
#            type_map[key[2:]] = key

        for package, info in self.updates.items():
            for k, v in type_map.items():
                if len(info['updateinfo'][k]) > 0:
                    p_types[v].append(package)

        for arg in self.args['flags']:
            p_list = p_list + p_types[arg]

        self.p_list = p_list

    def run_updates(self):

        if len(self.p_list) == 0:
            logging.info('no packages to update')
            return 1

        yb = yum.YumBase()
        yb.doConfigSetup(errorlevel=0, debuglevel=0)
        yb.doLoggingSetup(debuglevel=0, errorlevel=0)

        if not self.update_middleware and self.middleware is not None:
            yb.conf.exclude = self.middleware

        yb.conf.skip_broken = True
   
        logging.info('packages to update: %s' % ' '.join(self.p_list))
        logging.info('exclude list (middleware): %s' % ' '.join(yb.conf.exclude))
       
        # split package name and arch
        for package in self.p_list:
            ldot = package.split('.')
            if len(ldot) == 1:
                p_name = ldot[0]
                yb.update(name=p_name)
            else:
                if ldot[-1] in archs:
                    p_name = '.'.join(ldot[:-1])
                    p_arch = ldot[-1]
                    yb.update(name=p_name, arch=p_arch)
                else:
                    p_name = package
                    yb.update(name=p_name)

        # goto to the end of /var/log/yum.log
        yum_log = open(yb.conf.logfile, 'r')
        yum_log.seek(0,2)    
                     
        # disable any writes to stdout
        s_orig = sys.stdout
        sys.stdout = open('/dev/null', 'w')

        yb.excludePackages()
        yb.resolveDeps()
        yb.buildTransaction()
        yb.processTransaction()

        sys.stdout = s_orig

        # get and log info about changed packages during update
        for line in yum_log:
            logging.info(line.rstrip())

        return 0



if __name__ == '__main__':

    # run this script as root
    if os.getuid() <> 0:
        params = ''
        if len(sys.argv) > 1:
                params = ' '.join(sys.argv[1:])
        cmd = 'sudo python %s %s' % (sys.argv[0], params)
        result = run_command(cmd=cmd)
        print result['stdout'], result['stderr']
        sys.exit(result['ret'])

    # all code below running under root

    set_logging(log_file=log_general, log_format=log_format, log_to_stdout=True, level=logging.INFO)

    args = ArgParse()

    if not args.verify():
        args.print_help()
        sys.exit(1)

    args_parsed = args.get_args()

    logging.info('started yum update')
    logging.info('script arguments: %s' % ' '.join(sys.argv[1:]))
    updates = InstallUpdates(log=log_general, middleware=middleware, args=args_parsed)
    updates.run_updates() 
    logging.info('finished yum update')
