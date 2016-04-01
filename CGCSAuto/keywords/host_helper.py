import time

from consts.auth import Tenant
from consts.cgcs import HostAavailabilityState, HostAdminState
from consts.timeout import HostTimeout
from keywords import system_helper
from keywords.security_helper import LinuxUser
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient, SSHFromSSH
from utils.tis_log import LOG


def reboot_hosts(hostnames, timeout=HostTimeout.REBOOT, con_ssh=None, fail_ok=False):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if isinstance(hostnames, str):
        hostnames = [hostnames]

    reboot_con = False
    controller = system_helper.get_active_controller_name(con_ssh)
    hostnames = list(set(hostnames))
    if controller in hostnames:
        reboot_con = True
        hostnames.remove(controller)

    user, password = LinuxUser.get_current_user_password()
    # reboot hosts other than active controller
    for host in hostnames:
        prompt = '.*' + host + '\:~\$'
        host_ssh = SSHFromSSH(ssh_client=con_ssh, host=host, user=user, password=password, initial_prompt=prompt)
        host_ssh.connect()
        current_host = host_ssh.get_hostname()
        if not current_host == host:
            raise exceptions.SSHException("Current host is {} instead of {}".format(current_host, host))

        LOG.info("Rebooting {}".format(host))
        host_ssh.send('sudo reboot -f')
        host_ssh.expect('.*[pP]assword:.*')
        host_ssh.send(password)
        con_ssh.expect(timeout=30)

    if reboot_con:
        LOG.info("Rebooting active controller: {}".format(controller))
        con_ssh.send('sudo reboot -f')
        con_ssh.expect('.*[pP]assword:.*')
        con_ssh.send(password)
        time.sleep(20)
        con_ssh.connect(retry=True, retry_timeout=timeout)
        _wait_for_openstack_cli_enable(con_ssh=con_ssh)
        hostnames.append(controller)

    time.sleep(30)
    hostnames = sorted(hostnames)
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    unlocked_hosts_all = table_parser.get_values(table_, 'hostname', administrative='unlocked')
    locked_hosts_all = table_parser.get_values(table_, 'hostname', administrative='locked')
    unlocked_hosts = list(set(unlocked_hosts_all) & set(hostnames))
    locked_hosts = list(set(locked_hosts_all) & set(hostnames))

    LOG.info("Locked: {}. Unlocked:{}".format(locked_hosts, unlocked_hosts))
    sorted_total_hosts = sorted(locked_hosts + unlocked_hosts)
    if not sorted_total_hosts == hostnames:
        raise exceptions.HostError("Some hosts are neither locked or unlocked. \nHosts Rebooted: {}. Locked: {}; "
                                   "Unlocked: {}".format(hostnames, locked_hosts, unlocked_hosts))
    unlocked_hosts_in_states = True
    locked_hosts_in_states = True
    if len(locked_hosts) > 0:
        locked_hosts_in_states = _wait_for_hosts_states(locked_hosts, timeout=HostTimeout.REBOOT, check_interval=10,
                                                        duration=8, con_ssh=con_ssh, availability=['online'])

    if len(unlocked_hosts) > 0:
        unlocked_hosts_in_states = _wait_for_hosts_states(unlocked_hosts, timeout=HostTimeout.REBOOT, check_interval=10,
                                                          con_ssh=con_ssh, availability=['available', 'degraded'])

    states_vals = {}
    task_unfinished_msg = ''
    for host in hostnames:
        vals = get_hostshow_values(host, con_ssh, 'task', 'availability')
        if not vals['task'] == '':
            task_unfinished_msg = task_unfinished_msg + "{} still in task: {}. ".format(host, vals['task'])
        states_vals[host] = vals

    message = "Host(s) state(s) - {}. ".format(states_vals)

    if locked_hosts_in_states and unlocked_hosts_in_states and task_unfinished_msg == '':
        return [0, message]

    err_msg = "Host(s) not in expected availability states or task unfinished. " + message + task_unfinished_msg
    if fail_ok:
        return [1, err_msg]
    else:
        raise exceptions.HostPostCheckFailed(err_msg)


def __hosts_stay_in_states(hosts, duration=10, con_ssh=None, **states):
    end_time = time.time() + duration
    while time.time() < end_time:
        if not __hosts_in_states(hosts=hosts, con_ssh=con_ssh, **states):
            return False

    return True


