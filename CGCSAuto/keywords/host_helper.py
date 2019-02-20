import re
import os
import time
import copy
from contextlib import contextmanager
from xml.etree import ElementTree

from consts.proj_vars import ProjVar
from consts.auth import Tenant, SvcCgcsAuto, HostLinuxCreds
from consts.build_server import DEFAULT_BUILD_SERVER, BUILD_SERVERS
from consts.timeout import HostTimeout, CMDTimeout, MiscTimeout
from consts.filepaths import WRSROOT_HOME
from consts.cgcs import HostAvailState, HostAdminState, HostOperState, Prompt, MELLANOX_DEVICE, MaxVmsSupported, \
    Networks, EventLogID, HostTask, PLATFORM_AFFINE_INCOMPLETE, TrafficControl, PLATFORM_NET_TYPES

from keywords import system_helper, common, kube_helper, security_helper
from utils import cli, exceptions, table_parser
from utils import telnet as telnetlib
from utils.clients.ssh import ControllerClient, SSHFromSSH, SSHClient
from utils.tis_log import LOG


@contextmanager
def ssh_to_host(hostname, username=None, password=None, prompt=None, con_ssh=None, timeout=60):
    """
    ssh to a host from ssh client.

    Args:
        hostname (str|None): host to ssh to. When None, return active controller ssh
        username (str):
        password (str):
        prompt (str):
        con_ssh (SSHClient):
        timeout (int)

    Returns (SSHClient): ssh client of the host

    Examples: with ssh_to_host('controller-1') as host_ssh:
                  host.exec_cmd(cmd)

    """
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    if not hostname:
        yield con_ssh
        return

    user = username if username else HostLinuxCreds.get_user()
    password = password if password else HostLinuxCreds.get_password()
    if not prompt:
        prompt = '.*' + hostname + r'\:~\$'
    original_host = con_ssh.get_hostname()
    if original_host != hostname:
        host_ssh = SSHFromSSH(ssh_client=con_ssh, host=hostname, user=user, password=password, initial_prompt=prompt,
                              timeout=timeout)
        host_ssh.connect(prompt=prompt)
        current_host = host_ssh.get_hostname()
        if not current_host == hostname:
            raise exceptions.SSHException("Current host is {} instead of {}".format(current_host, hostname))
        close = True
    else:
        close = False
        host_ssh = con_ssh
    try:
        yield host_ssh
    finally:
        if close:
            host_ssh.close()


def reboot_hosts(hostnames, timeout=HostTimeout.REBOOT, con_ssh=None, fail_ok=False, wait_for_offline=True,
                 wait_for_reboot_finish=True, check_hypervisor_up=True, check_webservice_up=True, force_reboot=True,
                 check_up_time=True):
    """
    Reboot one or multiple host(s)

    Args:
        hostnames (list|str): hostname(s) to reboot. str input is also acceptable when only one host to be rebooted
        timeout (int): timeout waiting for reboot to complete in seconds
        con_ssh (SSHClient): Active controller ssh
        fail_ok (bool): Whether it is okay or not for rebooting to fail on any host
        wait_for_offline (bool): Whether to wait for host to be offline after reboot
        wait_for_reboot_finish (bool): whether to wait for reboot finishes before return
        check_hypervisor_up (bool):
        check_webservice_up (bool):
        force_reboot (bool): whether to add -f, i.e., sudo reboot [-f]
        check_up_time (bool): Whether to ensure active controller uptime is more than 15 minutes before rebooting

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

    reboot_active = False
    active_con = system_helper.get_active_controller_name(con_ssh)
    hostnames = list(set(hostnames))
    if active_con in hostnames:
        reboot_active = True
        hostnames.remove(active_con)

    res, out = cli.system('host-list', rtn_list=True)
    LOG.info('\n{}'.format(out))

    is_simplex = system_helper.is_simplex()
    user, password = security_helper.LinuxUser.get_current_user_password()
    # reboot hosts other than active controller
    cmd = 'sudo reboot -f' if force_reboot else 'sudo reboot'

    for host in hostnames:
        prompt = '.*' + host + r'\:~\$'
        host_ssh = SSHFromSSH(ssh_client=con_ssh, host=host, user=user, password=password, initial_prompt=prompt)
        host_ssh.connect()
        current_host = host_ssh.get_hostname()
        if not current_host == host:
            raise exceptions.SSHException("Current host is {} instead of {}".format(current_host, host))

        LOG.info("Rebooting {}".format(host))
        host_ssh.send(cmd)
        host_ssh.expect(['.*[pP]assword:.*', 'Rebooting'])
        host_ssh.send(password)
        con_ssh.expect(timeout=120)

    # reconnect to lab and wait for system up if rebooting active controller
    if reboot_active:
        if check_up_time:
            LOG.info("Ensure uptime for controller(s) is at least 15 minutes before rebooting.")
            time_to_sleep = max(0, 910 - system_helper.get_controller_uptime(con_ssh=con_ssh))
            time.sleep(time_to_sleep)

        LOG.info("Rebooting active controller: {}".format(active_con))
        con_ssh.send('sudo reboot -f')
        index = con_ssh.expect(['.*[pP]assword:.*', 'Rebooting'])
        if index == 0:
            con_ssh.send(password)

        if is_simplex:
            _wait_for_simplex_reconnect(con_ssh=con_ssh, timeout=timeout)
        else:
            LOG.info("Active controller reboot started. Wait for 20 seconds then attempt to reconnect for "
                     "maximum {}s".format(timeout))
            time.sleep(20)
            con_ssh.connect(retry=True, retry_timeout=timeout)

            LOG.info("Reconnected via fip. Waiting for system show cli to re-enable")
            _wait_for_openstack_cli_enable(con_ssh=con_ssh)

    if not wait_for_offline and not is_simplex:
        msg = "Hosts reboot -f cmd sent"
        LOG.info(msg)
        return -1, msg

    if hostnames:
        time.sleep(30)
        hostnames = sorted(hostnames)
        hosts_in_rebooting = wait_for_hosts_states(
                hostnames, timeout=HostTimeout.FAIL_AFTER_REBOOT, check_interval=10, duration=8, con_ssh=con_ssh,
                availability=[HostAvailState.OFFLINE, HostAvailState.FAILED])

        if not hosts_in_rebooting:
            hosts_info = get_host_show_values_for_hosts(hostnames, ['task', 'availability'], con_ssh=con_ssh)
            raise exceptions.HostError("Some hosts are not rebooting. \nHosts info:{}".format(hosts_info))

    if reboot_active:
        hostnames.append(active_con)
        if not is_simplex:
            wait_for_hosts_states(
                    active_con, timeout=HostTimeout.FAIL_AFTER_REBOOT, fail_ok=True, check_interval=10, duration=8,
                    con_ssh=con_ssh, availability=[HostAvailState.OFFLINE, HostAvailState.FAILED])

    if not wait_for_reboot_finish:
        msg = 'Host(s) in offline state'
        LOG.info(msg)
        return -1, msg

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
            for host_unlocked in unlocked_hosts:
                LOG.info("Waiting for task clear for {}".format(host_unlocked))
                # TODO: check fail_ok?
                wait_for_host_values(host_unlocked, timeout=HostTimeout.TASK_CLEAR, fail_ok=False, task='')

            LOG.info("Get available hosts after task clear and wait for hypervsior/webservice up")
            hosts_tab = table_parser.table(cli.system('host-list --nowrap', ssh_client=con_ssh))
            hosts_to_check_tab = table_parser.filter_table(hosts_tab, hostname=unlocked_hosts)
            hosts_avail = table_parser.get_values(hosts_to_check_tab, 'hostname',
                                                  availability=HostAvailState.AVAILABLE)

            if hosts_avail and (check_hypervisor_up or check_webservice_up):

                all_nodes = system_helper.get_hostnames_per_personality(con_ssh=con_ssh)
                computes = list(set(hosts_avail) & set(all_nodes['compute']))
                controllers = list(set(hosts_avail) & set(all_nodes['controller']))
                if system_helper.is_small_footprint(con_ssh):
                    computes += controllers

                if check_webservice_up and controllers:
                    res, hosts_webdown = wait_for_webservice_up(controllers, fail_ok=fail_ok, con_ssh=con_ssh,
                                                                timeout=HostTimeout.WEB_SERVICE_UP)
                    if not res:
                        err_msg = "Hosts web-services not active in system servicegroup-list: {}".format(hosts_webdown)
                        if fail_ok:
                            return 3, err_msg
                        else:
                            raise exceptions.HostPostCheckFailed(err_msg)

                if check_hypervisor_up and computes:
                    res, hosts_hypervisordown = wait_for_hypervisors_up(computes, fail_ok=fail_ok, con_ssh=con_ssh,
                                                                        timeout=HostTimeout.HYPERVISOR_UP)
                    if not res:
                        err_msg = "Hosts not up in nova hypervisor-list: {}".format(hosts_hypervisordown)
                        if fail_ok:
                            return 2, err_msg
                        else:
                            raise exceptions.HostPostCheckFailed(err_msg)

                hosts_affine_incomplete = []
                for host in list(set(computes) & set(hosts_avail)):
                    if not wait_for_tasks_affined(host, fail_ok=True):
                        hosts_affine_incomplete.append(host)

                if hosts_affine_incomplete:
                    err_msg = "Hosts platform tasks affining incomplete: {}".format(hosts_affine_incomplete)
                    # if fail_ok:
                    #     return 4, err_msg
                    # else:
                    #     raise exceptions.HostPostCheckFailed(err_msg)

                    # Do not fail the test due to task affining incomplete for now to unblock test case.
                    # Workaround for CGTS-10715.
                    LOG.error(err_msg)

    states_vals = {}
    failure_msg = ''
    for host in hostnames:
        vals = get_hostshow_values(host, fields=['task', 'availability'])
        if not vals['task'] == '':
            failure_msg += " {} still in task: {}.".format(host, vals['task'])
        states_vals[host] = vals
    from keywords.kube_helper import wait_for_nodes_ready
    hosts_not_ready = wait_for_nodes_ready(hostnames, timeout=30, con_ssh=con_ssh, fail_ok=fail_ok)[1]
    if hosts_not_ready:
        failure_msg += " {} not ready in kubectl get ndoes".format(hosts_not_ready)

    message = "Host(s) state(s) - {}.".format(states_vals)

    if locked_hosts_in_states and unlocked_hosts_in_states and failure_msg == '':
        succ_msg = "Hosts {} rebooted successfully".format(hostnames)
        LOG.info(succ_msg)
        return 0, succ_msg

    err_msg = "Host(s) not in expected states or task unfinished. " + message + failure_msg
    if fail_ok:
        LOG.warning(err_msg)
        return 1, err_msg
    else:
        raise exceptions.HostPostCheckFailed(err_msg)


def recover_simplex(con_ssh=None, fail_ok=False, auth_info=Tenant.get('admin')):
    """
    Ensure simplex host is unlocked, available, and hypervisor up
    This function should only be called for simplex system

    Args:
        con_ssh (SSHClient):
        fail_ok (bool)
        auth_info (dict)

    """
    if not con_ssh:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    if not con_ssh._is_connected():
        con_ssh.connect(retry=True, retry_timeout=HostTimeout.REBOOT)
    _wait_for_openstack_cli_enable(con_ssh=con_ssh, timeout=HostTimeout.REBOOT, auth_info=auth_info)

    host = 'controller-0'
    is_unlocked = (get_hostshow_value(host=host, field='administrative', auth_info=auth_info, con_ssh=con_ssh)
                   == HostAdminState.UNLOCKED)

    if not is_unlocked:
        unlock_host(host=host, available_only=True, fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info)
    else:
        wait_for_hosts_ready(host, fail_ok=fail_ok, check_task_affinity=False, con_ssh=con_ssh, auth_info=auth_info)


def wait_for_hosts_ready(hosts, fail_ok=False, check_task_affinity=False, con_ssh=None, auth_info=Tenant.get('admin'),
                         timeout=None):
    """
    Wait for hosts to be in online state if locked, and available and hypervisor/webservice up if unlocked
    Args:
        hosts:
        fail_ok: whether to raise exception when fail
        check_task_affinity
        con_ssh:
        auth_info
        timeout

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    expt_online_hosts = system_helper.get_hostnames(hosts=hosts, administrative=HostAdminState.LOCKED,
                                                    auth_info=auth_info, con_ssh=con_ssh)
    expt_avail_hosts = system_helper.get_hostnames(hosts=hosts, administrative=HostAdminState.UNLOCKED,
                                                   auth_info=auth_info, con_ssh=con_ssh)

    res_lock = res_unlock = True
    timeout_args = {'timeout': timeout} if timeout else {}
    from keywords.kube_helper import wait_for_nodes_ready
    if expt_online_hosts:
        LOG.info("Wait for hosts to be online: {}".format(hosts))
        res_lock = wait_for_hosts_states(expt_online_hosts, availability=HostAvailState.ONLINE, fail_ok=fail_ok,
                                         con_ssh=con_ssh, auth_info=auth_info, **timeout_args)

        res_kube = wait_for_nodes_ready(hosts=expt_online_hosts, timeout=30, con_ssh=con_ssh, fail_ok=fail_ok)[0]
        res_lock = res_lock and res_kube

    if expt_avail_hosts:
        hypervisors = list(set(get_hypervisors(con_ssh=con_ssh, auth_info=auth_info)) & set(expt_avail_hosts))
        controllers = list(set(system_helper.get_controllers(con_ssh=con_ssh, auth_info=auth_info)) &
                           set(expt_avail_hosts))

        LOG.info("Wait for hosts to be available: {}".format(hosts))
        res_unlock = wait_for_hosts_states(expt_avail_hosts, availability=HostAvailState.AVAILABLE, fail_ok=fail_ok,
                                           con_ssh=con_ssh, auth_info=auth_info, **timeout_args)

        if res_unlock:
            res_1 = wait_for_task_clear_and_subfunction_ready(hosts, fail_ok=fail_ok, auth_info=auth_info,
                                                              con_ssh=con_ssh)
            res_unlock = res_unlock and res_1

        if controllers:
            LOG.info("Wait for webservices up for hosts: {}".format(controllers))
            res_2 = wait_for_webservice_up(controllers, fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info,
                                           timeout=HostTimeout.WEB_SERVICE_UP)
            res_unlock = res_unlock and res_2
        if hypervisors:
            LOG.info("Wait for hypervisors up for hosts: {}".format(hypervisors))
            res_3 = wait_for_hypervisors_up(hypervisors, fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info,
                                            timeout=HostTimeout.HYPERVISOR_UP)
            res_unlock = res_unlock and res_3

            if check_task_affinity:
                for host in hypervisors:
                    # Do not fail the test due to task affining incomplete for now to unblock test case.
                    # Workaround for CGTS-10715.
                    wait_for_tasks_affined(host, fail_ok=True, auth_info=auth_info, con_ssh=con_ssh)
                    # res_4 = wait_for_tasks_affined(host=host, fail_ok=fail_ok, auth_info=auth_info, con_ssh=con_ssh)
                    # res_unlock = res_unlock and res_4

        res_kube = wait_for_nodes_ready(hosts=expt_avail_hosts, timeout=30, con_ssh=con_ssh, fail_ok=fail_ok)[0]
        res_unlock = res_unlock and res_kube

    return res_lock and res_unlock


def wait_for_task_clear_and_subfunction_ready(hosts, fail_ok=False, con_ssh=None, use_telnet=False, con_telnet=None,
                                              timeout=HostTimeout.SUBFUNC_READY, auth_info=Tenant.get('admin')):
    if isinstance(hosts, str):
        hosts = [hosts]

    hosts_to_check = list(hosts)
    LOG.info("Waiting for task clear and subfunctions enable/available (if applicable) for hosts: {}".
             format(hosts_to_check))
    end_time = time.time() + timeout
    while time.time() < end_time:
        hosts_vals = get_host_show_values_for_hosts(hosts_to_check, ['subfunction_avail', 'subfunction_oper', 'task'],
                                                    con_ssh=con_ssh, use_telnet=use_telnet,
                                                    con_telnet=con_telnet, auth_info=auth_info)
        for host, vals in hosts_vals.items():
            if not vals['task'] and vals['subfunction_avail'] in ('', HostAvailState.AVAILABLE) and \
                    vals['subfunction_oper'] in ('', HostOperState.ENABLED):
                hosts_to_check.remove(host)

        if not hosts_to_check:
            LOG.info("Hosts task cleared and subfunctions (if applicable) are now in enabled/available states")
            return True

        time.sleep(10)

    err_msg = "Host(s) subfunctions are not all in enabled/available states: {}".format(hosts_to_check)
    if fail_ok:
        LOG.warning(err_msg)
        return False

    raise exceptions.HostError(err_msg)


def get_host_show_values_for_hosts(hostnames, fields, merge_lines=False, con_ssh=None, use_telnet=False,
                                   con_telnet=None, auth_info=Tenant.get('admin')):
    if isinstance(fields, str):
        fields = [fields]

    states_vals = {}
    for host in hostnames:
        vals = get_hostshow_values(host, fields, merge_lines=merge_lines, con_ssh=con_ssh,
                                   use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)
        states_vals[host] = vals

    return states_vals


def __hosts_stay_in_states(hosts, duration=10, con_ssh=None, auth_info=Tenant.get('admin'), **states):
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
        if not __hosts_in_states(hosts=hosts, con_ssh=con_ssh, auth_info=auth_info, **states):
            return False
        time.sleep(1)

    return True


