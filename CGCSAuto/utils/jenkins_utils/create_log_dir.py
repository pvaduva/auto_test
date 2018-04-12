import os
from time import strftime
from optparse import OptionParser
import setups


def create_log_dir(lab, logs_dir=None):
    # compute directory for all logs based on resultlog arg, lab, and timestamp on local machine
    logs_dir = logs_dir if logs_dir else os.path.expanduser("~")
    if '/AUTOMATION_LOGS' in logs_dir:
        logs_dir = logs_dir.split(sep='/AUTOMATION_LOGS')[0]
    if not logs_dir.endswith('/'):
        logs_dir += '/'

    lab = lab.lower().replace('-', '_')
    labname = setups.get_lab_dict(lab).get('short_name').replace('-', '_').lower().strip()
    session_dir = logs_dir + "AUTOMATION_LOGS/" + labname + '/' + strftime('%Y%m%d%H%M')
    os.makedirs(session_dir, exist_ok=True)

    return session_dir

def create_functest_log_dir(logs_dir=None):

    logs_dir = logs_dir if logs_dir else os.path.expanduser("~")
    if '/AUTOMATION_LOGS' in logs_dir:
        logs_dir = logs_dir.split(sep='/AUTOMATION_LOGS')[0]
    if not logs_dir.endswith('/'):
        logs_dir += '/'

    session_dir = logs_dir + "AUTOMATION_LOGS/" + 'functest/' + strftime('%Y%m%d%H%M')
    os.makedirs(session_dir, exist_ok=True)

    return session_dir

def create_refstack_log_dir(logs_dir=None):

    logs_dir = logs_dir if logs_dir else os.path.expanduser("~")
    if '/AUTOMATION_LOGS' in logs_dir:
        logs_dir = logs_dir.split(sep='/AUTOMATION_LOGS')[0]
    if not logs_dir.endswith('/'):
        logs_dir += '/'

    session_dir = logs_dir + "AUTOMATION_LOGS/" + 'refstack/' + strftime('%Y%m%d%H%M')
    os.makedirs(session_dir, exist_ok=True)

    return session_dir


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-d', '--dir', action='store', type='string', dest='logs_dir',
                      help='home directory for automation logs. e.g., /sandbox')

    options, args = parser.parse_args()
    auto_home = options.logs_dir

    log_dir = create_log_dir(lab=args[0], logs_dir=auto_home)
    print(log_dir)
