import pytest
from pytest import skip
import time
from utils.tis_log import LOG
from keywords import system_helper, host_helper, install_helper
from consts.proj_vars import InstallVars
from utils import table_parser
from consts.cgcs import HostAvailabilityState, HostOperationalState


# def test_system_upgrade_controller_1(upgrade_setup, check_system_health_query_upgrade):
#
#     LOG.tc_func_start("UPGRADE_TEST")
#
#     lab = upgrade_setup['lab']
#     current_version = upgrade_setup['current_version']
#     upgrade_version = upgrade_setup['upgrade_version']
#
#     # run system upgrade-start
#     # must be run in controller-0
#     active_controller = system_helper.get_active_controller_name()
#     LOG.tc_step("Checking if active controller is controller-0......")
#     assert "controller-0" in active_controller, "The active controller is not " \
#                                                 "controller-0. Make controller-0 " \
#                                                 "active before starting upgrade"
#
#     force = False
#     LOG.tc_step("Checking system health for upgrade .....")
#     if check_system_health_query_upgrade[0] == 0:
#         LOG.info("System health OK for upgrade......")
#     elif check_system_health_query_upgrade[0] == 2:
#         LOG.info("System health indicate minor alarms; using --force option to start upgrade......")
#         force = True
#     else:
#         assert False, "System health query upgrade failed: {}".format(check_system_health_query_upgrade[1])
#
#     LOG.info("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
#     system_helper.system_upgrade_start(force=force)
#     LOG.tc_step("upgrade started successfully......")
#
#     # upgrade standby controller
#     LOG.tc_step("Upgrading controller-1")
#     host_helper.upgrade_host("controller-1", lock=True)
#     LOG.tc_step("Host controller-1 is upgraded successfully......")
#
#     # unlock upgraded controller-1
#     LOG.tc_step("Unlocking controller-1 after upgrade......")
#     host_helper.unlock_host("controller-1", available_only=True, check_hypervisor_up=False)
#     LOG.tc_step("Host controller-1 unlocked after upgrade......")
#

@pytest.fixture(scope='function')
def check_for_upgrade_abort():
    upgrade_info = dict()
    lab = InstallVars.get_install_var('LAB')
    upgrade_info['LAB'] = lab
    table_ = system_helper.system_upgrade_show()[1]
    print("Upgrade show {}".format(table_))
    if "No upgrade in progress" in table_:
        LOG.warning("No upgrade in progress, cannot be aborted")
        return 1, None

    upgrade_release = table_parser.get_value_two_col_table(table_, "to_release")
    current_release = table_parser.get_value_two_col_table(table_, "from_release")
    upgraded_hostnames = host_helper.get_upgraded_host_names(upgrade_release)
    upgraded = len(upgraded_hostnames)
    upgrade_info['current_release'] = current_release
    upgrade_info['upgrade_release'] = upgrade_release
    upgrade_info['upgraded_hostnames'] = upgraded_hostnames

    if upgraded >= 2:
        LOG.warning("Both controllers are upgraded; Full system installation required to abort"
                    ": {} ".format(upgraded_hostnames))
        return 2, upgrade_info
    elif upgraded == 1:
        LOG.warning("Only one  controller is upgraded; In service abort is possible: "
                    "{} ".format(upgraded_hostnames))
        return 0, upgrade_info
    else:
        LOG.warning("No host is upgraded. ")
        return 3, upgrade_info


# def test_system_upgrade_abort_after_controller_1(check_for_upgrade_abort):
#     """
#     Test abort upgrade procedure after only controller-1 is upgraded.
#     Args:
#         check_for_upgrade_abort:
#
#     Test Steps:
#         -
#         -
#
#     Teardown:
#
#     Returns:
#
#     """
#     rc, upgraded_info = check_for_upgrade_abort
#
#     if rc != 0:
#         skip("Test skipped; Cannot abort upgrade; please check pre-check logs")
#
#     # abort upgrade
#     LOG.tc_step("Aborting updgrade .....")
#     system_helper.abort_upgrade()
#     LOG.info("Aborting updgrade ")
#
#     active_controller = system_helper.get_active_controller_name()
#     if "controller-1" in active_controller:
#         # Swact to  controller-0
#         LOG.tc_step("Making controller-0 active.....")
#         rc, output = host_helper.swact_host(hostname="controller-1")
#         assert rc == 0, "Failed to swact: {}".format(output)
#         LOG.info("Swacted to controller-0 ......")
#
#
#     # downgrade standby controller
#     LOG.tc_step("Upgrading controller-1")
#     host_helper.downgrade_host("controller-1", lock=True)
#     LOG.info("Host controller-1 is downgraded successfully......")
#
#     # unlocke upgraded controller-1
#     LOG.tc_step("Unlocking controller-1 after upgrade......")
#     host_helper.unlock_host("controller-1", available_only=True, check_hypervisor_up=False)
#     LOG.info("Host controller-1 unlocked after downgrade......")
#
#
#     # Complete downgrade
#     LOG.tc_step("Completing downgrade ...")
#     system_helper.complete_upgrade()
#     LOG.tc_step("Downgrade is complete......")
#
#     # Delete the upgrade load
#
#     LOG.tc_step("Deleting  {} load... ".format(upgraded_info['upgrade_release']))
#     system_helper.delete_imported_load()
#     LOG.tc_step("Delete  previous load version {}".format(upgraded_info['upgrade_release']))
#
#     lab = upgraded_info['LAB']
#     LOG.info("Lab: {} downgraded successfully".format(lab['name']))
#

