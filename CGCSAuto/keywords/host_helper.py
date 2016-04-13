import re
import time
from contextlib import contextmanager

from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient, SSHFromSSH
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import HostAavailabilityState, HostAdminState
from consts.timeout import HostTimeout
from keywords import system_helper
from keywords.security_helper import LinuxUser


@contextmanager
def ssh_to_host(hostname, username=None, password=None, prompt=None, con_ssh=None):
    """
    ssh to a host from sshclient.

    Args:
        hostname (str): host to ssh to
        username (str):
        password (str):
        prompt (str):
        con_ssh (SSHClient):

    Returns (SSHClient): ssh client of the host

    Examples: with ssh_to_host('controller-1') as host_ssh:
                  host.exec_cmd(cmd)

    """
    default_user, default_password = LinuxUser.get_current_user_password()
    user = username if username else default_user
    password = password if password else default_password
    if not prompt:
        prompt = '.*' + hostname + '\:~\$'
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    host_ssh = SSHFromSSH(ssh_client=con_ssh, host=hostname, user=user, password=password, initial_prompt=prompt)
    host_ssh.connect()
    current_host = host_ssh.get_hostname()
    if not current_host == hostname:
        raise exceptions.SSHException("Current host is {} instead of {}".format(current_host, hostname))
    try:
        yield host_ssh
    finally:
        if current_host == hostname:
            host_ssh.close()


def reboot_hosts(hostnames, timeout=HostTimeout.REBOOT, con_ssh=None, fail_ok=False):
    """
    Reboot one or multiple host(s)

    Args:
        hostnames (list): list of hostnames to reboot. str input is also acceptable when only one host to be rebooted
        timeout (int): timeout waiting for reboot to complete in seconds
        con_ssh (SSHClient): Active controller ssh
        fail_ok (bool): Whether it is okay or not for rebooting to fail on any host

    Returns (list): [rtn_code, message]
        [0, ''] hosts are successfully rebooted and back to available/degraded or online state.

    """
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
            task_unfinished_msg = "{}{} still in task: {}. ".format(task_unfinished_msg, host, vals['task'])
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
    """

    Args:
        hosts:
        duration:
        con_ssh:
        **states:

    Returns:

    """
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


def lock_host(host, force=False, lock_timeout=HostTimeout.LOCK, timeout=HostTimeout.ONLINE_AFTER_LOCK, con_ssh=None,
              fail_ok=False, check_first=True):
    """
    lock a host.

    Args:
        host (str): hostname or id in string format
        force (bool):
        lock_timeout (int): max time in seconds waiting for host to goto locked state after locking attempt.
        timeout (int): how many seconds to wait for host to go online after lock
        con_ssh (SSHClient):
        fail_ok (bool):
        check_first (bool):

    Returns: [return_code, error_message]  Non-zero return code scenarios only applicable when fail_ok=True
        [0, ''] Successfully locked and host goes online
        [1, stderr] Lock host rejected
        [2, ''] Successfully locked but host did not become become locked within 10 seconds
        [3, ]

    """
    if get_hostshow_value(host, 'availability') in ['offline', 'failed']:
        LOG.warning("Host in offline or failed state!")

    if check_first:
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

    # Wait for task complete. If task stucks, fail the test regardless. Perhaps timeout needs to be increased.
    _wait_for_host_states(host=host, timeout=lock_timeout, task='', fail_ok=False)

    # TODO: Should this considered as fail??
    #  vim_progress_status | Lock of host compute-0 rejected because there are no other hypervisors available.
    if _wait_for_host_states(host=host, timeout=5, vim_progress_status='lock host .* rejected.*',
                             regex=True, fail_ok=True, con_ssh=con_ssh):
        return [4, "Lock host {} is rejected due to no other hypervisor. Details in host-show vim_process_status.".
                format(host)]

    if _wait_for_host_states(host=host, timeout=5, vim_progress_status='Migrate of instance .* from host .* failed.*',
                             regex=True, fail_ok=True, con_ssh=con_ssh):
        return [5, "Lock host {} is rejected due to migrate vm failed. Details in host-show vm_process_status.".
                format(host)]

    if not _wait_for_host_states(host, timeout=10, administrative=HostAdminState.LOCKED, con_ssh=con_ssh):
        if fail_ok:
            return [2, "Host is not in locked state."]
        else:
            raise exceptions.HostPostCheckFailed("Host is not locked.")
    LOG.info("{} is {}locked.".format(host, extra_msg))

    if _wait_for_host_states(host, timeout=timeout, availability='online'):
        # ensure the online status lasts for more than 5 seconds. Sometimes host goes online then offline to reboot..
        time.sleep(5)
        if _wait_for_host_states(host, timeout=timeout, availability='online'):
            return [0, '']

    if fail_ok:
        return [3, "host state is not online"]
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


