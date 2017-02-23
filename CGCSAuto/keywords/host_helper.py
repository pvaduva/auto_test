import re
import time
from contextlib import contextmanager
from xml.etree import ElementTree

from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient, SSHFromSSH, SSHClient
from utils.tis_log import LOG

from consts.auth import Tenant, SvcCgcsAuto
from consts.cgcs import HostAvailabilityState, HostAdminState, HostOperationalState, Prompt, MELLANOX_DEVICE
from consts.timeout import HostTimeout, CMDTimeout
from consts.build_server import DEFAULT_BUILD_SERVER, BUILD_SERVERS

from keywords import system_helper, common
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
    original_host = con_ssh.get_hostname()

    host_ssh = SSHFromSSH(ssh_client=con_ssh, host=hostname, user=user, password=password, initial_prompt=prompt)
    host_ssh.connect()
    current_host = host_ssh.get_hostname()
    if not current_host == hostname:
        raise exceptions.SSHException("Current host is {} instead of {}".format(current_host, hostname))
    try:
        yield host_ssh
    finally:
        if current_host != original_host:
            host_ssh.close()


def reboot_hosts(hostnames, timeout=HostTimeout.REBOOT, con_ssh=None, fail_ok=False, wait_for_reboot_finish=True,
                 check_hypervisor_up=True, check_webservice_up=True):
    """
    Reboot one or multiple host(s)

    Args:
        hostnames (list|str): hostname(s) to reboot. str input is also acceptable when only one host to be rebooted
        timeout (int): timeout waiting for reboot to complete in seconds
        con_ssh (SSHClient): Active controller ssh
        fail_ok (bool): Whether it is okay or not for rebooting to fail on any host
        wait_for_reboot_finish (bool): whether to wait for reboot finishes before return
        check_hypervisor_up (bool):
        check_webservice_up (bool):

    Returns (tuple): (rtn_code, message)
        (-1, "Reboot host command sent") Reboot host command is sent, but did not wait for host to be back up
        (0, "Host(s) state(s) - <states_dict>.") hosts rebooted and back to available/degraded or online state.
        (1, "Host(s) not in expected availability states or task unfinished. (<states>) (<task>)" )
        (2, "Hosts not up in nova hypervisor-list: <list of hosts>)"
        (3, "Hosts web-services not active in system servicegroup-list")
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

    res, out = cli.system('host-list', rtn_list=True)
    LOG.info('\n{}'.format(out))

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

    if not wait_for_reboot_finish:
        msg = "Reboot hosts command sent."
        LOG.info(msg)
        return -1, msg

    if hostnames:
        time.sleep(30)
        hostnames = sorted(hostnames)
        hosts_in_rebooting = wait_for_hosts_states(
                hostnames, timeout=HostTimeout.FAIL_AFTER_REBOOT, check_interval=10, duration=8, con_ssh=con_ssh,
                availability=[HostAvailabilityState.OFFLINE, HostAvailabilityState.FAILED])

        if not hosts_in_rebooting:
            hosts_info = get_host_show_values_for_hosts(hostnames, ['task', 'availability'], con_ssh=con_ssh)
            raise exceptions.HostError("Some hosts are not rebooting. \nHosts info:{}".format(hosts_info))

    if reboot_con:
        hostnames.append(controller)

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
        locked_hosts_in_states = wait_for_hosts_states(locked_hosts, timeout=HostTimeout.REBOOT, check_interval=10,
                                                       duration=8, con_ssh=con_ssh, availability=['online'])

    if len(unlocked_hosts) > 0:
        unlocked_hosts_in_states = wait_for_hosts_states(unlocked_hosts, timeout=HostTimeout.REBOOT, check_interval=10,
                                                         con_ssh=con_ssh, availability=['available', 'degraded'])

        if unlocked_hosts_in_states:
            hosts_tab = table_parser.table(cli.system('host-list --nowrap', ssh_client=con_ssh))
            hosts_to_check_tab = table_parser.filter_table(hosts_tab, hostname=unlocked_hosts)
            hosts_avail = table_parser.get_values(hosts_to_check_tab, 'hostname',
                                                  availability=HostAvailabilityState.AVAILABLE)

            if hosts_avail and (check_hypervisor_up or check_webservice_up):

                all_nodes = system_helper._get_nodes(con_ssh)
                computes = list(set(hosts_avail) & set(list(all_nodes['computes'])))
                controllers = list(set(hosts_avail) & set(list(all_nodes['controllers'])))
                if system_helper.is_small_footprint(con_ssh):
                    computes += controllers

                if check_hypervisor_up and computes:
                    res, hosts_hypervisordown = wait_for_hypervisors_up(computes, fail_ok=fail_ok, con_ssh=con_ssh,
                                                                        timeout=120)
                    if not res:
                        err_msg = "Hosts not up in nova hypervisor-list: {}".format(hosts_hypervisordown)
                        if fail_ok:
                            return 2, err_msg
                        else:
                            raise exceptions.HostPostCheckFailed(err_msg)

                if check_webservice_up and controllers:
                    res, hosts_webdown = wait_for_webservice_up(controllers, fail_ok=fail_ok, con_ssh=con_ssh,
                                                                timeout=90)
                    if not res:
                        err_msg = "Hosts web-services not active in system servicegroup-list: {}".format(hosts_webdown)
                        if fail_ok:
                            return 3, err_msg
                        else:
                            raise exceptions.HostPostCheckFailed(err_msg)

    states_vals = {}
    task_unfinished_msg = ''
    for host in hostnames:
        vals = get_hostshow_values(host, fields=['task', 'availability'])
        if not vals['task'] == '':
            task_unfinished_msg = ' '.join([task_unfinished_msg, "{} still in task: {}.".format(host, vals['task'])])
        states_vals[host] = vals

    message = "Host(s) state(s) - {}.".format(states_vals)

    if locked_hosts_in_states and unlocked_hosts_in_states and task_unfinished_msg == '':
        succ_msg = "Hosts {} rebooted successfully".format(hostnames)
        LOG.info(succ_msg)
        return 0, succ_msg

    err_msg = "Host(s) not in expected states or task unfinished. " + message + task_unfinished_msg
    if fail_ok:
        LOG.warning(err_msg)
        return 1, err_msg
    else:
        raise exceptions.HostPostCheckFailed(err_msg)


def wait_for_hosts_ready(hosts, con_ssh=None):
    """
    Wait for hosts to be in online state is locked, and available and hypervisor/webservice up if unlocked
    Args:
        hosts:
        con_ssh:

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    expt_online_hosts = get_hosts(hosts, administrative=HostAdminState.LOCKED)
    expt_avail_hosts = get_hosts(hosts, administrative=HostAdminState.LOCKED)

    if expt_online_hosts:
        LOG.info("Wait for hosts to be online: {}".format(hosts))
        wait_for_host_states(hosts, availability=HostAvailabilityState.ONLINE, fail_ok=False)

    if expt_avail_hosts:
        hypervisors = list(set(get_hypervisors()) & set(hosts))
        controllers = list(set(system_helper.get_controllers()) & set(hosts))

        LOG.info("Wait for hosts to be available: {}".format(hosts))
        wait_for_host_states(hosts, availability=HostAvailabilityState.AVAILABLE, fail_ok=False)

        if controllers:
            LOG.info("Wait for webservices up for hosts: {}".format(controllers))
            wait_for_webservice_up(controllers, fail_ok=False, con_ssh=con_ssh, timeout=90)

        if hypervisors:
            LOG.info("Wait for hypervisors up for hosts: {}".format(hypervisors))
            wait_for_hypervisors_up(hypervisors, fail_ok=False, con_ssh=con_ssh, timeout=90)


def get_host_show_values_for_hosts(hostnames, fields, merge_lines=False, con_ssh=None):
    if isinstance(fields, str):
        fields = [fields]

    states_vals = {}
    for host in hostnames:
        vals = get_hostshow_values(host, fields, merge_lines=merge_lines, con_ssh=con_ssh)
        states_vals[host] = vals

    return states_vals


def __hosts_stay_in_states(hosts, duration=10, con_ssh=None, **states):
    """
    Check if hosts stay in specified state(s) for given duration.

    Args:
        hosts (list|str): hostname(s)
        duration (int): duration to check for in seconds
        con_ssh (SSHClient):
        **states: such as availability=[online, available]

    Returns:
        bool: True if host stayed in specified states for given duration; False if host is not in specified states
            anytime in the duration.

    """
    end_time = time.time() + duration
    while time.time() < end_time:
        if not __hosts_in_states(hosts=hosts, con_ssh=con_ssh, **states):
            return False

    return True


