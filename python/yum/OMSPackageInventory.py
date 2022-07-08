import os
import sys
import datetime
import logging
import subprocess
import yum
from yum.update_md import UpdateMetadata

#packages updates information log, format below, available as UpdatesSystem_CL in OMS/Log Analytics
#time stamp;package name;current version;new version:security critical;security important;security moderate;security low;bugfix;enhancement;updates id
log_updates = '/var/opt/microsoft/omsagent/log/updates_system.log'
log_general = '/var/opt/microsoft/omsagent/log/updates_system_general.log'

log_format = '%(asctime)s %(levelname)s: %(message)s'

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

class YumUpdates:

    def __init__(self, log=False):
        self.yb = yum.YumBase()
        self.yb.doConfigSetup(errorlevel=0, debuglevel=0)
        self.stats = {'p_updates': 0, 'p_no_updates': 0, 'updates':0}
        self.md_info = self._get_md()
        self.updates = {}
        self.noupdates = {}
        self._get_updates()
        if log:
            logging.info('up to date packages: %s, packages with updates: %s, updates: %s' % (str(self.stats['p_no_updates']), str(self.stats['p_updates']), str(self.stats['updates'])))

    def _get_md(self):
        md_info = UpdateMetadata()
        for repo in self.yb.repos.listEnabled():
            if not repo.enabled:
                continue
            try: # attempt to grab the updateinfo.xml.gz from the repodata
                md_info.add(repo)
            except yum.Errors.RepoMDError:
                continue # No metadata found for this repo
            except OSError, (errno, strerror):
                logging.error('OSError(%s): %s' % (errno, strerror))
                continue
            except:
                logging.error('Unexpected error: %s' % sys.exc_info()[0])
                continue
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
                self.stats['p_updates'] += 1
                p_name = '%s.%s' % (item.name, item.arch)
                self.updates[p_name] = {'new': item}
                # try to find old version
                pkg_old = None
                try:
                    pkg_old = self.yb.rpmdb.searchNevra(name=item.name, arch=item.arch)[0]
                except IndexError:
                    pkg_old = self.yb.rpmdb.searchNevra(name=item.name)[0]
                self.updates[p_name]['cur'] = pkg_old


        # get installed
        pi = self.yb.doPackageLists(pkgnarrow='installed')
        installed = {}
        if pi.installed:
            for item in pi.installed:
                p_name = '%s.%s' % (item.name, item.arch)
                installed[p_name] = {'cur': item}
        
        self.noupdates = installed

        # remove from list of installed packages (self.noupdates) those which have updates (self.updates)
        for pkg, info in self.updates.items():
            # handle situation when arch of new package differs from old
            if pkg in self.noupdates:
                del self.noupdates[pkg]
            else:
                for arch in ['i386', 'i686', 'noarch', 'x86_64']:
                    pkg_arch = '%s.%s' % (info['new'].name, arch)
                    if pkg_arch in self.noupdates:
                        del self.noupdates[pkg_arch]
 
        self.stats['p_no_updates'] += len(self.noupdates)



    def _get_updates_updateinfo(self):
        for package, info in self.updates.items():
            p = info['cur']
            self.updates[package]['updateinfo'] = self._get_updateinfo(md_info=self.md_info, p=p)

    def export_simple(self):
        for package, info in self.updates.items():
            print package, info, '\n'

    def _export_csv_line(self, updateinfo):
        result = []
        trans = {'critical': 'securitycritical', 'important': 'securityimportant', 'moderate': 'securitymoderate', 'low': 'securitylow', 'bugfix': 'bugfix', 'enhancement': 'enhancement'}        
        for u_type in updateinfo.keys():
           for update_id in updateinfo[u_type]:
                result.append([trans[u_type], update_id]) 
        return result

    def export_csv(self, log_updates, stdout=False, s=';', noupdates=False):

        ts = datetime.datetime.now().strftime('%s')
        f = open(log_updates, 'a')

        # export info about up to date packages (no updates available)
        if noupdates:
            # 1519133484;httpd;currentVersion;newVersion;;0;
            # currentVersion = newVersion
            for package, info in self.noupdates.items():
                cur = '%s-%s' % (info['cur'].version, info['cur'].release)
                output = '%s%s%s%s%s%s%s%s%s%s%s%s%s\n' % (ts, s, package, s, cur, s, cur, s, '', s, 'uptodate', s, '') 
                f.write(output)
                if stdout:
                    print output

        # export info about packages for which updates are available
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
                output = '%s%s%s%s%s%s%s%s%s%s%s%s%s\n' % (ts, s, package, s, cur, s, new, s, item[0], s, 'needed', s, item[1])
                f.write(output)
                if stdout:
                    print output
        f.close()


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

    set_logging(log_file=log_general, log_format=log_format, log_to_stdout=True, level=logging.INFO)

    logging.info('started') 
    app = YumUpdates(log=True)
    app.export_csv(log_updates=log_updates, noupdates=True)
    logging.info('finished')
    os.chmod(log_general, 0644)
    os.chmod(log_updates, 0644)
    sys.exit(0)
