import re
import os

from configparser import ConfigParser
from optparse import OptionParser

from consts.auth import HostLinuxCreds, Tenant
from consts.proj_vars import ProjVar
from consts.cgcs import TIMESTAMP_PATTERN
from consts.kpi_vars import KPI_DATE_FORMAT
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient
from utils import lab_info
from keywords import host_helper, common


def record_kpi(local_kpi_file, kpi_name, host=None, log_path=None, end_pattern=None, start_pattern=None,
               start_path=None, extended_regex=False, python_pattern=None, average_for_all=False, lab_name=None,
               con_ssh=None, sudo=False, topdown=False, init_time=None, build_id=None, start_host=None,
               uptime=5, start_pattern_init=False, sw_version=None, patch=None, unit=None, kpi_val=None):

    """
    Record kpi in ini format in given file
    Args:
        local_kpi_file (str): local file path to store the kpi data
        kpi_name (str): name of the kpi
        host (str|None): which tis host the log is located at. When None, assume host is active controller
        start_host (str|None): specify only if host to collect start log is different than host for end log
        log_path (str): log_path on given host to check the kpi timestamps.
            Required if start_time or end_time is not specified
        end_pattern (str): One of the two options. Option2 only applies to duration type of KPI
            1. pattern that signals the end or the value of the kpi. Used in Linux cmd 'grep'
            2. end timestamp in following format: e.g., 2017-01-23 12:22:59 (for duration type of KPI)
        start_pattern (str|None): One of the two options. Only required for duration type of the KPI, where we
            need to calculate the time delta ourselves.
            1. pattern that signals the start of the kpi. Used in Linux cmd 'grep'.
            2. start timestamp in following format: e.g., 2017-01-23 12:10:00
        start_path (str|None): log path to search for start_pattern if path is different than log_path for end_pattern
        extended_regex (bool): whether to use -E in grep for extended regex.
        python_pattern (str): Only needed for KPI that is directly taken from log without post processing,
            e.g., rate for drbd sync
        average_for_all (bool): whether to get all instances from the log and get average
        lab_name (str): e.g., ip_1-4, hp380
        con_ssh (SSHClient|None): ssh client of active controller
        sudo (bool): whether to access log with sudo
        topdown (bool): whether to search log from top down. Default is bottom up.
        init_time (str|None): when set, logs prior to this timestamp will be ignored.
        uptime (int|str): get load average for the previous <uptime> minutes via 'uptime' cmd
        start_pattern_init (bool): when set, use the timestamp of the start
        pattern as the init time for the end pattern
        sw_version (str): e.g., 17.07
        patch (str): patch name
        unit (str): unit for the kpi value if not 'Time(s)'
    Returns:

    """
    try:
        if not lab_name:
            lab = ProjVar.get_var('LAB')
            if not lab:
                raise ValueError("lab_name needs to be provided")
        else:
            lab = lab_info.get_lab_dict(labname=lab_name)

        kpi_dict = {'lab': lab['name']}
        if start_pattern and end_pattern and build_id:
            # No need to ssh to system if both timestamps are known
            if re.match(TIMESTAMP_PATTERN, end_pattern) and re.match(TIMESTAMP_PATTERN, start_pattern):
                duration = common.get_timedelta_for_isotimes(time1=start_pattern, time2=end_pattern).total_seconds()
                kpi_dict.update({'value': duration, 'timestamp': end_pattern, 'build_id': build_id})
                append_to_kpi_file(local_kpi_file=local_kpi_file, kpi_name=kpi_name, kpi_dict=kpi_dict)
                return

        if not con_ssh:
            con_ssh = ControllerClient.get_active_controller(fail_ok=True)
            if not con_ssh:
                if not ProjVar.get_var('LAB'):
                    ProjVar.set_var(lab=lab)
                    ProjVar.set_var(source_admin=Tenant.ADMIN)
                con_ssh = SSHClient(lab.get('floating ip'), HostLinuxCreds.get_user(), HostLinuxCreds.get_password(),
                                    CONTROLLER_PROMPT)
                con_ssh.connect()

        if not build_id:
            build_id = ProjVar.get_var('BUILD_ID')
            if not build_id:
                build_id = lab_info.get_build_id(labname=lab['name'], con_ssh=con_ssh)
        kpi_dict.update({'build_id': build_id})

        if not sw_version:
            sw_version = ProjVar.get_var('SW_VERSION')
            if not sw_version:
                sw_version = lab_info._get_build_info(con_ssh, 'SW_VERSION')[0]
            if isinstance(sw_version, list):
                sw_version = ', '.join(sw_version)
        kpi_dict.update({'sw_version': sw_version})

        if not patch:
            patch = ProjVar.get_var('PATCH')
            if patch:
                patch = '\n'.join(patch)
                kpi_dict.update({'patch': patch})

        load_average = get_load_average(ssh_client=con_ssh, uptime=uptime)
        kpi_dict.update({'load_average': load_average})

        if not unit:
            unit = 'Time(s)'
        kpi_dict.update({'unit': unit})

        if host:
            kpi_dict['host'] = host
        if log_path:
            kpi_dict['log_path'] = log_path

        if kpi_val is not None:
            time_stamp = common.get_date_in_format(ssh_client=con_ssh, date_format=KPI_DATE_FORMAT)
        else:
            if start_pattern:
                kpi_val, time_stamp, count = get_duration(start_pattern=start_pattern, start_path=start_path,
                                                          end_pattern=end_pattern, log_path=log_path,
                                                          host=host, sudo=sudo, topdown=topdown,
                                                          extended_regex=extended_regex,
                                                          average_for_all=average_for_all,
                                                          init_time=init_time, start_host=start_host,
                                                          start_pattern_init=start_pattern_init, con_ssh=con_ssh)
            else:
                kpi_val, time_stamp, count = get_match(pattern=end_pattern, log_path=log_path, host=host,
                                                       extended_regex=extended_regex, python_pattern=python_pattern,
                                                       average_for_all=average_for_all, sudo=sudo, topdown=topdown,
                                                       init_time=init_time, con_ssh=con_ssh)

        kpi_dict.update({'timestamp': time_stamp, 'value': kpi_val})

        append_to_kpi_file(local_kpi_file=local_kpi_file, kpi_name=kpi_name, kpi_dict=kpi_dict)

    except Exception as e:
        print("Failed to record kpi. Error: {}".format(e.__str__()))
        import traceback
        import sys
        traceback.print_exc(file=sys.stdout)


