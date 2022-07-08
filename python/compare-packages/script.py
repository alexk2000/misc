import argparse
import subprocess
import prettytable

parser = argparse.ArgumentParser()
parser.add_argument("server1", help="Name or ip of sevrer1")
parser.add_argument("server2", help="Name or ip of server2")
parser.add_argument("username", help="Username for accessing the servers")
parser.add_argument("sshkey", help="Path to ssh key for accessing the servers")
args = parser.parse_args()

# test command modified, it prints exit code to stdout, 0 - Debian, 1 - Redhat
CMD_TEST = 'test -e /etc/lsb-release; echo $?'
CMD_REDHAT = "rpm -qa --qf \"%{NAME} %{VERSION}\n\""
CMD_DEB = 'dpkg -l | grep "^ii" | awk "{print \$2, \$3}"'

pkgsonly1 = []
pkgsonly2 = []
pkgsdiff = {}

# just generic function to run external command
def run_command(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=None):
    proc = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr, env=env)
    outs, errs = proc.communicate()
    ret = proc.returncode
    return {'ret': ret, 'stdout': outs, 'stderr': errs}


def package_list(server, key=args.sshkey, username=args.username):
    cmd_ssh = 'ssh -i {} {}@{}'.format(key, username, server)
    cmd_test = '{} \'{}\''.format(cmd_ssh, CMD_TEST)
    result = run_command(cmd=cmd_test)
    # result['ret'] == 1 means ssh command failed
    if result['ret'] == 0:
        # ssh is ok, verifying result['stdout'], 0 - Debian, 1 - Redhat
        if int(result['stdout']) == 0:
            cmd_ = CMD_DEB
        else:
            cmd_ = CMD_REDHAT
    else:
        print('{} error: {} ({})'.format(server, result['stderr'], cmd_test))
        # exit because this is fatal error
        return None

    cmd_packages = '{} \'{}\''.format(cmd_ssh, cmd_)
    result = run_command(cmd=cmd_packages)
    # result['ret'] == 1 means ssh command failed
    if result['ret'] == 0:
        process = result['stdout'].decode('utf-8').rstrip().split("\n")
        serverdict = dict([line.split() for line in process])
        return serverdict
    else:
        print('{} error: {} ({})'.format(server, result['stderr'], cmd_packages))
        # exit because this is fatal error
        return None

server1dict = package_list(server=args.server1)
# exit if not getting package list for server1
if server1dict is None:
    exit(1)

# exit if not getting package list for server2
server2dict = package_list(server=args.server2)
if server2dict is None:
    exit(1)

# no changes below
for key in server1dict:
    if key not in server2dict:
        pkgsonly1.append(key)
    else:
        if server1dict[key] != server2dict[key]:
            pkgsdiff[key] = [server1dict[key], server2dict[key]]

for key in server2dict:
    if key not in server1dict:
        pkgsonly2.append(key)
        
table = prettytable.PrettyTable(['Package name', args.server1, args.server2])

for item in pkgsdiff:
    table.add_row([item, pkgsdiff[item][0], pkgsdiff[item][1]])

print("\n" + "=" * 100 + "\n")
print("Packages only on {0}:\n\n{1}".format(args.server1, ", ".join(pkgsonly1)))
print("\n" + "=" * 100 + "\n")
print("Packages only on {0}:\n\n{1}".format(args.server2, ", ".join(pkgsonly2)))
print("\n" + "=" * 100 + "\n")
print("Different package versions")
print(table)

exit(0)