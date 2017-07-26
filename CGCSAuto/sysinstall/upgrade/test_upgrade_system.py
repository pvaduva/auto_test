import time
from utils.tis_log import LOG
from utils.ssh import ControllerClient, SSHClient
from keywords import system_helper, host_helper, install_helper, storage_helper
from consts.filepaths import BuildServerPath
from consts.proj_vars import  UpgradeVars
from consts.cgcs import HostAvailabilityState, HostOperationalState

def test_system_upgrade(upgrade_setup, check_system_health_query_upgrade):

    lab = upgrade_setup['lab']
    current_version = upgrade_setup['current_version']
    upgrade_version = upgrade_setup['upgrade_version']
    bld_server = upgrade_setup['build_server']

    force = False
    controller0 = lab['controller-0']
    host_helper.ensure_host_provisioned(controller0.name)
    LOG.tc_step("Checking system health for upgrade .....")
    if check_system_health_query_upgrade[0] == 0:
        LOG.info("System health OK for upgrade......")
    elif check_system_health_query_upgrade[0] == 2:
        LOG.info("System health indicate minor alarms; using --force option to start upgrade......")
        force = True
    else:
        assert False, "System health query upgrade failed: {}".format(check_system_health_query_upgrade[1])

    LOG.tc_step("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
    system_helper.system_upgrade_start(force=force)
    LOG.info("upgrade started successfully......")

    # upgrade standby controller
    LOG.tc_step("Upgrading controller-1")
    host_helper.upgrade_host("controller-1", lock=True)
    LOG.info("Host controller-1 is upgraded successfully......")

    # unlock upgraded controller-1
    LOG.tc_step("Unlocking controller-1 after upgrade......")
    host_helper.unlock_host("controller-1", available_only=True, check_hypervisor_up=False)
    LOG.info("Host controller-1 unlocked after upgrade......")

    time.sleep(60)
      # Before Swacting ensure the controller-1 is in available state
    if not host_helper.wait_for_host_states("controller-1", timeout=360, fail_ok=True,
                                            operational=HostOperationalState.ENABLED,
                                            availability=HostAvailabilityState.AVAILABLE):
        err_msg = " Swacting to controller-1 is not possible because controller-1 is not in available state " \
              "within  the specified timeout"
        assert False, err_msg

    # Swact to standby contime.sleep(60)  troller-1
    LOG.tc_step("Swacting to controller-1 .....")
    rc, output = host_helper.swact_host(hostname="controller-0")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted and  controller-1 has become active......")

    active_controller = system_helper.get_active_controller_name()
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

    upgrade_hosts = install_helper.get_non_controller_system_hosts()
    LOG.info("Starting upgrade of the other system hosts: {}".format(upgrade_hosts))

    for host in upgrade_hosts:
        LOG.tc_step("Starting {} upgrade.....".format(host))
        if "storage" in host:
            # wait for replication  to be healthy
            storage_helper.wait_for_ceph_health_ok()

        host_helper.upgrade_host(host, lock=True)
        LOG.info("{} is upgraded successfully.....".format(host))
        LOG.tc_step("Unlocking {} after upgrade......".format(host))
        host_helper.unlock_host(host, available_only=True)
        LOG.info("Host {} unlocked after upgrade......".format(host))
        LOG.info("Host {} upgrade complete.....".format(host))

    # Activate the upgrade
    LOG.tc_step("Activating upgrade....")
    system_helper.activate_upgrade()
    LOG.info("Upgrade activate complete.....")

    # Make controller-0 the active controller
    # Swact to standby controller-0
    LOG.tc_step("Making controller-0 active.....")
    rc, output = host_helper.swact_host(hostname="controller-1")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted to controller-0 ......")

    # Complete upgrade
    LOG.tc_step("Completing upgrade from  {} to {}".format(current_version, upgrade_version))
    system_helper.complete_upgrade()
    LOG.info("Upgrade is complete......")

    LOG.info("Lab: {} upgraded successfully".format(lab['name']))

    # Delete the previous load
    LOG.tc_step("Deleting  {} load... ".format(current_version))
    system_helper.delete_imported_load()
    LOG.tc_step("Delete  previous load version {}".format(current_version))

    LOG.tc_step("Downloading images to upgraded {} lab ".format( upgrade_version))
    install_helper.download_image(lab, bld_server, BuildServerPath.GUEST_IMAGE_PATHS[upgrade_version])

    load_path = UpgradeVars.get_upgrade_var('TIS_BUILD_DIR')
    LOG.tc_step("Downloading heat temples to upgraded {} lab ".format( upgrade_version))
    install_helper.download_heat_templates(lab, bld_server, load_path)

    LOG.tc_step("Downloading lab config scripts to upgraded {} lab ".format( upgrade_version))
    install_helper.download_lab_config_files(lab, bld_server, load_path)