def append_to_kpi_file(local_kpi_file, kpi_name, kpi_dict):
    config = ConfigParser()
    config[kpi_name] = kpi_dict

    kpi_expanded_path = os.path.expanduser(local_kpi_file)
    kpi_directories = os.path.dirname(kpi_expanded_path)

    if os.path.exists(kpi_expanded_path):
        file_opts = 'a+'
    else:
        file_opts = 'w+'

    if not os.path.exists(kpi_directories):
        os.makedirs(kpi_directories)

    with open(kpi_expanded_path, file_opts) as kpi_file:
        config.write(kpi_file)
        kpi_file.seek(0)
        print("\nContent in KPI file {}: \n{}".format(local_kpi_file, kpi_file.read()))


def get_load_average(ssh_client, uptime=5):
    uptime_map = {
        '1': 0,
        '5': 1,
        '15': 2
    }
    out = ssh_client.exec_cmd('uptime')[1]
    uptimes = out.split('load average: ')[-1].split(', ')
    return float(uptimes[uptime_map[str(uptime)]])


def search_log(file_path, ssh_client, pattern, extended_regex=False, get_all=False, top_down=False, sudo=False,
               init_time=None):

    prefix_space = False
    if 'bash' in file_path:
        ssh_client.exec_cmd('HISTCONTROL=ignorespace')
        prefix_space = True
        sudo = True

    # Reformat the timestamp to add or remove T based on the actual format in specified log
    if init_time:
        tmp_cmd = """zgrep -m 1 "" {} | awk '{{print $1}}'""".format(file_path)
        if sudo:
            tmp_time = ssh_client.exec_sudo_cmd(tmp_cmd, fail_ok=False, prefix_space=prefix_space)[1]
        else:
            tmp_time = ssh_client.exec_cmd(tmp_cmd, fail_ok=False, prefix_space=prefix_space)[1]

        if re.search('\dT\d', tmp_time):
            init_time = init_time.strip().replace(' ', 'T')
        else:
            init_time = init_time.strip().replace('T', ' ')

    # Compose the zgrep cmd to search the log
    init_filter = """| awk '$0 > "{}"'""".format(init_time) if init_time else ''
    count = '' if get_all else '|grep --color=never -m 1 ""'
    extended_regex = '-E ' if extended_regex else ''
    base_cmd = '' if top_down else '|tac'
    cmd = 'zgrep --color=never {}"{}" {}|grep -v grep{}{}{}'.format(extended_regex, pattern, file_path, init_filter,
                                                                    base_cmd, count)
    print("Send: {}".format(cmd))
    if sudo:
        out = ssh_client.exec_sudo_cmd(cmd, fail_ok=True, prefix_space=prefix_space)[1]
    else:
        out = ssh_client.exec_cmd(cmd, fail_ok=True, prefix_space=prefix_space)[1]
    print("Output: {}".format(out))

    if not out:
        raise ValueError("Nothing returned when run cmd from {}: {}".format(ssh_client.host, cmd))
    return out


