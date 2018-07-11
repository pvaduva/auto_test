import os
from time import strftime
from optparse import OptionParser
import setups


def create_log_dir(lab, logs_dir=None, sub_dir=None):
    # compute directory for all logs based on resultlog arg, lab, and timestamp on local machine
    logs_dir = logs_dir if logs_dir else os.path.expanduser("~")
    automation_logs = 'AUTOMATION_LOGS'
    if automation_logs in logs_dir:
        logs_dir = logs_dir.split(sep='/{}'.format(automation_logs))[0]
    if sub_dir:
        automation_logs = os.path.join(automation_logs, sub_dir.lower())

    lab = lab.lower().replace('-', '_')
    labname = setups.get_lab_dict(lab).get('short_name').replace('-', '_').lower().strip()
    session_dir = os.path.join(logs_dir, automation_logs, labname, strftime('%Y%m%d%H%M'))
    os.makedirs(session_dir, exist_ok=True)

    return session_dir


def create_test_log_dir(testname, logs_dir=None):

    logs_dir = logs_dir if logs_dir else os.path.expanduser("~")
    if '/AUTOMATION_LOGS' in logs_dir:
        logs_dir = logs_dir.split(sep='/AUTOMATION_LOGS')[0]
    if not logs_dir.endswith('/'):
        logs_dir += '/'

    session_dir = logs_dir + "AUTOMATION_LOGS/" + testname + '/' + strftime('%Y%m%d%H%M')
    os.makedirs(session_dir, exist_ok=True)

    return session_dir


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-d', '--dir', action='store', type='string', dest='logs_dir',
                      help='home directory for automation logs. e.g., /sandbox')
    parser.add_option('--subdir', '--sub-dir', '--sub_dir', action='store', type='string', dest='sub_dir',
                      help='Sub-folder under AUTOMATION_LOGS dir, such as refstack')

    options, args = parser.parse_args()
    auto_home = options.logs_dir
    sub_dir = options.sub_dir

    log_dir = create_log_dir(lab=args[0], logs_dir=auto_home, sub_dir=sub_dir)
    print(log_dir)
