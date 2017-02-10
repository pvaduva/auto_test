import time
import datetime
import os.path
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from keywords import system_helper, host_helper
from consts.timeout import MTCTimeout

KILL_CMD = 'kill -9'
# KILL_CMD = 'kill'


def get_ancestor_process(name, host, cmd='', fail_ok=False, retries=5, retry_interval=3, con_ssh=None):
    """

    Args:
        name:
        host:
        cmd:
        fail_ok:
        retries:
        retry_interval:
        con_ssh:

    Returns:
        pid (str),          process id
        ppid (str),         parent process id
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
        ppid = proc_attr[0]
        pid = proc_attr[1]
        cmdline = ' '.join(proc_attr[2:])
        LOG.info('ppid={}, pid={}\ncmdline={}'.format(ppid, pid, cmdline))

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
    con_ssh = con_ssh or ControllerClient.get_active_controller()

    code, output = con_ssh.exec_sudo_cmd('cat {} | head -n1'.format(pid_file), fail_ok=False)
    LOG.info('code={}, output={}'.format(code, output))

    # assert 0 != code or output.strip() == pid, \
    #     'Mismatched PID, expected:<{}>, from pid_file:<{}>, pid_file={}'.format(pid, output.strip(), pid_file)

    if output != pid:
        LOG.info('Mismatched PID, expected:<{}>, from pid_file:<{}>, pid_file={}'.format(
            pid, output.strip(), pid_file))
    else:
        LOG.info('OK PID:{} matches with that from pid_file:{}, pid_file={}'.format(pid, output.strip(), pid_file))

    return output == pid


def get_process_from_sm(name, con_ssh=None, retries=6, interval=5, pid_file=''):
    con_ssh = con_ssh or ControllerClient.get_active_controller()

    cmd = 'sm-dump --impact --pid --pid_file | /usr/bin/grep "{}"'.format(name)
    for i in range(1, retries+1):

        code, output = con_ssh.exec_sudo_cmd(cmd, fail_ok=True)

        if 0 != code or not output:
            LOG.warn('Cannot find the process:{} in SM with error code:\n{}\noutput:{}'.format(
                name, code, con_ssh.exec_sudo_cmd('sm-dump --impact --pid --pid_file')))
            continue

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

                severity = results_array[3]

                pid = results_array[4]
                if results_array[5] != pid_file:
                    LOG.warn('pid_file not matching with that from SM-dump, pid_file={}, from sm-dump={}'.format(
                        pid_file, results_array[5]))
                pid_file = results_array[5]

                # others = results_array[6:]

                LOG.info('proc_name={}'.format(proc_name))
                LOG.info('expect_status={}'.format(expect_status))
                LOG.info('actual_status={}'.format(actual_status))
                LOG.info('severity={}'.format(severity))
                LOG.info('pid={}'.format(pid))
                LOG.info('pid_file={}'.format(pid_file))
                # LOG.info('others={}'.format(others))

                if pid_file:
                    if not verify_process_with_pid_file(pid, pid_file, con_ssh=con_ssh):
                        LOG.warn('pid of service mismatch that from pid-file, pid:{}, pid-file:{}, proc-name:{}'.format(
                            pid, pid_file, proc_name))

                        # break

                return pid, proc_name, pid_file

            except IndexError as e:
                LOG.warn('lacking information from sm-dump, line:{}, error:{}'.format(line, e))
                break

        LOG.info('attempt:{:02d} to find pid from sm for pocess:{}'.format(i, name))

        time.sleep(interval)

    return -1, '', ''


def is_controller_swacted(prev_active,
                          swact_start_timeout=MTCTimeout.KILL_PROCESS_SWACT_NOT_START,
                          swact_complete_timeout=MTCTimeout.KILL_PROCESS_SWACT_COMPLETE,
                          con_ssh=None):
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
    LOG.info('impact={}, host={}, expecting_impact={}'.format(impact, host, expecting_impact))

    if impact == 'swact':
        prev_active = kwargs.get('active_controller', None)
        if prev_active is None:
            LOG.error('no previous active-controller provided:{}'.format(kwargs))
            return False

        if expecting_impact:
            return is_controller_swacted(
                prev_active, con_ssh=con_ssh, swact_start_timeout=40, swact_complete_timeout=80)
        else:
            return not is_controller_swacted(prev_active, con_ssh=con_ssh, swact_start_timeout=10)

    elif impact in ['enabled-degraded', 'disabled-failed']:
        return check_host_status(host, impact, expecting=expecting_impact, con_ssh=con_ssh)

    else:
        LOG.warn('impact-checker for impact:{} not implemented yet, kwargs:{}'.format(impact, kwargs))
        return False


def get_process_info(name, cmd='', pid_file='', host='', check_sm=True, con_ssh=None):

    active_controller = system_helper.get_active_controller_name()
    if not host:
        host = active_controller

    if host == active_controller and check_sm:
        pid, proc_name, pid_file = get_process_from_sm(name, con_ssh=con_ssh, pid_file=pid_file)

        if -1 != pid:
            return pid, proc_name, pid_file

        LOG.info('Cannot find the process:{} in SM, try with ps'.format(name))

    pid = get_ancestor_process(name, host, cmd=cmd, con_ssh=con_ssh)[0]
    if -1 == pid:
        return -1, '', ''
    return pid, name, ''


def kill_controller_process_verify_impact(
        name, cmd='', pid_file='', retries=2, impact='swact', interval=20,
        kill_retries=10, on_active_controller=True, con_ssh=None):
    """
    Kill the process with the specified name.
        -- First, using the information from SM (output of sm-dump) to find the process: name, pid, pid_file (if any)
        -- If not found, using ps/pkill ...

    Args:
        name:
        cmd:
        pid_file:
        retries:
        impact:
        interval:
        kill_retries (int):     number of retries to kill the same pid
        on_active_controller:
        con_ssh:

    Returns:
        0   suceess
        -1  failure because of impact NOT happening after killing the process up to threshold times
        -2  failure because of impact happening before killing threshold times

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

    if retries < 1:
        LOG.warn('to kill the process {} time? times must greater than 0'.format(retries))
        return None

    count = 0
    exec_times = []
    killed_pids = []

    # TODO
    # while True:
    for _ in range(30):
        count += 1

        pid, proc_name = get_process_info(name, cmd=cmd, host=host, pid_file=pid_file, con_ssh=con_ssh)[0:2]

        if killed_pids and killed_pids[-1] == pid:
            LOG.warn('Old PID and new PID are the same?! prev-pid={}, new-pid={}'.format(killed_pids[-1], pid))
            # TODO
            time.sleep(1)
            continue

        last_killed_pid = killed_pids[-1] if killed_pids else None
        # last_kill_time = exec_times[-1] if exec_times else None

        killed_pids.append(pid)
        exec_times.append(datetime.datetime.utcnow())

        LOG.info('iteration{:02d}: before kill CLI, proc_name={}, pid={}, last_killed_pid={}'.format(
            count, proc_name, pid, last_killed_pid))
        LOG.info('\tactive-controller={}, standby-controller={}'.format(active_controller, standby_controller))

        kill_cmd = '{} {}'.format(KILL_CMD, pid)
        # TODO need to make the loop number configurable
        for _ in range(kill_retries):
            with host_helper.ssh_to_host(host, con_ssh=con_ssh) as con:
                code, output = con.exec_sudo_cmd(kill_cmd, fail_ok=True)
                if 0 != code:
                    LOG.warn('Failed to kill pid:{}, cmd={}, output=<{}>'.format(pid, kill_cmd, output))
                    time.sleep(0.5)
                else:
                    LOG.info('OK to kill pid:{} on host:{}, cmd={}, output=<{}>'.format(pid, host, kill_cmd, output))
                    break

        LOG.info('iteration{:02d}: after CLI:{}, code={}, output={}'.format(count, kill_cmd, code, output))

        if count < retries:
            if 0 != code:
                LOG.info('iteration{:02d}: failed to kill process:{}, already IMPACTed?, '
                         'after CLI:{}, code={}, output={}'.format(count, pid, kill_cmd, code, output))

            # IMPACT should not happen yet
            if not check_impact(
                    impact, active_controller=active_controller, expecting_impact=False, host=host, con_ssh=con_ssh):
                LOG.error('Impact:{} observed unexpectedly, it should happen only after killing {} times, '
                          'actual killed times:{}'.format(impact, retries, count))
                return -2

            LOG.info('iteration{:02d}: OK, NO impact as expected, impact={}'.format(count, impact))

        else:
            no_standby_controller = standby_controller is None
            expecting_impact = True if not no_standby_controller else False
            if not check_impact(
                    impact, active_controller=active_controller,
                    expecting_impact=expecting_impact, host=host, con_ssh=con_ssh):
                LOG.error('No impact after killing process {} {} times, while {}'.format(
                    proc_name, count, ('expecting impact' if expecting_impact else 'not expecting impact')))

                return -1

            LOG.info('final: iteration{:02d}: OK, IMPACT happened (if applicable) as expected, impact={}'.format(
                count, impact))
            break

        time.sleep(interval)

    active_controller, standby_controller = system_helper.get_active_standby_controllers(con_ssh=con_ssh)

    LOG.info('OK, after impact:{} (tried:{} times), now active-controller={}, standby-controller={}'.format(
        impact, count, active_controller, standby_controller))

    return 0
