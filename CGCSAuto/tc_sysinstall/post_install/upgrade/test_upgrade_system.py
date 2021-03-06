import time

from utils.tis_log import LOG
from keywords import system_helper, host_helper, install_helper, storage_helper, upgrade_helper
from consts.filepaths import BuildServerPath
from consts.stx import HostAvailState, HostOperState
from consts.timeout import HostTimeout


def test_system_upgrade(upgrade_setup, check_system_health_query_upgrade):
    lab = upgrade_setup['lab']
    current_version = upgrade_setup['current_version']
    upgrade_version = upgrade_setup['upgrade_version']
    bld_server = upgrade_setup['build_server']
    collect_kpi = upgrade_setup['col_kpi']
    missing_manifests = False
    cinder_configuration = False
    force = False

    controller0 = lab['controller-0']
    if not upgrade_helper.is_host_provisioned(controller0.name):
        rc, output = upgrade_helper.upgrade_host_lock_unlock(controller0.name)
        assert rc == 0, "Failed to lock/unlock host {}: {}".format(controller0.name, output)

    # update health query
    # system_upgrade_health = list(upgrade_helper.get_system_health_query_upgrade())
    system_upgrade_health = list(upgrade_helper.get_system_health_query_upgrade_2())

    LOG.tc_step("Checking system health for upgrade .....")
    if system_upgrade_health[0] == 0:
        LOG.info("System health OK for upgrade......")
    elif system_upgrade_health[0] == 2:
        if system_upgrade_health[2] and "lock_unlock" in system_upgrade_health[2].keys():
            controller_nodes = system_upgrade_health[2]["lock_unlock"][0]
            LOG.info("Locking/Unlocking required for {} ......".format(controller_nodes))
            if 'controller-1' in controller_nodes:
                rc, output = upgrade_helper.upgrade_host_lock_unlock('controller-1')
                assert rc == 0, "Failed to lock/unlock host {}: {}".format('controller-1', output)
            if 'controller-0' in controller_nodes:
                rc, output = upgrade_helper.upgrade_host_lock_unlock('controller-0')
                assert rc == 0, "Failed to lock/unlock host {}: {}".format('controller-0', output)
                time.sleep(60)
                # system_upgrade_health[2]["swact"][0] = False
        if system_upgrade_health[2]["swact"][0]:
            LOG.info("Swact Required: {}".format(system_upgrade_health[2]["swact"][1]))
            host_helper.swact_host('controller-0')
            time.sleep(60)
            host_helper.swact_host('controller-1')
            time.sleep(60)
        if system_upgrade_health[2]["force_upgrade"][0]:
            LOG.info("{}; using --force option to start upgrade......"
                     .format(system_upgrade_health[2]["force_upgrade"][1]))
            force = True

    else:
        assert False, "System health query upgrade failed: {}".format(system_upgrade_health[1])

    # if system_upgrade_health[0] == 0:
    #     LOG.info("System health OK for upgrade......")
    # if system_upgrade_health[0] == 1:
    #     assert False, "System health query upgrade failed: {}".format(system_upgrade_health[1])
    #
    # if system_upgrade_health[0] == 4 or system_upgrade_health[0] == 2:
    #     LOG.info("System health indicate missing manifests; lock/unlock controller-0 to resolve......")
    #     missing_manifests = True
    #     if any("Cinder configuration" in k for k in system_upgrade_health[1].keys()):
    #         cinder_configuration = True
    #
    # if system_upgrade_health[0] == 3 or system_upgrade_health[0] == 2:
    #
    #     LOG.info("System health indicate minor alarms; using --force option to start upgrade......")
    #     force = True
    #
    # if missing_manifests:
    #     LOG.info("Locking/Unlocking to resolve missing manifests in controller......")
    #
    #     lock_unlock_hosts = []
    #     if any("controller-1" in k for k in system_upgrade_health[1].keys()):
    #         lock_unlock_hosts.append('controller-1')
    #     if any("controller-0" in k for k in system_upgrade_health[1].keys()):
    #         lock_unlock_hosts.append('controller-0')
    #         cinder_configuration = False
    #
    #     for host in lock_unlock_hosts:
    #         rc, output = upgrade_helper.upgrade_host_lock_unlock(host)
    #         assert rc == 0, "Failed to lock/unlock host {}: {}".format(host, output)
    #
    # if cinder_configuration:
    #     LOG.info("Invalid Cinder configuration: Swact to controller-1 and back to synchronize.......")
    #     host_helper.swact_host('controller-0')
    #     time.sleep(60)
    #     host_helper.swact_host('controller-1')

    LOG.tc_step("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
    upgrade_helper.system_upgrade_start(force=force)
    upgrade_helper.wait_for_upgrade_states("started")
    LOG.info("upgrade started successfully......")
    if collect_kpi:
        upgrade_helper.collect_upgrade_start_kpi(lab, collect_kpi)

    # upgrade standby controller
    LOG.tc_step("Upgrading controller-1")
    upgrade_helper.upgrade_host("controller-1", lock=True)
    LOG.info("Host controller-1 is upgraded successfully......")

    # unlock upgraded controller-1
    LOG.tc_step("Unlocking controller-1 after upgrade......")
    host_helper.unlock_host("controller-1", timeout=(HostTimeout.CONTROLLER_UNLOCK + 10), available_only=True,
                            check_hypervisor_up=False)
    LOG.info("Host controller-1 unlocked after upgrade......")

    time.sleep(60)

    # Before Swacting ensure the controller-1 is in available state
    if not system_helper.wait_for_host_values("controller-1", timeout=600, fail_ok=True,
                                              operational=HostOperState.ENABLED,
                                              availability=HostAvailState.AVAILABLE):
        err_msg = " Swacting to controller-1 is not possible because controller-1 is not in available state " \
                  "within  the specified timeout"
        assert False, err_msg

    # Swact to standby contime.sleep(60)  troller-1
    LOG.tc_step("Swacting to controller-1 .....")
    rc, output = host_helper.swact_host(hostname="controller-0")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted and  controller-1 has become active......")

    time.sleep(60)

    # upgrade  controller-0
    LOG.tc_step("Upgrading  controller-0......")
    controller0 = lab['controller-0']

    # open vlm console for controller-0 for boot through mgmt interface
    if 'vbox' not in lab['name']:
        LOG.info("Opening a vlm console for controller-0 .....")
        install_helper.open_vlm_console_thread("controller-0", upgrade=True)

    LOG.info("Starting {} upgrade.....".format(controller0.name))
    upgrade_helper.upgrade_host(controller0.name, lock=True)
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
            ceph_health_timeout = 300
            if 'vbox' in lab['name']:
                ceph_health_timeout = 3600
            storage_helper.wait_for_ceph_health_ok(timeout=ceph_health_timeout)

        upgrade_helper.upgrade_host(host, lock=True)
        LOG.info("{} is upgraded successfully.....".format(host))
        LOG.tc_step("Unlocking {} after upgrade......".format(host))
        host_helper.unlock_host(host, available_only=True)
        LOG.info("Host {} unlocked after upgrade......".format(host))
        LOG.info("Host {} upgrade complete.....".format(host))

    # Activate the upgrade
    LOG.tc_step("Activating upgrade....")
    upgrade_helper.activate_upgrade()
    LOG.info("Upgrade activate complete.....")

    # Make controller-0 the active controller
    # Swact to standby controller-0
    LOG.tc_step("Making controller-0 active.....")
    rc, output = host_helper.swact_host(hostname="controller-1")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted to controller-0 ......")

    # Complete upgrade
    LOG.tc_step("Completing upgrade from  {} to {}".format(current_version, upgrade_version))
    upgrade_helper.complete_upgrade()
    LOG.info("Upgrade is complete......")

    LOG.info("Lab: {} upgraded successfully".format(lab['name']))

    # Delete the previous load
    LOG.tc_step("Deleting  {} load... ".format(current_version))
    upgrade_helper.delete_imported_load()
    LOG.tc_step("Delete  previous load version {}".format(current_version))

    LOG.tc_step("Downloading images to upgraded {} lab ".format(upgrade_version))
    install_helper.download_image(lab, bld_server, BuildServerPath.GUEST_IMAGE_PATHS[upgrade_version])

    load_path = upgrade_setup['load_path']

    LOG.tc_step("Downloading heat temples to upgraded {} lab ".format(upgrade_version))
    install_helper.download_heat_templates(lab, bld_server, load_path)

    LOG.tc_step("Downloading lab config scripts to upgraded {} lab ".format(upgrade_version))
    install_helper.download_lab_config_files(lab, bld_server, load_path)