def get_duration(start_pattern, end_pattern, log_path, host, con_ssh, start_path=None, extended_regex=False,
                 start_host=None, average_for_all=False, sudo=False, topdown=False, init_time=None,
                 start_pattern_init=False):
    """
    Get duration in seconds between start and end timestamps when searching log from bottom up
    Args:
        start_pattern:
        end_pattern:
        log_path:
        host:
        con_ssh: SSHClient for active controller
        start_path:
        extended_regex:
        start_host
        average_for_all:
        sudo:
        topdown
        init_time: only look for matching line in log after init_time
        start_pattern_init (bool): whether to use the start time stamp as the init time for end time stamp.

    Returns:

    """
    def get_end_times(init_time_, host_ssh_):
        if re.match(TIMESTAMP_PATTERN, end_pattern):
            end_times_ = [end_pattern]
        else:
            end_line = search_log(file_path=log_path, ssh_client=host_ssh_, pattern=end_pattern, sudo=sudo,
                                  extended_regex=extended_regex, get_all=average_for_all, top_down=topdown,
                                  init_time=init_time_)
            end_times_ = re.findall(TIMESTAMP_PATTERN, end_line)
        return end_times_

    start_host = start_host if start_host else host
    end_times = None
    with host_helper.ssh_to_host(hostname=start_host, con_ssh=con_ssh) as host_ssh:
        if re.match(TIMESTAMP_PATTERN, start_pattern):
            start_times = [start_pattern]
        else:
            start_path = start_path if start_path else log_path
            start_line = search_log(file_path=start_path, ssh_client=host_ssh, pattern=start_pattern, sudo=sudo,
                                    extended_regex=extended_regex, get_all=average_for_all, top_down=topdown,
                                    init_time=init_time)
            start_times = re.findall(TIMESTAMP_PATTERN, start_line)
        if start_pattern_init:
            init_time = start_times[0]

        if start_host == host:
            end_times = get_end_times(init_time_=init_time, host_ssh_=host_ssh)

    if end_times is None:
        with host_helper.ssh_to_host(hostname=host, con_ssh=con_ssh) as end_ssh:
            end_times = get_end_times(init_time_=init_time, host_ssh_=end_ssh)

    count = len(start_times)
    end_count = len(end_times)
    diff = end_count - count
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


def get_match(pattern, log_path, host, con_ssh, python_pattern=None, extended_regex=False, average_for_all=False,
              sudo=False, topdown=False, init_time=None):
    with host_helper.ssh_to_host(hostname=host, con_ssh=con_ssh) as host_ssh:
        line = search_log(file_path=log_path, ssh_client=host_ssh, pattern=pattern, extended_regex=extended_regex,
                          get_all=average_for_all, sudo=sudo, top_down=topdown, init_time=init_time)

    timestamp_pattern = '\d{4}-\d{2}-\d{2}[T| ]\d{2}:\d{2}:\d{2}'
    time_stamp = re.findall(timestamp_pattern, line)[-1]

    python_pattern = python_pattern if python_pattern else pattern
    vals = re.findall(python_pattern, line)
    count = len(vals)
    if count > 1:
        if average_for_all:
            vals = [int(float(val)) for val in vals]
            final_val = ','.join([str(int(sum(vals)/count)), str(min(vals)), str(max(vals))])
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
    parser.add_option('--build', action='store', dest='build_id', help='Build ID of the TiC system')
    parser.add_option('--host', action='store', dest='host', help='Host to check log from')
    parser.add_option('--log', '--log_path', '--logpath', '--log-path', action='store', dest='log_path',
                      help="log_path to search for start_pattern and/or end_pattern")
    parser.add_option('--start_log', '--start-log', '--startlog', action='store', dest='start_path', default=None,
                      help="log path to search for start_pattern if path is different than log_path for end_pattern")
    parser.add_option('-f', '--file', action='store', dest='local_path', help='local file path to store kpi data')
    parser.add_option('--end', action='store', dest='end_pattern', help='end pattern or the kpi pattern to grep in log')
    parser.add_option('--python', action='store', dest='python_pattern', default=None,
                      help='python pattern to search from grep output')
    parser.add_option('--start', action='store', dest='start_pattern', default=None,
                      help='start pattern to grep in log')
    parser.add_option('--all', action='store_true', dest='get_all', help='grep all occurrences and get average')
    parser.add_option('--sudo', action='store_true', dest='sudo', help='access log with sudo')
    parser.add_option('--topdown', action='store_true', dest='topdown', help='search log from top down')
    parser.add_option('--init-time', '--init', action='store', dest='init_time', default=None,
                      help='Ignore logs prior to init time')
    parser.add_option('--uptime', action='store', dest='uptime', default=5,
                      help="Valid value: 1, 5, or 15. Load average in 'uptime'")

    options, args = parser.parse_args()
    mandatory = ['kpi_name', 'lab_name', 'local_path', 'end_pattern']
    for mandatory_arg in mandatory:
        if not options.__dict__[mandatory_arg]:
            parser.print_help()
            raise parser.error("Parameter '{}' is missing. Mandatory parameters: {}".format(mandatory_arg, mandatory))

    record_kpi(local_kpi_file=options.local_path, kpi_name=options.kpi_name, log_path=options.log_path,
               end_pattern=options.end_pattern, start_pattern=options.start_pattern, start_path=options.start_path,
               python_pattern=options.python_pattern, lab_name=options.lab_name, host=options.host,
               average_for_all=options.get_all, sudo=options.sudo, topdown=options.topdown, init_time=options.init_time,
               uptime=options.uptime, build_id=options.build_id)
