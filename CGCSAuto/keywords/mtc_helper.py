import time
import datetime
import os.path
import pexpect

from utils.tis_log import LOG
from utils.ssh import ControllerClient
from keywords import system_helper, host_helper, storage_helper
from consts.timeout import MTCTimeout

KILL_CMD = 'kill -9'


def get_ancestor_process(name, host, cmd='', fail_ok=False, retries=5, retry_interval=3, con_ssh=None):
    """
    Get the ancestor of the processes with the given name and command-line if any.

    Args:
        name:       name of the process
        host:       host on which to find the process
        cmd:        executable name
        fail_ok:    do not throw exception when errors
        retries:        times to try before return
        retry_interval: wait before next re-try
        con_ssh:        ssh connection/client to the active controller

    Returns:
        pid (str),          process id, -1 if there is any error
        ppid (str),         parent process id, -1 if there is any error
        cmdline (str)       command line of the process
    """
    retries = retries if retries > 1 else 3
    retry_interval = retry_interval if retry_interval > 0 else 1

    if cmd:
        ps_cmd = 'ps -e -oppid,pid,cmd | /usr/bin/grep "{}\|{}" | /usr/bin/grep -v grep | /usr/bin/grep {}'.format(
            name, os.path.basename(cmd), cmd)
    else:
        ps_cmd = 'ps -e -oppid,pid,cmd | /usr/bin/grep "{}" | /usr/bin/grep -v grep'.format(name)

    code, output = -1, ''
    if fail_ok:
        for count in range(retries):
            with host_helper.ssh_to_host(host, con_ssh=con_ssh) as con0_ssh:
                code, output = con0_ssh.exec_cmd(ps_cmd, fail_ok=True)
                if 0 == code and output.strip():
                    break
                LOG.warn('Failed to run cli:{} on controller at iteration:{:02d}, '
                         'wait:{} seconds and try again'.format(cmd, count, retry_interval))
                time.sleep(retry_interval)
    else:
        with host_helper.ssh_to_host(host, con_ssh=con_ssh) as con0_ssh:
            code, output = con0_ssh.exec_cmd(ps_cmd, fail_ok=False)

    if not (0 == code and output.strip()):
        LOG.error('Failed to find process with name:{} and cmd:{}'.format(name, cmd))
        return -1, -1, ''

    procs = []
    ppids = []
    for line in output.strip().splitlines():
        proc_attr = line.strip().split()
        if not proc_attr:
            continue
        try:
            ppid = proc_attr[0]
            pid = proc_attr[1]
            cmdline = ' '.join(proc_attr[2:])
            LOG.info('ppid={}, pid={}\ncmdline={}'.format(ppid, pid, cmdline))
        except IndexError:
            LOG.warn('Failed to execute ps -p ?! cmd={}, line={}, output={}'.format(
                cmd, line, output.strip()))
            continue

        if cmd and cmd not in cmdline:
            continue
        # procs.append((ppid, pid, cmdline))
        procs.append((pid, ppid, cmdline))
        ppids.append(ppid)

    if len(procs) <= 0:
        LOG.error('Could not find process with name:{} and cmd:{}'.format(name, cmd))
        return -1, -1, ''

    pids = [v[1] for v in procs]
    # if len(pids) != 2:
    if len(pids) == 1:
        LOG.info('porcs[0]:{}'.format(procs[0]))
        return procs[0]

    LOG.warn('Multiple ({}) parent processes?, ppids:{}'.format(len(ppids), ppids))

    # ppids = set(ppids)
    if '1' not in ppids:
        LOG.warn('Init is not the grand parent process?, ppids:{}'.format(ppids))

    for ppid, pid, cmdline in procs:
        if pid in ppids and ppid not in pids and 1 != pid:
            LOG.info('pid={}, ppid={}, cmdline={}'.format(pid, ppid, cmdline))
            return pid, ppid, cmdline

    LOG.error('Could not find process, procs:{}, ppids:{}, pids:{}'.format(procs, ppids, pids))
    return -1, -1, ''