def _wait_for_hosts_states(hosts, timeout=HostTimeout.REBOOT, check_interval=5, duration=3, con_ssh=None, **states):
    """

    Args:
        hosts:
        timeout:
        check_interval:
        duration (int): wait for a host to be in given state(s) for at least <duration> seconds
        con_ssh:
        **states:

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]
    for key, value in states.items():
        if isinstance(value, str):
            value = [value]
            states[key] = value

    LOG.info("Waiting for {} to reach state(s): {}...".format(hosts, states))
    end_time = time.time() + timeout
    while time.time() < end_time:
        if __hosts_stay_in_states(hosts, con_ssh=con_ssh, duration=duration, **states):
            LOG.info("{} have reached state(s): {}".format(hosts, states))
            return True
        time.sleep(check_interval)
    else:
        LOG.warning("Timed out waiting for {} in state(s) - {}".format(hosts, states))
        return False


def __hosts_in_states(hosts, con_ssh=None, **states):

    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, hostname=hosts)
    for state_name, values in states.items():
        actual_states = table_parser.get_column(table_, state_name)
        for actual_state in actual_states:
            if actual_state not in values:
                LOG.debug("At least one host from {} has {} state(s) in {} instead of {}".
                          format(hosts, state_name, actual_state, values))
                return False

    return True


def lock_host(host, force=False, timeout=HostTimeout.ONLINE_AFTER_LOCK, con_ssh=None, fail_ok=False):
    """
    lock a host.

    Args:
        host:
        force:
        timeout (int): how many seconds to wait for host to go online after lock
        con_ssh:
        fail_ok:

    Returns: [return_code, error_message]  Non-zero return code scenarios only applicable when fail_ok=True
        [0, ''] Successfully locked and host goes online
        [1, stderr] Lock host rejected
        [2, ''] Successfully locked but host did not become online before timeout


    """
    if get_hostshow_value(host, 'availability') in ['offline', 'failed']:
        LOG.warning("Host in offline or failed state!")

    admin_state = get_hostshow_value(host, 'administrative', con_ssh=con_ssh)
    if admin_state == 'locked':
        LOG.info("Host already locked. Do nothing.")
        return [-1, 'Host already locked. Do nothing.']

    LOG.info("Locking {}...".format(host))
    positional_arg = host
    extra_msg = ''
    if force:
        positional_arg += ' --force'
        extra_msg = 'force '

    # TODO: add check for storage monitors count?
    exitcode, output = cli.system('host-lock', positional_arg, ssh_client=con_ssh, fail_ok=fail_ok,
                                  auth_info=Tenant.ADMIN, rtn_list=True)

    if exitcode == 1:
        return [1, output]

    if not _wait_for_host_states(host, timeout=10, administrative=HostAdminState.LOCKED, con_ssh=con_ssh):
        if fail_ok:
            return [3, "Host is not in locked state."]
        else:
            raise exceptions.HostPostCheckFailed("Host is not locked.")
    LOG.info("{} is {}locked.".format(host, extra_msg))

    if _wait_for_host_states(host, timeout=timeout, availability='online'):
        # ensure the online status lasts for more than 5 seconds. Sometimes host goes online then offline to reboot..
        time.sleep(5)
        if _wait_for_host_states(host, timeout=timeout, availability='online'):
            return [0, '']

    if fail_ok:
        return [2, "host state is not online"]
    else:
        raise exceptions.HostPostCheckFailed("Host did not go online within {} seconds after {}lock".
                                             format(timeout, extra_msg))


def unlock_host(host, timeout=HostTimeout.CONTROLLER_UNLOCK, fail_ok=False, con_ssh=None):
    """

    Args:
        host (str):
        timeout (int): MAX seconds to wait for host to become available or degraded after unlocking
        fail_ok (bool):
        con_ssh:

    Returns:
        [0, '']
        [1, <stderr>]                                   ---only applicable if fail_ok
        [2, "Host is not in unlocked state"]            ---only applicable if fail_ok
        [3, "Host state did not change to available or degraded within timeout"]        --only applicable if fail_ok
        [4, "Host is in degraded state after unlocked."]

    """
    if get_hostshow_value(host, 'availability') == 'offline':
        _wait_for_host_states(host, availability=[HostAavailabilityState.AVAILABLE, HostAavailabilityState.ONLINE],
                              fail_ok=False)

    if get_hostshow_value(host, 'administrative', con_ssh=con_ssh) == HostAdminState.UNLOCKED:
        message = "Host already unlocked. Do nothing"
        LOG.info(message)
        return [-1, message]

    exitcode, output = cli.system('host-unlock', host, ssh_client=con_ssh, auth_info=Tenant.ADMIN, rtn_list=True,
                                  fail_ok=fail_ok, timeout=60)
    if exitcode == 1:
        return [1, output]

    if not _wait_for_host_states(host, timeout=30, administrative=HostAdminState.UNLOCKED, con_ssh=con_ssh,
                                 fail_ok=fail_ok):
        return [2, "Host is not in unlocked state"]

    if not _wait_for_host_states(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
                                 availability=[HostAavailabilityState.AVAILABLE, HostAavailabilityState.DEGRADED]):
        return [3, "Host state did not change to available or degraded within timeout"]

    if get_hostshow_value(host, 'availability') == HostAavailabilityState.DEGRADED:
        LOG.warning("Host is in degraded state after unlocked.")
        return [4, "Host is in degraded state after unlocked."]

    return [0, '']


def get_hostshow_value(host, field, con_ssh=None):
    return get_hostshow_values(host, con_ssh, field)[field]


def get_hostshow_values(host, con_ssh=None, *fields):
    """

    Args:
        host:
        con_ssh:
        *fields:

    Returns (dict): {field1: value1, field2: value2, ...}

    """
    table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh))
    rtn = {}
    for field in fields:
        val = table_parser.get_value_two_col_table(table_, field)
        rtn[field] = val
    return rtn


def _wait_for_openstack_cli_enable(con_ssh=None, timeout=30, fail_ok=False):
    cli_enable_end_time = time.time() + timeout
    while True:
        try:
            cli.system('show', ssh_client=con_ssh, timeout=timeout)
            return True
        except Exception as e:
            if time.time() > cli_enable_end_time:
                if fail_ok:
                    LOG.warning("Timed out waiting for cli to enable. \nException: {}".format(e))
                    return False
                raise


def _wait_for_host_states(host, timeout=HostTimeout.REBOOT, check_interval=3, fail_ok=True, con_ssh=None, **states):
    if not states:
        raise ValueError("Expected host state(s) has to be specified via keyword argument states")

    LOG.info("Waiting for {} to reach state(s) - {}".format(host, states))
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh))
        for field, val in states.items():
            actual_val = table_parser.get_value_two_col_table(table_, field)
            if isinstance(val, str):
                val = [val]
            LOG.info("Expected val: {}; Actual val: {}".format(val, actual_val))
            for expected_val in val:
                if actual_val.strip().lower() == expected_val.strip().lower():
                    LOG.info("Host {} has reached {}".format(field, expected_val))
                    break
            else:   # no match found. run system host-show again
                LOG.info("Host {} is {}".format(field, actual_val))
                break
        else:
            LOG.info("{} is in states: {}".format(host, states))
            return True
        time.sleep(check_interval)
    else:
        if fail_ok:
            return False
        raise exceptions.TimeoutException("{} did not reach expected states - {}".format(host, states))


def swact_host(hostname=None, swact_start_timeout=HostTimeout.SWACT, fail_ok=False, con_ssh=None):
    active_host = system_helper.get_active_controller_name(con_ssh=con_ssh)
    if hostname is None:
        hostname = active_host

    exitcode, msg = cli.system('host-swact', hostname, ssh_client=con_ssh, auth_info=Tenant.ADMIN, fail_ok=fail_ok,
                               rtn_list=True)
    if exitcode == 1:
        return [1, msg]

    if hostname != active_host:
        _wait_for_host_states(hostname, timeout=swact_start_timeout, fail_ok=False, con_ssh=con_ssh, task='')
        return [2, "{} is not active controller host, thus swact request failed as expected.".format(hostname)]
    return _wait_for_swact_complete(hostname, con_ssh, swact_start_timeout=swact_start_timeout, fail_ok=fail_ok)


def _wait_for_swact_complete(before_host, con_ssh=None, swact_start_timeout=30, swact_complete_timeout=30,
                             floating_ssh_timeout=30, fail_ok=True):
    """
    Wait for swact to start and complete
    NOTE: This function assumes swact command was run from ssh session using floating ip!!

    Args:
        before_host:
        con_ssh:
        swact_start_timeout:
        swact_complete_timeout:

    Returns:

    """
    start = time.time()
    end_swact_start = start + swact_start_timeout
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    while con_ssh._is_connected(fail_ok=True):
        if time.time() > end_swact_start:
            if fail_ok:
                return [3, "Swact did not start within {}".format(swact_start_timeout)]
            raise exceptions.HostPostCheckFailed("Timed out waiting for swact. SSH to {} is still alive.".
                                                 format(con_ssh.host))
    LOG.info("ssh to {} disconnected, indicating swacting initiated.".format(con_ssh.host))

    con_ssh.connect(retry=True, retry_timeout=floating_ssh_timeout)

    # Give it sometime before openstack cmds enables on after host
    _wait_for_openstack_cli_enable(con_ssh=con_ssh, fail_ok=False)

    after_host = system_helper.get_active_controller_name()
    LOG.info("Host before swacting: {}, host after swacting: {}".format(before_host, after_host))

    if before_host == after_host:
        if fail_ok:
            return [4, "Active controller did not change after swact within {}".format(swact_complete_timeout)]
        raise exceptions.HostPostCheckFailed("Swact failed. Active controller host did not change")

    return [0, '']


def get_good_computes(con_ssh=None):
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    personality = 'compute'
    if system_helper.is_small_footprint(con_ssh):
        personality = 'controller'
    hosts = table_parser.get_values(table_, 'hostname', personality=personality, availability='available',
                                    operational='enabled', administrative='unlocked')
    LOG.debug("Computes that are in good states: {}".format(hosts))
    return hosts

