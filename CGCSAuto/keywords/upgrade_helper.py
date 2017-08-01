"""
This module provides helper functions for host upgrade functions
"""

import time
from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from keywords import system_helper, host_helper, install_helper, orchestration_helper, storage_helper
from consts.cgcs import HostOperationalState, HostAvailabilityState, Prompt, HostAdminState
from consts.auth import Tenant, HostLinuxCreds
from consts.timeout import HostTimeout


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
        if host_helper.get_hostshow_value(host, 'administrative', con_ssh=con_ssh) == HostAdminState.UNLOCKED:
            message = "Host is not locked. Locking host  before starting upgrade"
            LOG.info(message)
            rc, output = host_helper.lock_host(host, con_ssh=con_ssh, fail_ok=True)

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

    if not host_helper.wait_for_host_states(host, timeout=timeout, check_interval=60,
                                            availability=HostAvailabilityState.ONLINE, con_ssh=con_ssh,
                                            fail_ok=fail_ok):
        err_msg = "Host {} did not become online  after upgrade".format(host)
        if fail_ok:
            return 3, err_msg
        else:
            raise exceptions.HostError(err_msg)

    if host.strip() == "controller-1":
        rc, output = _wait_for_upgrade_data_migration_complete(timeout=timeout,
                                                               auth_info=auth_info, fail_ok=fail_ok, con_ssh=con_ssh)
        if rc != 0:
            err_msg = "Host {} upgrade data migration failure: {}".format(host, output)
            if fail_ok:
                return 2, err_msg
            else:
                raise exceptions.HostError(err_msg)

    if unlock:
        rc, output = host_helper.unlock_host(host, fail_ok=True, available_only=True)
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


def _wait_for_upgrade_data_migration_complete(timeout=1800, check_interval=60, auth_info=Tenant.ADMIN,
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
    """
    Gets the target release of a upgrade hosts
    Args:
        hostnames(str/list):  specifies the host or list of hosts
        con_ssh:

    Returns:  list of target releases.

    """
    if isinstance(hostnames, str):
        hostnames = [hostnames]

    table_ = table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, hostname=hostnames)
    return table_parser.get_column(table_, "target_release")


def get_hosts_upgrade_running_release(hostnames, con_ssh=None):
    """
    Gets the running_release of host(s)
    Args:
        hostnames (str/list): specifies the host or list of hosts
        con_ssh:

    Returns: list of running release ids.

    """
    if isinstance(hostnames, str):
        hostnames = [hostnames]

    table_ = table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(hostname=hostnames, table_=table_)
    return table_parser.get_column(table_, "running_release")


def get_system_health_query_upgrade(con_ssh=None):
    """
    Queries the upgrade health of a system in use.
    Args:
        con_ssh:

    Returns: tuple
        (0, None) - success
        (1, dict(error msg) ) -  health query reported errors

    """

    output = (cli.system('health-query-upgrade', ssh_client=con_ssh)).splitlines()
    failed = {}
    ok = {}
    for line in output:
        if ":" in line:
            k, v = line.split(":")
            if "[OK]" in v.strip():
                ok[k.strip()] = v.strip()
            elif "[Fail]" in v.strip():
                failed[k.strip()] = v.strip()
        elif "Missing manifests" in line:
            failed[line] = line
    if len(failed) > 0:
        return 1, failed
    else:
        return 0, None


def system_upgrade_start(con_ssh=None, force=False, fail_ok=False):
    """
    Starts upgrade
    Args:
        con_ssh:
        force:
        fail_ok:

    Returns (tuple):
        (0, output)
        (1, <stderr>) : "if fail_ok is true # cli returns stderr.
        (2, <stderr>) : "applicable only if fail_ok is true. upgrade-start rejected:
        An upgrade is already in progress."
    """
    if force:
        rc, output = cli.system("upgrade-start", positional_args='--force', fail_ok=True, ssh_client=con_ssh)
    else:
        rc, output = cli.system("upgrade-start", fail_ok=True, ssh_client=con_ssh)

    if rc == 0:
        LOG.info("system upgrade-start ran successfully.")
        return 0, output

    else:
        if "An upgrade is already in progress" in output:
            # upgrade already in progress
            LOG.warning("Upgrade is already in progress. No need to start")
            if fail_ok:
                return 2, output
            else:
                raise exceptions.CLIRejected(output)
        else:
            err_msg = "CLI system command failed: {}".format(output)
            LOG.warning(err_msg)
            if fail_ok:
                return 1, output
            else:
                raise exceptions.CLIRejected(err_msg)