def verify_process_with_pid_file(pid, pid_file, con_ssh=None):
    """
    Check if the given PID matching the PID in the specified pid_file

    Args:
        pid:        process id
        pid_file:   the file containing the process id
        con_ssh:    ssh connnection/client to the host on which the process resides

    Returns:

    """
    con_ssh = con_ssh or ControllerClient.get_active_controller()

    code, output = con_ssh.exec_sudo_cmd('cat {} | head -n1'.format(pid_file), fail_ok=False)
    LOG.info('code={}, output={}'.format(code, output))

    if output != pid:
        LOG.info('Mismatched PID, expected:<{}>, from pid_file:<{}>, pid_file={}'.format(
            pid, output.strip(), pid_file))
    else:
        LOG.info('OK PID:{} matches with that from pid_file:{}, pid_file={}'.format(pid, output.strip(), pid_file))

    return output == pid


def get_process_from_sm(name, con_ssh=None, pid_file='', expecting_status='enabled-active'):
    """
    Get the information for the process from SM, including PID, Name, Current Status and Pid-File

    Args:
        name:               name of the process
        con_ssh:            ssh connection/client to the active-controller
        pid_file:           known pid-file path/name to compare with
        expecting_status:   expected status of the process

    Returns:
        pid (str):          process id
        proc_name (str):    process name
        actual_status (str):    actual/current status of the process
        sm_pid_file (str):      pid-file in records of SM
    """
    con_ssh = con_ssh or ControllerClient.get_active_controller()

    cmd = 'sm-dump --impact --pid --pid_file | /usr/bin/grep "{}"'.format(name)

    code, output = con_ssh.exec_sudo_cmd(cmd, fail_ok=True)

    if 0 != code or not output:
        LOG.warn('Cannot find the process:{} in SM with error code:\n{}\noutput:{}'.format(
            name, code, con_ssh.exec_sudo_cmd('sm-dump --impact --pid --pid_file')))
        return -1, '', ''

    pid, proc_name, sm_pid_file, actual_status = -1, '', '', ''

    for line in output.splitlines():
        results_array = line.strip().split()
        LOG.info('results_array={}'.format(results_array))

        try:
            proc_name = results_array[0]
            if proc_name != name:
                continue

            expect_status = results_array[1]
            actual_status = results_array[2]
            if expect_status != actual_status:
                LOG.warn('service:{} is not in expected status yet. expected:{}, actual:{}. Retry'.format(
                    proc_name, expect_status, actual_status))
                break

            if actual_status != expecting_status:
                LOG.warn('service:{} is not in expected status yet. expected:{}, actual:{}. Retry'.format(
                    proc_name, expecting_status, actual_status))
                break

            pid = results_array[4]
            if results_array[5] != sm_pid_file:
                LOG.warn('pid_file not matching with that from SM-dump, pid_file={}, sm-dump-pid_file={}'.format(
                    sm_pid_file, results_array[5]))
            sm_pid_file = results_array[5]

            if pid_file and sm_pid_file != pid_file:
                LOG.warn('pid_file differs from input pid_file, pid_file={}, sm-dump-pid_file={}'.format(
                    pid_file, sm_pid_file))

            if sm_pid_file:
                if not verify_process_with_pid_file(pid, sm_pid_file, con_ssh=con_ssh):
                    LOG.warn('pid of service mismatch that from pid-file, pid:{}, pid-file:{}, proc-name:{}'.format(
                        pid, sm_pid_file, proc_name))

            return pid, proc_name, actual_status, sm_pid_file

        except IndexError as e:
            LOG.warn('lacking information from sm-dump, line:{}, error:{}'.format(line, e))

    if -1 != pid:
        existing, msg = storage_helper.check_pid_exists(pid, host_ssh=con_ssh)
        if not existing:
            LOG.warn('Process not existing, name={}, pid={}, msg={}'.format(name, pid, msg))
            return -1, '', ''

    return pid, proc_name, actual_status, sm_pid_file


