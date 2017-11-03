import re
from configparser import ConfigParser
from optparse import OptionParser

from consts.auth import HostLinuxCreds, Tenant
from consts.proj_vars import ProjVar
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient
from utils import lab_info
from keywords import host_helper, common


def record_kpi(local_kpi_file, kpi_name, host, log_path, end_pattern, start_pattern=None, extended_regex=False,
               python_pattern=None, average_for_all=False, lab_name=None, con_ssh=None, sudo=False, topdown=False):
    """
    Record kpi in ini format in given file
    Args:
        local_kpi_file (str): local file path to store the kpi data
        kpi_name (str): name of the kpi
        host (str): which tis host the log is located at
        log_path (str): log_path on given host to check the kpi timestamps
        end_pattern (str): pattern that signals the end or the value of the kpi. Used in Linux cmd 'grep'
        start_pattern (str|None): pattern that signals the end of the kpi. Used in Linux cmd 'grep'. Only required for
            duration type of the KPI, where we need to calculate the time delta ourselves.
        extended_regex (bool): whether to use -E in grep for extended regex.
        python_pattern (str): Only needed for KPI that is directly taken from log without post processing,
            e.g., rate for drbd sync
        average_for_all (bool): whether to get all instances from the log and get average
        lab_name (str): e.g., ip_1-4, hp380
        con_ssh (SSHClient|None): ssh client of active controller
        sudo (bool): whether to access log with sudo

    Returns:

    """
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller(fail_ok=True)
        if not con_ssh:
            lab = lab_info.get_lab_dict(labname=lab_name)
            ProjVar.set_var(lab=lab)
            ProjVar.set_var(source_admin=Tenant.ADMIN)
            con_ssh = SSHClient(lab.get('floating ip'), HostLinuxCreds.get_user(), HostLinuxCreds.get_password(),
                                CONTROLLER_PROMPT)
            con_ssh.connect()

    kpi_dict = {'host': host, 'log_path': log_path}

    with host_helper.ssh_to_host(hostname=host, con_ssh=con_ssh) as host_ssh:
        if start_pattern:
            kpi_val, time_stamp, count = get_duration(start_pattern=start_pattern, end_pattern=end_pattern,
                                                      log_path=log_path, host_ssh=host_ssh, sudo=sudo, topdown=topdown,
                                                      extended_regex=extended_regex, average_for_all=average_for_all)
        else:
            kpi_val, time_stamp, count = get_match(pattern=end_pattern, log_path=log_path, host_ssh=host_ssh,
                                                   extended_regex=extended_regex, python_pattern=python_pattern,
                                                   average_for_all=average_for_all, sudo=sudo, topdown=topdown)

    kpi_dict.update({'timestamp': time_stamp, 'value': kpi_val})

    config = ConfigParser()
    config[kpi_name] = kpi_dict
    with open(local_kpi_file, 'a+') as kpi_file:
        config.write(kpi_file)
        kpi_file.seek(0)
        print("Content in KPI file {}: \n{}".format(local_kpi_file, kpi_file.read()))


def search_log(file_path, ssh_client, pattern, extended_regex=False, get_all=False, top_down=False, sudo=False):
    count = '-m 1 ' if not get_all else ''
    extended_regex = '-E ' if extended_regex else ''
    base_cmd = 'cat' if top_down else 'tac'
    cmd = '{} {} | grep --color=never {}{}"{}"'.format(base_cmd, file_path, count, extended_regex, pattern)
    prefix_space = False
    if 'bash' in file_path:
        ssh_client.exec_cmd('HISTCONTROL=ignorespace')
        prefix_space = True

    if sudo:
        out = ssh_client.exec_sudo_cmd(cmd, fail_ok=True, prefix_space=prefix_space)[1]
    else:
        if prefix_space:
            cmd = ' {}'.format(cmd)
        out = ssh_client.exec_cmd(cmd, fail_ok=True)[1]

    if not out:
        raise ValueError("Nothing returned when run cmd from {}: {}".format(ssh_client.host, cmd))
    return out