def _wait_for_host_states(host, timeout=HostTimeout.REBOOT, check_interval=3, strict=True, regex=False, fail_ok=True,
                          con_ssh=None, **states):
    if not states:
        raise ValueError("Expected host state(s) has to be specified via keyword argument states")

    LOG.info("Waiting for {} to reach state(s) - {}".format(host, states))
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh))
        for field, val in states.items():
            actual_val = table_parser.get_value_two_col_table(table_, field)
            LOG.error("Actual_val: {}".format(actual_val))
            actual_val_lower = actual_val.lower()
            if isinstance(val, str):
                val = [val]
            LOG.info("Expected val(s): {}; Actual val: {}".format(val, actual_val))
            for expected_val in val:
                expected_val_lower = expected_val.strip().lower()
                found_match = False
                if regex:
                    if strict:
                        res_ = re.match(expected_val_lower, actual_val_lower)
                    else:
                        res_ = re.search(expected_val_lower, actual_val_lower)
                    if res_:
                        found_match = True
                else:
                    if strict:
                        found_match = actual_val_lower == expected_val_lower
                    else:
                        found_match = actual_val_lower in expected_val_lower

                if found_match:
                    LOG.info("{} {} has reached: {}".format(host, field, actual_val))
                    break
            else:   # no match found. run system host-show again
                LOG.info("{} {} is {}".format(host, field, actual_val))
                break
        else:
            LOG.info("{} is in states: {}".format(host, states))
            return True
        time.sleep(check_interval)
    else:
        msg = "{} did not reach states - {}".format(host, states)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.TimeoutException(msg)


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
        [0,''] if swact complete pass
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


def get_hosts(hosts=None, con_ssh=None, **states):
    """
    Filter out a list of hosts with specified states from given hosts.

    Args:
        hosts (list): list of hostnames to filter out from. If None, all hosts will be considered.
        con_ssh:
        **states: fields that customized a host. for instance avaliability='available', personality='controller'
        will make sure that a list of host that are available and controller to be returned by the function.

    Returns (list):A list of host specificed by the **states

    """
    # get_hosts(availability='available', personality='controller')
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    if hosts:
        table_ = table_parser.filter_table(table_, hostname=hosts)
    return table_parser.get_values(table_, 'hostname', **states)


def get_nova_computes(con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get nova computes listed in nova host-list.

    System: Regular, Small footprint

    Args:
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list):
        List of nova computes
    """

    table_ = table_parser.table(cli.nova('host-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'host_name', service='compute', zone='nova')


def get_hosts_by_storage_aggregate(storage_backing='local_image', con_ssh=None):
    """
    Return a list of hosts that supports the given storage backing.

    System: Regular, Small footprint

    Args:
        storage_backing (str): 'local_image', 'local_lvm', or 'remote'
        con_ssh (SSHClient):

    Returns: (list)
        such as ['compute-0', 'compute-2', 'compute-1', 'compute-3']
        or [] if no host supports this storage backing

    """
    storage_backing = storage_backing.strip().lower()
    if 'image' in storage_backing:
        aggregate = 'local_storage_image_hosts'
    elif 'lvm' in storage_backing:
        aggregate = 'local_storage_lvm_hosts'
    elif 'remote' in storage_backing:
        aggregate = 'remote_storage_hosts'
    else:
        raise ValueError("Invalid storage backing provided. "
                         "Please use one of these: 'local_image', 'local_lvm', 'remote'")

    table_ = table_parser.table(cli.nova('aggregate-details', aggregate, ssh_client=con_ssh,
                                         auth_info=Tenant.ADMIN))
    hosts = table_parser.get_values(table_, 'Hosts', Name=aggregate)[0]
    hosts = hosts.split(',')
    if len(hosts) == 0 or hosts == ['']:
        hosts = []
    else:
        hosts = [eval(host) for host in hosts]

    LOG.info("Hosts with {} backing: {}".format(storage_backing, hosts))
    return hosts


def get_up_hosts_with_storage_backing(storage_backing, con_ssh=None):
    hosts_with_backing = get_hosts_by_storage_aggregate(storage_backing, con_ssh=con_ssh)
    if system_helper.is_small_footprint(controller_ssh=con_ssh):
        up_hosts = get_nova_computes(con_ssh=con_ssh)
    else:
        up_hosts = get_hypervisors(state='up', status='enabled', con_ssh=con_ssh)

    candidate_hosts = list(set(hosts_with_backing) & set(up_hosts))
    return candidate_hosts


def get_hypervisors(state=None, status=None, con_ssh=None):
    """
    Return a list of hypervisors names in specified state and status. If None is set to state and status,
    all hypervisors will be returned.

    System: Regular

    Args:
        state (str): e.g., 'up', 'down'
        status (str): e.g., 'enabled', 'disabled'
        con_ssh (SSHClient):

    Returns (list):
        List of hypervisor names. Return [] if no match found.
        Always return [] for small footprint lab. i.e., do not work with small footprint lab
    """
    table_ = table_parser.table(cli.nova('hypervisor-list', auth_info=Tenant.ADMIN, ssh_client=con_ssh))
    target_header = 'Hypervisor hostname'

    if state is None and status is None:
        return table_parser.get_column(table_, target_header)

    params = {}
    if state is not None:
        params['State'] = state
    if status is not None:
        params['Status'] = status
    return table_parser.get_values(table_, target_header=target_header, **params)