def is_controller_swacted(prev_active,
                          swact_start_timeout=MTCTimeout.KILL_PROCESS_SWACT_NOT_START,
                          swact_complete_timeout=MTCTimeout.KILL_PROCESS_SWACT_COMPLETE,
                          con_ssh=None):
    """
    Wait and check if the active-controller on the system was 'swacted' with give time period

    Args:
        prev_active:            previous active controller
        swact_start_timeout:    check within this time frame if the swacting started
        swact_complete_timeout: check if the swacting (if any) completed in this time period
        con_ssh:                ssh connection/client to the current active-controller

    Returns:

    """
    LOG.info('Check if the controllers started to swact within:{}, and completing swacting within:{}'.format(
        swact_start_timeout, swact_complete_timeout))

    code, msg = host_helper.wait_for_swact_complete(
        prev_active, con_ssh=con_ssh, fail_ok=True,
        swact_start_timeout=swact_start_timeout, swact_complete_timeout=swact_complete_timeout)

    LOG.info('code={}, msg={}'.format(code, msg))
    return 0 == code


def check_host_status(host, target_status, expecting=True, con_ssh=None):
    LOG.info('check for host:{} expecting status:{}'.format(host, target_status))
    try:
        operational, availability = target_status.split('-')
    except ValueError as e:
        LOG.error('unknown host status:{}, error:{}'.format(target_status, e))
        raise

    if expecting:
        return host_helper.wait_for_hosts_states(
            host, timeout=MTCTimeout.KILL_PROCESS_HOST_CHANGE_STATUS, check_interval=0, duration=1,
            con_ssh=con_ssh, fail_ok=True, **{'operational': operational, 'availability': availability})
        # return host_helper.wait_for_host_states(
        #     host, timeout=MTCTimeout.KILL_PROCESS_HOST_CHANGE_STATUS, check_interval=1,
        #     fail_ok=True, **{'operational': operational, 'availability': availability}, con_ssh=con_ssh)
    else:
        return not host_helper.wait_for_hosts_states(
            host, timeout=MTCTimeout.KILL_PROCESS_HOST_KEEP_STATUS, check_interval=3, duration=3,
            con_ssh=con_ssh, fail_ok=True, **{'operational': operational, 'availability': availability})
        # return not host_helper.wait_for_host_states(
        #     host, timeout=MTCTimeout.KILL_PROCESS_HOST_KEEP_STATUS, check_interval=1,
        #     fail_ok=True, **{'operational': operational, 'availability': availability})


def check_impact(impact, host='', expecting_impact=False, con_ssh=None, **kwargs):
    """
    Check if the expected IMPACT happens (or NOT) on the specified host

    Args:
        impact (str):   system behavior to check, including:
                            swact   ---  the active controller swacting
                            enabled-degraded    ---     the host changed to 'enalbed-degraded' status
                            disabled-failed     ---     the host changed to 'disabled-failed' status
                            ...
        host (str):     the host to check
        expecting_impact (bool):    if the IMPACT should happen
        con_ssh:                    ssh connection/client to the active controller
        **kwargs:

    Returns:
        boolean -   whether the IMPACT happens as expected

    """
    LOG.info('impact={}, host={}, expecting_impact={}'.format(impact, host, expecting_impact))

    if impact == 'swact':
        prev_active = kwargs.get('active_controller', None)
        if prev_active is None:
            LOG.error('no previous active-controller provided:{}'.format(kwargs))
            return False

        if expecting_impact:
            return is_controller_swacted(
                prev_active, con_ssh=con_ssh, swact_start_timeout=20, swact_complete_timeout=80)
        else:
            return not is_controller_swacted(prev_active, con_ssh=con_ssh, swact_start_timeout=20)

    elif impact in ['enabled-degraded', 'disabled-failed']:
        return check_host_status(host, impact, expecting=expecting_impact, con_ssh=con_ssh)

    else:
        LOG.warn('impact-checker for impact:{} not implemented yet, kwargs:{}'.format(impact, kwargs))
        return False