def get_duration(start_pattern, end_pattern, log_path, host_ssh, extended_regex=False, average_for_all=False,
                 sudo=False, topdown=False):
    """
    Get duration in seconds between start and end timestamps when searching log from bottom up
    Args:
        start_pattern:
        end_pattern:
        log_path:
        host_ssh:
        extended_regex:
        average_for_all:
        sudo:

    Returns:

    """
    start_line = search_log(file_path=log_path, ssh_client=host_ssh, pattern=start_pattern, sudo=sudo,
                            extended_regex=extended_regex, get_all=average_for_all, top_down=topdown)
    end_line = search_log(file_path=log_path, ssh_client=host_ssh, pattern=end_pattern, sudo=sudo,
                          extended_regex=extended_regex, get_all=average_for_all, top_down=topdown)

    timestamp_pattern = '\d{4}-\d{2}-\d{2}[T| ]\d{2}:\d{2}:\d{2}'
    start_times = re.findall(timestamp_pattern, start_line)
    end_times = re.findall(timestamp_pattern, end_line)
    count = len(start_times)
    diff = len(end_times) - count
    if diff in [0, 1]:
        end_times = end_times[:count]
    else:
        raise ValueError("Please check start and end pattern, they are not 1 to 1 mapped")

    durations = []
    end_time = None
    for i in range(count):
        start_time = start_times[i]
        end_time = end_times[i]
        duration = common.get_timedelta_for_isotimes(time1=start_time, time2=end_time).total_seconds()
        if duration < 0:
            raise ValueError(
                "KPI end timestamp is earlier than start timestamp. Please check KPI start and end patterns.")

        durations.append(duration)

    if count > 1:
        average_duration = sum(durations) / count
    else:
        average_duration = durations[0]
    return average_duration, end_time, count


def get_match(pattern, log_path, host_ssh, python_pattern=None, extended_regex=False, average_for_all=False,
              sudo=False, topdown=False):
    line = search_log(file_path=log_path, ssh_client=host_ssh, pattern=pattern, extended_regex=extended_regex,
                      get_all=average_for_all, sudo=sudo, top_down=topdown)
    timestamp_pattern = '\d{4}-\d{2}-\d{2}[T| ]\d{2}:\d{2}:\d{2}'
    time_stamp = re.findall(timestamp_pattern, line)[-1]

    python_pattern = python_pattern if python_pattern else pattern
    vals = re.findall(python_pattern, line)
    count = len(vals)
    if count > 1:
        if average_for_all:
            vals = [float(val) for val in vals]
            final_val = (sum(vals) / float(count), min(vals), max(vals))
        else:
            raise ValueError("Please check python_pattern, more than 1 match found with python pattern in 1 grep match")
    else:
        final_val = vals[0]
    return final_val, time_stamp, count


if __name__ == '__main__':
    """
    Usage:
    python3.5 utils/kpi/kpi_log_parser.py --lab=wcp_7-12 --file=/home/yliu12/AUTOMATION_LOGS/kpitest.txt \
        --log=/var/log/nova/nova-compute.log --kpi=yang_kpi --host=compute-0 --end="Numa node=1; memory: "
    Output:
        Content of KPI file /home/yliu12/AUTOMATION_LOGS/kpitest.txt:
        [yang_kpi]
        value = Numa node=1; memory:
        log_path = /var/log/nova/nova-compute.log
        host = compute-0
        timestamp = 2017-11-01 19:54:34

    """
    parser = OptionParser()
    parser.add_option('-k', '--kpi', action='store', type='string', dest='kpi_name', help='kpi name')
    parser.add_option('--lab', action='store', dest='lab_name', help='Connect to given lab to check logs')
    parser.add_option('--host', action='store', dest='host', help='Host to check log from')
    parser.add_option('--log', '--log_path', '--logpath', '--log-path', action='store', dest='log_path')
    parser.add_option('-f', '--file', action='store', dest='local_path', help='local file path to store kpi data')
    parser.add_option('--end', action='store', dest='end_pattern', help='end pattern or the kpi pattern to grep in log')
    parser.add_option('--python', action='store', dest='python_pattern', default=None,
                      help='python pattern to search from grep output')
    parser.add_option('--start', action='store', dest='start_pattern', default=None,
                      help='start pattern to grep in log')
    parser.add_option('--all', action='store_true', dest='get_all', help='grep all occurrences and get average')
    parser.add_option('--sudo', action='store_true', dest='sudo', help='access log with sudo')
    parser.add_option('--topdown', action='store_true', dest='topdown', help='search log from top down')

    options, args = parser.parse_args()
    mandatory = ['kpi_name', 'lab_name', 'host', 'log_path', 'local_path', 'end_pattern']
    for mandatory_arg in mandatory:
        if not options.__dict__[mandatory_arg]:
            parser.print_help()
            raise parser.error("Parameter '{}' is missing. Mandatory parameters: {}".format(mandatory_arg, mandatory))

    record_kpi(local_kpi_file=options.local_path, kpi_name=options.kpi_name, log_path=options.log_path,
               end_pattern=options.end_pattern, start_pattern=options.start_pattern,
               python_pattern=options.python_pattern, lab_name=options.lab_name, host=options.host,
               average_for_all=options.get_all, sudo=options.sudo, topdown=options.topdown)