def wait_for_hosts_states(hosts, timeout=HostTimeout.REBOOT, check_interval=5, duration=3, con_ssh=None,
                          use_telnet=False, con_telnet=None, fail_ok=True, auth_info=Tenant.get('admin'), **states):
    """
    Wait for hosts to go in specified states via system host-list

    Args:
        hosts (str|list):
        timeout (int):
        check_interval (int):
        duration (int): wait for a host to be in given state(s) for at least <duration> seconds
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        fail_ok (bool)
        auth_info
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
        if __hosts_stay_in_states(hosts, con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                  duration=duration, auth_info=auth_info, **states):
            LOG.info("{} have reached state(s): {}".format(hosts, states))
            return True
        time.sleep(check_interval)
    else:
        msg = "Timed out waiting for {} in state(s) - {}".format(hosts, states)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.HostTimeout(msg)


def __hosts_in_states(hosts, con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin'), **states):

    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh, use_telnet=use_telnet,
                                           con_telnet=con_telnet, auth_info=auth_info))
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
              use_telnet=False, con_telnet=None, fail_ok=False, check_first=True, swact=False,
              check_cpe_alarm=True, auth_info=Tenant.get('admin')):
    """
    lock a host.

    Args:
        host (str): hostname or id in string format
        force (bool):
        lock_timeout (int): max time in seconds waiting for host to goto locked state after locking attempt.
        timeout (int): how many seconds to wait for host to go online after lock
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        fail_ok (bool):
        check_first (bool):
        swact (bool): whether to check if host is active controller and do a swact before attempt locking
        check_cpe_alarm (bool): whether to wait for cpu usage alarm gone before locking
        auth_info

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
    # FIXME temp workaround
    if 'controller' in host and not fail_ok and not use_telnet \
            and system_helper.is_two_node_cpe(con_ssh=con_ssh, auth_info=auth_info):
        from keywords.kube_helper import get_openstack_pods_info
        if get_openstack_pods_info(pod_names='mariadb', fail_ok=True, con_ssh=con_ssh):
            from pytest import skip
            skip("mariadb issue. Skip without testing for now.")

    host_avail, host_admin = get_hostshow_values(host, ('availability', 'administrative'), rtn_list=True,
                                                 con_ssh=con_ssh, auth_info=auth_info,
                                                 use_telnet=use_telnet, con_telnet=con_telnet)
    if host_avail in [HostAvailState.OFFLINE, HostAvailState.FAILED]:
        LOG.warning("Host in offline or failed state before locking!")

    if check_first and host_admin == 'locked':
        msg = "{} already locked. Do nothing.".format(host)
        LOG.info(msg)
        return -1, msg

    is_aio_dup = system_helper.is_two_node_cpe(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                               auth_info=auth_info)

    if swact:
        if is_active_controller(host, con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                auth_info=auth_info) and \
                len(system_helper.get_controllers(con_ssh=con_ssh, auth_info=auth_info, use_telnet=use_telnet,
                                                  con_telnet=con_telnet, operational=HostOperState.ENABLED)) > 1:
            LOG.info("{} is active controller, swact first before attempt to lock.".format(host))
            swact_host(host, con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)
            if is_aio_dup:
                time.sleep(90)

    if check_cpe_alarm and is_aio_dup:
        LOG.info("For AIO-duplex, wait for cpu usage high alarm gone on active controller before locking standby")
        active_con = system_helper.get_active_controller_name(con_ssh=con_ssh, use_telnet=use_telnet,
                                                              con_telnet=con_telnet, auth_info=auth_info)
        entity_id = 'host={}'.format(active_con)
        system_helper.wait_for_alarms_gone([(EventLogID.CPU_USAGE_HIGH, entity_id)], check_interval=45,
                                           fail_ok=fail_ok, con_ssh=con_ssh, timeout=300, use_telnet=use_telnet,
                                           con_telnet=con_telnet, auth_info=auth_info)

    positional_arg = host
    extra_msg = ''
    if force:
        positional_arg += ' --force'
        extra_msg = 'force '

    LOG.info("Locking {}...".format(host))
    exitcode, output = cli.system('host-lock', positional_arg, ssh_client=con_ssh, fail_ok=fail_ok,
                                  auth_info=auth_info, rtn_list=True, use_telnet=use_telnet,
                                  con_telnet=con_telnet)

    if exitcode == 1:
        return 1, output

    table_ = table_parser.table(output)
    task_val = table_parser.get_value_two_col_table(table_, field='task')
    admin_val = table_parser.get_value_two_col_table(table_, field='administrative')

    if admin_val != HostAdminState.LOCKED:
        if 'Locking' not in task_val:
            wait_for_host_values(host=host, timeout=30, check_interval=0, fail_ok=True, task='Locking', con_ssh=con_ssh,
                                 use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)

        # Wait for task complete. If task stucks, fail the test regardless. Perhaps timeout needs to be increased.
        wait_for_host_values(host=host, timeout=lock_timeout, task='', fail_ok=False, con_ssh=con_ssh,
                             use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)

        if not wait_for_host_values(host, timeout=20, administrative=HostAdminState.LOCKED, con_ssh=con_ssh,
                                    use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info):

            #  vim_progress_status | Lock of host compute-0 rejected because there are no other hypervisors available.
            vim_status = get_hostshow_value(host, field='vim_progress_status', auth_info=auth_info, con_ssh=con_ssh)
            if re.search('ock .* host .* rejected.*', vim_status):
                msg = "Lock host {} is rejected. Details in host-show vim_process_status.".format(host)
                code = 4
            elif re.search('Migrate of instance .* from host .* failed.*', vim_status):
                msg = "Lock host {} failed due to migrate vm failed. Details in host-show vm_process_status.".format(
                    host)
                code = 5
            else:
                msg = "Host is not in locked state"
                code = 2

            if fail_ok:
                return code, msg
            raise exceptions.HostPostCheckFailed(msg)

    LOG.info("{} is {}locked. Waiting for it to go Online...".format(host, extra_msg))

    if wait_for_host_values(host, timeout=timeout, availability=HostAvailState.ONLINE, auth_info=auth_info,
                            con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet):
        # ensure the online status lasts for more than 5 seconds. Sometimes host goes online then offline to reboot..
        time.sleep(5)
        if wait_for_host_values(host, timeout=timeout, availability=HostAvailState.ONLINE, auth_info=auth_info,
                                con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet):
            if wait_for_host_values(host, timeout=HostTimeout.TASK_CLEAR, task='', auth_info=auth_info,
                                    con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet):
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


def wait_for_ssh_disconnect(ssh=None, timeout=120, check_interval=3, fail_ok=False):
    if ssh is None:
        ssh = ControllerClient.get_active_controller()

    end_time = time.time() + timeout
    while ssh._is_connected(fail_ok=True):
        if time.time() > end_time:
            if fail_ok:
                return False
            raise exceptions.HostTimeout("Timed out waiting {} ssh to disconnect".format(ssh.host))

        time.sleep(check_interval)

    LOG.info("ssh to {} disconnected".format(ssh.host))
    return True


def _wait_for_simplex_reconnect(con_ssh=None, timeout=HostTimeout.CONTROLLER_UNLOCK, use_telnet=False,
                                con_telnet=None, auth_info=Tenant.get('admin'), duplex_direct=False):
    time.sleep(30)
    if not use_telnet:
        if not con_ssh:
            con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
            con_ssh = ControllerClient.get_active_controller(name=con_name)

        wait_for_ssh_disconnect(ssh=con_ssh, check_interval=10, timeout=300)
        time.sleep(30)
        con_ssh.connect(retry=True, retry_timeout=timeout)
        ControllerClient.set_active_controller(con_ssh)
    else:
        if not con_telnet:
            raise ValueError("con_telnet has to be provided when use_telnet=True.")
        con_telnet.expect(["ogin:"], HostTimeout.CONTROLLER_UNLOCK)
        con_telnet.login()
        con_telnet.exec_cmd("xterm")

    if not duplex_direct:
        # Give it sometime before openstack cmds enables on after host
        _wait_for_openstack_cli_enable(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                       auth_info=auth_info, fail_ok=False, timeout=timeout, check_interval=10,
                                       reconnect=True, single_node=True)
        time.sleep(10)
        LOG.info("Re-connected via ssh and openstack CLI enabled")


def unlock_host(host, timeout=HostTimeout.CONTROLLER_UNLOCK, available_only=False, fail_ok=False, con_ssh=None,
                use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin'), check_hypervisor_up=True,
                check_webservice_up=True, check_subfunc=True, check_first=True, con0_install=False):
    """
    Unlock given host
    Args:
        host (str):
        timeout (int): MAX seconds to wait for host to become available or degraded after unlocking
        available_only(bool): if True, wait for host becomes Available after unlock; otherwise wait for either
            Degraded or Available
        fail_ok (bool):
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        auth_info (dict):
        check_hypervisor_up (bool): Whether to check if host is up in nova hypervisor-list
        check_webservice_up (bool): Whether to check if host's web-service is active in system servicegroup-list
        check_subfunc (bool): whether to check subfunction_oper and subfunction_avail for CPE system
        check_first (bool): whether to check host state before unlock.
        con0_install (bool)

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
        (8, "Failed to wait for host to reach Available state after unlocked to Degraded state")
                # only applicable if fail_ok and available_only are True
        (9, "Host subfunctions operational and availability are not enable and available system host-show") # CPE only
        (10, "<host> is not ready in kubectl get nodes after unlock")

    """
    LOG.info("Unlocking {}...".format(host))
    if not use_telnet and not con_ssh:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    if check_first:
        if get_hostshow_value(host, 'availability', con_ssh=con_ssh, use_telnet=use_telnet, auth_info=auth_info,
                              con_telnet=con_telnet,) in [HostAvailState.OFFLINE, HostAvailState.FAILED]:
            LOG.info("Host is offline or failed, waiting for it to go online, available or degraded first...")
            wait_for_host_values(host, availability=[HostAvailState.AVAILABLE, HostAvailState.ONLINE,
                                                     HostAvailState.DEGRADED], con_ssh=con_ssh,
                                 use_telnet=use_telnet, con_telnet=con_telnet, fail_ok=False, auth_info=auth_info)

        if get_hostshow_value(host, 'administrative', con_ssh=con_ssh, use_telnet=use_telnet, auth_info=auth_info,
                              con_telnet=con_telnet) == HostAdminState.UNLOCKED:
            message = "Host already unlocked. Do nothing"
            LOG.info(message)
            return -1, message

    is_simplex = system_helper.is_simplex(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                          auth_info=auth_info)

    exitcode, output = cli.system('host-unlock', host, ssh_client=con_ssh, use_telnet=use_telnet, auth_info=auth_info,
                                  con_telnet=con_telnet, rtn_list=True, fail_ok=fail_ok, timeout=60)
    if exitcode == 1:
        return 1, output

    if is_simplex or con0_install:
        time.sleep(120)
        _wait_for_simplex_reconnect(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info,
                                    timeout=timeout)

    if not wait_for_host_values(host, timeout=60, administrative=HostAdminState.UNLOCKED, con_ssh=con_ssh,
                                use_telnet=use_telnet, con_telnet=con_telnet, fail_ok=fail_ok, auth_info=auth_info):
        return 2, "Host is not in unlocked state"

    if not wait_for_host_values(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
                                use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info,
                                availability=[HostAvailState.AVAILABLE, HostAvailState.DEGRADED]):
        return 3, "Host state did not change to available or degraded within timeout"

    if not wait_for_host_values(host, timeout=HostTimeout.TASK_CLEAR, fail_ok=fail_ok, con_ssh=con_ssh,
                                auth_info=auth_info, use_telnet=use_telnet, con_telnet=con_telnet, task=''):
        return 5, "Task is not cleared within {} seconds after host goes available".format(HostTimeout.TASK_CLEAR)

    if get_hostshow_value(host, 'availability', con_ssh=con_ssh, use_telnet=use_telnet, auth_info=auth_info,
                          con_telnet=con_telnet) == HostAvailState.DEGRADED:
        if not available_only:
            LOG.warning("Host is in degraded state after unlocked.")
            return 4, "Host is in degraded state after unlocked."
        else:
            if not wait_for_host_values(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
                                        use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info,
                                        availability=HostAvailState.AVAILABLE):
                err_msg = "Failed to wait for host to reach Available state after unlocked to Degraded state"
                LOG.warning(err_msg)
                return 8, err_msg

    if check_hypervisor_up or check_webservice_up or check_subfunc:

        table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh, auth_info=auth_info,
                                               use_telnet=use_telnet, con_telnet=con_telnet))

        subfunc = table_parser.get_value_two_col_table(table_, 'subfunctions')
        personality = table_parser.get_value_two_col_table(table_, 'personality')
        string_total = subfunc + personality

        is_controller = 'controller' in string_total
        is_compute = bool(re.search('compute|worker', string_total))

        if check_hypervisor_up and is_compute:
            if not wait_for_hypervisors_up(host, fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info,
                                           use_telnet=use_telnet, con_telnet=con_telnet,
                                           timeout=HostTimeout.HYPERVISOR_UP)[0]:
                return 6, "Host is not up in nova hypervisor-list"

            if not is_simplex:
                # wait_for_tasks_affined(host, con_ssh=con_ssh)
                # Do not fail the test due to task affining incomplete for now to unblock test case.
                # Workaround for CGTS-10715.
                wait_for_tasks_affined(host, con_ssh=con_ssh, fail_ok=True)

        if check_webservice_up and is_controller:
            if not wait_for_webservice_up(host, fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info,
                                          use_telnet=use_telnet, con_telnet=con_telnet, timeout=300)[0]:
                return 7, "Host web-services is not active in system servicegroup-list"

        if check_subfunc and is_controller and is_compute:
            # wait for subfunction states to be operational enabled and available
            if not wait_for_host_values(host, timeout=90, fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info,
                                        use_telnet=use_telnet, con_telnet=con_telnet,
                                        subfunction_oper=HostOperState.ENABLED,
                                        subfunction_avail=HostAvailState.AVAILABLE):
                err_msg = "Host subfunctions operational and availability did not change to enabled and available" \
                          " within timeout"
                LOG.warning(err_msg)
                return 9, err_msg

    if get_hostshow_value(host, 'availability', con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                          auth_info=auth_info) == HostAvailState.DEGRADED:
        if not available_only:
            LOG.warning("Host is in degraded state after unlocked.")
            return 4, "Host is in degraded state after unlocked."
        else:
            if not wait_for_host_values(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
                                        use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info,
                                        availability=HostAvailState.AVAILABLE):
                err_msg = "Failed to wait for host to reach Available state after unlocked to Degraded state"
                LOG.warning(err_msg)
                return 8, err_msg

    from keywords.kube_helper import wait_for_nodes_ready
    if not use_telnet and not wait_for_nodes_ready(hosts=host, timeout=40, con_ssh=con_ssh, fail_ok=fail_ok)[0]:
        err_msg = "{} is not ready in kubectl get nodes after unlock".format(host)
        return 10, err_msg

    LOG.info("Host {} is successfully unlocked and in available state".format(host))
    return 0, "Host is unlocked and in available state."