def get_process_info(name, cmd='', pid_file='', host='', sm_process=True, con_ssh=None):
    """
    Get the information of the process with the specified name

    Args:
        name (str):     name of the process
        cmd (str):      path of the executable
        pid_file (str): path of the file containing the process id
        host (str):     host on which the process resides
        sm_process (bool):  if it is a SM service/process
        con_ssh:        ssh connection/client to the active controller

    Returns:

    """
    active_controller = system_helper.get_active_controller_name()
    if not host:
        host = active_controller

    if sm_process:
        if host != active_controller:
            LOG.warn('Trying to get SM process from non-active controller?')
        pid, name, status, pid_file = get_process_from_sm(name, con_ssh=con_ssh, pid_file=pid_file)
        if status != 'enabled-active':
            LOG.warn('SM process is in status:{}, not "enabled-active"'.format(status))
            if 'disabl' in status:
                LOG.warn('Wrong controller? Or controller already swacted, wait and try on the other controller')
                time.sleep(10)
                return get_process_from_sm(name, pid_file=pid_file)

            return -1, name, status, pid_file
        else:
            return pid, name, status, pid_file

    else:
        LOG.info('Try to find the process:{} using "ps"'.format(name))

        pid = get_ancestor_process(name, host, cmd=cmd, con_ssh=con_ssh)[0]
        if -1 == pid:
            return -1, '', '', ''

        return pid, name, '', ''


def is_process_running(pid, host, con_ssh=None, retries=10, interval=3):
    """
    Check if the process with the PID is existing

    Args:
        pid (str):      process id
        host (str):     host the process resides
        con_ssh:        ssh connection/client to the host
        retries (int):  times to re-try if no process found before return failure
        interval (int): time to wait before next re-try

    Returns:
        boolean     - true if the process existing, false otherwise
        msg (str)   - the details of the process or error messages
    """
    cmd = 'ps -p {}'.format(pid)
    for _ in range(retries):
        with host_helper.ssh_to_host(host, con_ssh=con_ssh) as con:
            code, output = con.exec_sudo_cmd(cmd, fail_ok=True)
            if 0 != code:
                LOG.warn('Process:{} DOES NOT exist, error:{}'.format(pid, output))
            else:
                return True, output
            time.sleep(interval)

    return False, ''