def wait_for_hosts_states(hosts, timeout=HostTimeout.REBOOT, check_interval=5, duration=3, con_ssh=None, fail_ok=True,
                          **states):
    """
    Wait for hosts to go in specified states

    Args:
        hosts (str|list):
        timeout (int):
        check_interval (int):
        duration (int): wait for a host to be in given state(s) for at least <duration> seconds
        con_ssh (SSHClient):
        **states: such as availability=[online, available]

    Returns (bool): True if host reaches specified states within timeout, and stays in states for given duration;
            False otherwise

    """
    if not hosts:
        raise ValueError("No host(s) provided to wait for states.")

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
        msg = "Timed out waiting for {} in state(s) - {}".format(hosts, states)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.HostTimeout(msg)


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
              fail_ok=False, check_first=True, swact=False):
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
        swact (bool): whether to check if host is active controller and do a swact before attempt locking

    Returns: (return_code(int), msg(str))   # 1, 2, 3, 4, 5, 6 only returns when fail_ok=True
        (-1, "Host already locked. Do nothing.")
        (0, "Host is locked and in online state."]
        (1, <stderr>)   # Lock host cli rejected
        (2, "Host is not in locked state")  # cli ran okay, but host did not reach locked state within timeout
        (3, "Host did not go online within <timeout> seconds after (force) lock")   # Locked but didn't go online
        (4, "Lock host <host> is rejected. Details in host-show vim_process_status.")
        (5, "Lock host <host> failed due to migrate vm failed. Details in host-show vm_process_status.")
        (6, "Task is not cleared within 180 seconds after host goes online")

    """
    LOG.info("Locking {}...".format(host))
    if get_hostshow_value(host, 'availability') in ['offline', 'failed']:
        LOG.warning("Host in offline or failed state before locking!")

    if check_first:
        admin_state = get_hostshow_value(host, 'administrative', con_ssh=con_ssh)
        if admin_state == 'locked':
            LOG.info("Host already locked. Do nothing.")
            return -1, "Host already locked. Do nothing."

    if swact:
        if is_active_controller(host) and len(system_helper.get_controllers()) > 1:
            LOG.info("{} is active controller, swact first before attempt to lock.")
            swact_host(host, con_ssh=con_ssh)

    positional_arg = host
    extra_msg = ''
    if force:
        positional_arg += ' --force'
        extra_msg = 'force '

    exitcode, output = cli.system('host-lock', positional_arg, ssh_client=con_ssh, fail_ok=fail_ok,
                                  auth_info=Tenant.ADMIN, rtn_list=True)

    if exitcode == 1:
        return 1, output

    # Wait for task complete. If task stucks, fail the test regardless. Perhaps timeout needs to be increased.
    wait_for_host_states(host=host, timeout=lock_timeout, task='', fail_ok=False)

    #  vim_progress_status | Lock of host compute-0 rejected because there are no other hypervisors available.
    if wait_for_host_states(host=host, timeout=5, vim_progress_status='ock .* host .* rejected.*',
                            regex=True, strict=False, fail_ok=True, con_ssh=con_ssh):
        msg = "Lock host {} is rejected. Details in host-show vim_process_status.".format(host)
        if fail_ok:
            return 4, msg
        raise exceptions.HostPostCheckFailed(msg)

    if wait_for_host_states(host=host, timeout=5, vim_progress_status='Migrate of instance .* from host .* failed.*',
                            regex=True, strict=False, fail_ok=True, con_ssh=con_ssh):
        msg = "Lock host {} failed due to migrate vm failed. Details in host-show vm_process_status.".format(host)
        if fail_ok:
            return 5, msg
        exceptions.HostPostCheckFailed(msg)

    if not wait_for_host_states(host, timeout=20, administrative=HostAdminState.LOCKED, con_ssh=con_ssh):
        msg = "Host is not in locked state"
        if fail_ok:
            return 2, msg
        raise exceptions.HostPostCheckFailed(msg)

    LOG.info("{} is {}locked. Waiting for it to go Online...".format(host, extra_msg))

    if wait_for_host_states(host, timeout=timeout, availability='online'):
        # ensure the online status lasts for more than 5 seconds. Sometimes host goes online then offline to reboot..
        time.sleep(5)
        if wait_for_host_states(host, timeout=timeout, availability='online'):
            if wait_for_host_states(host, timeout=HostTimeout.TASK_CLEAR, task=''):
                LOG.info("Host is successfully locked and in online state.")
                return 0, "Host is locked and in online state."
            else:
                msg = "Task is not cleared within {} seconds after host goes online".format(HostTimeout.TASK_CLEAR)
                if fail_ok:
                    LOG.warning(msg)
                    return 6, msg
                raise exceptions.HostPostCheckFailed(msg)

    msg = "Host did not go online within {} seconds after {}lock".format(timeout, extra_msg)
    if fail_ok:
        return 3, msg
    else:
        raise exceptions.HostPostCheckFailed(msg)


def unlock_host(host, timeout=HostTimeout.CONTROLLER_UNLOCK, available_only=False, fail_ok=False, con_ssh=None,
                auth_info=Tenant.ADMIN, check_hypervisor_up=True, check_webservice_up=True, check_subfunc=True):
    """
    Unlock given host
    Args:
        host (str):
        timeout (int): MAX seconds to wait for host to become available or degraded after unlocking
        available_only(bool): if True, wait for host becomes Available after unlock; otherwise wait for either
            Degraded or Available
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        check_hypervisor_up (bool): Whether to check if host is up in nova hypervisor-list
        check_webservice_up (bool): Whether to check if host's web-service is active in system servicegroup-list
        check_subfunc (bool): whether to check subfunction_oper and subfunction_avail for CPE system

    Returns (tuple):  Only -1, 0, 4 senarios will be returned if fail_ok=False
        (-1, "Host already unlocked. Do nothing")
        (0, "Host is unlocked and in available state.")
        (1, <stderr>)   # cli returns stderr. only applicable if fail_ok
        (2, "Host is not in unlocked state")    # only applicable if fail_ok
        (3, "Host state did not change to available or degraded within timeout")    # only applicable if fail_ok
        (4, "Host is in degraded state after unlocked.")    # Only applicable if available_only=False
        (5, "Task is not cleared within 180 seconds after host goes available")        # Applicable if fail_ok
        (6, "Host is not up in nova hypervisor-list")   # Host with compute function only. Applicable if fail_ok
        (7, "Host web-services is not active in system servicegroup-list") # controllers only. Applicable if fail_ok
        (8, "Failed to wait for host to reach Available state after unlocked to Degraded state")    # only applicable if fail_ok and available_only are True
        (9, "Host subfunctions operational and availability are not enable and available system host-show") # CPE only

    """
    LOG.info("Unlocking {}...".format(host))
    if get_hostshow_value(host, 'availability') in [HostAvailabilityState.OFFLINE, HostAvailabilityState.FAILED]:
        LOG.info("Host is offline or failed, waiting for it to go online, available or degraded first...")
        wait_for_host_states(host, availability=[HostAvailabilityState.AVAILABLE, HostAvailabilityState.ONLINE,
                                                 HostAvailabilityState.DEGRADED],
                             fail_ok=False)

    if get_hostshow_value(host, 'administrative', con_ssh=con_ssh) == HostAdminState.UNLOCKED:
        message = "Host already unlocked. Do nothing"
        LOG.info(message)
        return -1, message

    exitcode, output = cli.system('host-unlock', host, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                                  fail_ok=fail_ok, timeout=60)
    if exitcode == 1:
        return 1, output

    if not wait_for_host_states(host, timeout=30, administrative=HostAdminState.UNLOCKED, con_ssh=con_ssh,
                                fail_ok=fail_ok):
        return 2, "Host is not in unlocked state"

    if not wait_for_host_states(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
                                availability=[HostAvailabilityState.AVAILABLE, HostAvailabilityState.DEGRADED]):
        return 3, "Host state did not change to available or degraded within timeout"

    if not wait_for_host_states(host, timeout=HostTimeout.TASK_CLEAR, fail_ok=fail_ok, con_ssh=con_ssh, task=''):
        return 5, "Task is not cleared within {} seconds after host goes available".format(HostTimeout.TASK_CLEAR)

    if get_hostshow_value(host, 'availability') == HostAvailabilityState.DEGRADED:
        if not available_only:
            LOG.warning("Host is in degraded state after unlocked.")
            return 4, "Host is in degraded state after unlocked."
        else:
            if not wait_for_host_states(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
                                        availability=HostAvailabilityState.AVAILABLE):
                err_msg = "Failed to wait for host to reach Available state after unlocked to Degraded state"
                LOG.warning(err_msg)
                return 8, err_msg

    if check_hypervisor_up or check_webservice_up or check_subfunc:

        table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh))

        subfunc = table_parser.get_value_two_col_table(table_, 'subfunctions')
        personality = table_parser.get_value_two_col_table(table_, 'personality')
        string_total = subfunc + personality

        is_controller = 'controller' in string_total
        is_compute = 'compute' in string_total

        if check_hypervisor_up and is_compute:
            if not wait_for_hypervisors_up(host, fail_ok=fail_ok, con_ssh=con_ssh, timeout=120)[0]:
                return 6, "Host is not up in nova hypervisor-list"

        if check_webservice_up and is_controller:
            if not wait_for_webservice_up(host, fail_ok=fail_ok, con_ssh=con_ssh, timeout=300)[0]:
                return 7, "Host web-services is not active in system servicegroup-list"

        if check_subfunc and is_controller and is_compute:
            # wait for subfunction states to be operational enabled and available
            if not wait_for_host_states(host, timeout=90, fail_ok=fail_ok, con_ssh=con_ssh,
                                        subfunction_oper=HostOperationalState.ENABLED,
                                        subfunction_avail=HostAvailabilityState.AVAILABLE):
                err_msg = "Host subfunctions operational and availability did not change to enabled and available" \
                          " within timeout"
                LOG.warning(err_msg)
                return 9, err_msg

    if get_hostshow_value(host, 'availability') == HostAvailabilityState.DEGRADED:
        if not available_only:
            LOG.warning("Host is in degraded state after unlocked.")
            return 4, "Host is in degraded state after unlocked."
        else:
            if not wait_for_host_states(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
                                        availability=HostAvailabilityState.AVAILABLE):
                err_msg = "Failed to wait for host to reach Available state after unlocked to Degraded state"
                LOG.warning(err_msg)
                return 8, err_msg

    LOG.info("Host {} is successfully unlocked and in available state".format(host))
    return 0, "Host is unlocked and in available state."


def unlock_hosts(hosts, timeout=HostTimeout.CONTROLLER_UNLOCK, fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN,
                 check_hypervisor_up=False, check_webservice_up=False):
    """
    Unlock given hosts. Please use unlock_host() keyword if only one host needs to be unlocked.
    Args:
        hosts (list|str): Host(s) to unlock
        timeout (int): MAX seconds to wait for host to become available or degraded after unlocking
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        check_hypervisor_up (bool): Whether to check if host is up in nova hypervisor-list
        check_webservice_up (bool): Whether to check if host's web-service is active in system servicegroup-list


    Returns (dict): {host_0: res_0, host_1: res_1, ...}
        where res is a tuple as below, and scenario 1, 2, 3 only applicable if fail_ok=True
        (-1, "Host already unlocked. Do nothing")
        (0, "Host is unlocked and in available state.")
        (1, <stderr>)
        (2, "Host is not in unlocked state")
        (3, "Host is not in available or degraded state.")
        (4, "Host is in degraded state after unlocked.")
        (5, "Host is not up in nova hypervisor-list")   # Host with compute function only
        (6, "Host web-services is not active in system servicegroup-list") # controllers only

    """
    if not hosts:
        raise ValueError("No host(s) provided to unlock.")

    LOG.info("Unlocking {}...".format(hosts))

    if isinstance(hosts, str):
        hosts = [hosts]

    res = {}
    hosts_to_unlock = list(set(hosts))
    for host in hosts:
        if get_hostshow_value(host, 'administrative', con_ssh=con_ssh) == HostAdminState.UNLOCKED:
            message = "Host already unlocked. Do nothing"

            res[host] = -1, message
            hosts_to_unlock.remove(host)

    if not hosts_to_unlock:
        LOG.info("Host(s) already unlocked. Do nothing.")
        return res

    if len(hosts_to_unlock) != len(hosts):
        LOG.info("Some host(s) already unlocked. Unlocking the rest: {}".format(hosts_to_unlock))

    hosts_to_check = []
    for host in hosts_to_unlock:
        exitcode, output = cli.system('host-unlock', host, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                                      fail_ok=fail_ok, timeout=60)
        if exitcode == 1:
            res[host] = 1, output
        else:
            hosts_to_check.append(host)

    if not wait_for_hosts_states(hosts_to_check, timeout=60, administrative=HostAdminState.UNLOCKED, con_ssh=con_ssh):
        LOG.warning("Some host(s) not in unlocked states after 60 seconds.")

    if not wait_for_hosts_states(hosts_to_check, timeout=timeout, check_interval=10, con_ssh=con_ssh,
                                 availability=[HostAvailabilityState.AVAILABLE, HostAvailabilityState.DEGRADED]):
        LOG.warning("Some host(s) state did not change to available or degraded within timeout")

    hosts_tab = table_parser.table(cli.system('host-list --nowrap', ssh_client=con_ssh))
    hosts_to_check_tab = table_parser.filter_table(hosts_tab, hostname=hosts_to_check)
    hosts_unlocked = table_parser.get_values(hosts_to_check_tab, target_header='hostname', administrative='unlocked')
    hosts_not_unlocked = list(set(hosts_to_check) - set(hosts_unlocked))
    hosts_unlocked_tab = table_parser.filter_table(hosts_to_check_tab, hostname=hosts_unlocked)
    hosts_avail = table_parser.get_values(hosts_unlocked_tab, 'hostname', availability=HostAvailabilityState.AVAILABLE)
    hosts_degrd = table_parser.get_values(hosts_unlocked_tab, 'hostname', availability=HostAvailabilityState.DEGRADED)
    hosts_other = list(set(hosts_unlocked) - set(hosts_avail) - set(hosts_degrd))

    for host in hosts_not_unlocked:
        res[host] = 2, "Host is not in unlocked state."
    for host in hosts_degrd:
        res[host] = 4, "Host is in degraded state after unlocked."
    for host in hosts_other:
        res[host] = 3, "Host is not in available or degraded state."

    if hosts_avail and (check_hypervisor_up or check_webservice_up):

        all_nodes = system_helper._get_nodes(con_ssh)
        computes = list(set(hosts_avail) & set(list(all_nodes['computes'])))
        controllers = list(set(hosts_avail) & set(list(all_nodes['controllers'])))
        if system_helper.is_small_footprint(con_ssh):
            computes += controllers

        if check_hypervisor_up and computes:
            hosts_hypervisordown = wait_for_hypervisors_up(computes, fail_ok=fail_ok, con_ssh=con_ssh, timeout=120)[1]
            for host in hosts_hypervisordown:
                res[host] = 5, "Host is not up in nova hypervisor-list"
                hosts_avail = list(set(hosts_avail) - set(hosts_hypervisordown))

        if check_webservice_up and controllers:
            hosts_webdown = wait_for_webservice_up(controllers, fail_ok=fail_ok, con_ssh=con_ssh, timeout=90)[1]
            for host in hosts_webdown:
                res[host] = 6, "Host web-services is not active in system servicegroup-list"
            hosts_avail = list(set(hosts_avail) - set(hosts_webdown))

    for host in hosts_avail:
        res[host] = 0, "Host is unlocked and in available state."

    if not len(res) == len(hosts):
        raise exceptions.CommonError("Something wrong with the keyword. Number of hosts in result is incorrect.")

    if not fail_ok:
        for host in res:
            if res[host][0] not in [0, 4]:
                raise exceptions.HostPostCheckFailed(" Not all host(s) unlocked successfully. Detail: {}".format(res))

    LOG.info("Results for unlocking hosts: {}".format(res))
    return res


def get_hostshow_value(host, field, merge_lines=False, con_ssh=None):
    """
    Retrieve the value of certain field in the system host-show from get_hostshow_values()

    Examples:
        admin_state = get_hostshow_value(host, 'administrative', con_ssh=con_ssh)
        would return if host is 'locked' or 'unlocked'

    Args:
        host (str): hostname to check for
        field (str): The field of the host-show table
        con_ssh (SSHClient)

    Returns:
        The value of the specified field for given host

    """
    return get_hostshow_values(host, field, merge_lines=merge_lines, con_ssh=con_ssh)[field]


def get_hostshow_values(host, fields, merge_lines=False, con_ssh=None):
    """
    Get values of specified fields for given host

    Args:
        host (str):
        con_ssh (SSHClient):
        *fields: field names

    Returns (dict): {field1: value1, field2: value2, ...}

    """

    table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh))
    if not fields:
        raise ValueError("At least one field name needs to provided via *fields")

    if isinstance(fields, str):
        fields = [fields]

    rtn = {}
    for field in fields:
        val = table_parser.get_value_two_col_table(table_, field, merge_lines=merge_lines)
        rtn[field] = val
    return rtn


def _wait_for_openstack_cli_enable(con_ssh=None, timeout=60, fail_ok=False, check_interval=1):
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
            time.sleep(check_interval)


def wait_for_host_states(host, timeout=HostTimeout.REBOOT, check_interval=3, strict=True, regex=False, fail_ok=True,
                         con_ssh=None, **states):
    if not states:
        raise ValueError("Expected host state(s) has to be specified via keyword argument states")

    LOG.info("Waiting for {} to reach state(s) - {}".format(host, states))
    end_time = time.time() + timeout
    last_vals = {}
    for field in states:
        last_vals[field] = None
    while time.time() < end_time:
        table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh))
        for field, expt_vals in states.items():
            actual_val = table_parser.get_value_two_col_table(table_, field)
            # ['Lock of host compute-0 rejected because instance vm-from-vol-t1 is', 'suspended.']
            if isinstance(actual_val, list):
                actual_val = ' '.join(actual_val)

            actual_val_lower = actual_val.lower()
            if isinstance(expt_vals, str):
                expt_vals = [expt_vals]

            for expected_val in expt_vals:
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
                if last_vals[field] != actual_val_lower:
                    LOG.info("{} {} is {}.".format(host, field, actual_val))
                last_vals[field] = actual_val_lower
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


def swact_host(hostname=None, swact_start_timeout=HostTimeout.SWACT, swact_complete_timeout=HostTimeout.SWACT,
               fail_ok=False, con_ssh=None):
    """
    Swact active controller from given hostname.

    Args:
        hostname (str|None): When None, active controller will be used for swact.
        swact_start_timeout (int): Max time to wait between cli executs and swact starts
        swact_complete_timeout (int): Max time to wait for swact to complete after swact started
        fail_ok (bool):
        con_ssh (SSHClient):

    Returns (tuple): (rtn_code(int), msg(str))      # 1, 3, 4 only returns when fail_ok=True
        (0, "Active controller is successfully swacted.")
        (1, <stderr>)   # swact host cli rejected
        (2, "<hostname> is not active controller host, thus swact request failed as expected.")
        (3, "Swact did not start within <swact_start_timeout>")
        (4, "Active controller did not change after swact within <swact_complete_timeou>")

    """
    active_host = system_helper.get_active_controller_name(con_ssh=con_ssh)
    if hostname is None:
        hostname = active_host

    exitcode, msg = cli.system('host-swact', hostname, ssh_client=con_ssh, auth_info=Tenant.ADMIN, fail_ok=fail_ok,
                               rtn_list=True)
    if exitcode == 1:
        return 1, msg

    if hostname != active_host:
        wait_for_host_states(hostname, timeout=swact_start_timeout, fail_ok=False, con_ssh=con_ssh, task='')
        return 2, "{} is not active controller host, thus swact request failed as expected.".format(hostname)

    rtn = wait_for_swact_complete(hostname, con_ssh, swact_start_timeout=swact_start_timeout,
                                  swact_complete_timeout=swact_complete_timeout, fail_ok=fail_ok)
    if rtn[0] == 0:
        res = wait_for_webservice_up(system_helper.get_active_controller_name(), fail_ok=fail_ok, con_ssh=con_ssh)[0]
        if not res:
            return 5, "Web-services for new controller is not active"

    return rtn


def wait_for_swact_complete(before_host, con_ssh=None, swact_start_timeout=30, swact_complete_timeout=30,
                            floating_ssh_timeout=30, fail_ok=True):
    """
    Wait for swact to start and complete
    NOTE: This function assumes swact command was run from ssh session using floating ip!!

    Args:
        before_host (str): Active controller name before swact request
        con_ssh (SSHClient):
        swact_start_timeout (int): Max time to wait between cli executs and swact starts
        swact_complete_timeout (int): Max time to wait for swact to complete after swact started

    Returns (tuple):
        (0, "Active controller is successfully swacted.")
        (3, "Swact did not start within <swact_start_timeout>")     # returns when fail_ok=True
        (4, "Active controller did not change after swact within <swact_complete_timeou>")  # returns when fail_ok=True

    """
    start = time.time()
    end_swact_start = start + swact_start_timeout
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    while con_ssh._is_connected(fail_ok=True):

        if time.time() > end_swact_start:
            if fail_ok:
                return 3, "Swact did not start within {}".format(swact_start_timeout)
            raise exceptions.HostPostCheckFailed("Timed out waiting for swact. SSH to {} is still alive.".
                                                 format(con_ssh.host))
    LOG.info("ssh to {} disconnected, indicating swacting initiated.".format(con_ssh.host))

    # permission denied is received when ssh right after swact initiated. Add delay to avoid sanity failure
    time.sleep(30)
    con_ssh.connect(retry=True, retry_timeout=floating_ssh_timeout)

    # Give it sometime before openstack cmds enables on after host
    _wait_for_openstack_cli_enable(con_ssh=con_ssh, fail_ok=False)

    after_host = system_helper.get_active_controller_name()
    LOG.info("Host before swacting: {}, host after swacting: {}".format(before_host, after_host))

    if before_host == after_host:
        if fail_ok:
            return 4, "Active controller did not change after swact within {}".format(swact_complete_timeout)
        raise exceptions.HostPostCheckFailed("Swact failed. Active controller host did not change")

    return 0, "Active controller is successfully swacted."


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


def get_nova_hosts(zone='nova', con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get nova hosts listed in nova host-list.

    System: Regular, Small footprint

    Args:
        zone (str): returns only the hosts with specified zone
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): a list of hypervisors in given zone
    """

    table_ = table_parser.table(cli.nova('host-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'host_name', service='compute', zone=zone)


def wait_for_hypervisors_up(hosts, timeout=HostTimeout.HYPERVISOR_UP_AFTER_AVAIL, check_interval=3, fail_ok=False,
                            con_ssh=None):
    """
    Wait for given hypervisors to be up and enabled in nova hypervisor-list
    Args:
        hosts (list|str): names of the hypervisors, such as compute-0
        timeout (int):
        check_interval (int):
        fail_ok (bool):
        con_ssh (SSHClient):

    Returns (tuple): res_bool(bool), hosts_not_up(list)
        (True, [])      # all hypervisors given are up and enabled
        (False, [<hosts_not_up>]    # some hosts are not up and enabled

    """
    if isinstance(hosts, str):
        hosts = [hosts]
    hypervisors = get_hypervisors(con_ssh=con_ssh)

    if not set(hosts) <= set(hypervisors):
        msg = "Some host(s) not in nova hypervisor-list. Host(s) given: {}. Hypervisors: {}".format(hosts, hypervisors)
        raise exceptions.HostPreCheckFailed(msg)

    hosts_to_check = list(hosts)
    LOG.info("Waiting for {} to be up in nova hypervisor-list...".format(hosts))
    end_time = time.time() + timeout
    while time.time() < end_time:
        up_hosts = get_hypervisors(state='up', status='enabled')
        for host in hosts_to_check:
            if host in up_hosts:
                hosts_to_check.remove(host)

        if not hosts_to_check:
            msg = "Host(s) {} are up and enabled in nova hypervisor-list".format(hosts)
            LOG.info(msg)
            return True, hosts_to_check

        time.sleep(check_interval)
    else:
        msg = "Host(s) {} are not up in hypervisor-list within timeout".format(hosts_to_check)
        if fail_ok:
            LOG.warning(msg)
            return False, hosts_to_check
        raise exceptions.HostTimeout(msg)


def wait_for_hosts_in_nova_compute(hosts, timeout=90, check_interval=3, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):

    if isinstance(hosts, str):
        hosts = [hosts]

    hosts_to_check = list(hosts)
    LOG.info("Waiting for {} to be shown in nova host-list...".format(hosts))
    end_time = time.time() + timeout
    while time.time() < end_time:
        hosts_in_nova = get_nova_hosts(con_ssh=con_ssh, auth_info=auth_info)

        for host in hosts:
            if host in hosts_in_nova:
                hosts_to_check.remove(host)

        if not hosts_to_check:
            msg = "Host(s) {} appeared in nova host-list".format(hosts)
            LOG.info(msg)
            return True, hosts_to_check

        time.sleep(check_interval)
    else:
        msg = "Host(s) {} did not shown in nova host-list within timeout".format(hosts_to_check)
        if fail_ok:
            LOG.warning(msg)
            return False, hosts_to_check
        raise exceptions.HostTimeout(msg)


def wait_for_webservice_up(hosts, timeout=90, check_interval=3, fail_ok=False, con_ssh=None):

    if isinstance(hosts, str):
        hosts = [hosts]

    hosts_to_check = list(hosts)
    LOG.info("Waiting for {} to be active for web-service in system servicegroup-list...".format(hosts))
    end_time = time.time() + timeout

    while time.time() < end_time:

        table_ = table_parser.table(cli.system('servicegroup-list', ssh_client=con_ssh))
        table_ = table_parser.filter_table(table_, service_group_name='web-services')
        # need to check for strict True because 'go-active' state is not 'active' state
        active_hosts = table_parser.get_values(table_, 'hostname', state='active', strict=True)

        for host in hosts:
            if host in active_hosts:
                hosts_to_check.remove(host)

        if not hosts_to_check:
            msg = "Host(s) {} are active for web-service in system servicegroup-list".format(hosts)
            LOG.info(msg)
            return True, hosts_to_check

        time.sleep(check_interval)
    else:
        msg = "Host(s) {} are not active for web-service in system servicegroup-list within timeout".format(hosts_to_check)
        if fail_ok:
            LOG.warning(msg)
            return False, hosts_to_check
        raise exceptions.HostTimeout(msg)


def get_hosts_in_aggregate(aggregate, con_ssh=None):
    aggregates_tab = table_parser.table(cli.nova('aggregate-list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    avail_aggregates = table_parser.get_column(aggregates_tab, 'Name')
    if aggregate not in avail_aggregates:
        LOG.warning("Requested aggregate {} is not in nova aggregate-list".format(aggregate))
        return []

    table_ = table_parser.table(cli.nova('aggregate-details', aggregate, ssh_client=con_ssh,
                                         auth_info=Tenant.ADMIN))
    hosts = table_parser.get_values(table_, 'Hosts', Name=aggregate)[0]
    hosts = hosts.split(',')
    if len(hosts) == 0 or hosts == ['']:
        hosts = []
    else:
        hosts = [eval(host) for host in hosts]

    LOG.info("Hosts in {} aggregate: {}".format(aggregate, hosts))
    return hosts


def get_hosts_by_storage_aggregate(storage_backing='local_image', con_ssh=None):
    """
    Return a list of hosts that supports the given storage backing.

    System: Regular, Small footprint

    Args:
        storage_backing (str): 'local_image', 'local_lvm', or 'remote'
        con_ssh (SSHClient):

    Returns (tuple):
        such as ('compute-0', 'compute-2', 'compute-1', 'compute-3')
        or () if no host supports this storage backing

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

    hosts = get_hosts_in_aggregate(aggregate, con_ssh=con_ssh)

    LOG.info("Hosts with {} backing: {}".format(storage_backing, hosts))
    return hosts


def get_nova_hosts_with_storage_backing(storage_backing, con_ssh=None):
    hosts_with_backing = get_hosts_by_storage_aggregate(storage_backing, con_ssh=con_ssh)
    up_hosts = get_up_hypervisors(con_ssh=con_ssh)

    candidate_hosts = tuple(set(hosts_with_backing) & set(up_hosts))
    return candidate_hosts


def get_nova_host_with_min_or_max_vms(rtn_max=True, hosts=None, con_ssh=None):
    """
    Get name of a compute host with least of most vms.

    Args:
        rtn_max (bool): when True, return hostname with the most number of vms on it; otherwise return hostname with
            least number of vms on it.
        hosts (list): choose from given hosts. If set to None, choose from all up hypervisors
        con_ssh (SSHClient):

    Returns (str): hostname

    """
    hosts_to_check = get_hypervisors(state='up', status='enabled', con_ssh=con_ssh)
    if hosts:
        if isinstance(hosts, str):
            hosts = [hosts]
        hosts_to_check = list(set(hosts_to_check) & set(hosts))

    table_ = system_helper.get_vm_topology_tables('computes')[0]

    vms_nums = [int(table_parser.get_values(table_, 'servers', Host=host)[0]) for host in hosts_to_check]

    if rtn_max:
        index = vms_nums.index(max(vms_nums))
    else:
        index = vms_nums.index(min(vms_nums))

    return hosts_to_check[index]


def get_up_hypervisors(con_ssh=None):
    return get_hypervisors(state='up', status='enabled', con_ssh=con_ssh)


def get_hypervisors(state=None, status=None, con_ssh=None):
    """
    Return a list of hypervisors names in specified state and status. If None is set to state and status,
    all hypervisors will be returned.

    System: Regular

    Args:
        state (str): e.g., 'up', 'down'
        status (str): e.g., 'enabled', 'disabled'
        con_ssh (SSHClient):

    Returns (list): a list of hypervisor names. Return () if no match found.
        Always return () for small footprint lab. i.e., do not work with small footprint lab
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


def _get_element_tree_virsh_xmldump(instance_name, host_ssh):
    code, output = host_ssh.exec_sudo_cmd(cmd='virsh dumpxml {}'.format(instance_name))
    if not 0 == code:
        raise exceptions.SSHExecCommandFailed("virsh dumpxml failed to execute.")

    element_tree = ElementTree.fromstring(output)
    return element_tree


def get_values_virsh_xmldump(instance_name, host_ssh, tag_path, target_type='element'):
    """

    Args:
        instance_name (str): instance_name of a vm. Such as 'instance-00000002'
        host_ssh (SSHFromSSH): ssh of the host that hosting the given instance
        tag_path (str): the tag path to reach to the target element. such as 'memoryBacking/hugepages/page'
        target_type (str): 'element', 'dict', 'text'

    Returns (list): list of Elements, dictionaries, or strings based on the target_type param.

    """
    target_type = target_type.lower().strip()
    root_element = _get_element_tree_virsh_xmldump(instance_name, host_ssh)
    elements = root_element.findall(tag_path)

    if 'dict' in target_type:
        dics = []
        for element in elements:
            dics.append(element.attrib)
        return dics

    elif 'text' in target_type:
        texts = []
        for element in elements:
            text_list = element.itertext()
            if not text_list:
                LOG.warning("No text found under tag: {}.".format(tag_path))
            else:
                texts.append(text_list[0])
                if len(text_list) > 1:
                    LOG.warning(("More than one text found under tag: {}, returning the first one.".format(tag_path)))

        return texts

    else:
        return elements


def modify_host_cpu(host, function, timeout=CMDTimeout.HOST_CPU_MODIFY, fail_ok=False, con_ssh=None,
                    auth_info=Tenant.ADMIN, **kwargs):
    """
    Modify host cpu to given key-value pairs. i.e., system host-cpu-modify -f <function> -p<id> <num of cores> <host>
    Notes: This assumes given host is already locked.

    Args:
        host (str): hostname of host to be modified
        function (str): cpu function to modify. e.g., 'shared'
        timeout (int): Timeout waiting for system host-cpu-modify cli to return
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        **kwargs: processor id and number of cores pair(s). e.g., p0=1, p1=1

    Returns (tuple): (rtn_code(int), message(str))
        (0, "Host cpu function modified successfully")
        (1, <stderr>)   # cli rejected
        (2, "Number of actual log_cores for <proc_id> is different than number set. Actual: <num>, expect: <num>")

    """
    LOG.info("Modifying host {} CPU function {} to {}".format(host, function, kwargs))

    if not kwargs:
        raise ValueError("At least one key-value pair such as p0=1 has to be provided.")

    final_args = {}
    proc_args = ''
    for proc, cores in kwargs.items():
        if cores is not None:
            final_args[proc] = cores
            cores = str(cores)
            proc_args = ' '.join([proc_args, '-'+proc.lower().strip(), cores])

    if not final_args:
        raise ValueError("cores values cannot be all None")

    if not proc_args:
        raise ValueError("At least one key-value pair should have non-None value. e.g., p1=2")

    subcmd = ' '.join(['host-cpu-modify', '-f', function.lower().strip(), proc_args])
    code, output = cli.system(subcmd, host, fail_ok=fail_ok, ssh_client=con_ssh, auth_info=auth_info, timeout=timeout,
                              rtn_list=True)

    if code == 1:
        return 1, output

    LOG.info("Post action check for host-cpu-modify...")
    table_ = table_parser.table(output)
    table_ = table_parser.filter_table(table_, assigned_function=function)

    threads = get_host_threads_count(host, con_ssh=con_ssh)

    for proc, num in final_args.items():
        num = int(num)
        proc_id = re.findall('\d+', proc)[0]
        expt_cores = threads*num
        actual_cores = len(table_parser.get_values(table_, 'log_core', processor=proc_id))
        if expt_cores != actual_cores:
            msg = "Number of actual log_cores for {} is different than number set. Actual: {}, expect: {}". \
                format(proc, actual_cores, expt_cores)
            if fail_ok:
                LOG.warning(msg)
                return 2, msg
            raise exceptions.HostPostCheckFailed(msg)

    msg = "Host cpu function modified successfully"
    LOG.info(msg)
    return 0, msg


def compare_host_to_cpuprofile(host, profile_uuid, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Compares the cpu function assignments of a host and a cpu profile.

    Args:
        host (str): name of host
        profile_uuid (str): name or uuid of the cpu profile
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (rtn_code(int), message(str))
        (0, "The host and cpu profile have the same information")
        (2, "The function of one of the cores has not been changed correctly: <core number>")

    """
    if not host or not profile_uuid:
        raise ValueError("There is either no host or no cpu profile given.")

    def check_range(core_group, core_num):
        group = []
        if isinstance(core_group, str):
            group.append(core_group)
        elif isinstance(core_group, list):
            for proc in core_group:
                group.append(proc)

        for processors in group:
            parts = processors.split(' ')
            cores = parts[len(parts) - 1]
            ranges = cores.split(',')
            for range in ranges:
                if range == '':
                    continue
                range = range.split('-')
                if len(range) == 2:
                    if int(range[0]) <= int(core_num) <= int(range[1]):
                        return True
                elif len(range) == 1:
                    if int(range[0]) == int(core_num):
                        return True
        LOG.warn("Could not match {} in {}".format(core_num, core_group))
        return False

    table_ = table_parser.table(cli.system('host-cpu-list', host))
    functions = table_parser.get_column(table_=table_, header='assigned_function')

    table_ = table_parser.table(cli.system('cpuprofile-show', profile_uuid))

    platform_cores = table_parser.get_value_two_col_table(table_, field='platform cores')
    vswitch_cores = table_parser.get_value_two_col_table(table_, field='vswitch cores')
    shared_cores = table_parser.get_value_two_col_table(table_, field='shared cores')
    vm_cores = table_parser.get_value_two_col_table(table_, field='vm cores')

    msg = "The function of one of the cores has not been changed correctly: "

    for i in range(0, len(functions)):
        if functions[i] == 'Platform':
            if not check_range(platform_cores, i):
                LOG.warning(msg + str(i))
                return 2, msg + str(i)
        elif functions[i] == 'vSwitch':
            if not check_range(vswitch_cores, i):
                LOG.warning(msg + str(i))
                return 2, msg + str(i)
        elif functions[i] == 'Shared':
            if not check_range(shared_cores, i):
                LOG.warning(msg + str(i))
                return 2, msg + str(i)
        elif functions[i] == 'VMs':
            if not check_range(vm_cores, i):
                LOG.warning(msg + str(i))
                return 2, msg + str(i)

    msg = "The host and cpu profile have the same information"
    return 0, msg


def apply_cpu_profile(host, profile_uuid, timeout=CMDTimeout.CPU_PROFILE_APPLY, fail_ok=False, con_ssh=None,
                    auth_info=Tenant.ADMIN):
    """
    Apply the given cpu profile to the host.
    Assumes the host is already locked.

    Args:
        host (str): name of host
        profile_uuid (str): name or uuid of the cpu profile
        timeout (int): timeout to wait for cli to return
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (rtn_code(int), message(str))
        (0, "cpu profile applied successfully")
        (1, <stderr>)   # cli rejected
        (2, "The function of one of the cores has not been changed correctly: <core number>")
    """
    if not host or not profile_uuid:
        raise ValueError("There is either no host or no cpu profile given.")

    LOG.info("Applying cpu profile: {} to host: {}".format(profile_uuid, host))

    code, output = cli.system('host-apply-cpuprofile', '{} {}'.format(host, profile_uuid), fail_ok=fail_ok,
                              ssh_client=con_ssh, auth_info=auth_info, timeout=timeout, rtn_list=True)

    if 1 == code:
        LOG.warning(output)
        return 1, output

    LOG.info("Post action host-apply-cpuprofile")
    res, out = compare_host_to_cpuprofile(host, profile_uuid)

    if res != 0:
        LOG.warning(output)
        return res, out

    success_msg = "cpu profile applied successfully"
    LOG.info(success_msg)
    return 0, success_msg


def get_host_cpu_cores_for_function(hostname, function='vSwitch', core_type='log_core', thread=0, con_ssh=None,
                                    auth_info=Tenant.ADMIN):
    """
    Get processor/logical cpu cores/per processor on thread 0 for given function for host via system host-cpu-list

    Args:
        hostname (str): hostname to pass to system host-cpu-list
        function (str): such as 'Platform', 'vSwitch', or 'VMs'
        core_type (str): 'phy_core' or 'log_core'
        thread (int): thread number. 0 or 1
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (dict): format: {<proc_id> (int): <log_cores> (list), ...}
        e.g., {0: [1, 2], 1: [21, 22]}

    """
    table_ = table_parser.table(cli.system('host-cpu-list', hostname, ssh_client=con_ssh, auth_info=auth_info))
    procs = list(set(table_parser.get_values(table_, 'processor', thread=thread)))
    res_dict = {}
    print(table_parser.get_values(table_, core_type, assigned_function=function))

    for proc in procs:
        cores = table_parser.get_values(table_, core_type, processor=proc, assigned_function=function, thread=thread)
        res_dict[int(proc)] = sorted([int(item) for item in cores])

    LOG.info("{} {} {}s per processor on thread {}: {}".format(hostname, function, core_type, thread, res_dict))
    return res_dict


def get_logcores_counts(host, proc_ids=(0, 1), thread='0', functions=None, con_ssh=None):
    """
    Get number of logical cores on given processor on thread 0.

    Args:
        host:
        proc_ids:
        thread:
        con_ssh:

    Returns (dict):

    """
    table_ = table_parser.table(cli.system('host-cpu-list', host, ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, thread=thread)

    rtns = []
    kwargs = {}
    if functions:
        kwargs = {'assigned_function': functions}

    for i in proc_ids:
        cores_on_proc = table_parser.get_values(table_, 'log_core', processor=str(i), **kwargs)
        LOG.info("Cores on proc {}: {}".format(i, cores_on_proc))
        rtns.append(len(cores_on_proc))

    return rtns


def get_host_threads_count(host, con_ssh=None):
    """
    Return number of threads for specific host.
    Notes: when hyperthreading is disabled, the number is usually 1; when enabled, the number is usually 2.

    Args:
        host (str): hostname
        con_ssh (SSHClient):

    Returns (int): number of threads

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    code, output = con_ssh.exec_cmd('''vm-topology -s topology | grep --color='never' "{}.*Threads/Core="'''.
                                    format(host))
    if code != 0:
        raise exceptions.SSHExecCommandFailed("CMD stderr: {}".format(output))

    pattern = "Threads/Core=(\d),"
    return int(re.findall(pattern, output)[0])


def get_host_procs(hostname, con_ssh=None):
    table_ = table_parser.table(cli.system('host-cpu-list', hostname, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    procs = table_parser.get_column(table_, 'processor')
    return sorted(set(procs))


def get_vswitch_port_engine_map(host_ssh):
    """
    Get vswitch cores mapping on host from /etc/vswitch/vswitch.ini

    Args:
        host_ssh (SSHClient): ssh of a nova host

    Notes: assume the output format will be: 'port-map="0:1,2 1:12,13"', 'port-map="0,1:1,2"', or 'port-map="0:1,2"'

    Returns (dict): format: {<proc_id> (str): <log_cores> (list), ...}
        e.g., {'0': ['1', '2'], '1': ['1', '2']}

    """
    output = host_ssh.exec_cmd('''grep --color='never' "^port-map=" /etc/vswitch/vswitch.ini''', fail_ok=False)[1]

    host_vswitch_map = eval(output.split(sep='=')[1].strip())
    host_vswitch_map_list = host_vswitch_map.split(sep=' ')

    host_vswitch_dict = {}
    for ports_maps in host_vswitch_map_list:
        ports_str, cores_str = ports_maps.split(sep=':')
        ports = ports_str.split(',')
        cores = cores_str.split(',')
        for port in ports:
            host_vswitch_dict[port] = sorted(int(item) for item in cores)

    LOG.info("ports/cores mapping on {} is: {}".format(host_ssh.get_hostname(), host_vswitch_dict))
    return host_vswitch_dict


def get_expected_vswitch_port_engine_map(host_ssh):
    """
    Get expected ports and vswitch cores mapping via vshell port-list and vshell engine-list

    Args:
        host_ssh (SSHClient): ssh of a nova host

    Returns (dict): format: {<proc_id> (str): <log_cores> (list), ...}
        e.g., {'0': ['1', '2'], '1': ['1', '2']}

    """
    ports_tab = table_parser.table(host_ssh.exec_cmd("vshell port-list", fail_ok=False)[1])
    ports_tab = table_parser.filter_table(ports_tab, type='physical')

    cores_tab = table_parser.table(host_ssh.exec_cmd("vshell engine-list", fail_ok=False)[1])

    header = 'socket' if 'socket' in ports_tab['headers'] else 'socket-id'
    sockets_for_ports = sorted(int(item) for item in list(set(table_parser.get_column(ports_tab, header))))
    sockets_for_cores = sorted(int(item) for item in list(set(table_parser.get_column(cores_tab, 'socket-id'))))
    expt_map = {}
    if sockets_for_ports == sockets_for_cores:
        for socket in sockets_for_ports:
            soc_ports = table_parser.get_values(ports_tab, 'id', **{header: str(socket)})
            soc_cores = sorted(int(item) for item in table_parser.get_values(cores_tab, 'cpuid',
                                                                             **{'socket-id': str(socket)}))
            for port in soc_ports:
                expt_map[port] = soc_cores

    else:
        all_ports = table_parser.get_column(ports_tab, 'id')
        all_cores = sorted(int(item) for item in table_parser.get_column(cores_tab, 'cpuid'))
        for port in all_ports:
            expt_map[port] = all_cores

    return expt_map


def get_local_storage_backing(host, con_ssh=None):
    table_ = table_parser.table(cli.system('host-lvg-show', host + ' nova-local', ssh_client=con_ssh))
    return eval(table_parser.get_value_two_col_table(table_, 'parameters'))['instance_backing']


def check_host_local_backing_type(host, storage_type='image', con_ssh=None):
    backing_storage_types = get_local_storage_backing(host, con_ssh=con_ssh).lower()
    LOG.debug('host:{} supports local-storage types:{}'.format(host, backing_storage_types))
    if storage_type not in backing_storage_types:
        return False

    return True


def modify_host_lvg(host, lvm='nova-local', inst_backing=None, inst_lv_size=None, concurrent_ops=None, lock=True,
                    unlock=True, fail_ok=False, check_first=True, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Modify host lvg

    Args:
        host (str): host to modify lvg for
        lvm (str): local volume group name. nova-local by default
        inst_backing (str): image, lvm, or remote
        inst_lv_size (int): instance lv size in MiB
        concurrent_ops (int): number of current disk operations
        lock (bool): whether or not to lock host before modify
        unlock (bool): whether or not to unlock host and verify config after modify
        fail_ok (bool): whether or not raise exception if host-lvg-modify cli got rejected
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple):
        (0, "Host is configured")       host configured
        (1, <stderr>)
        (2, )

    """

    if inst_backing is not None:
        if 'image' in inst_backing:
            inst_backing = 'image'
        elif 'lvm' in inst_backing:
            inst_backing = 'lvm'
            # if inst_lv_size is None:
            #     raise ValueError("Instance local volume size has to be provided when instance backing is 'lvm'")
        elif 'remote' in inst_backing:
            inst_backing = 'remote'
        else:
            raise ValueError("Invalid instance backing provided. Choose from: image, lvm, remote.")

    def check_host_config(lvg_tab=None):
        err_msg = ''
        if lvg_tab is None:
            lvg_tab = table_parser.table(cli.system('host-lvg-show', '{} {}'.format(host, lvm), ssh_client=con_ssh))

        if inst_backing is not None:
            post_inst_backing = eval(table_parser.get_value_two_col_table(lvg_tab, 'parameters'))['instance_backing']
            if inst_backing != post_inst_backing:
                err_msg += "Instance backing is {} instead of {}\n".format(post_inst_backing, inst_backing)

        if inst_lv_size is not None:
            post_inst_lv_size = int(table_parser.get_value_two_col_table(lvg_tab, 'lvm_vg_size'))
            if int(inst_lv_size) != post_inst_lv_size:
                err_msg += "Instance local volume size is {} instead of {}\n".format(post_inst_lv_size, inst_lv_size)

        if concurrent_ops is not None:
            post_concurrent_ops = eval(table_parser.get_value_two_col_table(lvg_tab, 'parameters'))[
                'concurrent_disk_operations']

            if int(concurrent_ops) != post_concurrent_ops:
                err_msg += "Concurrent disk operations is {} instead of {}".format(post_concurrent_ops,
                                                                                   concurrent_ops)
        return err_msg

    args_dict = {
        '--instance_backing': inst_backing,
        '--instances_lv_size_mib': inst_lv_size,
        '--concurrent_disk_operations': concurrent_ops
    }
    args = ''

    for key, val in args_dict.items():
        if val is not None:
            args += ' {} {}'.format(key, val)

    if not args:
        raise ValueError("At least one of the values should be supplied: inst_backing, inst_lv_size, concurrent_ops'")

    args += ' {} {}'.format(host, lvm)

    if check_first:
        pre_check_err = check_host_config()
        if not pre_check_err:
            msg = "Host already configured with requested lvg values. Do nothing."
            LOG.info(msg)
            return -1, msg

    if lock:
        lock_host(host, con_ssh=con_ssh, swact=True)

    LOG.info("Modifying host-lvg for {} with params: {}".format(host, args))
    code, output = cli.system('host-lvg-modify', args, fail_ok=fail_ok, rtn_list=True, auth_info=auth_info,
                              ssh_client=con_ssh)

    def check_host_config(lvg_tab=None):
        err_msg = ''
        if lvg_tab is None:
            lvg_tab = table_parser.table(cli.system('host-lvg-show', '{} {}'.format(host, lvm), ssh_client=con_ssh))

        if inst_backing is not None:
            post_inst_backing = eval(table_parser.get_value_two_col_table(lvg_tab, 'parameters'))['instance_backing']
            if inst_backing != post_inst_backing:
                err_msg += "Instance backing is {} instead of {}\n".format(post_inst_backing, inst_backing)

        if inst_lv_size is not None:
            post_inst_lv_size = int(table_parser.get_value_two_col_table(lvg_tab, 'lvm_vg_size'))
            if int(inst_lv_size) != post_inst_lv_size:
                err_msg += "Instance local volume size is {} instead of {}\n".format(post_inst_lv_size, inst_lv_size)

        if concurrent_ops is not None:
            post_concurrent_ops = eval(table_parser.get_value_two_col_table(lvg_tab, 'parameters'))[
                'concurrent_disk_operations']

            if int(concurrent_ops) != post_concurrent_ops:
                err_msg += "Concurrent disk operations is {} instead of {}".format(post_concurrent_ops,
                                                                                   concurrent_ops)
        return err_msg

    err = ''
    if code == 0:
        err = check_host_config(table_parser.table(output))
        if err:
            err = "host-lvg-modify output check failed. " + err
            rtn_code = 2

    if unlock:
        unlock_host(host, con_ssh=con_ssh)

        if not err:
            LOG.info("Checking host lvg configurations are applied correctly after host unlock")
            err = check_host_config()
            if err:
                err = "Host lvg config check failed after host unlock. " + err
                rtn_code = 3

    if code == 1:
        return 1, output

    if err:
        if fail_ok:
            LOG.warning(err)
            return rtn_code, err
        else:
            raise exceptions.HostPostCheckFailed(err)

    return 0, "Host is configured successfully"


def set_host_storage_backing(host, inst_backing, lvm='nova-local', lock=True, unlock=True, wait_for_host_aggregate=True,
                             fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """

    Args:
        host (str): host to modify lvg for
        lvm (str): local volume group name. nova-local by default
        inst_backing (str): image, lvm, or remote
        wait_for_host_aggregate (bool): Whether or not wait for host to appear in host-aggregate for specified backing
        lock (bool): whether or not to lock host before modify
        unlock (bool): whether or not to unlock host and verify config after modify
        fail_ok (bool): whether or not raise exception if host-lvg-modify cli got rejected
        auth_info (dict):
        con_ssh (SSHClient):

    Returns:

    """
    if wait_for_host_aggregate and not unlock:
        raise ValueError("'wait_for_host_aggregate=True' requires 'unlock=True'")

    code, output = modify_host_lvg(host, lvm=lvm, inst_backing=inst_backing, lock=lock, unlock=unlock, fail_ok=fail_ok,
                                   auth_info=auth_info, con_ssh=con_ssh)
    if code > 0:
        return code, output

    if wait_for_host_aggregate:
        res = wait_for_host_in_aggregate(host=host, storage_backing=inst_backing, fail_ok=fail_ok)
        if not res:
            err = "Host {} did not appear in {} host-aggregate within timeout".format(host, inst_backing)
            return 4, err

    return 0, "{} storage backing is successfully set to {}".format(host, inst_backing)


def wait_for_host_in_aggregate(host, storage_backing, timeout=120, check_interval=3, fail_ok=False, con_ssh=None):

    endtime = time.time() + timeout
    while time.time() < endtime:
        hosts_with_backing = get_hosts_by_storage_aggregate(storage_backing=storage_backing, con_ssh=con_ssh)
        if host in hosts_with_backing:
            LOG.info("{} appeared in host-aggregate for {} backing".format(host, storage_backing))
            return True

        time.sleep(check_interval)

    err_msg = "Timed out waiting for {} to appear in {} host-aggregate".format(host, storage_backing)
    if fail_ok:
        LOG.warning(err_msg)
        return False
    else:
        raise exceptions.HostError(err_msg)

def is_host_local_image_backing(host, con_ssh=None):
    return check_host_local_backing_type(host, storage_type='image', con_ssh=con_ssh)


def is_host_local_lvm_backing(host, con_ssh=None):
    return check_host_local_backing_type(host, storage_type='lvm', con_ssh=con_ssh)

# Remove unused keywords for now, Kate has reported these are not working properly
# def check_lab_local_backing_type(storage_type=None, con_ssh=None):
#     hypervisors = get_hypervisors(state='up', status='enabled', con_ssh=con_ssh)
#     if not hypervisors:
#         return False
#
#     for hypervisor in hypervisors:
#         if check_host_local_backing_type(hypervisor, storage_type=storage_type):
#             return True
#
#     return False
#
#
# def has_local_image_backing(con_ssh=None):
#     if check_lab_local_backing_type('image'):
#         return True
#
#     return False
#
#
# def has_local_lvm_backing(con_ssh=None):
#     if check_lab_local_backing_type('lvm'):
#         return True
#
#     return False


def get_hosts_with_local_storage_backing_type(storage_type=None, con_ssh=None):
    hosts = []
    for h in get_hypervisors(state='up', status='enabled', con_ssh=con_ssh):
        if check_host_local_backing_type(h, storage_type=storage_type, con_ssh=con_ssh):
            hosts.append(h)
    return hosts


def __parse_total_cpus(output):
    last_line = output.split()[-1]
    # Total usable vcpus: 64.0, total allocated vcpus: 56.0 >> 56.0000
    total = round(float(last_line.split(sep=':')[-1].strip()), 4)
    return total


def get_total_allocated_vcpus_in_log(host, con_ssh=None):
    """

    Args:
        host:
        con_ssh:

    Returns (float): float with 4 digits after decimal point

    """
    with ssh_to_host(host, con_ssh=con_ssh) as host_ssh:
        output = host_ssh.exec_cmd('cat /var/log/nova/nova-compute.log | grep -i "total allocated vcpus" | tail -n 3',
                                   fail_ok=False)[1]
        total_allocated_vcpus = __parse_total_cpus(output)
        return total_allocated_vcpus


def wait_for_total_allocated_vcpus_update_in_log(host_ssh, prev_cpus=None, expt_cpus=None, timeout=60, fail_ok=False):
    """
    Wait for total allocated vcpus in nova-compute.log gets updated to a value that is different than given value

    Args:
        host_ssh (SSHFromSSH):
        prev_cpus (list):
        timeout (int):
        fail_ok (bool): whether to raise exception when allocated vcpus number did not change

    Returns (float): New value of total allocated vcpus as float with 4 digits after decimal point

    """
    cmd = 'cat /var/log/nova/nova-compute.log | grep -i "total allocated vcpus" | tail -n 3'

    end_time = time.time() + timeout
    if prev_cpus is None and expt_cpus is None:
        prev_output = host_ssh.exec_cmd(cmd, fail_ok=False)[1]
        prev_cpus = __parse_total_cpus(prev_output)

    # convert to str
    if prev_cpus:
        prev_cpus = round(prev_cpus, 4)

    while time.time() < end_time:
        output = host_ssh.exec_cmd(cmd, fail_ok=False)[1]
        allocated_cpus = __parse_total_cpus(output)
        if expt_cpus is not None:
            if allocated_cpus == expt_cpus:
                return expt_cpus

        elif allocated_cpus != prev_cpus:
            return allocated_cpus
    else:
        msg = "Total allocated vcpus is not updated within timeout in nova-compute.log"
        if fail_ok:
            LOG.warning(msg)
            return prev_cpus
        raise exceptions.HostTimeout(msg)


def get_vcpus_for_computes(hosts=None, rtn_val='used_now', con_ssh=None):
    """

    Args:
        hosts:
        rtn_val (str): valid values: used_now, used_max, total
        con_ssh:

    Returns (dict): host(str),cpu_val(float with 4 digits after decimal point) pairs as dictionary

    """
    if hosts is None:
        hosts = get_nova_hosts(con_ssh=con_ssh)
    elif isinstance(hosts, str):
        hosts = [hosts]

    hosts_cpus = {}
    for host in hosts:
        table_ = table_parser.table(cli.nova('host-describe', host, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
        cpus_str = table_parser.get_values(table_, target_header='cpu', strict=False, PROJECT=rtn_val)[0]
        hosts_cpus[host] = round(float(cpus_str), 4)

    LOG.debug("Hosts {} cpus: {}".format(rtn_val, hosts_cpus))
    return hosts_cpus


def _get_host_logcores_per_thread(host, con_ssh=None):
    table_ = table_parser.table(cli.system('host-cpu-list', host, ssh_client=con_ssh))
    threads = list(set(table_parser.get_column(table_, 'thread')))
    cores_per_thread = {}
    for thread in threads:
        table_thread = table_parser.filter_table(table_, strict=True, regex=False, thread=thread)
        cores_str = table_parser.get_column(table_thread, 'log_core')
        cores_per_thread[int(thread)] = [int(core) for core in cores_str]

    return cores_per_thread


def get_thread_num_for_cores(log_cores, host, con_ssh=None):
    cores_per_thread = _get_host_logcores_per_thread(host=host, con_ssh=con_ssh)

    core_thread_dict = {}
    for thread, cores_for_thread in cores_per_thread.items():
        for core in log_cores:
            if int(core) in cores_for_thread:
                core_thread_dict[core] = thread

        if len(core_thread_dict) == len(log_cores):
            return core_thread_dict
    else:
        raise exceptions.HostError("Cannot find thread num for all cores provided. Cores provided: {}. Threads found: "
                                   "{}".format(log_cores, core_thread_dict))


def get_logcore_siblings(host, con_ssh=None):
    """
    Get cpu pairs for given host.
    Args:
        host (str): such as compute-1
        con_ssh (SSHClient):

    Returns (list): list of log_core_siblings(tuple). Output examples:
        - HT enabled: [[0, 20], [1, 21], ..., [19, 39]]
        - HT disabled: [[0], [1], ..., [19]]
    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    host_topology = con_ssh.exec_cmd("vm-topology -s topology | awk '/{}/, /^[ ]*$/'".format(host), fail_ok=False)[1]
    table_ = table_parser.table(host_topology)

    siblings_tab = table_parser.filter_table(table_, cpu_id='sibling_id')
    cpu_ids = [int(cpu_id) for cpu_id in siblings_tab['headers'][1:]]
    sibling_ids = siblings_tab['values'][0][1:]

    if sibling_ids[0] == '-':
        LOG.warning("{} has no sibling cores. Hyper-threading needs to be enabled to have sibling cores.")
        return [[cpu_id] for cpu_id in cpu_ids]

    sibling_ids = [int(sibling_id) for sibling_id in sibling_ids]
    # find pairs and sort the cores in pair and convert to tuple (set() cannot be applied to item as list)
    sibling_pairs = [tuple(sorted(sibling_pair)) for sibling_pair in list(zip(cpu_ids, sibling_ids))]
    sibling_pairs = sorted(list(set(sibling_pairs)))       # remove dup pairs and sort it to start from smallest number
    sibling_pairs = [list(sibling_pair) for sibling_pair in sibling_pairs]

    LOG.info("Sibling cores for {} from vm-topology: {}".format(host, sibling_pairs))
    return sibling_pairs


def get_vcpus_info_in_log(host_ssh, numa_nodes=None, rtn_list=False, con_ssh=None):
    """
    Get vcpus info from nova-compute.log on nova compute host
    Args:
        host_ssh (SSHClient):
        numa_nodes (list): such as [0, 1]
        rtn_list (bool): whether to return dictionary or list
        con_ssh:

    Returns (dict|list):
        Examples: { 0: {'pinned_cpulist': [], 'unpinned_cpulist': [3, 4, 5,...], 'cpu_usage': 0.0, 'pinned': 0, ...},
                    1: {....}}

    """
    hostname = host_ssh.get_hostname()
    if numa_nodes is None:
        numa_nodes = [0, 1]

    res_dict = {}
    for numa_node in numa_nodes:
        res_dict[numa_node] = {}

        # sample output:
        # 2016-07-15 16:20:50.302 99972 INFO nova.compute.resource_tracker [req-649d9338-ee0b-477c-8848-
        # 89cc94114b58 - - - - -] Numa node=1; cpu_usage:32.000, pcpus:36, pinned:32, shared:0.000, unpinned:4;
        # pinned_cpulist:18-19,21-26,28-35,54-55,57-62,64-71, unpinned_cpulist:20,27,56,63
        output = host_ssh.exec_cmd('cat /var/log/nova/nova-compute.log | grep -i -E "Numa node={}; .*unpinned:" '
                                   '| tail -n 1'.format(numa_node), fail_ok=False)[1]

        output = ''.join(output.split(sep='\n'))
        cpu_info = output.split(sep="Numa node={}; ".format(numa_node))[-1].replace('; ', ', '). split(sep=', ')

        print("Cpu info: {}".format(cpu_info))
        for info in cpu_info:
            key, value = info.split(sep=':')

            if key in ['pinned_cpulist', 'unpinned_cpulist']:
                value = common._parse_cpus_list(value)
            elif key in ['cpu_usage', 'shared']:
                value = float(value)
            elif key == 'map':
                pass
            else:
                value = int(value)

            res_dict[numa_node][key] = value

    LOG.info("VCPU info for {} parsed from compute-nova.log: {}".format(host_ssh.get_hostname(), res_dict))
    if rtn_list:
        return [res_dict[node] for node in numa_nodes]

    return res_dict


def get_vcpus_for_instance_via_virsh(host_ssh, instance_name, rtn_list=False):
    """
    Get a list of pinned vcpus for given instance via 'sudo virsh vcpupin <instance_name>'

    Args:
        host_ssh (SSHFromSSH):
        instance_name (str):
        rtn_list (bool):

    Returns (list|dict): list of vcpus ids used by specified instance such as [8, 9], or {0: [8], 1: [9]}

    """

    output = host_ssh.exec_sudo_cmd("virsh vcpupin {} | grep -v '^[ \t]*$'".format(instance_name), fail_ok=False)[1]

    # sample output:
    # VCPU: CPU Affinity
    # ----------------------------------
    #   0: 8
    #   1: 9

    vcpu_lines = output.split(sep='----\n')[1].split(sep='\n')
    print("vcpus_lines: {}".format(vcpu_lines))
    vcpus = {}
    for line in vcpu_lines:
        # line example: '  0: 8'
        key, pcpus = line.strip().split(sep=': ')
        vcpus[int(key)] = common._parse_cpus_list(pcpus.strip())

    if rtn_list:
        all_cpus = []
        for cpus in vcpus.values():
            all_cpus += cpus
        return sorted(all_cpus)

    return vcpus


def get_hosts_per_storage_backing(con_ssh=None):
    """
    Get hosts for each possible storage backing
    Args:
        con_ssh:

    Returns (dict): {'local_image': <cow hosts list>,
                    'local_lvm': <lvm hosts list>,
                    'remote': <remote hosts list>
                    }
    """

    hosts = {'local_image': get_hosts_by_storage_aggregate('local_image', con_ssh=con_ssh),
             'local_lvm': get_hosts_by_storage_aggregate('local_lvm', con_ssh=con_ssh),
             'remote': get_hosts_by_storage_aggregate('remote', con_ssh=con_ssh)}

    return hosts


def get_coredumps_and_crashreports():
    LOG.info("Getting existing system crash reports from /var/crash/ and coredumps from /var/lib/systemd/coredump/")

    hosts_tab = table_parser.table(cli.system('host-list'))
    all_hosts = table_parser.get_column(hosts_tab, 'hostname')

    hosts_tab = table_parser.filter_table(hosts_tab, exclude=True, availability=HostAvailabilityState.FAILED)
    hosts_tab = table_parser.filter_table(hosts_tab, exclude=True, availability=HostAvailabilityState.OFFLINE)

    hosts_to_check = table_parser.get_column(hosts_tab, 'hostname')

    if not all_hosts == hosts_to_check:
        LOG.warning("Some host(s) in offline or failed state - {}, checking other hosts only".
                    format(set(all_hosts) - set(hosts_to_check)))

    core_dumps_and_reports = {}
    for host in hosts_to_check:
        with ssh_to_host(hostname=host) as host_ssh:
            core_dump_output = host_ssh.exec_cmd('ls -l /var/lib/systemd/coredump/', fail_ok=False)[1]
            core_dumps = core_dump_output.splitlines()[1:]
            crash_report_output = host_ssh.exec_cmd('ls -l /var/crash/', fail_ok=False)[1]
            crash_reports = crash_report_output.splitlines()[1:]

            core_dumps_and_reports[host] = core_dumps, crash_reports

    LOG.info("core dumps and crash reports per host: {}".format(core_dumps_and_reports))
    return core_dumps_and_reports


def modify_mtu_on_interfaces(hosts, mtu_val, network_type, lock_unlock=True, fail_ok=False, con_ssh=None):

    if not hosts:
        raise exceptions.HostError("No hostname provided.")

    mtu_val = int(mtu_val)

    if isinstance(hosts, str):
        hosts = [hosts]

    res = {}
    rtn_code = 0
    for host in hosts:
        if_names = system_helper.get_host_interfaces_info(host, rtn_val='name', net_type=network_type, con_ssh=con_ssh)

        if lock_unlock:
            lock_host(host, swact=True)

        LOG.info("Modify MTU for {} {} interfaces to: {}".format(host, network_type, mtu_val))

        res_for_ifs = {}
        for if_name in if_names:
            args = "-m {} {} {}".format(mtu_val, host, if_name)
            # system host-if-modify controller-1 <port_uuid>--imtu <mtu_value>
            code, output = cli.system('host-if-modify', args, fail_ok=fail_ok, rtn_list=True, ssh_client=con_ssh)
            res_for_ifs[if_name] = code, output

            if code != 0:
                rtn_code = 1

        res[host] = res_for_ifs

    if lock_unlock:
        unlock_hosts(hosts, check_hypervisor_up=True, check_webservice_up=True)

    check_failures = []
    for host in hosts:
        host_res = res[host]
        for if_name in host_res:
            mod_res = host_res[if_name]

            # Check mtu modified correctly
            if mod_res[0] == 0:
                actual_mtu = int(system_helper.get_host_if_show_values(host, interface=if_name, fields=['imtu'],
                                                                       con_ssh=con_ssh)[0])
                if not actual_mtu == mtu_val:
                    check_failures.append((host, if_name, actual_mtu))

    if check_failures:
        msg = "Actual MTU value after modify is not as expected. Expected MTU value: {}. Actual [Host, Interface, " \
              "MTU value]: {}".format(mtu_val, check_failures)
        if fail_ok:
            return 2, msg
        raise exceptions.HostPostCheckFailed(msg)

    return rtn_code, res


def get_hosts_and_pnets_with_pci_devs(pci_type='pci-sriov', up_hosts_only=True, con_ssh=None, auth_info=Tenant.ADMIN):
    state = 'up' if up_hosts_only else None
    hosts = get_hypervisors(state=state)

    hosts_pnets_with_pci = {}
    for host_ in hosts:
        pnets_ = system_helper.get_host_interfaces_info(host_, rtn_val='provider networks', net_type=pci_type,
                                                        con_ssh=con_ssh, auth_info=auth_info)
        if pnets_ and pnets_ != 'None':
            pnets_ = pnets_[0].split(sep=',')
            hosts_pnets_with_pci[host_] = pnets_

    if not hosts_pnets_with_pci:
        LOG.info("No {} interface found from any of following hosts: {}".format(pci_type, hosts))
    else:
        LOG.info("Hosts and provider networks with {} devices: {}".format(pci_type, hosts_pnets_with_pci))

    return hosts_pnets_with_pci


def is_active_controller(host, con_ssh=None):
    personality = eval(get_hostshow_value(host, field='capabilities',
                                          merge_lines=True, con_ssh=con_ssh)).get('Personality', '')
    return personality.lower() == 'Controller-Active'.lower()


def upgrade_host(host, timeout=HostTimeout.UPGRADE, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN,
                 lock=False, unlock=False):
    """
    Upgrade given host
    Args:
        host (str):
        timeout (int): MAX seconds to wait for host to become online after unlocking
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (str):
        unlock (bool):


    Returns (tuple):
        (0, "Host is upgraded and in online state.")
        (1, "Cli host upgrade rejected. Applicable only if ail_ok")
        (2, "Host failed data migration. Applicable only if fail_ok")
        (3, "Host did not come online after upgrade. Applicable if fail_ok ")
        (4, "Host fail lock before starting upgrade". Applicable if lock arg is True and fail_ok")
        (5, "Host fail to unlock after host upgrade.  Applicable if unlock arg is True and fail_ok")
        (6, "Host unlocked after upgrade, but alarms are not cleared after 120 seconds.
        Applicable if unlock arg is True and fail_ok")

    """
    LOG.info("Upgrading host {}...".format(host))

    if lock:
        if get_hostshow_value(host, 'administrative', con_ssh=con_ssh) == HostAdminState.UNLOCKED:
            message = "Host is not locked. Locking host  before starting upgrade"
            LOG.info(message)
            rc, output = lock_host(host, con_ssh=con_ssh, fail_ok=True)

            if rc != 0 and rc != -1:
                err_msg = "Host {} fail on lock before starting upgrade: {}".fromat(host, output)
                if fail_ok:
                    return 4, err_msg
                else:
                    raise exceptions.HostError(err_msg)

    exitcode, output = cli.system('host-upgrade', host, ssh_client=con_ssh, auth_info=auth_info,
                                  rtn_list=True, fail_ok=True, timeout=timeout)
    if exitcode == 1:
        err_msg = "Host {} cli upgrade host failed: {}".format(host, output)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.HostError(err_msg)

    # sleep for 180 seconds to let host be re-installed with upgrade release
    time.sleep(180)

    if not wait_for_host_states(host, timeout=timeout, check_interval=60, availability=HostAvailabilityState.ONLINE,
                                con_ssh=con_ssh, fail_ok=fail_ok):
        err_msg = "Host {} did not become online  after upgrade".format(host)
        if fail_ok:
            return 3, err_msg
        else:
            raise exceptions.HostError(err_msg)

    if host.strip() == "controller-1":
        rc, output = _wait_for_upgrade_data_migration_complete(timeout=timeout,
                                                               auth_info=auth_info, fail_ok=fail_ok, con_ssh=con_ssh)
        if rc != 0:
            err_msg = "Host {} updrade data migration failure: {}".format(host, output)
            if fail_ok:
                return 2, err_msg
            else:
                raise exceptions.HostError(err_msg)

    if unlock:
        rc, output = unlock_host(host, fail_ok=True, available_only=True)
        if rc != 0:
            err_msg = "Host {} fail to unlock after host upgrade: ".format(host, output)
            if fail_ok:
                return 5, err_msg
            else:
                raise exceptions.HostError(err_msg)

        # wait until  400.001  alarms get cleared
        if not system_helper.wait_for_alarm_gone("400.001", fail_ok=True):
            err_msg = "Alarms did not clear after host {} upgrade and unlock: ".format(host)
            if fail_ok:
                return 6, err_msg
            else:
                raise exceptions.HostError(err_msg)

    LOG.info("Upgrading host {} complete ...".format(host))
    return 0, None


def upgrade_hosts(hosts, timeout=HostTimeout.UPGRADE, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN,
                  lock=False, unlock=False):
    """
    Upgrade given hosts list one by one
    Args:
        hosts (list): list of hostname of hosts to be upgraded
        timeout (int): MAX seconds to wait for host to become online after upgrading
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (str):
        unlock (bool):

    Returns (tuple):
        (0, "Hosts are upgraded and in online state.")
        (1, "Upgrade on host failed. applicable if fail_ok

    """
    LOG.info("Upgrading {}...".format(hosts))
    active_controller = system_helper.get_active_controller_name()
    if active_controller in hosts:
        hosts = hosts.remove(active_controller)

    LOG.info("Checking if active controller {} is already upgraded ....".format(active_controller))

    if get_hosts_upgrade_target_release(active_controller) in get_hosts_upgrade_target_release(hosts):
        message = " Active controller {} is not upgraded.  Must be upgraded first".format(active_controller)
        LOG.info(message)
        return 1, message
    #keep original host

    controllers = sorted([h for h in hosts if "controller" in h])
    storages = sorted([h for h in hosts if "storage" in h])
    computes = sorted([h for h in hosts if h not in storages and h not in controllers])
    upgrade_hosts = controllers + storages + computes

    for host in upgrade_hosts:
        rc, output =  upgrade_host(host, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                                   auth_info=auth_info, lock=lock, unlock=unlock)
        if rc != 0:
            if fail_ok:
                return rc, output
            else:
                raise exceptions.HostError(output)
        else:
            LOG.info("Host {} upgrade completed".format(host))

    return 0, "hosts {} upgrade done ".format(upgrade_hosts)


def _wait_for_upgrade_data_migration_complete(timeout=1800, check_interval=60, auth_info=Tenant.ADMIN, fail_ok=False, con_ssh=None):
    """
    Waits until upgrade data migration is complete or fail
    Args:
        timeout (int): MAX seconds to wait for data migration to complete
        fail_ok (bool): if true return error code
        con_ssh (SSHClient):
        auth_info (str):

    Returns (tuple):
        (0, "Upgrade data migration complete.")
        (1, "Upgrade dat migration failed. Applicable only if ail_ok")
        (2, "Upgrade data migration timeout out before complete. Applicable only if fail_ok")
        (3, "Timeout waiting the Host upgrade data migration to complete. Applicable if fail_ok ")

    """

    endtime = time.time() + timeout
    while time.time() < endtime:
        upgrade_progress_tab = table_parser.table(cli.system('upgrade-show', ssh_client=con_ssh, auth_info=auth_info))
        upgrade_progress_tab = table_parser.filter_table(upgrade_progress_tab, Property="state")
        if "data-migration-complete" in table_parser.get_column(upgrade_progress_tab, 'Value'):
            LOG.info("Upgrade data migration is complete")
            return 0, "Upgrade data migration is complete"
        elif "data-migration-failed" in table_parser.get_column(upgrade_progress_tab, 'Value'):
            err_msg = "Host Upgrade data migration failed."
            LOG.warning(err_msg)
            if fail_ok:
                return 1, err_msg
            else:
                raise exceptions.HostError(err_msg)

        time.sleep(check_interval)

    err_msg = "Timed out waiting for upgrade data migration to complete state"
    if fail_ok:
        LOG.warning(err_msg)
        return 3, err_msg
    else:
        raise exceptions.HostError(err_msg)


def get_hosts_upgrade_target_release(hostnames, con_ssh=None):
    if isinstance(hostnames, str):
        hostnames = [hostnames]

    table_ = table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, hostname=hostnames)
    return table_parser.get_column(table_, "target_release")


def get_hosts_upgrade_running_release(hostnames, con_ssh=None):
    if isinstance(hostnames, str):
        hostnames = [hostnames]

    table_ = table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(hostname=hostnames)
    return table_parser.get_column(table_, "running_release")


def ensure_host_provisioned(host, cons_ssh=None):
    """
    check if host is provisioned.

    Args:
        host (str): hostname or id in string format
        con_ssh (SSHClient):

    Returns: (return_code(int), msg(str))   # 1, 2, 3, 4, 5 only returns when fail_ok=True
        (0, "Host is host is provisioned)
    """
    LOG.info("Checking if host {} is already provisioned ....".format(host))
    if is_host_provisioned(host, con_ssh=None):
        return 0, "Host {} is provisioned"

    LOG.info("Host {} not provisioned ; doing lock/unlock to provision the host ....".format(host))
    rc, output = lock_host(host,con_ssh=cons_ssh)
    if rc != 0 and rc != -1:
        err_msg =  "Lock host {} rejected".format(host)
        raise exceptions.HostError(err_msg)

    rc, output = unlock_host(host, available_only=True, con_ssh=cons_ssh)
    if rc != 0:
        err_msg = "Unlock host {} failed: {}".format(host, output)
        raise exceptions.HostError(err_msg)

    LOG.info("Checking if host {} is provisioned after lock/unlock ....".format(host))
    if not is_host_provisioned(host, con_ssh=None):
        raise exceptions.HostError("Failed to provision host {}")
    return 0, "Host {} is provisioned after lock/unlock"


def is_host_provisioned(host, con_ssh=None):
    invprovisioned = get_hostshow_value(host, "invprovision", con_ssh=con_ssh)
    LOG.info("Host {} is {}".format(host, invprovisioned))
    return "provisioned" == invprovisioned.strip()


def get_upgraded_host_names(upgrade_release, con_ssh=None):

    table_ = table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, target_release=upgrade_release)
    return table_parser.get_column(table_, "hostname")


def downgrade_host(host, timeout=HostTimeout.UPGRADE, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN,
                 lock=False, unlock=False):
    """
    Downgrade given host
    Args:
        host (str):
        timeout (int): MAX seconds to wait for host to become online after unlocking
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (str):
        unlock (bool):


    Returns (tuple):
        (0, "Host is downgraded and in online state.")
        (1, "Cli host downgrade rejected. Applicable only if ail_ok")
        (2, "Host did not come online after downgrade. Applicable if fail_ok ")
        (3, "Host fail lock before starting downgrade". Applicable if lock arg is True and fail_ok")
        (4, "Host fail to unlock after host downgrade.  Applicable if unlock arg is True and fail_ok")
        (5, "Host unlocked after downgrade, but alarms are not cleared after 120 seconds.
        Applicable if unlock arg is True and fail_ok")

    """
    LOG.info("Downgrading host {}...".format(host))

    if lock:
        if get_hostshow_value(host, 'administrative', con_ssh=con_ssh) == HostAdminState.UNLOCKED:
            message = "Host is not locked. Locking host  before starting downgrade"
            LOG.info(message)
            rc, output = lock_host(host, con_ssh=con_ssh, fail_ok=True)

            if rc != 0 and rc != -1:
                err_msg = "Host {} fail on lock before starting downgrade: {}".fromat(host, output)
                if fail_ok:
                    return 3, err_msg
                else:
                    raise exceptions.HostError(err_msg)

    exitcode, output = cli.system('host-downgrade', host, ssh_client=con_ssh, auth_info=auth_info,
                                  rtn_list=True, fail_ok=True, timeout=timeout)
    if exitcode == 1:
        err_msg = "Host {} cli downgrade host failed: {}".format(host, output)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.HostError(err_msg)


    # sleep for 180 seconds to let host be re-installed with previous release
    time.sleep(180)

    if not wait_for_host_states(host, timeout=timeout, check_interval=60, availability=HostAvailabilityState.ONLINE,
                                con_ssh=con_ssh, fail_ok=fail_ok):
        err_msg = "Host {} did not become online  after downgrade".format(host)
        if fail_ok:
            return 2, err_msg
        else:
            raise exceptions.HostError(err_msg)

    if unlock:
        rc, output = unlock_host(host, fail_ok=True, available_only=True)
        if rc != 0:
            err_msg = "Host {} fail to unlock after host downgrade: ".format(host, output)
            if fail_ok:
                return 4, err_msg
            else:
                raise exceptions.HostError(err_msg)

        # wait until  400.001  alarms get cleared
        if not system_helper.wait_for_alarm_gone("400.001", fail_ok=True):
            err_msg = "Alarms did not clear after host {} downgrade and unlock: ".format(host)
            if fail_ok:
                return 5, err_msg
            else:
                raise exceptions.HostError(err_msg)

    LOG.info("Downgrading host {} complete ...".format(host))
    return 0, None


def get_sm_dump_table(controller, con_ssh=None):
    """

    Args:
        controller (str|SSHClient): controller name/ssh client to get sm-dump for
        con_ssh (SSHClient): ssh client for active controller

    Returns ():
    table_ (dict): Dictionary of a table parsed by tempest.
            Example: table =
            {
                'headers': ["Field", "Value"];
                'values': [['name', 'internal-subnet0'], ['id', '36864844783']]}

    """
    if isinstance(controller, str):
        with ssh_to_host(controller, con_ssh=con_ssh) as host_ssh:
            return table_parser.sm_dump_table(host_ssh.exec_sudo_cmd('sm-dump', fail_ok=False)[1])

    host_ssh = controller
    return table_parser.sm_dump_table(host_ssh.exec_sudo_cmd('sm-dump', fail_ok=False)[1])


def get_sm_dump_items(controller, item_names=None, con_ssh=None):
    """
    get sm dump dict for specified items
    Args:
        controller (str|SSHClient): hostname or ssh client for a controller such as controller-0, controller-1
        item_names (list|str): such as 'oam-services', or ['oam-ip', 'oam-services']
        con_ssh (SSHClient):

    Returns (dict): such as {'oam-services': {'desired-state': 'active', 'actual-state': 'active'},
                             'oam-ip': {...}
                            }

    """
    sm_dump_tab = get_sm_dump_table(controller=controller, con_ssh=con_ssh)
    if item_names:
        if isinstance(item_names, str):
            item_names = [item_names]

        sm_dump_tab = table_parser.filter_table(sm_dump_tab, name=item_names)

    sm_dump_items = table_parser.row_dict_table(sm_dump_tab, key_header='name', unique_key=True)
    return sm_dump_items


def get_sm_dump_item_states(controller, item_name, con_ssh=None):
    """
    get desired and actual states of given item

    Args:
        controller (str|SSHClient): hostname or host_ssh for a controller such as controller-0, controller-1
        item_name (str): such as 'oam-services'
        con_ssh (SSHClient):

    Returns (tuple): (<desired-state>, <actual-state>) such as ('active', 'active')

    """
    item_value_dict = get_sm_dump_items(controller=controller, item_names=item_name, con_ssh=con_ssh)[item_name]

    return item_value_dict['desired-state'], item_value_dict['actual-state']


def wait_for_sm_dump_desired_states(controller, item_names=None, timeout=60, strict=True, fail_ok=False, con_ssh=None):
    """
    Wait for sm_dump item(s) to reach desired state(s)

    Args:
        controller (str): controller name
        item_names (str|list|None): item(s) name(s) to wait for desired state(s). Wait for desired states for all items
            when set to None.
        timeout (int): max seconds to wait
        strict (bool): whether to find strict match for given item_names. e.g., item_names='drbd-', strict=False will
            check all items whose name contain 'drbd-'
        fail_ok (bool): whether or not to raise exception if any item did not reach desired state before timed out
        con_ssh (SSHClient):

    Returns (bool): True if all of given items reach desired state

    """

    LOG.info("Waiting for {} {} in sm-dump to reach desired state".format(controller, item_names))
    if item_names is None:
        item_names = get_sm_dump_items(controller=controller, item_names=item_names, con_ssh=con_ssh)

    elif not strict:
        table_ = get_sm_dump_table(controller=controller, con_ssh=con_ssh)
        item_names = table_parser.get_values(table_, 'name', strict=False, name=item_names)

    if isinstance(item_names, str):
        item_names = [item_names]

    items_to_check = {}
    for item in item_names:
        items_to_check[item] = {}
        items_to_check[item]['prev-state'] = items_to_check[item]['actual-state'] = \
            items_to_check[item]['desired-state'] = ''

    def __wait_for_desired_state(ssh_client):
        end_time = time.time() + timeout

        while time.time() < end_time:
            items_names_to_check = list(items_to_check.keys())
            items_states = get_sm_dump_items(ssh_client, item_names=items_names_to_check, con_ssh=con_ssh)

            for item_ in items_states:
                items_to_check[item_].update(**items_states[item_])

                prev_state = items_to_check[item_]['prev-state']
                desired_state = items_states[item_]['desired-state']
                actual_state = items_states[item_]['actual-state']

                if desired_state == actual_state:
                    LOG.info("{} in sm-dump has reached desired state: {}".format(item_, desired_state))
                    items_to_check.pop(item_)
                    continue

                elif prev_state and actual_state != prev_state:
                    LOG.info("{} actual state changed from {} to {} while desired state is: {}".
                             format(item_, prev_state, actual_state, desired_state))

                # items_to_check[item_].update(actual_state=actual_state)
                items_to_check[item_].update(prev_state=actual_state)
                # items_to_check[item_].update(desired_state=desired_state)

            if not items_to_check:
                return True

            time.sleep(3)

        err_msg = "Timed out waiting for sm-dump item(s) to reach desired state(s): {}".format(items_to_check)
        if fail_ok:
            LOG.warning(err_msg)
            return False
        else:
            raise exceptions.TimeoutException(err_msg)

    if isinstance(controller, str):
        with ssh_to_host(controller, con_ssh=con_ssh) as host_ssh:
            return __wait_for_desired_state(host_ssh)
    else:
        return __wait_for_desired_state(controller)


# This is a copy from installer_helper due to blocking issues in installer_helper on importing non-exist modules
@contextmanager
def ssh_to_build_server(bld_srv=DEFAULT_BUILD_SERVER, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                        prompt=None):
    """
    ssh to given build server.
    Usage: Use with context_manager. i.e.,
        with ssh_to_build_server(bld_srv=cgts-yow3-lx) as bld_srv_ssh:
            # do something
        # ssh session will be closed automatically

    Args:
        bld_srv (str|dict): build server ip, name or dictionary (choose from consts.build_serve.BUILD_SERVERS)
        user (str): svc-cgcsauto if unspecified
        password (str): password for svc-cgcsauto user if unspecified
        prompt (str|None): expected prompt. such as: svc-cgcsauto@yow-cgts4-lx.wrs.com$

    Yields (SSHClient): ssh client for given build server and user

    """
    # Get build_server dict from bld_srv param.
    if isinstance(bld_srv, str):
        for bs in BUILD_SERVERS:
            if bs['name'] in bld_srv or bs['ip'] == bld_srv:
                bld_srv = bs
                break
        else:
            raise exceptions.BuildServerError("Requested build server - {} is not found. Choose server ip or "
                                              "server name from: {}".format(bld_srv, BUILD_SERVERS))
    elif bld_srv not in BUILD_SERVERS:
        raise exceptions.BuildServerError("Unknown build server: {}. Choose from: {}".format(bld_srv, BUILD_SERVERS))

    prompt = prompt if prompt else Prompt.BUILD_SERVER_PROMPT_BASE.format(user, bld_srv['name'])
    bld_server_conn = SSHClient(bld_srv['ip'], user=user, password=password, initial_prompt=prompt)
    bld_server_conn.connect()

    try:
        yield bld_server_conn
    finally:
        bld_server_conn.close()


def get_host_co_processor_pci_list(hostname):

    host_pci_info = []
    with ssh_to_host(hostname) as host_ssh:
        LOG.info("Getting the Co-processor pci list for host {}".format(hostname))
        cmd = " lspci -nnm | grep Co-processor | awk ' !/Virtual/'"
        rc, output = host_ssh.exec_cmd(cmd)
        if rc == 0:
            for pci_line in output.splitlines():
                pci_attributes = pci_line.split('"')
                while ' ' in pci_attributes:
                    pci_attributes.remove(' ')
                while '' in pci_attributes:
                    pci_attributes.remove('')

                pci_address = ("0000:{}".format(pci_attributes[0])).strip()
                pci_name = "pci_{}".format(pci_address.replace('.', '_').replace(':', '_').strip())
                vendor_name = pci_attributes[2].split(' [')[0]
                LOG.info("vendor ={} pci_address = {} pci_name= {}".format(vendor_name, pci_address, pci_name))
                vendor_id = (pci_attributes[2].split(' [')[1]).replace(']', '')
                device_name = pci_attributes[3].split(' [')[0]
                device_id = pci_attributes[3].split(' [')[1].replace(']', '')
                pci_info = {'pci_address': pci_address,
                            'pci_name': pci_name,
                            'vendor_name': vendor_name,
                            'vendor_id': vendor_id,
                            'device_id': device_id
                           }
                cmd2 = " lspci -nnm | grep Co-processor | grep \"{} Virtual\" | awk 'NR == 1'".format(device_name)
                rc, vf_line = host_ssh.exec_cmd(cmd2)

                if rc == 0:
                    vf_line_attr = vf_line.split('"')
                    while ' ' in vf_line_attr:
                        vf_line_attr.remove(' ')
                    while '' in vf_line_attr:
                        vf_line_attr.remove('')
                    vf_device_id = vf_line_attr[3].split(' [')[1].replace(']', '')
                    pci_info['vf_device_id'] = vf_device_id

                host_pci_info.append(pci_info)
                LOG.info("The Co-processor pci list for host {}: {}".format(hostname, pci_info ))

    return host_pci_info


def get_mellanox_ports(host):
    """
    Get Mellanox data ports for given host

    Args:
        host (str): hostname

    Returns (list):

    """
    data_ports = system_helper.get_host_ports_for_net_type(host, net_type='data', rtn_list=True)
    mt_ports = system_helper.get_host_ports_info(host, 'uuid', if_name=data_ports, strict=False, regex=True,
                                                 **{'device type': MELLANOX_DEVICE})
    LOG.info("Mellanox ports: {}".format(mt_ports))
    return mt_ports


def is_host_locked(host,  con_ssh=None):
        admin_state = get_hostshow_value(host, 'administrative', con_ssh=con_ssh)
        return admin_state == 'locked'