def wait_for_tasks_affined(host, timeout=180, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    if system_helper.is_simplex(con_ssh=con_ssh, auth_info=auth_info):
        return True

    LOG.info("Check {} non-existent on {}".format(PLATFORM_AFFINE_INCOMPLETE, host))
    if not con_ssh:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    with ssh_to_host(host, con_ssh=con_ssh) as host_ssh:
        end_time = time.time() + timeout
        while time.time() < end_time:
            if not host_ssh.file_exists(PLATFORM_AFFINE_INCOMPLETE):
                LOG.info("{} platform tasks re-affined successfully".format(host))
                return True
            time.sleep(5)

    err = "{} did not clear on {}".format(PLATFORM_AFFINE_INCOMPLETE, host)
    if fail_ok:
        LOG.warning(err)
        return False
    raise exceptions.HostError(err)


def unlock_hosts(hosts, timeout=HostTimeout.CONTROLLER_UNLOCK, fail_ok=True, con_ssh=None,
                 auth_info=Tenant.get('admin'), check_hypervisor_up=False, check_webservice_up=False,
                 use_telnet=False, con_telnet=None):

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
        use_telnet
        con_telnet


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
        (7, "Host platform tasks affining incomplete")
        (8, "Host status not ready in kubectl get nodes")

    """
    if not hosts:
        raise ValueError("No host(s) provided to unlock.")

    LOG.info("Unlocking {}...".format(hosts))

    if isinstance(hosts, str):
        hosts = [hosts]

    res = {}
    hosts_to_unlock = list(set(hosts))
    for host in hosts:
        if get_hostshow_value(host, 'administrative', con_ssh=con_ssh, use_telnet=use_telnet, auth_info=auth_info,
                              con_telnet=con_telnet) == HostAdminState.UNLOCKED:
            message = "Host already unlocked. Do nothing"

            res[host] = -1, message
            hosts_to_unlock.remove(host)

    if not hosts_to_unlock:
        LOG.info("Host(s) already unlocked. Do nothing.")
        return res

    if len(hosts_to_unlock) != len(hosts):
        LOG.info("Some host(s) already unlocked. Unlocking the rest: {}".format(hosts_to_unlock))

    is_simplex = system_helper.is_simplex(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                          auth_info=auth_info)
    hosts_to_check = []
    for host in hosts_to_unlock:
        exitcode, output = cli.system('host-unlock', host, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                                      fail_ok=fail_ok, timeout=60, use_telnet=use_telnet,
                                      con_telnet=con_telnet)
        if exitcode == 1:
            res[host] = 1, output
        else:
            hosts_to_check.append(host)

    if not hosts_to_check:
        LOG.warning("Unlock host(s) rejected: {}".format(hosts_to_unlock))
        return res

    if is_simplex:
        _wait_for_simplex_reconnect(con_ssh=con_ssh, timeout=HostTimeout.CONTROLLER_UNLOCK, auth_info=auth_info,
                                    use_telnet=use_telnet, con_telnet=con_telnet)

    if not wait_for_hosts_states(hosts_to_check, timeout=60, administrative=HostAdminState.UNLOCKED, con_ssh=con_ssh,
                                 use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info):
        LOG.warning("Some host(s) not in unlocked states after 60 seconds.")

    if not wait_for_hosts_states(hosts_to_check, timeout=timeout, check_interval=10, con_ssh=con_ssh,
                                 use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info,
                                 availability=[HostAvailState.AVAILABLE, HostAvailState.DEGRADED]):
        LOG.warning("Some host(s) state did not change to available or degraded within timeout")

    hosts_tab = table_parser.table(cli.system('host-list --nowrap', ssh_client=con_ssh, auth_info=auth_info))
    hosts_to_check_tab = table_parser.filter_table(hosts_tab, hostname=hosts_to_check)
    hosts_unlocked = table_parser.get_values(hosts_to_check_tab, target_header='hostname', administrative='unlocked')
    hosts_not_unlocked = list(set(hosts_to_check) - set(hosts_unlocked))
    hosts_unlocked_tab = table_parser.filter_table(hosts_to_check_tab, hostname=hosts_unlocked)
    hosts_avail = table_parser.get_values(hosts_unlocked_tab, 'hostname', availability=HostAvailState.AVAILABLE)
    hosts_degrd = table_parser.get_values(hosts_unlocked_tab, 'hostname', availability=HostAvailState.DEGRADED)
    hosts_other = list(set(hosts_unlocked) - set(hosts_avail) - set(hosts_degrd))

    for host in hosts_not_unlocked:
        res[host] = 2, "Host is not in unlocked state."
    for host in hosts_degrd:
        res[host] = 4, "Host is in degraded state after unlocked."
    for host in hosts_other:
        res[host] = 3, "Host is not in available or degraded state."

    if hosts_avail and (check_hypervisor_up or check_webservice_up):

        all_nodes = system_helper.get_hostnames_per_personality(con_ssh=con_ssh, use_telnet=use_telnet,
                                                                auth_info=auth_info, con_telnet=con_telnet)
        computes = list(set(hosts_avail) & set(all_nodes['compute']))
        controllers = list(set(hosts_avail) & set(all_nodes['controller']))
        if system_helper.is_small_footprint(con_ssh, auth_info=auth_info):
            computes += controllers

        if check_hypervisor_up and computes:
            hosts_hypervisordown = wait_for_hypervisors_up(computes, fail_ok=fail_ok, con_ssh=con_ssh,
                                                           use_telnet=use_telnet, con_telnet=con_telnet,
                                                           timeout=HostTimeout.HYPERVISOR_UP,
                                                           auth_info=auth_info)[1]
            for host in hosts_hypervisordown:
                res[host] = 5, "Host is not up in nova hypervisor-list"
                hosts_avail = list(set(hosts_avail) - set(hosts_hypervisordown))

        if check_webservice_up and controllers:
            hosts_webdown = wait_for_webservice_up(controllers, fail_ok=fail_ok, con_ssh=con_ssh, timeout=180,
                                                   use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)[1]
            for host in hosts_webdown:
                res[host] = 6, "Host web-services is not active in system servicegroup-list"
            hosts_avail = list(set(hosts_avail) - set(hosts_webdown))

        hosts_affine_incomplete = []
        for host in list(set(computes) & set(hosts_avail)):
            if not wait_for_tasks_affined(host, fail_ok=True, auth_info=auth_info):
                msg = "Host {} platform tasks affining incomplete".format(host)
                hosts_affine_incomplete.append(host)

                # Do not fail the test due to task affining incomplete for now to unblock test case.
                # Workaround for CGTS-10715.
                LOG.error(msg)
                # res[host] = 7,
        # hosts_avail = list(set(hosts_avail) - set(hosts_affine_incomplete))

    if hosts_avail and not use_telnet:
        from keywords.kube_helper import wait_for_nodes_ready
        hosts_not_ready = wait_for_nodes_ready(hosts=hosts_avail, timeout=30, con_ssh=con_ssh, fail_ok=fail_ok)[1]
        if hosts_not_ready:
            hosts_avail = list(set(hosts_avail) - set(hosts_not_ready))
            for host in hosts_not_ready:
                res[host] = 8, "Host status not ready in kubectl get nodes"

    for host in hosts_avail:
        res[host] = 0, "Host is unlocked and in available state."

    if not len(res) == len(hosts):
        raise exceptions.CommonError("Something wrong with the keyword. Number of hosts in result is incorrect.")

    if not fail_ok:
        for host in res:
            if res[host][0] not in [-1, 0, 4]:
                raise exceptions.HostPostCheckFailed(" Not all host(s) unlocked successfully. Detail: {}".format(res))

    LOG.info("Results for unlocking hosts: {}".format(res))
    return res


def get_hostshow_value(host, field, merge_lines=False, con_ssh=None, use_telnet=False, con_telnet=None,
                       auth_info=Tenant.get('admin')):
    """
    Retrieve the value of certain field in the system host-show from get_hostshow_values()

    Examples:
        admin_state = get_hostshow_value(host, 'administrative', con_ssh=con_ssh)
        would return if host is 'locked' or 'unlocked'

    Args:
        host (str): hostname to check for
        field (str): The field of the host-show table
        merge_lines (bool)
        con_ssh (SSHClient)
        use_telnet
        con_telnet
        auth_info

    Returns:
        The value of the specified field for given host

    """
    return get_hostshow_values(host, field, merge_lines=merge_lines, con_ssh=con_ssh,
                               use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)[field]


def get_hostshow_values(host, fields, merge_lines=False, con_ssh=None, use_telnet=False, con_telnet=None,
                        auth_info=Tenant.get('admin'), rtn_list=False):
    """
    Get values of specified fields for given host

    Args:
        host (str):
        con_ssh (SSHClient):
        fields (list|str|tuple): field names
        merge_lines (bool)
        use_telnet
        con_telnet
        auth_info
        rtn_list

    Returns (dict): {field1: value1, field2: value2, ...}

    """

    table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh, use_telnet=use_telnet,
                                           con_telnet=con_telnet, auth_info=auth_info))
    if not fields:
        raise ValueError("At least one field name needs to provided via *fields")

    if isinstance(fields, str):
        fields = [fields]

    res_dict = {}
    res_list = []
    for field in fields:
        val = table_parser.get_value_two_col_table(table_, field, merge_lines=merge_lines)
        if rtn_list:
            res_list.append(val)
        else:
            res_dict[field] = val

    res = res_list if rtn_list else res_dict
    return res


def _wait_for_openstack_cli_enable(con_ssh=None, timeout=HostTimeout.SWACT, fail_ok=False, check_interval=10,
                                   reconnect=True, use_telnet=False,  con_telnet=None, single_node=None,
                                   auth_info=Tenant.get('admin')):
    """
    Wait for 'system show' cli to work on active controller. Also wait for host task to clear and subfunction ready.
    Args:
        con_ssh:
        timeout:
        fail_ok:
        check_interval:
        reconnect:
        use_telnet:
        con_telnet:
        auth_info

    Returns (bool):

    """
    from keywords import container_helper

    if not use_telnet and not con_ssh:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    def check_sysinv_cli():

        cli.system('show', ssh_client=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                   timeout=timeout, auth_info=auth_info)
        time.sleep(10)
        active_con = system_helper.get_active_controller_name(con_ssh=con_ssh, use_telnet=use_telnet,
                                                              con_telnet=con_telnet, auth_info=auth_info)

        if ((single_node or (single_node is None and system_helper.is_simplex())) and
                get_hostshow_value(host=active_con, field='administrative') == HostAdminState.LOCKED):
            LOG.info("Simplex system in locked state. Wait for task to clear only")
            wait_for_host_values(host=active_con, timeout=HostTimeout.LOCK, task='', con_ssh=con_ssh,
                                 use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)
        else:
            wait_for_task_clear_and_subfunction_ready(hosts=active_con, con_ssh=con_ssh, use_telnet=use_telnet,
                                                      con_telnet=con_telnet, auth_info=auth_info)
        is_openstack_applied = container_helper.is_stx_openstack_deployed(con_ssh=con_ssh, auth_info=auth_info,
                                                                          use_telnet=use_telnet, con_telnet=con_telnet)
        LOG.info("system cli and subfunction enabled")
        return is_openstack_applied

    def check_nova_cli():
        cli.nova('list', ssh_client=con_ssh, use_telnet=use_telnet, con_telnet=con_ssh, timeout=timeout)
        LOG.info("nova cli enabled")

    cli_enable_end_time = time.time() + timeout
    LOG.info("Waiting for system cli and subfunctions to be ready and nova cli (if stx-openstack applied) to be "
             "enabled on active controller")
    check_nova = None
    while time.time() < cli_enable_end_time:
        try:
            if check_nova is None:
                check_nova = check_sysinv_cli()
            if check_nova:
                check_nova_cli()
            return True
        except:
            if not use_telnet and not con_ssh._is_connected():
                if reconnect:
                    LOG.info("con_ssh connection lost while waiting for system to recover. Attempt to reconnect...")
                    con_ssh.connect(retry_timeout=timeout, retry=True)
                else:
                    LOG.error("system disconnected")
                    if fail_ok:
                        return False
                    raise

            time.sleep(check_interval)

    err_msg = "Timed out waiting for system to recover. Time waited: {}".format(timeout)
    if fail_ok:
        LOG.warning(err_msg)
        return False
    raise TimeoutError(err_msg)


def wait_for_host_values(host, timeout=HostTimeout.REBOOT, check_interval=3, strict=True, regex=False, fail_ok=True,
                         con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin'), **kwargs):
    """
    Wait for host values via system host-show
    Args:
        host:
        timeout:
        check_interval:
        strict:
        regex:
        fail_ok:
        con_ssh:
        use_telnet:
        con_telnet:
        auth_info
        **kwargs: key/value pair to wait for.

    Returns:

    """
    if not kwargs:
        raise ValueError("Expected host state(s) has to be specified via keyword argument states")

    LOG.info("Waiting for {} to reach state(s) - {}".format(host, kwargs))
    end_time = time.time() + timeout
    last_vals = {}
    for field in kwargs:
        last_vals[field] = None

    while time.time() < end_time:
        table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh, auth_info=auth_info,
                                               use_telnet=use_telnet, con_telnet=con_telnet))
        for field, expt_vals in kwargs.items():
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
            LOG.info("{} is in state(s): {}".format(host, kwargs))
            return True
        time.sleep(check_interval)
    else:
        msg = "{} did not reach state(s) within {}s - {}".format(host, timeout, kwargs)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.TimeoutException(msg)


def swact_host(hostname=None, swact_start_timeout=HostTimeout.SWACT, swact_complete_timeout=HostTimeout.SWACT,
               fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None, use_telnet=False, con_telnet=None,
               wait_for_alarm=False):
    """
    Swact active controller from given hostname.

    Args:
        hostname (str|None): When None, active controller will be used for swact.
        swact_start_timeout (int): Max time to wait between cli executes and swact starts
        swact_complete_timeout (int): Max time to wait for swact to complete after swact started
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info
        use_telnet
        con_telnet
        wait_for_alarm (bool),: whether to wait for pre-swact alarms after swact

    Returns (tuple): (rtn_code(int), msg(str))      # 1, 3, 4 only returns when fail_ok=True
        (0, "Active controller is successfully swacted.")
        (1, <stderr>)   # swact host cli rejected
        (2, "<hostname> is not active controller host, thus swact request failed as expected.")
        (3, "Swact did not start within <swact_start_timeout>")
        (4, "Active controller did not change after swact within <swact_complete_timeou>")

    """
    active_host = system_helper.get_active_controller_name(con_ssh=con_ssh, use_telnet=use_telnet,
                                                           con_telnet=con_telnet, auth_info=auth_info)
    if hostname is None:
        hostname = active_host

    pre_alarms = None
    if wait_for_alarm:
        pre_alarms = system_helper.get_alarms(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet)

    exitcode, msg = cli.system('host-swact', hostname, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True, use_telnet=use_telnet, con_telnet=con_telnet)
    if exitcode == 1:
        return 1, msg

    if hostname != active_host:
        wait_for_host_values(hostname, timeout=swact_start_timeout, fail_ok=False, con_ssh=con_ssh, auth_info=auth_info,
                             use_telnet=use_telnet, con_telnet=con_telnet, task='')
        return 2, "{} is not active controller host, thus swact request failed as expected.".format(hostname)

    if use_telnet:
        rtn = wait_for_swact_complete_tel_session(hostname, swact_start_timeout=swact_start_timeout,
                                                  swact_complete_timeout=swact_complete_timeout,
                                                  fail_ok=fail_ok)
    else:
        rtn = wait_for_swact_complete(hostname, con_ssh, swact_start_timeout=swact_start_timeout, auth_info=auth_info,
                                      swact_complete_timeout=swact_complete_timeout, fail_ok=fail_ok)
    if rtn[0] == 0:
        try:
            if use_telnet:
                new_active_host = 'controller-1' if hostname == 'controller-0' else 'controller-0'
                telnet_session = get_host_telnet_session(new_active_host)
                res = wait_for_webservice_up(new_active_host, use_telnet=True, con_telnet=telnet_session,
                                             fail_ok=fail_ok)[0]
                if not res:
                    return 5, "Web-services for new controller is not active"

                hypervisor_up_res = wait_for_hypervisors_up(hostname, fail_ok=fail_ok, use_telnet=True,
                                                            con_telnet=telnet_session)
                if not hypervisor_up_res:
                    return 6, "Hypervisor state is not up for {} after swacted".format(hostname)
            else:
                res = wait_for_webservice_up(system_helper.get_active_controller_name(), fail_ok=fail_ok,
                                             auth_info=auth_info, con_ssh=con_ssh)[0]
                if not res:
                    return 5, "Web-services for new controller is not active"

                if system_helper.is_two_node_cpe(con_ssh=con_ssh, auth_info=auth_info):
                    hypervisor_up_res = wait_for_hypervisors_up(hostname, fail_ok=fail_ok, con_ssh=con_ssh,
                                                                auth_info=auth_info)
                    if not hypervisor_up_res:
                        return 6, "Hypervisor state is not up for {} after swacted".format(hostname)

                    for host in ('controller-0', 'controller-1'):
                        # task_aff_res = wait_for_tasks_affined(host, con_ssh=con_ssh, fail_ok=False,
                        #                                       auth_info=auth_info, timeout=300)

                        task_aff_res = wait_for_tasks_affined(host, con_ssh=con_ssh, fail_ok=True,
                                                              auth_info=auth_info, timeout=300)
                        if not task_aff_res:
                            msg = "tasks affining incomplete on {} after swact from {}".format(host, hostname)
                            # Do not fail the test due to task affining incomplete for now to unblock test case.
                            # Workaround for CGTS-10715.
                            LOG.error(msg=msg)
                            return 7, msg
        finally:
            # After swact, there is a delay for alarms to re-appear on new active controller, thus the wait.
            if pre_alarms:
                post_alarms = system_helper.get_alarms(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet)
                for alarm in pre_alarms:
                    if alarm not in post_alarms:
                        alarm_id, entity_id = alarm.split('::::')
                        system_helper.wait_for_alarm(alarm_id=alarm_id, entity_id=entity_id, fail_ok=True, timeout=300,
                                                     check_interval=15)

    return rtn


def wait_for_swact_complete(before_host, con_ssh=None, swact_start_timeout=HostTimeout.SWACT,
                            swact_complete_timeout=HostTimeout.SWACT, fail_ok=True, auth_info=Tenant.get('admin')):
    """
    Wait for swact to start and complete
    NOTE: This function assumes swact command was run from ssh session using floating ip!!

    Args:
        before_host (str): Active controller name before swact request
        con_ssh (SSHClient):
        swact_start_timeout (int): Max time to wait between cli executs and swact starts
        swact_complete_timeout (int): Max time to wait for swact to complete after swact started
        fail_ok
        auth_info

    Returns (tuple):
        (0, "Active controller is successfully swacted.")
        (3, "Swact did not start within <swact_start_timeout>")     # returns when fail_ok=True
        (4, "Active controller did not change after swact within <swact_complete_timeou>")  # returns when fail_ok=True
        (5, "400.001 alarm is not cleared within timeout after swact")
        (6, "tasks affining incomplete on <host>")

    """
    start = time.time()
    end_swact_start = start + swact_start_timeout
    if con_ssh is None:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    while con_ssh._is_connected(fail_ok=True):
        if time.time() > end_swact_start:
            if fail_ok:
                return 3, "Swact did not start within {}".format(swact_start_timeout)
            raise exceptions.HostPostCheckFailed("Timed out waiting for swact. SSH to {} is still alive.".
                                                 format(con_ssh.host))
        time.sleep(5)

    LOG.info("ssh to {} disconnected, indicating swacting initiated.".format(con_ssh.host))

    # permission denied is received when ssh right after swact initiated. Add delay to avoid sanity failure
    time.sleep(30)
    con_ssh.connect(retry=True, retry_timeout=swact_complete_timeout-30)

    # Give it sometime before openstack cmds enables on after host
    _wait_for_openstack_cli_enable(con_ssh=con_ssh, fail_ok=False, timeout=swact_complete_timeout, auth_info=auth_info)

    after_host = system_helper.get_active_controller_name(con_ssh=con_ssh, auth_info=auth_info)
    LOG.info("Host before swacting: {}, host after swacting: {}".format(before_host, after_host))

    if before_host == after_host:
        if fail_ok:
            return 4, "Active controller did not change after swact within {}".format(swact_complete_timeout)
        raise exceptions.HostPostCheckFailed("Swact failed. Active controller host did not change")

    drbd_res = system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CON_DRBD_SYNC, entity_id=after_host,
                                                 strict=False, fail_ok=fail_ok, timeout=300, con_ssh=con_ssh,
                                                 auth_info=auth_info)
    if not drbd_res:
        return 5, "400.001 alarm is not cleared within timeout after swact"

    return 0, "Active controller is successfully swacted."


def wait_for_swact_complete_tel_session(before_host, swact_start_timeout=HostTimeout.SWACT,
                                        swact_complete_timeout=HostTimeout.SWACT, fail_ok=True):
    """
    Wait for swact to start and complete. It uses telnet session to check swact

    Args:
        before_host (str): Active controller name before swact request

        swact_start_timeout (int): Max time to wait between cli executs and swact starts
        swact_complete_timeout (int): Max time to wait for swact to complete after swact started
        fail_ok

    Returns (tuple):
        (0, "Active controller is successfully swacted.")
        (3, "No telnet session with new active host"
        (4, "Swact did not start within <swact_start_timeout>")     # returns when fail_ok=True
        (5, "Active controller did not change after swact within <swact_complete_timeou>")  # returns when fail_ok=True
        (6, "400.001 alarm is not cleared within timeout after swact")

    """

    time.sleep(60)

    new_active_controller = 'controller-1' if before_host == 'controller-0' else 'controller-0'
    host_telnet_session = get_host_telnet_session(new_active_controller)

    if host_telnet_session is None:
        err_msg = "Cannot open telnet session with new active controller {}".format(new_active_controller)
        if fail_ok:
            return 3, err_msg
        else:
            raise exceptions.HostPostCheckFailed(err_msg)

    start = time.time()
    end_swact_start = start + swact_start_timeout
    swacted = False
    while not swacted:
        host_telnet_session.write_line("source /etc/nova/openrc")
        index, match, output = host_telnet_session.expect([bytes(Prompt.ADMIN_PROMPT, 'utf-8')], timeout=2)
        if match:
            swacted = True
        if time.time() > end_swact_start:
            if fail_ok:
                return 4, "Swact did not start within {}".format(swact_start_timeout)
            raise exceptions.HostPostCheckFailed("Timed out waiting for swact.")

    time.sleep(30)

    # Give it sometime before openstack cmds enables on after host
    _wait_for_openstack_cli_enable(use_telnet=True, con_telnet=host_telnet_session)

    after_host = system_helper.get_active_controller_name(use_telnet=True, con_telnet=host_telnet_session)
    LOG.info("Host before swacting: {}, host after swacting: {}".format(before_host, after_host))

    if before_host == after_host:
        if fail_ok:
            return 5, "Active controller did not change after swact within {}".format(swact_complete_timeout)
        raise exceptions.HostPostCheckFailed("Swact failed. Active controller host did not change")

    drbd_res = system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CON_DRBD_SYNC, entity_id=after_host,
                                                 use_telnet=True, con_telnet=host_telnet_session,
                                                 strict=False, fail_ok=fail_ok, timeout=300)
    if not drbd_res:
        return 6, "400.001 alarm is not cleared within timeout after swact"

    return 0, "Active controller is successfully swacted."


def get_nova_hosts(zone='nova', status='enabled', state='up', con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get nova hosts listed in nova host-list.

    System: Regular, Small footprint

    Args:
        zone (str): returns only the hosts with specified zone
        status
        state
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): a list of hypervisors in given zone
    """
    table_ = table_parser.table(cli.nova('service-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'Host', Binary='nova-compute', zone=zone, status=status, state=state)


def wait_for_hypervisors_up(hosts, timeout=HostTimeout.HYPERVISOR_UP, check_interval=5, fail_ok=False,
                            con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Wait for given hypervisors to be up and enabled in nova hypervisor-list
    Args:
        hosts (list|str): names of the hypervisors, such as compute-0
        timeout (int):
        check_interval (int):
        fail_ok (bool):
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        auth_info

    Returns (tuple): res_bool(bool), hosts_not_up(list)
        (True, [])      # all hypervisors given are up and enabled
        (False, [<hosts_not_up>]    # some hosts are not up and enabled

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    hypervisors = get_hypervisors(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info)

    if not set(hosts) <= set(hypervisors):
        msg = "Some host(s) not in nova hypervisor-list. Host(s) given: {}. Hypervisors: {}".format(hosts, hypervisors)
        raise exceptions.HostPreCheckFailed(msg)

    hosts_to_check = list(hosts)
    LOG.info("Waiting for {} to be up in nova hypervisor-list...".format(hosts))
    end_time = time.time() + timeout
    while time.time() < end_time:
        up_hosts = get_hypervisors(state='up', status='enabled', con_ssh=con_ssh, use_telnet=use_telnet,
                                   con_telnet=con_telnet, auth_info=auth_info)
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


def wait_for_webservice_up(hosts, timeout=HostTimeout.WEB_SERVICE_UP, check_interval=3, fail_ok=False, con_ssh=None,
                           use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):

    if isinstance(hosts, str):
        hosts = [hosts]

    hosts_to_check = list(hosts)
    LOG.info("Waiting for {} to be active for web-service in system servicegroup-list...".format(hosts_to_check))
    end_time = time.time() + timeout

    while time.time() < end_time:

        table_ = table_parser.table(cli.system('servicegroup-list', ssh_client=con_ssh, auth_info=auth_info,
                                               use_telnet=use_telnet, con_telnet=con_telnet))
        table_ = table_parser.filter_table(table_, service_group_name='web-services')
        # need to check for strict True because 'go-active' state is not 'active' state
        active_hosts = table_parser.get_values(table_, 'hostname', state='active', strict=True)

        for host in hosts:
            if host in active_hosts and host in hosts_to_check:
                hosts_to_check.remove(host)

        if not hosts_to_check:
            msg = "Host(s) {} are active for web-service in system servicegroup-list".format(hosts)
            LOG.info(msg)
            return True, hosts_to_check

        time.sleep(check_interval)
    else:
        msg = "Host(s) {} are not active for web-service in system servicegroup-list within timeout".\
            format(hosts_to_check)
        if fail_ok:
            LOG.warning(msg)
            return False, hosts_to_check
        raise exceptions.HostTimeout(msg)


def get_hosts_in_aggregate(aggregate, con_ssh=None, auth_info=Tenant.get('admin')):
    if 'image' in aggregate:
        aggregate = 'local_storage_image_hosts'
    elif 'remote' in aggregate:
        aggregate = 'remote_storage_hosts'
    else:
        aggregates_tab = table_parser.table(cli.nova('aggregate-list', ssh_client=con_ssh,
                                                     auth_info=auth_info))
        avail_aggregates = table_parser.get_column(aggregates_tab, 'Name')
        if aggregate not in avail_aggregates:
            LOG.warning("Requested aggregate {} is not in nova aggregate-list".format(aggregate))
            return []

    table_ = table_parser.table(cli.nova('aggregate-show', aggregate, ssh_client=con_ssh,
                                         auth_info=auth_info))
    hosts = table_parser.get_values(table_, 'Hosts', Name=aggregate)[0]
    hosts = hosts.split(',')
    if len(hosts) == 0 or hosts == ['']:
        hosts = []
    else:
        hosts = [eval(host) for host in hosts]

    LOG.info("Hosts in {} aggregate: {}".format(aggregate, hosts))
    return hosts


def get_hosts_in_storage_backing(storage_backing='local_image', up_only=True, hosts=None, con_ssh=None,
                                 auth_info=Tenant.get('admin')):
    """
    Return a list of hosts that supports the given storage backing.

    System: Regular, Small footprint

    Args:
        hosts (None|list|tuple): hosts to check
        storage_backing (str): 'local_image', or 'remote'
        up_only (bool): whether to return only up hypervisors
        con_ssh (SSHClient):
        auth_info

    Returns (tuple):
        such as ('compute-0', 'compute-2', 'compute-1', 'compute-3')
        or () if no host supports this storage backing

    """
    storage_backing = storage_backing.strip().lower()
    if 'image' in storage_backing:
        storage_backing = 'local_image'
    elif 'remote' in storage_backing:
        storage_backing = 'remote'
    else:
        raise ValueError("Invalid storage backing provided. "
                         "Please use one of these: 'local_image', 'remote'")

    hosts_per_backing = get_hosts_per_storage_backing(up_only=up_only, con_ssh=con_ssh, auth_info=auth_info,
                                                      hosts=hosts)
    return hosts_per_backing[storage_backing]


def get_nova_host_with_min_or_max_vms(rtn_max=True, hosts=None, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get name of a compute host with least of most vms.

    Args:
        rtn_max (bool): when True, return hostname with the most number of vms on it; otherwise return hostname with
            least number of vms on it.
        hosts (list): choose from given hosts. If set to None, choose from all up hypervisors
        con_ssh (SSHClient):
        auth_info

    Returns (str): hostname

    """
    hosts_to_check = get_hypervisors(state='up', status='enabled', con_ssh=con_ssh, auth_info=auth_info)
    if hosts:
        if isinstance(hosts, str):
            hosts = [hosts]
        hosts_to_check = list(set(hosts_to_check) & set(hosts))

    table_ = system_helper.get_vm_topology_tables('computes', auth_info=auth_info)[0]

    vms_nums = [int(table_parser.get_values(table_, 'servers', Host=host)[0]) for host in hosts_to_check]

    if rtn_max:
        index = vms_nums.index(max(vms_nums))
    else:
        index = vms_nums.index(min(vms_nums))

    return hosts_to_check[index]


def get_up_hypervisors(con_ssh=None, auth_info=Tenant.get('admin')):
    return get_hypervisors(state='up', status='enabled', con_ssh=con_ssh, auth_info=auth_info)


def get_hypervisors(state=None, status=None, con_ssh=None, use_telnet=False, con_telnet=None,
                    rtn_val='Hypervisor hostname', auth_info=Tenant.get('admin')):
    """
    Return a list of hypervisors names in specified state and status. If None is set to state and status,
    all hypervisors will be returned.

    System: Regular

    Args:
        state (str): e.g., 'up', 'down'
        status (str): e.g., 'enabled', 'disabled'
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        rtn_val (str): target header. e.g., ID, Hypervisor hostname
        auth_info

    Returns (list): a list of hypervisor names. Return () if no match found.
        Always return () for small footprint lab. i.e., do not work with small footprint lab
    """
    table_ = table_parser.table(cli.nova('hypervisor-list', auth_info=auth_info, ssh_client=con_ssh,
                                         use_telnet=use_telnet, con_telnet=con_telnet))
    target_header = rtn_val

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


def get_values_virsh_xmldump(instance_name, host_ssh, tag_paths, target_type='element'):
    """

    Args:
        instance_name (str): instance_name of a vm. Such as 'instance-00000002'
        host_ssh (SSHFromSSH): ssh of the host that hosting the given instance
        tag_paths (str|list|tuple): the tag path to reach to the target element. such as 'memoryBacking/hugepages/page'
        target_type (str): 'element', 'dict', 'text'

    Returns (list): list of Elements, dictionaries, or strings based on the target_type param.

    """
    target_type = target_type.lower().strip()
    root_element = _get_element_tree_virsh_xmldump(instance_name, host_ssh)

    is_str = False
    if isinstance(tag_paths, str):
        is_str = True
        tag_paths = [tag_paths]

    values_list = []
    for tag_path_ in tag_paths:
        elements = root_element.findall(tag_path_)

        if 'dict' in target_type:
            dics = []
            for element in elements:
                dics.append(element.attrib)
            values_list.append(dics)

        elif 'text' in target_type:
            texts = []
            for element in elements:
                text_list = list(element.itertext())
                if not text_list:
                    LOG.warning("No text found under tag: {}.".format(tag_path_))
                else:
                    texts.append(text_list[0])
                    if len(text_list) > 1:
                        LOG.warning(("More than one text found under tag: {}, returning the first one.".
                                     format(tag_path_)))

            values_list.append(texts)

        else:
            values_list.append(elements)

    if is_str:
        return values_list[0]
    else:
        return values_list


def _get_actual_mems(host):
    headers = ('mem_avail(MiB)', 'vm_hp_total_1G', 'vm_hp_pending_1G')
    displayed_mems = system_helper.get_host_mem_values(host=host, headers=headers, wait_for_update=False)

    actual_mems = {}
    for proc in displayed_mems:
        mem_avail, total_1g, pending_1g = displayed_mems[proc]
        actual_1g = total_1g if pending_1g is None else pending_1g

        args = '-2M {} {} {}'.format(mem_avail, host, proc)
        code, output = cli.system('host-memory-modify', args, fail_ok=True, rtn_list=True)
        if code == 0:
            raise exceptions.SysinvError('system host-memory-modify is not rejected when 2M pages exceeds mem_avail')

        # Processor 0:No available space for 2M huge page allocation, max 2M VM pages: 27464
        actual_mem = int(re.findall(r'max 2M VM pages: (\d+)', output)[0]) * 2
        actual_mems[proc] = (actual_mem, actual_1g)

    return actual_mems


def wait_for_mempage_update(host, proc_id=None, expt_1g=None, timeout=420, auth_info=Tenant.get('admin')):
    """
    Wait for host memory to be updated after modifying and unlocking host.
    Args:
        host:
        proc_id (int|list|None):
        expt_1g (int|list|None):
        timeout:
        auth_info

    Returns:

    """
    proc_id_type = type(proc_id)
    if not isinstance(expt_1g, proc_id_type):
        raise ValueError("proc_id and expt_1g have to be the same type")

    pending_2m = pending_1g = -1
    headers = ['vm_hp_total_1G', 'vm_hp_pending_1G', 'vm_hp_pending_2M']
    current_time = time.time()
    end_time = current_time + timeout
    pending_end_time = current_time + 120
    while time.time() < end_time:
        host_mems = system_helper.get_host_mem_values(host, headers, proc_id=proc_id, wait_for_update=False,
                                                      auth_info=auth_info)
        for proc in host_mems:
            current_1g, pending_1g, pending_2m = host_mems[proc]
            if not (pending_2m is None and pending_1g is None):
                break
        else:
            if time.time() > pending_end_time:
                LOG.info("Pending memories are None for at least 120 seconds")
                break
        time.sleep(15)
    else:
        err = "Pending memory after {}s. Pending 2M: {}; Pending 1G: {}".format(timeout, pending_2m, pending_1g)
        assert 0, err

    if expt_1g:
        if isinstance(expt_1g, int):
            expt_1g = [expt_1g]
            proc_id = [proc_id]

        for i in range(len(proc_id)):
            actual_1g = host_mems[proc_id[i]][0]
            expt = expt_1g[i]
            assert expt == actual_1g, "{} proc{} 1G pages - actual: {}, expected: {}".\
                format(host, proc_id[i], actual_1g, expt_1g)


def modify_host_memory(host, proc, gib_1g=None, gib_4k_range=None, actual_mems=None,
                       con_ssh=None, auth_into=Tenant.get('admin')):
    """

    Args:
        host (str):
        proc (int|str)
        gib_1g (None|int): 1g page to set
        gib_4k_range (None|tuple):
            None: no requirement on 4k page
            tuple: (min_val(None|int), max_val(None|int)) make sure 4k page total gib fall between the range (inclusive)
        actual_mems
        con_ssh
        auth_into

    Returns:

    """
    args = ''
    if not actual_mems:
        actual_mems = _get_actual_mems(host=host)
    mib_avail, page_1g = actual_mems[proc]

    if gib_1g is not None:
        page_1g = gib_1g
        args += ' -1G {}'.format(gib_1g)
    mib_avail_2m = mib_avail - page_1g*1024

    if gib_4k_range:
        min_4k, max_4k = gib_4k_range
        if not (min_4k is None and max_4k is None):
            if min_4k is None:
                gib_4k_final = max(0, max_4k - 2)
            elif max_4k is None:
                gib_4k_final = min_4k + 2
            else:
                gib_4k_final = (min_4k + max_4k)/2
            mib_avail_2m = mib_avail_2m - gib_4k_final*1024

    page_2m = int(mib_avail_2m/2)
    args += ' -2M {} {} {}'.format(page_2m, host, proc)

    cli.system('host-memory-modify', args, ssh_client=con_ssh, auth_info=auth_into)


def modify_host_cpu(host, cpu_function, timeout=CMDTimeout.HOST_CPU_MODIFY, fail_ok=False, con_ssh=None,
                    auth_info=Tenant.get('admin'), **kwargs):
    """
    Modify host cpu to given key-value pairs. i.e., system host-cpu-modify -f <function> -p<id> <num of cores> <host>
    Notes: This assumes given host is already locked.

    Args:
        host (str): hostname of host to be modified
        cpu_function (str): cpu function to modify. e.g., 'vSwitch', 'platform'
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
    LOG.info("Modifying host {} CPU function {} to {}".format(host, cpu_function, kwargs))

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

    subcmd = ' '.join(['host-cpu-modify', '-f', cpu_function.lower().strip(), proc_args])
    code, output = cli.system(subcmd, host, fail_ok=fail_ok, ssh_client=con_ssh, auth_info=auth_info, timeout=timeout,
                              rtn_list=True)

    if code == 1:
        return 1, output

    LOG.info("Post action check for host-cpu-modify...")
    table_ = table_parser.table(output)
    table_ = table_parser.filter_table(table_, assigned_function=cpu_function)

    threads = get_host_threads_count(host, con_ssh=con_ssh)

    for proc, num in final_args.items():
        num = int(num)
        proc_id = re.findall(r'\d+', proc)[0]
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


def add_host_interface(host, if_name, ports_or_ifs, if_type=None, pnet=None, ae_mode=None, tx_hash_policy=None,
                       vlan_id=None, mtu=None, if_class=None, network=None, ipv4_mode=None, ipv6_mode=None,
                       ipv4_pool=None, ipv6_pool=None, lock_unlock=True, fail_ok=False, con_ssh=None,
                       auth_info=Tenant.get('admin')):
    """

    Args:
        host:
        if_name:
        ports_or_ifs:
        if_type:
        pnet:
        ae_mode:
        tx_hash_policy:
        vlan_id:
        mtu:
        if_class:
        network:
        ipv4_mode:
        ipv6_mode:
        ipv4_pool:
        ipv6_pool:
        lock_unlock:
        fail_ok:
        con_ssh:
        auth_info:

    Returns:

    """
    if lock_unlock:
        lock_host(host=host, con_ssh=con_ssh, swact=True, fail_ok=False)

    if isinstance(ports_or_ifs, str):
        ports_or_ifs = [ports_or_ifs]
    args = '{} {}{}{} {}'.format(host, if_name, ' '+if_type if if_type else '', ' '+pnet if pnet else '',
                                 ' '.join(ports_or_ifs))
    opt_args_dict = {
        '--aemode': ae_mode,
        '--txhashpolicy': tx_hash_policy,
        '--vlan_id': vlan_id,
        '--imtu': mtu,
        '--ifclass': if_class,
        '--networks': network,
        '--ipv4-mode': ipv4_mode,
        '--ipv6-mode': ipv6_mode,
        '--ipv4-pool': ipv4_pool,
        '--ipv6-pool': ipv6_pool,
    }

    opt_args = ''
    for key, val in opt_args_dict.items():
        if val is not None:
            opt_args += '{} {} '.format(key, val)

    args = '{} {}'.format(args, opt_args).strip()
    code, out = cli.system('host-if-add', args, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True, fail_ok=fail_ok)
    if code > 0:
        return 1, out

    if lock_unlock:
        unlock_host(host, con_ssh=con_ssh)

    msg = "Interface {} successfully added to {}".format(if_name, host)
    LOG.info(msg)

    return 0, msg


def modify_host_interface(host, interface, pnet=None, ae_mode=None, tx_hash_policy=None,
                          mtu=None, if_class=None, network=None, ipv4_mode=None, ipv6_mode=None,
                          ipv4_pool=None, ipv6_pool=None, sriov_vif_count=None, new_if_name=None,
                          lock_unlock=True, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """

    Args:
        host:
        interface:
        pnet:
        ae_mode:
        tx_hash_policy:
        mtu:
        if_class:
        network:
        ipv4_mode:
        ipv6_mode:
        ipv4_pool:
        ipv6_pool:
        sriov_vif_count:
        new_if_name:
        lock_unlock:
        fail_ok:
        con_ssh:
        auth_info:

    Returns:

    """
    if lock_unlock:
        lock_host(host=host, con_ssh=con_ssh, swact=True, fail_ok=False)

    args = '{} {}'.format(host, interface)
    opt_args_dict = {
        '--ifname': new_if_name,
        '--aemode': ae_mode,
        '--txhashpolicy': tx_hash_policy,
        '--imtu': mtu,
        '--ifclass': if_class,
        '--networks': network,
        '--ipv4-mode': ipv4_mode,
        '--ipv6-mode': ipv6_mode,
        '--ipv4-pool': ipv4_pool,
        '--ipv6-pool': ipv6_pool,
        '--num-vfs': sriov_vif_count,
        '--providernetworks': pnet,
    }

    opt_args = ''
    for key, val in opt_args_dict.items():
        if val is not None:
            opt_args += '{} {} '.format(key, val)

    args = '{} {}'.format(args, opt_args).strip()
    code, out = cli.system('host-if-modify', args, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                           fail_ok=fail_ok)
    if code > 0:
        return 1, out

    if lock_unlock:
        unlock_host(host, con_ssh=con_ssh)

    msg = "{} interface {} is successfully modified".format(host, interface)
    LOG.info(msg)

    return 0, msg


def compare_host_to_cpuprofile(host, profile_uuid):
    """
    Compares the cpu function assignments of a host and a cpu profile.

    Args:
        host (str): name of host
        profile_uuid (str): name or uuid of the cpu profile

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
            for range_ in ranges:
                if range_ == '':
                    continue
                range_ = range_.split('-')
                if len(range_) == 2:
                    if int(range_[0]) <= int(core_num) <= int(range_[1]):
                        return True
                elif len(range_) == 1:
                    if int(range_[0]) == int(core_num):
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
        elif functions[i] == 'Applications':
            if not check_range(vm_cores, i):
                LOG.warning(msg + str(i))
                return 2, msg + str(i)

    msg = "The host and cpu profile have the same information"
    return 0, msg


def apply_cpu_profile(host, profile_uuid, timeout=CMDTimeout.CPU_PROFILE_APPLY, fail_ok=False, con_ssh=None,
                      auth_info=Tenant.get('admin')):
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


def is_lowlatency_host(host):
    subfuncs = get_hostshow_value(host=host, field='subfunctions')
    return 'lowlatency' in subfuncs


def get_host_cpu_cores_for_function(hostname, func='vSwitch', core_type='log_core', thread=0, con_ssh=None,
                                    auth_info=Tenant.get('admin'), rtn_dict_per_proc=True):
    """
    Get processor/logical cpu cores/per processor on thread 0 for given function for host via system host-cpu-list

    Args:
        hostname (str): hostname to pass to system host-cpu-list
        func (str|tuple|list): such as 'Platform', 'vSwitch', or 'Applications'
        core_type (str): 'phy_core' or 'log_core'
        thread (int|None): thread number. 0 or 1
        con_ssh (SSHClient):
        auth_info (dict):
        rtn_dict_per_proc (bool)

    Returns (dict|list): format: {<proc_id> (int): <log_cores> (list), ...}
        e.g., {0: [1, 2], 1: [21, 22]}

    """
    table_ = table_parser.table(cli.system('host-cpu-list', hostname, ssh_client=con_ssh, auth_info=auth_info))
    procs = list(set(table_parser.get_values(table_, 'processor', thread=thread))) if rtn_dict_per_proc else [None]
    res = {}

    convert = False
    if isinstance(func, str):
        func = [func]
        convert = True

    for proc in procs:
        funcs_cores = []
        for func_ in func:
            func_ = 'Applications' if func_.lower() == 'vms' else func_
            cores = table_parser.get_values(table_, core_type, processor=proc, assigned_function=func_, thread=thread)
            funcs_cores.append(sorted([int(item) for item in cores]))

        if convert:
            funcs_cores = funcs_cores[0]

        if proc is not None:
            res[int(str(proc))] = funcs_cores
        else:
            res = funcs_cores
            break

    LOG.info("{} {} {}s: {}".format(hostname, func, core_type, res))
    return res


def get_logcores_counts(host, proc_ids=(0, 1), thread='0', functions=None, con_ssh=None):
    """
    Get number of logical cores on given processor on thread 0.

    Args:
        host:
        proc_ids:
        thread (str|list): '0' or ['0', '1']
        con_ssh:
        functions (list|str)

    Returns (list):

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

    code, output = con_ssh.exec_sudo_cmd('''vm-topology --show topology | grep --color='never' "{}.*Threads/Core="'''.
                                         format(host))
    if code != 0:
        raise exceptions.SSHExecCommandFailed("CMD stderr: {}".format(output))

    pattern = r"Threads/Core=(\d),"
    return int(re.findall(pattern, output)[0])


def get_host_procs(hostname, con_ssh=None):
    table_ = table_parser.table(cli.system('host-cpu-list', hostname, ssh_client=con_ssh,
                                           auth_info=Tenant.get('admin')))
    procs = table_parser.get_column(table_, 'processor')
    return sorted(list(set(procs)))


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


def get_host_lvg_show_values(host, fields, lvg='nova-local', con_ssh=None, strict=False, auth_info=Tenant.get('admin')):
    """
    Get values for given fields in system host-lvg-show table
    Args:
        host (str):
        fields (str|list|tuple):
        lvg (str): e.g., nova-local (compute nodes), cgts-vg (controller/storage nodes)
        con_ssh (SSHClient):
        auth_info
        strict (bool)

    Returns:

    """
    table_ = table_parser.table(cli.system('host-lvg-show', '{} {}'.format(host, lvg), ssh_client=con_ssh,
                                           auth_info=Tenant.get('admin')))
    if isinstance(fields, str):
        fields = [fields]

    fields_to_convert = ('lvm_max_lv', 'lvm_cur_lv', 'lvm_max_pv', 'lvm_cur_pv', 'lvm_vg_size',
                         'lvm_vg_total_pe', 'lvm_vg_free_pe', 'parameters')

    vals = []
    for field in fields:
        val = table_parser.get_value_two_col_table(table_, field, merge_lines=True, strict=strict)
        if field in fields_to_convert:
            val = eval(val)
        vals.append(val)

    return vals


def get_host_instance_backing(host, con_ssh=None, auth_info=Tenant.get('admin')):
    params = get_host_lvg_show_values(host=host, fields='parameters', lvg='nova-local', con_ssh=con_ssh,
                                      auth_info=auth_info)[0]
    return params['instance_backing']


def is_host_with_instance_backing(host, storage_type='image', con_ssh=None):
    host_lvg_inst_backing = get_host_instance_backing(host, con_ssh=con_ssh).lower()

    return storage_type in host_lvg_inst_backing


def modify_host_lvg(host, lvg='nova-local', inst_backing=None, inst_lv_size=None, concurrent_ops=None, lock=True,
                    unlock=True, fail_ok=False, check_first=True, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Modify host lvg

    Args:
        host (str): host to modify lvg for
        lvg (str): local volume group name. nova-local by default
        inst_backing (str): image, lvm, or remote
        inst_lv_size (int|None): instance lv size in GiB
        concurrent_ops (int): number of current disk operations
        lock (bool): whether or not to lock host before modify
        unlock (bool): whether or not to unlock host and verify config after modify
        fail_ok (bool): whether or not raise exception if host-lvg-modify cli got rejected
        auth_info (dict):
        con_ssh (SSHClient):
        check_first (bool

    Returns (tuple):
        (0, "Host is configured")       host configured
        (1, <stderr>)
        (2, )

    """

    if inst_backing is not None:
        if 'image' in inst_backing:
            inst_backing = 'image'
        # elif 'lvm' in inst_backing:
        #     inst_backing = 'lvm'
        #     if inst_lv_size is None and lvg == 'nova-local':
        #         lvm_vg_size = get_host_lvg_show_values(host, fields='lvm_vg_size', lvg=lvg, con_ssh=con_ssh,
        #                                                strict=False)[0]
        #         inst_lv_size = min(50, int(int(lvm_vg_size)/2))    # half of the nova-local size up to 50g
        #         if inst_lv_size < 5:        # use default value if lvm_vg_size is less than 10g
        #             inst_lv_size = None
        elif 'remote' in inst_backing:
            inst_backing = 'remote'
        else:
            raise ValueError("Invalid instance backing provided. Choose from: image, lvm, remote.")

    def check_host_config(lvg_tab_=None):
        if lvg_tab_ is None:
            lvg_tab_ = table_parser.table(cli.system('host-lvg-show', '{} {}'.format(host, lvg), ssh_client=con_ssh))
        params = eval(table_parser.get_value_two_col_table(lvg_tab_, 'parameters'))
        err_msg = ''
        if lvg == 'nova-local':
            if inst_backing is not None:
                post_inst_backing = params['instance_backing']
                if inst_backing != post_inst_backing:
                    err_msg += "Instance backing is {} instead of {}\n".format(post_inst_backing, inst_backing)

            if inst_backing == 'lvm' and inst_lv_size is not None:
                post_inst_lv_size = params.get('instances_lv_size_gib', 0)
                if inst_lv_size != int(post_inst_lv_size):
                    err_msg += "Instance local volume size is {} instead of {}\n".format(post_inst_lv_size,
                                                                                         inst_lv_size)

            if concurrent_ops is not None:
                post_concurrent_ops = params['concurrent_disk_operations']
                if int(concurrent_ops) != post_concurrent_ops:
                    err_msg += "Concurrent disk operations is {} instead of {}".format(post_concurrent_ops,
                                                                                       concurrent_ops)
        # TODO: Add lvm_type
        return err_msg

    args_dict = {
        '-b': inst_backing,
        '-s': inst_lv_size,
        '-c': concurrent_ops
    }
    args = ''

    for key, val in args_dict.items():
        if val is not None:
            args += ' {} {}'.format(key, val)

    if not args:
        raise ValueError("At least one of the values should be supplied: inst_backing, inst_lv_size, concurrent_ops'")

    args += ' {} {}'.format(host, lvg)

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

    err = ''
    rtn_code = 0
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
                             fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
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

    code, output = modify_host_lvg(host, lvg=lvm, inst_backing=inst_backing, lock=lock, unlock=unlock, fail_ok=fail_ok,
                                   auth_info=auth_info, con_ssh=con_ssh)
    if code > 0:
        return code, output

    if wait_for_host_aggregate:
        res = wait_for_host_in_instance_backing(host=host, storage_backing=inst_backing, fail_ok=fail_ok)
        if not res:
            err = "Host {} did not appear in {} host-aggregate within timeout".format(host, inst_backing)
            return 4, err

    return 0, "{} storage backing is successfully set to {}".format(host, inst_backing)


def wait_for_host_in_instance_backing(host, storage_backing, timeout=120, check_interval=3, fail_ok=False, con_ssh=None):

    endtime = time.time() + timeout
    while time.time() < endtime:
        host_backing = get_host_instance_backing(host=host, con_ssh=con_ssh)
        if host_backing in storage_backing:
            LOG.info("{} is configured with {} backing".format(host, storage_backing))
            time.sleep(30)
            return True

        time.sleep(check_interval)

    err_msg = "Timed out waiting for {} to appear in {} host-aggregate".format(host, storage_backing)
    if fail_ok:
        LOG.warning(err_msg)
        return False
    else:
        raise exceptions.HostError(err_msg)


def is_host_local_image_backing(host, con_ssh=None):
    return is_host_with_instance_backing(host, storage_type='image', con_ssh=con_ssh)


def __parse_total_cpus(output):
    last_line = output.splitlines()[-1]
    print(last_line)
    # Final resource view: name=controller-0 phys_ram=44518MB used_ram=0MB phys_disk=141GB used_disk=1GB
    # free_disk=133GB total_vcpus=31 used_vcpus=0.0 pci_stats=[PciDevicePool(count=1,numa_node=0,product_id='0522',
    # tags={class_id='030000',configured='1',dev_type='type-PCI'},vendor_id='102b')]
    total = round(float(re.findall(r'used_vcpus=([\d|.]*) ', last_line)[0]), 4)
    return total


def get_total_allocated_vcpus_in_log(host=None, pod_name=None, con_ssh=None):
    """

    Args:
        host (str|None):
        pod_name (str|None): full name of nova compute pod
        con_ssh:

    Returns (float): float with 4 digits after decimal point
    """
    if not host and not pod_name:
        raise ValueError("host or pod_name has to be provided.")

    strict = True
    if not pod_name:
        strict = False
        pod_name = 'nova-compute-{}'.format(host)

    output = kube_helper.get_pod_logs(pod_name=pod_name, namespace='openstack', strict=strict,
                                      grep_pattern='Final resource view', tail_count=3, con_ssh=con_ssh)

    total_allocated_vcpus = __parse_total_cpus(output)
    return total_allocated_vcpus


def wait_for_total_allocated_vcpus_update_in_log(host, prev_cpus=None, expt_cpus=None, timeout=60, fail_ok=False,
                                                 con_ssh=None):
    """
    Wait for total allocated vcpus in nova-compute.log gets updated to a value that is different than given value

    Args:
        host:
        prev_cpus (None|float|int):
        expt_cpus (int|None)
        timeout (int):
        fail_ok (bool): whether to raise exception when allocated vcpus number did not change
        con_ssh

    Returns (float): New value of total allocated vcpus as float with 4 digits after decimal point

    """
    pod_name = kube_helper.get_openstack_pods_info('nova-compute-{}'.format(host), con_ssh=con_ssh)[0][0].get('name')

    end_time = time.time() + timeout
    if prev_cpus is None and expt_cpus is None:
        prev_cpus = get_total_allocated_vcpus_in_log(pod_name=pod_name, con_ssh=con_ssh)

    # convert to str
    if prev_cpus:
        prev_cpus = round(prev_cpus, 4)

    while time.time() < end_time:
        allocated_cpus = get_total_allocated_vcpus_in_log(pod_name=pod_name, con_ssh=con_ssh)
        if expt_cpus is not None:
            if allocated_cpus == expt_cpus:
                return expt_cpus
        elif allocated_cpus != prev_cpus:
            return allocated_cpus
        time.sleep(5)
    else:
        msg = "Total allocated vcpus is not updated within timeout in nova-compute.log"
        if fail_ok:
            LOG.warning(msg)
            return prev_cpus
        raise exceptions.HostTimeout(msg)


def get_vcpus_for_computes(hosts=None, rtn_val='vcpus_used', numa_node=None, con_ssh=None):
    """

    Args:
        hosts:
        rtn_val (str): valid values: vcpus_used, vcpus, vcpu_avail
        numa_node (int|str)
        con_ssh:

    Returns (dict): host(str),cpu_val(float with 4 digits after decimal point) pairs as dictionary

    """
    if hosts is None:
        hosts = get_up_hypervisors(con_ssh=con_ssh)
    elif isinstance(hosts, str):
        hosts = [hosts]

    if rtn_val == 'used_now':
        rtn_val = 'vcpus_used'

    if 'avail' not in rtn_val:
        hosts_cpus = get_hypervisor_info(hosts=hosts, rtn_val=rtn_val, con_ssh=con_ssh)
    elif numa_node is None:
        cpus_info = get_hypervisor_info(hosts=hosts, rtn_val=('vcpus', 'vcpus_used'), con_ssh=con_ssh)
        hosts_cpus = {}
        for host in hosts:
            total_cpu, used_cpu = cpus_info[host]
            hosts_cpus[host] = float(total_cpu) - float(used_cpu)
    else:
        numa_node = str(numa_node)
        compute_table = system_helper.get_vm_topology_tables('computes', con_ssh=con_ssh)[0]

        hosts_cpus = {}
        for host in hosts:
            numa_index = None
            host_values = {}
            for field in ('node', 'pcpus', 'U:dedicated', 'U:shared'):
                values = table_parser.get_values(table_=compute_table, target_header=field, host=host)[0]
                if isinstance(values, str):
                    values = [values]
                if field == 'node':
                    numa_index = values.index(numa_node)
                    continue
                host_values[field] = float(values[numa_index])

            hosts_cpus[host] = host_values['pcpus'] - host_values['U:dedicated'] - host_values['U:shared']

    return hosts_cpus


def get_hypervisor_info(hosts, rtn_val='id', con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get info from nova hypervisor-show for specified field
    Args:
        hosts (str|list): hostname(s)
        rtn_val (str|list|tuple): a field in hypervisor-show
        con_ssh:
        auth_info:

    Returns (dict): {<host>(str): val(str|list), ...}
    """
    if isinstance(hosts, str):
        hosts = [hosts]

    convert_to_str = False
    if isinstance(rtn_val, str):
        rtn_val = [rtn_val]
        convert_to_str = True

    hosts_info = get_hypervisor_list_info(hosts=hosts, con_ssh=con_ssh)
    hosts_vals = {}
    for host in hosts:
        host_uuid = hosts_info[host]['id']
        table_ = table_parser.table(cli.nova('hypervisor-show', host_uuid, ssh_client=con_ssh, auth_info=auth_info),
                                    combine_multiline_entry=True)

        vals = []
        for field_ in rtn_val:
            val = table_parser.get_value_two_col_table(table_, field=field_, strict=True, merge_lines=True)
            try:
                val = eval(val)
            except:
                pass
            vals.append(val)
        if convert_to_str:
            vals = vals[0]
        hosts_vals[host] = vals

    LOG.info("Hosts_info: {}".format(hosts_vals))
    return hosts_vals


def get_hypervisor_list_info(hosts=None, con_ssh=None):
    """

    Args:
        hosts:
        con_ssh:

    Returns (dict): host info in dict. e.g.,
        {'compute-0': {'id': <uuid>, 'state': 'up', 'status': 'enabled'}}

    """
    table_ = table_parser.table(cli.nova('hypervisor-list', ssh_client=con_ssh, auth_info=Tenant.get('admin')))
    if hosts:
        table_ = table_parser.filter_table(table_, **{'Hypervisor hostname': hosts})

    table_dict = table_parser.row_dict_table(table_, 'Hypervisor hostname', unique_key=True)
    return table_dict


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

    host_topology = con_ssh.exec_sudo_cmd("vm-topology --show topology | awk '/{}/, /^[ ]*$/'".format(host),
                                          fail_ok=False)[1]
    table_ = table_parser.table(host_topology)

    siblings_tab = table_parser.filter_table(table_, cpu_id='sibling_id')
    cpu_ids = [int(cpu_id) for cpu_id in siblings_tab['headers'][1:]]
    sibling_ids = siblings_tab['values'][0][1:]

    if sibling_ids[0] == '-':
        LOG.warning("{} has no sibling cores. Hyper-threading needs to be enabled to have sibling cores.".format(host))
        return [[cpu_id] for cpu_id in cpu_ids]

    sibling_ids = [int(sibling_id) for sibling_id in sibling_ids]
    # find pairs and sort the cores in pair and convert to tuple (set() cannot be applied to item as list)
    sibling_pairs = [tuple(sorted(sibling_pair)) for sibling_pair in list(zip(cpu_ids, sibling_ids))]
    sibling_pairs = sorted(list(set(sibling_pairs)))       # remove dup pairs and sort it to start from smallest number
    sibling_pairs = [list(sibling_pair) for sibling_pair in sibling_pairs]

    LOG.info("Sibling cores for {} from vm-topology: {}".format(host, sibling_pairs))
    return sibling_pairs


def get_vcpus_info_in_log(host_ssh, numa_nodes=None, rtn_list=False):
    """
    Get vcpus info from nova-compute.log on nova compute host
    Args:
        host_ssh (SSHClient):
        numa_nodes (list): such as [0, 1]
        rtn_list (bool): whether to return dictionary or list

    Returns (dict|list):
        Examples: { 0: {'pinned_cpulist': [], 'unpinned_cpulist': [3, 4, 5,...], 'cpu_usage': 0.0, 'pinned': 0, ...},
                    1: {....}}

    """
    # hostname = host_ssh.get_hostname()
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
        if not output:
            LOG.warning("Nothing grepped for numa node {}".format(numa_node))
            continue

        output = ''.join(output.split(sep='\n'))
        cpu_info = output.split(sep="Numa node={}; ".format(numa_node))[-1].replace('; ', ', '). split(sep=', ')

        print("Cpu info: {}".format(cpu_info))
        for info in cpu_info:
            key, value = info.split(sep=':')

            if key in ['pinned_cpulist', 'unpinned_cpulist']:
                value = common.parse_cpus_list(value)
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
        vcpus[int(key)] = common.parse_cpus_list(pcpus.strip())

    if rtn_list:
        all_cpus = []
        for cpus in vcpus.values():
            all_cpus += cpus
        return sorted(all_cpus)

    return vcpus


def get_vcpu_pins_for_instance_via_virsh(host_ssh, instance_name):
    vcpu_pins = get_values_virsh_xmldump(instance_name=instance_name, host_ssh=host_ssh,
                                         tag_paths='cputune/vcpupin', target_type='dict')
    return vcpu_pins


def get_hosts_per_storage_backing(up_only=True, con_ssh=None, auth_info=Tenant.get('admin'), hosts=None):
    """
    Get hosts for each possible storage backing
    Args:
        up_only (bool): whether to return up hypervisor only
        auth_info
        con_ssh:
        hosts (None|list|tuple): hosts to check

    Returns (dict): {'local_image': <cow hosts list>,
                    'remote': <remote hosts list>
                    }
    """
    if not hosts:
        host_func = get_up_hypervisors if up_only else get_hypervisors
        hosts = host_func(con_ssh=con_ssh, auth_info=auth_info)

    hosts_per_backing = {'local_image': [], 'remote': []}
    for host in hosts:
        backing = get_host_instance_backing(host=host, con_ssh=con_ssh, auth_info=auth_info)
        if backing == 'image':
            hosts_per_backing['local_image'].append(host)
        elif backing == 'remote':
            hosts_per_backing['remote'].append(host)
        else:
            raise NotImplementedError('Unknown instance backing for {}: {}'.format(host, backing))

    LOG.info("Hosts per storage backing: {}".format(hosts_per_backing))
    return hosts_per_backing


def get_coredumps_and_crashreports(move=True):
    """
    Get core dumps and crash reports from every host
    Args:
        move: whether to move coredumps and crashreports to local automation dir

    Returns (dict):

    """
    LOG.info("Getting existing system crash reports from /var/crash/ and coredumps from /var/lib/systemd/coredump/")

    hosts_tab = table_parser.table(cli.system('host-list'))
    all_hosts = table_parser.get_column(hosts_tab, 'hostname')

    hosts_tab = table_parser.filter_table(hosts_tab, exclude=True, availability=HostAvailState.FAILED)
    hosts_tab = table_parser.filter_table(hosts_tab, exclude=True, availability=HostAvailState.OFFLINE)

    hosts_to_check = table_parser.get_column(hosts_tab, 'hostname')

    if not all_hosts == hosts_to_check:
        LOG.warning("Some host(s) in offline or failed state - {}, checking other hosts only".
                    format(set(all_hosts) - set(hosts_to_check)))

    core_dumps_and_reports = {}
    active_con = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()
    con_dir = '{}/coredumps_and_crashreports/'.format(WRSROOT_HOME)
    con_ssh.exec_cmd('mkdir -p {}'.format(con_dir))
    scp_to_local = False
    ls_cmd = 'ls -l --time-style=+%Y-%d-%m_%H-%M-%S {} | cat'
    core_dump_dir = '/var/lib/systemd/coredump/'
    crash_report_dir = '/var/crash/'
    for host in hosts_to_check:
        with ssh_to_host(hostname=host) as host_ssh:
            core_dump_output = host_ssh.exec_cmd(ls_cmd.format(core_dump_dir), fail_ok=False)[1]
            core_dumps = core_dump_output.splitlines()[1:]
            crash_report_output = host_ssh.exec_cmd(ls_cmd.format(crash_report_dir), fail_ok=False)[1]
            crash_reports = crash_report_output.splitlines()[1:]
            core_dumps_and_reports[host] = core_dumps, crash_reports

            if move:
                if core_dumps:
                    for line in core_dumps:
                        timestamp, name = line.split(sep=' ')[-2:]
                        new_name = '_'.join((host, timestamp, name))
                        host_ssh.exec_sudo_cmd('mv {}/{} {}/{}'.format(core_dump_dir, name, core_dump_dir, new_name))

                    scp_to_local = True
                    host_ssh.scp_on_source(source_path='{}/*'.format(core_dump_dir),
                                           dest_user=HostLinuxCreds.get_user(),
                                           dest_ip=active_con, dest_path=con_dir,
                                           dest_password=HostLinuxCreds.get_password())
                    host_ssh.exec_sudo_cmd('rm -f {}*'.format(core_dump_dir))

                if crash_reports:
                    for line in crash_reports:
                        timestamp, name = line.split(sep=' ')[-2:]
                        new_name = '_'.join((host, timestamp, name))
                        host_ssh.exec_sudo_cmd('mv {}/{} {}/{}'.format(crash_report_dir, name, crash_report_dir,
                                                                       new_name))

                    scp_to_local = True
                    host_ssh.scp_on_source(source_path='{}/*'.format(crash_report_dir),
                                           dest_user=HostLinuxCreds.get_user(),
                                           dest_ip=active_con, dest_path=con_dir,
                                           dest_password=HostLinuxCreds.get_password())
                    host_ssh.exec_sudo_cmd('rm -f {}*'.format(crash_report_dir))

    if scp_to_local:
        con_ssh.exec_sudo_cmd('chmod -R 755 {}'.format(con_dir))

        log_dir = ProjVar.get_var('LOG_DIR')
        coredump_and_crashreport_dir = os.path.join(log_dir, 'coredumps_and_crashreports')
        os.makedirs(coredump_and_crashreport_dir, exist_ok=True)
        source_path = '{}/*'.format(con_dir)
        common.scp_from_active_controller_to_localhost(source_path=source_path, dest_path=coredump_and_crashreport_dir)
        con_ssh.exec_cmd('rm -f {}/*'.format(con_dir))

    LOG.info("core dumps and crash reports per host: {}".format(core_dumps_and_reports))
    return core_dumps_and_reports


def modify_mtu_on_interface(host, interface, mtu_val, network_type='data',
                            lock_unlock=True, fail_ok=False, con_ssh=None):
    mtu_val = int(mtu_val)

    LOG.info("Modify MTU for IF {} of NET-TYPE {} to: {} on {}".format(interface, network_type, mtu_val, host))

    args = "-m {} {} {}".format(mtu_val, host, interface)

    code, output = cli.system('host-if-modify', args, fail_ok=fail_ok, rtn_list=True, ssh_client=con_ssh)

    if code != 0:
        msg = "Attempt to change MTU failed on host:{} for IF:{} to MTU:{}".format(host, interface, mtu_val)
        if fail_ok:
            return 2, msg
        raise exceptions.HostPostCheckFailed(msg)

    if lock_unlock:
        unlock_host(host)

    return code, output


def modify_mtu_on_interfaces(hosts, mtu_val, network_type, lock_unlock=True, fail_ok=False, con_ssh=None):

    if not hosts:
        raise exceptions.HostError("No hostname provided.")

    mtu_val = int(mtu_val)

    if isinstance(hosts, str):
        hosts = [hosts]

    res = {}
    rtn_code = 0

    if_class = network_type
    network = ''
    if network_type in PLATFORM_NET_TYPES:
        if_class = 'platform'
        network = network_type

    for host in hosts:
        table_ = table_parser.table(cli.system('host-if-list', '{} --nowrap'.format(host), ssh_client=con_ssh))
        table_ = table_parser.filter_table(table_, **{'class': if_class})
        # exclude unmatched platform interfaces from the table.
        if 'platform' == if_class:
            platform_ifs = table_parser.get_values(table_, target_header='name', **{'class': 'platform'})
            for pform_if in platform_ifs:
                if_nets = system_helper.get_host_if_show_values(host=host, interface=pform_if, fields='networks',
                                                                con_ssh=con_ssh)[0]
                if_nets = [if_net.strip() for if_net in if_nets.split(sep=',')]
                if network not in if_nets:
                    table_ = table_parser.filter_table(table_, strict=True, exclude=True, name=pform_if)

        uses_if_names = table_parser.get_values(table_, 'name', exclude=True, **{'uses i/f': '[]'})
        non_uses_if_names = table_parser.get_values(table_, 'name', exclude=False, **{'uses i/f': '[]'})
        uses_if_first = False
        if uses_if_names:
            current_mtu = int(system_helper.get_host_if_show_values(host, interface=uses_if_names[0], fields=['imtu'],
                                                                    con_ssh=con_ssh)[0])
            if current_mtu <= mtu_val:
                uses_if_first = True

        if uses_if_first:
            if_names = uses_if_names + non_uses_if_names
        else:
            if_names = non_uses_if_names + uses_if_names

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


def get_hosts_and_pnets_with_pci_devs(pci_type='pci-sriov', up_hosts_only=True, con_ssh=None,
                                      auth_info=Tenant.get('admin')):
    """

    Args:
        pci_type (str|list|tuple): pci-sriov, pci-passthrough
        up_hosts_only:
        con_ssh:
        auth_info:

    Returns (dict): hosts and pnets with ALL specified pci devs

    """
    state = 'up' if up_hosts_only else None
    hosts = get_hypervisors(state=state)

    hosts_pnets_with_pci = {}
    if isinstance(pci_type, str):
        pci_type = [pci_type]

    for host_ in hosts:
        pnets_list_for_host = []
        for pci_type_ in pci_type:

            pnets_list = system_helper.get_host_interfaces(host_, rtn_val='data networks', net_type=pci_type_,
                                                           con_ssh=con_ssh, auth_info=auth_info)
            pnets_for_type = []
            for pnets_ in pnets_list:
                pnets_for_type += pnets_

            if not pnets_for_type:
                LOG.info("{} {} interface data network not found".format(host_, pci_type_))
                pnets_list_for_host = []
                break
            pnets_list_for_host.append(list(set(pnets_for_type)))

        if pnets_list_for_host:
            pnets_final = pnets_list_for_host[0]
            for pnets_ in pnets_list_for_host[1:]:
                pnets_final = list(set(pnets_final) & set(pnets_))

            if pnets_final:
                hosts_pnets_with_pci[host_] = pnets_final

    if not hosts_pnets_with_pci:
        LOG.info("No {} interface found from any of following hosts: {}".format(pci_type, hosts))
    else:
        LOG.info("Hosts and provider networks with {} devices: {}".format(pci_type, hosts_pnets_with_pci))

    return hosts_pnets_with_pci


def is_active_controller(host, con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    personality = eval(get_hostshow_value(host, field='capabilities', auth_info=auth_info,
                                          merge_lines=True, con_ssh=con_ssh, use_telnet=use_telnet,
                                          con_telnet=con_telnet)).get('Personality', '')
    return personality.lower() == 'Controller-Active'.lower()


def upgrade_host(host, timeout=HostTimeout.UPGRADE, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin'),
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
        lock


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
                err_msg = "Host {} fail on lock before starting upgrade: {}".format(host, output)
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

    if not wait_for_host_values(host, timeout=timeout, check_interval=60, availability=HostAvailState.ONLINE,
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


def upgrade_hosts(hosts, timeout=HostTimeout.UPGRADE, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin'),
                  lock=False, unlock=False):
    """
    Upgrade given hosts list one by one
    Args:
        hosts (list): list of hostname of hosts to be upgraded
        timeout (int): MAX seconds to wait for host to become online after upgrading
        fail_ok (bool):
        con_ssh (SSHClient):
        lock (bool):
        auth_info (str):
        unlock (bool):

    Returns (tuple):
        (0, "Hosts are upgraded and in online state.")
        (1, "Upgrade on host failed. applicable if fail_ok

    """
    LOG.info("Upgrading {}...".format(hosts))
    active_controller = system_helper.get_active_controller_name()
    if active_controller in hosts:
        hosts.remove(active_controller)

    LOG.info("Checking if active controller {} is already upgraded ....".format(active_controller))

    if get_hosts_upgrade_target_release(active_controller) in get_hosts_upgrade_target_release(hosts):
        message = " Active controller {} is not upgraded.  Must be upgraded first".format(active_controller)
        LOG.info(message)
        return 1, message
    # keep original host

    controllers = sorted([h for h in hosts if "controller" in h])
    storages = sorted([h for h in hosts if "storage" in h])
    computes = sorted([h for h in hosts if h not in storages and h not in controllers])
    hosts_to_upgrade = controllers + storages + computes

    for host in hosts_to_upgrade:
        rc, output = upgrade_host(host, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                                  auth_info=auth_info, lock=lock, unlock=unlock)
        if rc != 0:
            if fail_ok:
                return rc, output
            else:
                raise exceptions.HostError(output)
        else:
            LOG.info("Host {} upgrade completed".format(host))

    return 0, "hosts {} upgrade done ".format(hosts_to_upgrade)


def _wait_for_upgrade_data_migration_complete(timeout=1800, check_interval=60, auth_info=Tenant.get('admin'),
                                              fail_ok=False, con_ssh=None):
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
    table_ = table_parser.filter_table(hostname=hostnames, table_=table_)
    return table_parser.get_column(table_, "running_release")


def ensure_host_provisioned(host, con_ssh=None):
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
    active_controller = system_helper.get_active_controller_name()
    conter_swact_back = False
    if active_controller == host:
        LOG.tc_step("Swact active controller and ensure active controller is changed")
        exit_code, output = swact_host(hostname=active_controller)
        assert 0 == exit_code, "{} is not recognized as active controller".format(active_controller)
        active_controller = system_helper.get_active_controller_name()
        conter_swact_back = True

    LOG.info("Host {} not provisioned ; doing lock/unlock to provision the host ....".format(host))
    rc, output = lock_host(host, con_ssh=con_ssh)
    if rc != 0 and rc != -1:
        err_msg = "Lock host {} rejected".format(host)
        raise exceptions.HostError(err_msg)

    rc, output = unlock_host(host, available_only=True, con_ssh=con_ssh)
    if rc != 0:
        err_msg = "Unlock host {} failed: {}".format(host, output)
        raise exceptions.HostError(err_msg)
    if conter_swact_back:
        LOG.tc_step("Swact active controller back and ensure active controller is changed")
        exit_code, output = swact_host(hostname=active_controller)
        assert 0 == exit_code, "{} is not recognized as active controller".format(active_controller)

    LOG.info("Checking if host {} is provisioned after lock/unlock ....".format(host))
    if not is_host_provisioned(host, con_ssh=None):
        raise exceptions.HostError("Failed to provision host {}")
    # Delay for the alarm to clear . Could be improved.
    time.sleep(120)
    return 0, "Host {} is provisioned after lock/unlock".format(host)


def is_host_provisioned(host, con_ssh=None):
    invprovisioned = get_hostshow_value(host, "invprovision", con_ssh=con_ssh)
    LOG.info("Host {} is {}".format(host, invprovisioned))
    return "provisioned" == invprovisioned.strip()


def get_upgraded_host_names(upgrade_release, con_ssh=None):

    table_ = table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, target_release=upgrade_release)
    return table_parser.get_column(table_, "hostname")


def downgrade_host(host, timeout=HostTimeout.UPGRADE, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin'),
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
        lock (bool)


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
                err_msg = "Host {} fail on lock before starting downgrade: {}".format(host, output)
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

    if not wait_for_host_values(host, timeout=timeout, check_interval=60, availability=HostAvailState.ONLINE,
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
        item_names (list|str|None): such as 'oam-services', or ['oam-ip', 'oam-services']
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
def ssh_to_build_server(bld_srv=None, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
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
    if bld_srv is None:
        bld_srv = DEFAULT_BUILD_SERVER

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


@contextmanager
def ssh_to_test_server(test_srv=SvcCgcsAuto.SERVER, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD, prompt=None):
    """
    ssh to test server.
    Usage: Use with context_manager. i.e.,
        with ssh_to_build_server(bld_srv=cgts-yow3-lx) as bld_srv_ssh:
            # do something
        # ssh session will be closed automatically

    Args:
        test_srv (str): test server ip
        user (str): svc-cgcsauto if unspecified
        password (str): password for svc-cgcsauto user if unspecified
        prompt (str|None): expected prompt. such as: svc-cgcsauto@yow-cgts4-lx.wrs.com$

    Yields (SSHClient): ssh client for given build server and user

    """
    # Get build_server dict from bld_srv param.

    prompt = prompt if prompt else Prompt.TEST_SERVER_PROMPT_BASE.format(user)
    test_server_conn = SSHClient(test_srv, user=user, password=password, initial_prompt=prompt)
    test_server_conn.connect()

    try:
        yield test_server_conn
    finally:
        test_server_conn.close()


def get_host_co_processor_pci_list(hostname):

    host_pci_info = []
    with ssh_to_host(hostname) as host_ssh:
        LOG.info("Getting the Co-processor pci list for host {}".format(hostname))
        cmd = "lspci -nnm | grep Co-processor | grep --color=never -v -A 1 -E 'Device \[0000\]|Virtual'"
        rc, output = host_ssh.exec_cmd(cmd)
        if rc != 0:
            return host_pci_info

        # sample output:
        # wcp7-12:
        # 09:00.0 "Co-processor [0b40]" "Intel Corporation [8086]" "DH895XCC Series QAT [0435]" "Intel Corporation [8086]" "Device [35c5]"
        # 09:01.0 "Co-processor [0b40]" "Intel Corporation [8086]" "DH895XCC Series QAT Virtual Function [0443]" "Intel Corporation [8086]" "Device [0000]"

        # wolfpass-13_14:
        # 3f:00.0 "Co-processor [0b40]" "Intel Corporation [8086]" "Device [37c8]" -r04 "Intel Corporation [8086]" "Device [35cf]"
        # 3f:01.0 "Co-processor [0b40]" "Intel Corporation [8086]" "Device [37c9]" -r04 "Intel Corporation [8086]" "Device [0000]"
        # --
        # da:00.0 "Co-processor [0b40]" "Intel Corporation [8086]" "Device [37c8]" -r04 "Intel Corporation [8086]" "Device [35cf]"
        # da:01.0 "Co-processor [0b40]" "Intel Corporation [8086]" "Device [37c9]" -r04 "Intel Corporation [8086]" "Device [0000]"
        dev_sets = output.split('--\n')
        for dev_set in dev_sets:
            pdev_line, vdev_line = dev_set.strip().splitlines()
            class_id, vendor_id, device_id = re.findall(r'\[([0-9a-fA-F]{4})\]', pdev_line)[0:3]
            vf_class_id, vf_vendor_id, vf_device_id = re.findall(r'\[([0-9a-fA-F]{4})\]', vdev_line)[0:3]
            assert vf_class_id == class_id
            assert vf_vendor_id == vendor_id
            assert device_id != vf_device_id

            vendor_name = re.findall(r'\"([^\"]+) \[{}\]'.format(vendor_id), pdev_line)[0]
            pci_alias = re.findall(r'\"([^\"]+) \[{}\]'.format(device_id), pdev_line)[0]
            if pci_alias == 'Device':
                pci_alias = None
            else:
                pci_alias = 'qat-{}-vf'.format(pci_alias.lower())
            pci_address = ("0000:{}".format(pdev_line.split(sep=' "', maxsplit=1)[0]))
            pci_name = "pci_{}".format(pci_address.replace('.', '_').replace(':', '_').strip())
            # Ensure class id is at least 6 digits as displayed in nova device-list and system host-device-list
            class_id = (class_id + '000000')[0:6]

            LOG.info("pci_name={} device_id={}".format(pci_name, device_id))
            pci_info = {'pci_address': pci_address,
                        'pci_name': pci_name,
                        'vendor_name': vendor_name,
                        'vendor_id': vendor_id,
                        'device_id': device_id,
                        'class_id': class_id,
                        'pci-alias': pci_alias,
                        'vf_device_id': vf_device_id,
                        }

            host_pci_info.append(pci_info)

        LOG.info("The Co-processor pci list for host {}: {}".format(hostname, host_pci_info))

    return host_pci_info


def get_mellanox_ports(host):
    """
    Get Mellanox data ports for given host

    Args:
        host (str): hostname

    Returns (list):

    """
    data_ports = system_helper.get_host_ports_for_net_type(host, net_type='data', ports_only=True)
    mt_ports = system_helper.get_host_ports_values(host, 'uuid', if_name=data_ports, strict=False, regex=True,
                                                   **{'device type': MELLANOX_DEVICE})
    LOG.info("Mellanox ports: {}".format(mt_ports))
    return mt_ports


def is_host_locked(host,  con_ssh=None):
        admin_state = get_hostshow_value(host, 'administrative', con_ssh=con_ssh)
        return admin_state == 'locked'


def get_host_network_interface_dev_names(host, con_ssh=None):

    dev_names = []
    with ssh_to_host(host, con_ssh=con_ssh) as host_ssh:

        cmd = "ifconfig -a | sed 's/[ \t].*//;/^$/d;/^lo/d'"
        rc, output = host_ssh.exec_sudo_cmd(cmd)
        if rc == 0:
            output = output.splitlines()
            for dev in output:
                if dev.endswith(':'):
                    dev = dev[:-1]
                dev_names.append(dev)
            LOG.info("Host {} interface device names: {}".format(host, dev_names))
        else:
            LOG.warning("Failed to get interface device names for host {}".format(host))

    return dev_names


def scp_files_to_controller(host, file_path, dest_dir, controller=None, dest_user=None, sudo=False, con_ssh=None,
                            fail_ok=True):
    dest_server = controller if controller else ''
    dest_user = dest_user if dest_user else ''
    con_ssh.scp_files(source_file=file_path, source_server=host, source_password=HostLinuxCreds.get_password(),
                      source_user=HostLinuxCreds.get_user(),
                      dest_file=dest_dir, dest_user=dest_user, dest_password=HostLinuxCreds.get_password(),
                      dest_server=dest_server, sudo=sudo, fail_ok=fail_ok)


def get_host_interfaces_for_net_type(host, net_type='infra', if_type=None, exclude_iftype=False, con_ssh=None):
    """
    Get interface names for given net_type that is expected to be listed in ifconfig on host
    Args:
        host (str):
        net_type (str): 'infra', 'mgmt' or 'oam', (data is handled in AVS thus not shown in ifconfig on host)
        if_type (str|None): When None, interfaces with all eth types will return
        exclude_iftype(bool): whether or not to exclude the if type specified.
        con_ssh (SSHClient):

    Returns (dict): {
        'ethernet': [<dev1>, <dev2>, etc],
        'vlan': [<dev1.vlan1>, <dev2.vlan2>, etc],
        'ae': [(<if1_name>, [<dev1_names>]), (<if2_name>, [<dev2_names>]), ...]
        }

    """
    LOG.info("Getting expected eth names for {} network on {}".format(net_type, host))
    table_origin = system_helper.get_host_interfaces_table(host=host, con_ssh=con_ssh)

    if if_type:
        table_ = table_parser.filter_table(table_origin, exclude=exclude_iftype, **{'type': if_type})
    else:
        table_ = copy.deepcopy(table_origin)

    network = ''
    if_class = net_type
    if net_type in PLATFORM_NET_TYPES:
        if_class = 'platform'
        network = net_type

    table_ = table_parser.filter_table(table_, **{'class': if_class})
    # exclude unmatched platform interfaces from the table.
    if 'platform' == if_class:
        platform_ifs = table_parser.get_values(table_, target_header='name', **{'class': 'platform'})
        for pform_if in platform_ifs:
            if_nets = system_helper.get_host_if_show_values(host=host, interface=pform_if, fields='networks')[0]
            if_nets = [if_net.strip() for if_net in if_nets.split(sep=',')]
            if network not in if_nets:
                table_ = table_parser.filter_table(table_, strict=True, exclude=True, name=pform_if)

    interfaces = {}
    table_eth = table_parser.filter_table(table_, **{'type': 'ethernet'})
    eth_ifs = table_parser.get_values(table_eth, 'ports')
    interfaces['ethernet'] = eth_ifs
    # such as ["[u'enp134s0f1']", "[u'enp131s0f1']"]

    table_ae = table_parser.filter_table(table_, **{'type': 'ae'})
    ae_names = table_parser.get_values(table_ae, 'name')
    ae_ifs = table_parser.get_values(table_ae, 'uses i/f')

    ae_list = []
    for i in range(len(ae_names)):
        ae_list.append((ae_names[i], ae_ifs[i]))
    interfaces['ae'] = ae_list

    table_vlan = table_parser.filter_table(table_, **{'type': ['vlan', 'vxlan']})
    vlan_ifs_ = table_parser.get_values(table_vlan, 'uses i/f')
    vlan_ids = table_parser.get_values(table_vlan, 'vlan id')
    vlan_list = []
    for i in range(len(vlan_ifs_)):
        # assuming only 1 item in 'uses i/f' list
        vlan_useif = eval(vlan_ifs_[i])[0]
        vlan_useif_ports = eval(table_parser.get_values(table_origin, 'ports', name=vlan_useif)[0])
        if vlan_useif_ports:
            vlan_useif = vlan_useif_ports[0]
        vlan_list.append("{}.{}".format(vlan_useif, vlan_ids[i]))

    LOG.info("Expected eth names for {} network on {}: {}".format(net_type, host, interfaces))
    return interfaces


def get_ntpq_status(host, con_ssh=None):
    """
    Get ntp status via 'sudo ntpq -pn'

    Args:
        host (str): host to check
        con_ssh (SSHClient)

    Returns(tuple): (<code>, <msg>)
        - (0, "<host> NTPQ is in healthy state")
        - (1, "No NTP server selected")
        - (2, "Some NTP servers are discarded")

    """
    cmd = 'ntpq -pn'
    with ssh_to_host(host, con_ssh=con_ssh) as host_ssh:
        output = host_ssh.exec_sudo_cmd(cmd, fail_ok=False)[1]

    output_lines = output.splitlines()
    server_lines = list(output_lines)
    for line in output_lines:
        server_lines.remove(line)
        if '======' in line:
            break

    selected = None
    discarded = []
    for server_line in server_lines:
        if re.match("{}.*".format(Networks.MGMT_IP), server_line[1:]):
            continue

        if server_line.startswith('*'):
            selected = server_line
        elif server_line.startswith('-') or server_line.startswith('x') or server_line.startswith(' '):
            discarded.append(server_line)

    if not selected:
        return 1, "No NTP server selected"

    if discarded:
        return 2, "Some NTP servers are discarded"

    return 0, "{} NTPQ is in healthy state".format(host)


def wait_for_ntp_sync(host, timeout=MiscTimeout.NTPQ_UPDATE, fail_ok=False, con_ssh=None,
                      auth_info=Tenant.get('admin')):

    LOG.info("Waiting for ntp alarm to clear or sudo ntpq -pn indicate unhealthy server for {}".format(host))
    end_time = time.time() + timeout
    msg = ntp_alarms = None
    if not con_ssh:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    while time.time() < end_time:
        ntp_alarms = system_helper.get_alarms(alarm_id=EventLogID.NTP_ALARM, entity_id=host, strict=False,
                                              con_ssh=con_ssh, auth_info=auth_info)
        status, msg = get_ntpq_status(host, con_ssh=con_ssh)
        if ntp_alarms and status != 0:
            LOG.info("Valid NTP alarm")
            return True
        elif not ntp_alarms and status == 0:
            LOG.info("NTP alarm cleared and sudo ntpq shows servers healthy")
            return True

        LOG.info("NTPQ status: {}; NTP alarms: {}".format(msg, ntp_alarms))
        time.sleep(30)

    err_msg = "Timed out waiting for NTP alarm to be in sync with ntpq output. NTPQ status: {}; NTP alarms: {}".\
        format(msg, ntp_alarms)
    if fail_ok:
        LOG.warning(err_msg)
        return False

    raise exceptions.HostTimeout(err_msg)


def get_host_cpu_model(host, con_ssh=None):
    """
    Get cpu model for a given host. e.g., Intel(R) Xeon(R) CPU E5-2680 v2 @ 2.80GHz
    Args:
        host (str): e.g., compute-0
        con_ssh (SSHClient):

    Returns (str):
    """
    table_ = table_parser.table(cli.system('host-cpu-list --nowrap', host, ssh_client=con_ssh))
    cpu_model = table_parser.get_column(table_, 'processor_model')[0]

    LOG.info("CPU Model for {}: {}".format(host, cpu_model))
    return cpu_model


def get_max_vms_supported(host, con_ssh=None):
    max_count = 10
    cpu_model = get_host_cpu_model(host=host, con_ssh=con_ssh)
    if ProjVar.get_var('IS_VBOX'):
        max_count = MaxVmsSupported.VBOX
    elif re.search(r'Xeon.* CPU D-[\d]+', cpu_model):
        max_count = MaxVmsSupported.XEON_D

    LOG.info("Max number vms supported on {}: {}".format(host, max_count))
    return max_count


def get_hypersvisors_with_config(hosts=None, up_only=True, hyperthreaded=None, storage_backing=None, con_ssh=None):
    """
    Get hypervisors with specified configurations
    Args:
        hosts (None|list):
        up_only (bool):
        hyperthreaded
        storage_backing (None|str):
        con_ssh (SSHClient):

    Returns (list): list of hosts meeting the requirements

    """
    if up_only:
        hypervisors = get_up_hypervisors(con_ssh=con_ssh)
    else:
        hypervisors = get_hypervisors(con_ssh=con_ssh)

    if hosts:
        candidate_hosts = list(set(hypervisors) & set(hosts))
    else:
        candidate_hosts = hypervisors

    if candidate_hosts and storage_backing:
        candidate_hosts = get_hosts_in_storage_backing(storage_backing=storage_backing, con_ssh=con_ssh,
                                                       hosts=candidate_hosts)

    if hyperthreaded is not None and candidate_hosts:
        ht_hosts = []
        non_ht = []
        for host in candidate_hosts:
            if system_helper.is_hyperthreading_enabled(host, con_ssh=con_ssh):
                ht_hosts.append(host)
            else:
                non_ht.append(host)
        candidate_hosts = ht_hosts if hyperthreaded else non_ht

    return candidate_hosts


def lock_unlock_controllers(host_recover='function', alarm_ok=False, no_standby_ok=False):
    """
    lock/unlock both controller to get rid of the config out of date situations

    Args:
        host_recover (None|str): try to recover host if lock/unlock fails
        alarm_ok (bool)
        no_standby_ok (bool)

    Returns (tuple): return code and msg

    """
    active, standby = system_helper.get_active_standby_controllers()
    if standby:
        LOG.info("Locking unlocking controllers to complete action")
        from testfixtures.recover_hosts import HostsToRecover
        if host_recover:
            HostsToRecover.add(hostnames=standby, scope=host_recover)
        lock_host(standby)
        unlock_host(standby)
        if host_recover:
            HostsToRecover.remove(hostnames=standby, scope=host_recover)
        drbd_res = system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CON_DRBD_SYNC, entity_id=standby,
                                                     strict=False, fail_ok=alarm_ok, timeout=300, check_interval=20)
        if not drbd_res:
            return 1, "400.001 alarm is not cleared within timeout after unlock standby"

        lock_host(active, swact=True)
        unlock_host(active)
        drbd_res = system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CON_DRBD_SYNC, entity_id=active,
                                                     strict=False, fail_ok=alarm_ok, timeout=300)
        if not drbd_res:
            return 1, "400.001 alarm is not cleared within timeout after unlock standby"

    elif system_helper.is_simplex():
        LOG.info("Simplex system - lock/unlock only controller")
        lock_host('controller-0', swact=False)
        unlock_host('controller-0')

    else:
        LOG.warning("Standby controller unavailable. Unable to lock active controller.")
        if no_standby_ok:
            return 2, 'No standby available, thus unable to lock/unlock controllers'
        else:
            raise exceptions.HostError("Unable to lock/unlock controllers due to no standby controller")

    return 0, "Locking unlocking controller(s) completed"


def lock_unlock_hosts(hosts, force_lock=False, con_ssh=None, auth_info=Tenant.get('admin'), recover_scope='function'):
    """
    Lock/unlock hosts simultaneously when possible.
    Args:
        hosts (str|list):
        force_lock (bool): lock without migrating vms out
        con_ssh:
        auth_info
        recover_scope (None|str):

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    last_compute = last_storage = None
    from keywords import nova_helper
    from testfixtures.recover_hosts import HostsToRecover

    controllers, computes, storages = system_helper.get_hostnames_per_personality(con_ssh=con_ssh, auth_info=auth_info,
                                                                                  rtn_tuple=True)
    controllers = list(set(controllers) & set(hosts))
    computes_to_lock = list(set(computes) & set(hosts))
    storages = list(set(storages) & set(hosts))

    hosts_to_lock = list(computes_to_lock)
    if computes and not force_lock and len(computes) == len(computes_to_lock) and \
            nova_helper.get_vms(auth_info=auth_info):
        # leave a compute if there are vms on system and force lock=False
        last_compute = hosts_to_lock.pop()

    active, standby = system_helper.get_active_standby_controllers(con_ssh=con_ssh, auth_info=auth_info)

    if standby and standby in controllers:
        hosts_to_lock.append(standby)

        if storages and 'storage-0' in storages:
            # storage-0 cannot be locked with any controller
            last_storage = 'storage-0'
            storages.remove(last_storage)
    if storages:
        hosts_to_lock += storages

    LOG.info("Lock/unlock: {}".format(hosts_to_lock))
    hosts_locked = []
    try:
        for host in hosts_to_lock:
            HostsToRecover.add(hostnames=host, scope=recover_scope)
            lock_host(host, con_ssh=con_ssh, force=force_lock, auth_info=auth_info)
            hosts_locked.append(host)

    finally:
        if hosts_locked:
            unlock_hosts(hosts=hosts_locked, con_ssh=con_ssh, auth_info=auth_info)
            wait_for_hosts_ready(hosts=hosts_locked, con_ssh=con_ssh, auth_info=auth_info)
            HostsToRecover.remove(hosts_locked, scope=recover_scope)

        LOG.info("Lock/unlock last compute {} and storage {} if any".format(last_compute, last_storage))
        hosts_locked_next = []
        try:
            for host in (last_compute, last_storage):
                if host:
                    HostsToRecover.add(host, scope=recover_scope)
                    lock_host(host=host, con_ssh=con_ssh, auth_info=auth_info)
                    hosts_locked_next.append(host)

        finally:
            if hosts_locked_next:
                unlock_hosts(hosts_locked_next, con_ssh=con_ssh, auth_info=auth_info)
                wait_for_hosts_ready(hosts_locked_next, con_ssh=con_ssh, auth_info=auth_info)
                HostsToRecover.remove(hosts_locked_next, scope=recover_scope)

            if active in controllers:
                if active and system_helper.is_two_node_cpe(con_ssh=con_ssh, auth_info=auth_info):
                    system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CPU_USAGE_HIGH, check_interval=30,
                                                      timeout=300, con_ssh=con_ssh, entity_id=active,
                                                      auth_info=auth_info)
                LOG.info("Lock/unlock {}".format(active))
                HostsToRecover.add(active, scope=recover_scope)
                lock_host(active, swact=True, con_ssh=con_ssh, force=force_lock, auth_info=auth_info)
                unlock_hosts(active, con_ssh=con_ssh, auth_info=auth_info)
                wait_for_hosts_ready(active, con_ssh=con_ssh, auth_info=auth_info)
                HostsToRecover.remove(active, scope=recover_scope)

    LOG.info("Hosts lock/unlock completed: {}".format(hosts))


def get_traffic_control_rates(dev, con_ssh=None):
    """
    Check the traffic control profile on given device name

    Returns (dict): return traffic control rates in Mbit.
        e.g., {'root': [10000, 10000], 'drbd': [8000, 10000], ... }

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    output = con_ssh.exec_cmd('tc class show dev {}'.format(dev), expect_timeout=10)[1]

    traffic_classes = {}
    for line in output.splitlines():
        match = re.findall(TrafficControl.RATE_PATTERN, line)
        if match:
            ratio, rate, rate_unit, ceil_rate, ceil_rate_unit = match[0]
            class_name = TrafficControl.CLASSES[ratio]
        else:
            root_match = re.findall(TrafficControl.RATE_PATTERN_ROOT, line)
            if not root_match:
                raise NotImplementedError('Unrecognized traffic class line: {}'.format(line))
            rate, rate_unit, ceil_rate, ceil_rate_unit = root_match[0]
            class_name = 'root'

        rate = int(rate)
        ceil_rate = int(ceil_rate)

        rates = []
        for rate_info in ((rate, rate_unit), (ceil_rate, ceil_rate_unit)):
            rate_, unit_ = rate_info
            rate_ = int(rate_)
            if unit_ == 'G':
                rate_ = int(rate_*1000)
            elif unit_ == 'K':
                rate_ = int(rate_/1000)

            rates.append(rate_)

        traffic_classes[class_name] = rates

    LOG.info("Traffic classes for {}: ".format(dev, traffic_classes))
    return traffic_classes


def get_nic_speed(interface, con_ssh=None):
    """
    Check the speed on given interface name
    Args:
        interface (str|list)
        con_ssh

    Returns (list): return speed

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if isinstance(interface, str):
        interface = [interface]

    speeds = []
    for if_ in interface:
        if_speed = con_ssh.exec_cmd('cat /sys/class/net/{}/speed' .format(if_), expect_timeout=10, fail_ok=False)[1]
        speeds.append(int(if_speed))

    return speeds


def get_host_telnet_session(host, login=True, lab=None):

    if lab is None:
        lab = ProjVar.get_var('LAB')

    host_node = lab[host]
    if host_node is None:
        raise ValueError("A node object for host {} is not defined in lab dict : {}".format(host, lab))

    log_dir = ProjVar.get_var('LOG_DIR')

    if host_node.telnet_conn:
        host_node.telnet_conn.close()

    host_node.telnet_conn = telnetlib.connect(host_node.telnet_ip,
                                              int(host_node.telnet_port),
                                              negotiate=host_node.telnet_negotiate,
                                              port_login=True if host_node.telnet_login_prompt else False,
                                              vt100query=host_node.telnet_vt100query,
                                              log_path=log_dir + "/" + host_node.name + ".telnet.log", debug=False)

    if host_node.telnet_conn and login:
        host_node.telnet_conn.login()
    lab[host] = host_node
    return host_node.telnet_conn


def power_on_host(host, fail_ok=False, timeout=HostTimeout.REBOOT, unlock=True, con_ssh=None):
    """
    Power on given host, unlock after power on if unlock=True
    Args:
        host (str):
        fail_ok (bool):
        timeout (int):
        unlock (bool):
        con_ssh (SSHClient):

    Returns (tuple):
        (0, <success_msg>)  # host is powered on (and unlocked) successfully
        (1, <stderr>)       # host-power-on cli is rejected

    """
    admin_state, avail_state = get_hostshow_values(host=host, fields=['administrative', 'availability'],
                                                   con_ssh=con_ssh)
    if HostAvailState.POWER_OFF != avail_state or HostAdminState.LOCKED != admin_state:
        LOG.warning("Attempt to power-on {} while it's in {} & {} states".format(host, admin_state, avail_state))

    code, output = cli.system('host-power-on', host, ssh_client=con_ssh, fail_ok=fail_ok)
    if code != 0:
        return 1, output

    wait_for_host_values(host=host, timeout=60, task=HostTask.POWERING_ON, con_ssh=con_ssh, fail_ok=True)
    wait_for_host_values(host=host, timeout=timeout, availability=HostAvailState.ONLINE, fail_ok=False)

    msg = '{} is successfully powered on'.format(host)
    LOG.info(msg)

    if unlock:
        unlock_host(host=host, con_ssh=con_ssh, fail_ok=False)
        msg += ' and unlocked'

    return 0, msg


def clear_local_storage_cache(host, con_ssh=None):
    with ssh_to_host(host, con_ssh=con_ssh) as host_ssh:
        with host_ssh.login_as_root() as root_ssh:
            root_ssh.exec_cmd('rm -rf /var/lib/nova/instances/_base/*', fail_ok=True)
            root_ssh.exec_cmd('sync;echo 3 > /proc/sys/vm/drop_caches', fail_ok=True)


def get_host_device_list_values(host, field='name', list_all=False, con_ssh=None, auth_info=Tenant.get('admin'),
                                strict=True, regex=False, **kwargs):
    """
    Get the parsed version of the output from system host-device-list <host>
    Args:
        host (str): host's name
        field (str): field name to return value for
        list_all (bool): whether to list all devices including the disabled ones
        con_ssh (SSHClient):
        auth_info (dict):
        strict (bool): whether to perform strict search on filter
        regex (bool): whether to use regular expression to search the value in kwargs
        kwargs: key-value pairs to filter the table

    Returns (list): output of system host-device-list <host> parsed by table_parser

    """
    param = '--nowrap'
    param += ' --all' if list_all else ''
    table_ = table_parser.table(cli.system('host-device-list {}'.format(param), host, ssh_client=con_ssh,
                                           auth_info=auth_info))

    values = table_parser.get_values(table_, target_header=field, strict=strict, regex=regex, **kwargs)

    if field in ('numa_node', 'enabled'):
        try:
            values = [eval(val) for val in values]
        except:
            pass

    return values


def get_host_device_values(host, device, fields, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get host device values for given fields via system host-device-show
    Args:
        host:
        device:
        fields (str|list|tuple):
        con_ssh:
        auth_info:

    Returns (list):

    """
    args = "{} {}".format(host, device)
    table_ = table_parser.table(cli.system('host-device-show', args, ssh_client=con_ssh, auth_info=auth_info))

    if isinstance(fields, str):
        fields = [fields]

    vals = []
    for field in fields:
        value = table_parser.get_value_two_col_table(table_, field)
        if field in ('numa_node', 'sriov_numvfs', 'sriov_totalvfs', 'enabled'):
            try:
                value = eval(value)
            except:
                pass
        vals.append(value)

    return vals


def modify_host_device(host, device, new_name=None, new_state=None, check_first=True, lock_unlock=False, fail_ok=False,
                       con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Modify host device to given name or state.
    Args:
        host: host to modify
        device: device name or pci address
        new_name (str): new name to modify to
        new_state (bool): new state to modify to
        lock_unlock (bool): whether to lock unlock host before and after modify
        con_ssh (SSHClient):
        fail_ok (bool):
        check_first (bool):
        auth_info (dict):

    Returns (tuple):

    """
    args = ''
    fields = []
    expt_vals = []
    if new_name:
        fields.append('name')
        expt_vals.append(new_name)
        args += ' --name {}'.format(new_name)
    if new_state is not None:
        fields.append('enabled')
        expt_vals.append(new_state)
        args += ' --enabled {}'.format(new_state)

    if check_first and fields:
        vals = get_host_device_values(host, device, fields=fields, con_ssh=con_ssh, auth_info=auth_info)
        if vals == expt_vals:
            return -1, "{} device {} already set to given name and/or state".format(host, device)

    try:
        if lock_unlock:
            LOG.info("Lock host before modify host device")
            lock_host(host=host, con_ssh=con_ssh, auth_info=auth_info)

        LOG.info("Modify {} device {} with args: {}".format(host, device, args))
        args = "{} {} {}".format(host, device, args.strip())
        res, out = cli.system('host-device-modify', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                              auth_info=auth_info)

        if res == 1:
            return 1, out

        LOG.info("Verifying the host device new pci name")
        post_vals = get_host_device_values(host, device, fields=fields, con_ssh=con_ssh, auth_info=auth_info)
        assert expt_vals == post_vals, "{} device {} is not modified to given values. Expt: {}, actual: {}".\
            format(host, device, expt_vals, post_vals)

        msg = "{} device {} is successfully modified to given values".format(host, device)
        LOG.info(msg)
        return 0, msg
    finally:
        if lock_unlock:
            LOG.info("Unlock host after host device modify")
            unlock_host(host=host, con_ssh=con_ssh, auth_info=auth_info)


def enable_disable_hosts_devices(hosts, devices, enable=True, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Enable/Disable given devices on specified hosts. (lock/unlock required unless devices already in state)
    Args:
        hosts (str|list|tuple): hostname(s)
        devices (str|list|tuple): device(s) name or address via system host-device-list
        enable (bool): whether to enable or disable devices
        con_ssh
        auth_info

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    if isinstance(devices, str):
        devices = [devices]

    key = 'name' if 'pci_' in devices[0] else 'address'
    for host_ in hosts:
        states = get_host_device_list_values(host=host_, field='enabled', list_all=True, con_ssh=con_ssh,
                                             auth_info=auth_info, **{key: devices})
        if (not enable) in states:
            try:
                lock_host(host=host_, swact=True, con_ssh=con_ssh, auth_info=auth_info)
                for i in range(len(states)):
                    if states[i] is not enable:
                        device = devices[i]
                        modify_host_device(host=host_, device=device, new_state=enable, check_first=False,
                                           con_ssh=con_ssh, auth_info=auth_info)
            finally:
                unlock_host(host=host_, con_ssh=con_ssh, auth_info=auth_info)

        post_states = get_host_device_list_values(host=host_, field='enabled', list_all=True, con_ssh=con_ssh,
                                                  auth_info=auth_info, **{key: devices})
        assert not ((not enable) in post_states), "Some devices enabled!={} after unlock".format(enable)

    LOG.info("enabled={} set successfully for following devices on hosts {}: {}".format(enable, hosts, devices))


def get_host_cmdline_options(host, con_ssh=None):
    with ssh_to_host(hostname=host, con_ssh=con_ssh) as host_ssh:
        output = host_ssh.exec_cmd('cat /proc/cmdline')[1]

    return output


@contextmanager
def ssh_to_remote_node(host, username=None, password=None, prompt=None, ssh_client=None, use_telnet=False,
                       telnet_session=None):
    """
    ssh to a external node from sshclient.

    Args:
        host (str|None): hostname or ip address of remote node to ssh to.
        username (str):
        password (str):
        prompt (str):
        ssh_client (SSHClient): client to ssh from
        use_telnet:
        telnet_session:

    Returns (SSHClient): ssh client of the host

    Examples: with ssh_to_remote_node('128.224.150.92) as remote_ssh:
                  remote_ssh.exec_cmd(cmd)
\    """

    if not host:
        raise exceptions.SSHException("Remote node hostname or ip address must be provided")

    if use_telnet and not telnet_session:
        raise exceptions.SSHException("Telnet session cannot be none if using telnet.")

    if not ssh_client and not use_telnet:
        ssh_client = ControllerClient.get_active_controller()

    if not use_telnet:
        default_user, default_password = security_helper.LinuxUser.get_current_user_password()
    else:
        default_user = HostLinuxCreds.get_user()
        default_password = HostLinuxCreds.get_password()

    user = username if username else default_user
    password = password if password else default_password
    if use_telnet:
        original_host = telnet_session.exec_cmd('hostname')[1]
    else:
        original_host = ssh_client.host

    if not prompt:
        prompt = '.*' + host + r'\:~\$'

    remote_ssh = SSHClient(host, user=user, password=password, initial_prompt=prompt)
    remote_ssh.connect()
    current_host = remote_ssh.host
    if not current_host == host:
        raise exceptions.SSHException("Current host is {} instead of {}".format(current_host, host))
    try:
        yield remote_ssh
    finally:
        if current_host != original_host:
            remote_ssh.close()