def kill_controller_process_verify_impact(
        name, cmd='', pid_file='', retries=2, impact='swact', interval=20,
        action_timeout=90, total_retries=30, on_active_controller=True, con_ssh=None):
    """
    Kill the process with the specified name and verify the system behaviors as expected

    Args:
        name (str):             name of the process
        cmd (str):              executable of the process
        pid_file (str):         file containing process id
        retries (int):          times of killing actions upon which the IMPACT will be triggered
        impact (str):           system behavior including:
                                    swact   -- active controller is swacted
                                    enabled-degraded    -- the status of the service will change to
                                    disabled-failed     -- the status of the service will change to
                                    ...
        interval (int):         least time to wait between kills
        action_timeout (int):   kills and impact should happen within this time frame
        total_retries (int):    total number of retries for whole kill and wait actions
        on_active_controller (boolean):
        con_ssh:                ssh connection/client to the active controller

    Returns: (pid, host)
        pid:
            >0  suceess, the final PID of the process
            -1  failure because of impact NOT happening after killing the process up to threshold times
            -2  failure because of impact happening before killing threshold times
            -3  failure after try total_retries times
        host:
            the host tested on
    """
    active_controller, standby_controller = system_helper.get_active_standby_controllers(con_ssh=con_ssh)

    if on_active_controller:
        host = active_controller
        LOG.info('on active controller: {}'.format(host))
        con_ssh = con_ssh or ControllerClient.get_active_controller()
    else:
        host = standby_controller
        con_ssh = None

    LOG.info('on host: {}'.format(host))

    if total_retries < 1 or retries < 1:
        LOG.error('retries/total-retries < 1? retires:{}, total retries:{}'.format(retries, total_retries))
        return None

    for i in range(1, total_retries+1):
        LOG.info('kill-n-wait iteration:{:02d}'.format(i))

        exec_times = []
        killed_pids = []

        timeout = time.time() + action_timeout

        count = 0
        while time.time() < timeout:
            count += 1

            try:
                pid, proc_name = get_process_info(name, cmd=cmd, host=host, pid_file=pid_file, con_ssh=con_ssh)[0:2]

            except pexpect.exceptions.EOF:
                LOG.warn('Failed to get process id for {} on host:{}'.format(name, host))
                time.sleep(interval / 3)
                continue

            if -1 == pid:
                LOG.error('Failed to get PID for process with name:{}, cmd:{}, wait and retries'.format(name, cmd))
                time.sleep(interval / 3)
                continue

            if killed_pids and pid in killed_pids:
                LOG.warn('No new process re-created, prev-pid={}, cur-pid={}'.format(killed_pids[-1], pid))
                time.sleep(interval / 3)
                continue

            last_killed_pid = killed_pids[-1] if killed_pids else None
            killed_pids.append(pid)
            last_kill_time = exec_times[-1] if exec_times else None
            exec_times.append(datetime.datetime.utcnow())

            LOG.info('iteration{:02d}: before kill CLI, proc_name={}, pid={}, last_killed_pid={}, '
                     'last_kill_time={}'.format(count, proc_name, pid, last_killed_pid, last_kill_time))

            LOG.info('\tactive-controller={}, standby-controller={}'.format(
                active_controller, standby_controller))

            kill_cmd = '{} {}'.format(KILL_CMD, pid)

            with host_helper.ssh_to_host(host, con_ssh=con_ssh) as con:
                code, output = con.exec_sudo_cmd(kill_cmd, fail_ok=True)
                if 0 != code:
                    LOG.warn('iteration{:02d}: Failed to kill pid:{}, cmd={}, output=<{}>, not event existing?'.format(
                        count, pid, kill_cmd, output))
                    time.sleep(interval / 3)
                    continue

            LOG.info('iteration{:02d}: OK to kill pid:{} on host:{}, cmd={}, output=<{}>'.format(
                count, pid, host, kill_cmd, output))

            if count < retries:
                # IMPACT should not happen yet
                if not check_impact(impact, active_controller=active_controller,
                                    expecting_impact=False, host=host, con_ssh=con_ssh):
                    LOG.error('Impact:{} observed unexpectedly, it should happen only after killing {} times, '
                              'actual killed times:{}'.format(impact, retries, count))
                    return -2, host
                LOG.info('iteration{:02d}: OK, NO impact as expected, impact={}'.format(count, impact))

            else:
                no_standby_controller = standby_controller is None
                expecting_impact = True if not no_standby_controller else False
                if not check_impact(
                        impact, active_controller=active_controller,
                        expecting_impact=expecting_impact, host=host, con_ssh=con_ssh):
                    LOG.error('No impact after killing process {} {} times, while {}'.format(
                        proc_name, count, ('expecting impact' if expecting_impact else 'not expecting impact')))

                    return -1, host

                LOG.info('OK, final iteration{:02d}: OK, IMPACT happened (if applicable) as expected, impact={}'.format(
                    count, impact))

                active_controller, standby_controller = system_helper.get_active_standby_controllers(con_ssh=con_ssh)

                LOG.info('OK, after impact:{} (tried:{} times), now active-controller={}, standby-controller={}'.format(
                    impact, count, active_controller, standby_controller))

                pid, proc_name = get_process_info(name, cmd=cmd, host=host, pid_file=pid_file, con_ssh=con_ssh)[0:2]
                return pid, active_controller

            time.sleep(interval)

    return -3, host