def system_upgrade_show(con_ssh=None):

    """
    Get the current upgrade progress status
    Args:
        con_ssh:

    Returns (tuple):
        (0, dict/list) - success
        (1, <stderr>)   # cli returns stderr.

    """

    rc, output = cli.system("upgrade-show", fail_ok=True, ssh_client=con_ssh)

    if rc == 0:
        return rc, table_parser.table(output)
    else:
        return rc, output


def activate_upgrade(con_ssh=None, fail_ok=False):
    """
    Activates upgrade
    Args:
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple):
        (0, dict/list) - success
        (1, <stderr>)   # cli returns stderr, applicable if fail_ok is true

    """
    rc, output = cli.system('upgrade-activate', ssh_client=con_ssh, fail_ok=True, rtn_list=True)
    if rc != 0:
        err_msg = "CLI system upgrade-activate failed: {}".format(output)
        LOG.warning(err_msg)
        if fail_ok:
            return rc, output
        else:
            raise exceptions.CLIRejected(err_msg)

    if not system_helper.wait_for_alarm_gone("250.001", con_ssh=con_ssh, timeout=900, check_interval=60, fail_ok=True):

        alarms = system_helper.get_alarms(alarm_id="250.001")
        err_msg = "After activating upgrade alarms are not cleared : {}".format(alarms)
        LOG.warning(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.HostError(err_msg)

    if not wait_for_upgrade_activate_complete(fail_ok=True):
        err_msg = "Upgrade activate failed"
        LOG.warning(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.HostError(err_msg)

    LOG.info("Upgrade activation complete")
    return 0, None


def get_hosts_upgrade_status(con_ssh=None):
    return table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))


def get_upgrade_state(con_ssh=None):

    output = cli.system('upgrade-show', ssh_client=con_ssh)

    if ("+" and "-" and "|") in output:
        table_ = table_parser.table(output)
        table_ = table_parser.filter_table(table_, Property="state")
        return table_parser.get_column(table_, "Value")
    else:
        return output


def wait_for_upgrade_activate_complete(timeout=300, check_interval=60, fail_ok=False):
    upgrade_state = ''
    end_time = time.time() + timeout
    while time.time() < end_time:
        upgrade_state = get_upgrade_state()
        if "activation-complete" in upgrade_state:
            LOG.info('Upgrade activation-complete')
            return True

        time.sleep(check_interval)

    err_msg = "Upgrade activation did not complete after waiting for {} seconds. Current state is {}".\
        format(timeout, upgrade_state)
    if fail_ok:
        LOG.warning(err_msg)
        return False, None
    raise exceptions.TimeoutException(err_msg)


def complete_upgrade(con_ssh=None, fail_ok=False):
    """
    Completes upgrade
    Args:
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple):
        (0, dict/list)
        (1, <stderr>)   # cli returns stderr, applicable if fail_ok is true

    """
    rc, output = cli.system('upgrade-complete', ssh_client=con_ssh, fail_ok=True, rtn_list=True)
    if rc != 0:
        err_msg = "CLI system upgrade-complete rejected: {}".format(output)
        LOG.warning(err_msg)
        if fail_ok:
            return 1, output
        else:
            raise exceptions.CLIRejected(err_msg)

    return 0, "Upgrade complete"