def test_system_upgrade_controllers(upgrade_setup, check_system_health_query_upgrade):

    LOG.tc_func_start("UPGRADE_TEST")

    lab = upgrade_setup['lab']
    current_version = upgrade_setup['current_version']
    upgrade_version = upgrade_setup['upgrade_version']

    # run system upgrade-start
    # must be run in controller-0
    active_controller = system_helper.get_active_controller_name()
    LOG.tc_step("Checking if active controller is controller-0......")
    assert "controller-0" in active_controller, "The active controller is not " \
                                                "controller-0. Make controller-0 " \
                                                "active before starting upgrade"

    force = False
    LOG.tc_step("Checking system health for upgrade .....")
    if check_system_health_query_upgrade[0] == 0:
        LOG.info("System health OK for upgrade......")
    elif check_system_health_query_upgrade[0] == 2:
        LOG.info("System health indicate minor alarms; using --force option to start upgrade......")
        force = True
    else:
        assert False, "System health query upgrade failed: {}".format(check_system_health_query_upgrade[1])

    LOG.info("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
    system_helper.system_upgrade_start(force=force)
    LOG.tc_step("upgrade started successfully......")

    # upgrade standby controller
    LOG.tc_step("Upgrading controller-1")
    host_helper.upgrade_host("controller-1", lock=True)
    LOG.tc_step("Host controller-1 is upgraded successfully......")

    # unlock upgraded controller-1
    LOG.tc_step("Unlocking controller-1 after upgrade......")
    host_helper.unlock_host("controller-1", available_only=True, check_hypervisor_up=False)
    LOG.tc_step("Host controller-1 unlocked after upgrade......")

    time.sleep(60)
    # Before Swacting ensure the controller-1 is in available state
    if not host_helper.wait_for_host_states("controller-1", timeout=360, fail_ok=True,
                                            operational=HostOperationalState.ENABLED,
                                            availability=HostAvailabilityState.AVAILABLE):
        err_msg = " Swacting to controller-1 is not possible because controller-1 is not in available state " \
                  "within  the specified timeout"
        assert False, err_msg

    # Swact to standby controller-1
    LOG.tc_step("Swacting to controller-1 .....")
    rc, output = host_helper.swact_host(hostname="controller-0")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted and  controller-1 has become active......")
    time.sleep(60)
    # upgrade  controller-0
    LOG.tc_step("Upgrading  controller-0......")
    controller0 = lab['controller-0']

    LOG.info("Ensure controller-0 is provisioned before upgrade.....")
    host_helper.ensure_host_provisioned(controller0.name)
    LOG.info("Host {} is provisioned for upgrade.....".format(controller0.name))

    # open vlm console for controller-0 for boot through mgmt interface
    LOG.info("Opening a vlm console for controller-0 .....")
    install_helper.open_vlm_console_thread("controller-0")

    LOG.info("Starting {} upgrade.....".format(controller0.name))
    host_helper.upgrade_host(controller0.name, lock=True)
    LOG.info("controller-0 is upgraded successfully.....")

    # unlock upgraded controller-0
    LOG.tc_step("Unlocking controller-0 after upgrade......")
    host_helper.unlock_host(controller0.name, available_only=True)
    LOG.info("Host {} unlocked after upgrade......".format(controller0.name))

#
# def test_system_upgrade_abort_after_controllers(check_for_upgrade_abort):
#     """
#     Test abort upgrade procedure after only controller-1 is upgraded.
#     Args:
#         check_for_upgrade_abort:
#
#     Test Steps:
#         -
#         -
#
#     Teardown:
#
#     Returns:
#
#     """
#     rc, upgraded_info = check_for_upgrade_abort
#
#     if rc != 2:
#         skip("Test skipped; Both controllers are not upgraded; please check pre-check logs")
#
#     # abort upgrade
#     LOG.tc_step("Aborting updgrade .....")
#     system_helper.abort_upgrade()
#     LOG.info("Aborting updgrade ")
#
#     active_controller = system_helper.get_active_controller_name()
#     if "controller-0" in active_controller:
#         # Swact to  controller-1
#         LOG.tc_step("Making controller-1 active.....")
#         rc, output = host_helper.swact_host(hostname="controller-0")
#         assert rc == 0, "Failed to swact: {}".format(output)
#         LOG.info("Swacted to controller-1 ......")
#
#     upgrade_hosts = install_helper.get_non_controller_system_hosts()
#
#     # lock controller-0
#     LOG.tc_step("Locking controller-0 ...")
#     host_helper.lock_host("controller-0")
#     LOG.info("Host controller-0 is locked successfully......")
#
#     # wipe disk  storage and compute hosts, if present
#     LOG.tc_step("Wipe disks of hosts: {} ...".format(upgrade_hosts))
#     install_helper.wipe_disk_hosts(upgrade_hosts)
#     LOG.info("Hosts disk(s) have been wiped successfully......")
#
#     # power down storage and compute hosts, if present
#     LOG.tc_step("Powering off hosts: {} ...".format(upgrade_hosts))
#     install_helper.power_off_host(upgrade_hosts)
#     LOG.info("Hosts powered down successfully......")
#
#     # lock storage and compute hosts, if present
#     LOG.tc_step("Lock hosts: {} ...".format(upgrade_hosts))
#     install_helper.lock_hosts(upgrade_hosts)
#     LOG.info("Hosts locked  successfully......")
#
#
#     # downgrade  controller-0
#     LOG.tc_step("downgrading controller-0")
#     host_helper.downgrade_host("controller-0", lock=True)
#     LOG.info("Host controller-0 is downgraded successfully......")
#
#     # unlock downgraded controller-0
#     LOG.tc_step("Unlocking controller-0 after downgrade......")
#     host_helper.unlock_host("controller-0", available_only=True, check_hypervisor_up=False)
#     LOG.info("Host controller-0 unlocked after downgrade......")
#
#     # Swact to standby controller-0
#     LOG.tc_step("Swacting to controller-0 .....")
#     rc, output = host_helper.swact_host(hostname="controller-1")
#     assert rc == 0, "Failed to swact: {}".format(output)
#     LOG.info("Swacted and  controller-0 has become active......")
#
#     # downgrade  controller-1
#     LOG.tc_step("downgrading controller-1")
#     host_helper.downgrade_host("controller-1", lock=True)
#     LOG.info("Host controller-1 is downgraded successfully......")
#
#     # unlock downgraded controller-1
#     LOG.tc_step("Unlocking controller-1 after downgrade......")
#     host_helper.unlock_host("controller-1", available_only=True, check_hypervisor_up=False)
#     LOG.info("Host controller-1 unlocked after downgrade......")
#
#     # power on storages if present
#     storage_hosts = [host for host in upgrade_hosts if "storage" in host]
#     if len(storage_hosts) > 0:
#         LOG.tc_step("Powering on storage hosts: {} ...".format(storage_hosts))
#         install_helper.power_on_host(storage_hosts)
#         LOG.info("Storage hosts powered on and re-installed with previous load successfully......")
#         LOG.info("Unlocking Storage hosts {}.....".format(storage_hosts))
#         host_helper.unlock_hosts(storage_hosts)
#         LOG.info("Storage hosts cunlocked after reinstall......")
#
#         #TODO: Restore glance images
#         #TODO: Restore cinder volumes
#
#     # power on computes
#     compute_hosts = [host for host in upgrade_hosts if "storage" not in host]
#     if len(compute_hosts) > 0:
#         LOG.tc_step("Powering on compute hosts: {} ...".format(compute_hosts))
#         install_helper.power_on_host(compute_hosts)
#         LOG.info("Compute hosts powered on and re-installed with previous load successfully......")
#         LOG.info("Unlocking Compute hosts {}.....".format(compute_hosts))
#         host_helper.unlock_hosts(compute_hosts)
#         LOG.info("Compute hosts cunlocked after reinstall......")
#
#
#     # Complete downgrade
#     LOG.tc_step("Completing downgrade ...")
#     system_helper.complete_upgrade()
#     LOG.tc_step("Downgrade is complete......")
#
#     # Delete the upgrade load
#     LOG.tc_step("Deleting  {} load... ".format(upgraded_info['upgrade_release']))
#     system_helper.delete_imported_load()
#     LOG.tc_step("Delete  previous load version {}".format(upgraded_info['upgrade_release']))
#
#     lab = upgraded_info['LAB']
#     LOG.info("Lab: {} downgraded successfully".format(lab['name']))