def install_upgrade_license(license_path, timeout=30, con_ssh=None):
    """
    Installs upgrade license on controller-0
    Args:
        con_ssh (SSHClient): " SSH connection to controller-0"
        license_path (str): " license full path in controller-0"
        timeout (int);

    Returns (int): 0 - success; 1 - failure

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    cmd = "sudo license-install " + license_path
    con_ssh.send(cmd)
    end_time = time.time() + timeout
    rc = 1
    while time.time() < end_time:
        index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT, Prompt.Y_N_PROMPT], timeout=timeout)
        if index == 2:
            con_ssh.send('y')

        if index == 1:
            con_ssh.send(HostLinuxCreds.PASSWORD)

        if index == 0:
            rc = con_ssh.exec_cmd("echo $?")[0]
            con_ssh.flush()
            break

    return rc


def abort_upgrade(con_ssh=None, timeout=60, fail_ok=False):
    """
    Aborts upgrade
    Args:
        con_ssh (SSHClient):
        timeout (int)
        fail_ok (bool):

    Returns (tuple):
        (0, dict/list)
        (1, <stderr>)   # cli returns stderr, applicable if fail_ok is true

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    cmd = "source /etc/nova/openrc; system upgrade-abort"
    con_ssh.send(cmd)
    end_time = time.time() + timeout
    rc = 1
    while time.time() < end_time:
        index = con_ssh.expect([con_ssh.prompt,  Prompt.YES_N_PROMPT], timeout=timeout)
        if index == 1:
            con_ssh.send('yes')
            index = con_ssh.expect([con_ssh.prompt, Prompt.CONFIRM_PROMPT], timeout=timeout)
            if index == 1:
                con_ssh.send('abort')
                index = con_ssh.expect([con_ssh.prompt, Prompt.CONFIRM_PROMPT], timeout=timeout)
        if index == 0:
            rc = con_ssh.exec_cmd("echo $?")[0]
            con_ssh.flush()
            break

    if rc != 0:
        err_msg = "CLI system upgrade-abort rejected"
        LOG.warning(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.CLIRejected(err_msg)

    table_ = system_upgrade_show()[1]
    state = table_parser.get_value_two_col_table(table_, "state")
    if "aborting" in state:
        return 0, "Upgrade aborting"
    else:
        err_msg = "Upgrade abort failed"
        if fail_ok:
            LOG.warn(err_msg)
            return 1, err_msg
        else:
            raise exceptions.CLIRejected(err_msg)


def upgrade_controller0():
    """
    Upgrades controller-0
    Returns:

    """

    # upgrade  controller-0
    LOG.tc_step("Upgrading  controller-0......")

    controller0 = 'controller-0'
    LOG.info("Ensure controller-0 is provisioned before upgrade.....")
    host_helper.ensure_host_provisioned(controller0)
    LOG.info("Host {} is provisioned for upgrade.....".format(controller0))

    # open vlm console for controller-0 for boot through mgmt interface
    LOG.info("Opening a vlm console for controller-0 .....")
    install_helper.open_vlm_console_thread(controller0)

    LOG.info("Starting {} upgrade.....".format(controller0))
    upgrade_host(controller0, lock=True)
    LOG.info("controller-0 is upgraded successfully.....")

    # unlock upgraded controller-0
    LOG.tc_step("Unlocking controller-0 after upgrade......")
    host_helper.unlock_host(controller0, available_only=True)
    LOG.info("Host {} unlocked after upgrade......".format(controller0))


def upgrade_controller(controller_host, con_ssh=None, fail_ok=False):
    """
    Upgrades either controller-0 or controller-1
    Args:
        controller_host (str): the controller host name
        con_ssh (SSHClient):
        fail_ok(bool):

    Returns:
        if fail_ok is true  return error code and message

    """

    if controller_host not in ['controller-0', 'controller-1']:
        err_msg = "The specified host {} is not a controller host".format(controller_host)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.UpgradeError(err_msg)

    LOG.info("Upgrading Host {}".format(controller_host))
    if controller_host == 'controller-0':
        host_helper.ensure_host_provisioned(controller_host, con_ssh=con_ssh)
        LOG.info("Host {} is provisioned for upgrade.....".format(controller_host))

        # # open vlm console for controller-0 for boot through mgmt interface
        # LOG.info("Opening a vlm console for controller-0 .....")
        # install_helper.open_vlm_console_thread(controller_host)

    upgrade_host(controller_host, lock=True, con_ssh=con_ssh)
    LOG.info("Host {} is upgraded successfully......".format(controller_host))

    # unlock upgraded controller
    LOG.tc_step("Unlocking {} after upgrade......".format(controller_host))
    if controller_host == 'controller-1':
        host_helper.unlock_host(controller_host, available_only=True, check_hypervisor_up=False, con_ssh=con_ssh,
                                fail_ok=fail_ok)
    else:
        host_helper.unlock_host(controller_host, available_only=True, con_ssh=con_ssh, fail_ok=fail_ok)

    LOG.info("Host {} unlocked after upgrade......".format(controller_host))


def orchestration_upgrade_hosts(upgraded_hosts, orchestration_nodes):

    # Create upgrade strategy
    orchestration = 'upgrade'
    storage_apply_type = ''
    compute_apply_type = ''
    max_parallel_computes = 0
    alarm_restrictions = 'relaxed'
    if orchestration_nodes is None:
        orchestration_nodes = []
    elif isinstance(orchestration_nodes, str):
        orchestration_nodes = [orchestration_nodes]

    if upgraded_hosts is None:
        upgraded_hosts = []
    elif isinstance(upgraded_hosts, str):
        upgraded_hosts = [upgraded_hosts]

    if not isinstance(orchestration_nodes, list) or not isinstance(upgraded_hosts, list):
        raise exceptions.OrchestrationError("Value error: List of upgraded or orchestration nodes expected")

    if len(orchestration_nodes) > 0:

        upgrade_hosts_ = list(orchestration_nodes)
        upgraded_computes = len([h for h in upgraded_hosts if 'storage' not in h and 'controller' not in h])
        computes_to_upgrade = len([h for h in upgrade_hosts_ if 'storage' not in h and 'controller' not in h])
        storages_to_upgrade = len([h for h in upgrade_hosts_ if 'storage' in h])

        num_parallel_computes = int((computes_to_upgrade + upgraded_computes)/2)\
                                + (computes_to_upgrade + upgraded_computes) % 2
        if upgraded_computes > num_parallel_computes:
            num_parallel_computes = computes_to_upgrade

        if storages_to_upgrade > 0:
            storage_apply_type = 'parallel'
        if computes_to_upgrade > 0:
            if num_parallel_computes > 1:
                compute_apply_type = 'parallel'
                max_parallel_computes = num_parallel_computes
            else:
                compute_apply_type = 'serial'

        LOG.tc_step("Creating upgrade strategy  ......")
        orchestration_helper.create_strategy(orchestration, storage_apply_type=storage_apply_type,
                                             compute_apply_type=compute_apply_type,
                                             max_parallel_computes=max_parallel_computes,
                                             alarm_restrictions=alarm_restrictions)

        LOG.tc_step("Applying upgrade strategy ......")
        orchestration_helper.apply_strategy(orchestration)


def manual_upgrade_hosts(manual_nodes):
    """
    Upgrades hosts in manual_nodes list one by one.
    Args:
        manual_nodes (list): - specifies the list of nodes to be upgraded one at a time.

    Returns:

    """

    if len(manual_nodes) > 0:
        LOG.info("Starting upgrade of the other system hosts: {}".format(manual_nodes))
        nodes_to_upgrade = list(manual_nodes)
        if 'controller-0' in nodes_to_upgrade:

            upgrade_controller('controller-0')
            nodes_to_upgrade.remove('controller-0')

        for host in nodes_to_upgrade:
            LOG.tc_step("Starting {} upgrade.....".format(host))
            if "storage" in host:
                # wait for replication  to be healthy
                storage_helper.wait_for_ceph_health_ok()

                upgrade_host(host, lock=True)
                LOG.info("{} is upgraded successfully.....".format(host))
                LOG.tc_step("Unlocking {} after upgrade......".format(host))
                host_helper.unlock_host(host, available_only=True)
                LOG.info("Host {} unlocked after upgrade......".format(host))
                LOG.info("Host {} upgrade complete.....".format(host))


def upgrade_host_lock_unlock(host, con_ssh=None):
    """
     swact, if required, lock and unlock before upgrade.

    Args:
        host (str): hostname or id in string format
        con_ssh (SSHClient):

    Returns: (return_code(int), msg(str))
        (0, "Host is host is locked/unlocked)
    """
    LOG.info("Checking if host {} is active ....".format(host))

    active_controller = system_helper.get_active_controller_name()
    swact_back = False
    if active_controller == host:
        LOG.tc_step("Swact active controller and ensure active controller is changed")
        exit_code, output = host_helper.swact_host(hostname=active_controller)
        assert 0 == exit_code, "{} is not recognized as active controller".format(active_controller)
        active_controller = system_helper.get_active_controller_name()
        swact_back = True

    LOG.info("Host {}; doing lock/unlock to the host ....".format(host))
    rc, output = host_helper.lock_host(host, con_ssh=con_ssh)
    if rc != 0 and rc != -1:
        err_msg = "Lock host {} rejected".format(host)
        LOG.warn(err_msg)
        return 1, err_msg

    rc, output = host_helper.unlock_host(host, available_only=True, con_ssh=con_ssh)
    if rc != 0:
        err_msg = "Unlock host {} failed: {}".format(host, output)
        return 1, err_msg

    if swact_back:
        time.sleep(60)

        if not host_helper.wait_for_host_states(host, timeout=360, fail_ok=True,
                                                operational=HostOperationalState.ENABLED,
                                                availability=HostAvailabilityState.AVAILABLE):
            err_msg = " Swacting to standby is not possible because {} is not in available state " \
                  "within  the specified timeout".format(host)
            assert False, err_msg
        LOG.tc_step("Swact active controller back and ensure active controller is changed")
        rc, output = host_helper.swact_host(hostname=active_controller)
        if rc != 0:
            err_msg = "Failed to swact back to host {}: {}".format(host, output)
            return 1, err_msg

        LOG.info("Swacted and  {}  has become active......".format(host))

    return 0, "Host {} is  locked and unlocked successfully".format(host)


def get_upgraded_hosts(upgrade_version, con_ssh=None, fail_ok=False, source_creden_=None):
    """
    Gets the upgraded hosts in the current upgrade process.
    Args:
        upgrade_version(str): - specifies the upgrade version
        con_ssh:
        fail_ok:
        source_creden_:

    Returns:

    """

    table_ = table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh, fail_ok=fail_ok,
                                           source_creden_=source_creden_))
    table_ = table_parser.filter_table(table_, **{'running_release': upgrade_version})
    return table_parser.get_values(table_, 'hostname')

