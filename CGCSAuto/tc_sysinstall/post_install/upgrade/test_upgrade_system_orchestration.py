import time
from datetime import datetime

from utils.tis_log import LOG
from keywords import system_helper, host_helper, install_helper, upgrade_helper
from consts.filepaths import BuildServerPath
from consts.proj_vars import UpgradeVars
from consts.cgcs import HostAvailState, HostOperState


def test_system_upgrade(upgrade_setup, check_system_health_query_upgrade):
    """
    This test verifies the upgrade system using orchestration or manual (one node at a time) procedures. The system
    hosts are upgraded  in the order: controller-1, controller-0, storages, computes. Upgrading through orchestration or
    manual is selected through the argument option --orchestration. The standby controller-1 is always upgraded first
    using the manual upgrade regardless of the orchestration option. The remaining nodes are upgraded either one at a
    time or through orchestration depending on the option selected. The default is to use upgrade orchestration.  The
    --orchestration is specified in form: [<host personality>[:<number of hosts>]],  where:
        <personality>  is either compute or storage
        <number of hosts> is the number of hosts that are upgraded manually before using orchestration.
        e.g:
          --orchestration compute:1  -  do manual upgrade for controller-0, controller-1, all storages if exist
                                        and one compute,  the remaining computes are upgraded through orchestration.
          --orchestration default -  do manual upgrade for controller-1 and use orchestration for the rest of the nodes.
          --orchestration controller  - do manual upgrade for controller-1 and controller-0, the rest nodes are upgraded
                                        through orchestration.
          --orchestration storage:2   - use orchestration after 2 storages are upgraded manually.

    option specified during executing this test,  the system is upgraded
    Args:
        upgrade_setup:
        check_system_health_query_upgrade:

    Returns:

    """

    lab = upgrade_setup['lab']
    current_version = upgrade_setup['current_version']
    upgrade_version = upgrade_setup['upgrade_version']
    bld_server = upgrade_setup['build_server']
    collect_kpi = upgrade_setup['col_kpi']

    # orchestration = 'upgrade'
    man_upgrade_nodes = upgrade_setup['man_upgrade_nodes']
    orchestration_nodes = upgrade_setup['orchestration_nodes']
    system_upgrade_health = list(check_system_health_query_upgrade)
    missing_manifests = False
    force = False
    controller0 = lab['controller-0']
    if not upgrade_helper.is_host_provisioned(controller0.name):
        upgrade_helper.ensure_host_provisioned(controller0.name)
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
                # system_upgrade_health[2]["swact"] = False
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

    #
    #
    # LOG.tc_step("Checking system health for upgrade .....")
    # if system_upgrade_health[0] == 0:
    #     LOG.info("System health OK for upgrade......")
    # if system_upgrade_health[0] == 1:
    #     assert False, "System health query upgrade failed: {}".format(system_upgrade_health[1])
    #
    # if system_upgrade_health[0] == 4 or system_upgrade_health[0] == 2:
    #     LOG.info("System health indicate missing manifests; lock/unlock controller-0 to resolve......")
    #     missing_manifests = True
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
    #     if any("controller-1" in k for k in check_system_health_query_upgrade[1].keys()):
    #         lock_unlock_hosts.append('controller-1')
    #     if any("controller-0" in k for k in check_system_health_query_upgrade[1].keys()):
    #         lock_unlock_hosts.append('controller-0')
    #
    #     for host in lock_unlock_hosts:
    #         rc, output = upgrade_helper.upgrade_host_lock_unlock(host)
    #         assert rc == 0, "Failed to lock/unlock host {}: {}".format(host, output)

    upgrade_init_time = str(datetime.now())

    LOG.tc_step("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
    current_state = upgrade_helper.get_upgrade_state()
    if "No upgrade in progress" in current_state:
        upgrade_helper.system_upgrade_start(force=force)
        LOG.info("upgrade started successfully......")
    elif "started" in current_state:
        LOG.info("upgrade already started ......")
    else:
        LOG.info("upgrade is already in state {} please continue manual upgrade ......".format(current_state))
        assert False, "upgrade is already in state {} please continue manual upgrade ......".format(current_state)
    time.sleep(60)
    # upgrade standby controller
    LOG.tc_step("Upgrading controller-1")
    upgrade_helper.upgrade_controller('controller-1')

    time.sleep(60)

    # Swact to standby controller-1
    LOG.tc_step("Swacting to controller-1 .....")
    # Before Swacting ensure the controller-1 is in available state
    if not system_helper.wait_for_host_values("controller-1", timeout=900, fail_ok=True,
                                              operational=HostOperState.ENABLED,
                                              availability=HostAvailState.AVAILABLE):
        err_msg = " Swacting to controller-1 is not possible because controller-1 is not in available state " \
                  "within  the specified timeout"
        assert False, err_msg

    if collect_kpi:
        upgrade_helper.collected_upgrade_controller1_kpi(lab, collect_kpi, init_time=upgrade_init_time)

    rc, output = host_helper.swact_host(hostname="controller-0")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted and  controller-1 has become active......")
    time.sleep(120)
    # active_controller = system_helper.get_active_controller_name()

    if 'controller-1' in man_upgrade_nodes:
        man_upgrade_nodes.remove('controller-1')
    if len(man_upgrade_nodes) > 0:
        upgrade_helper.manual_upgrade_hosts(manual_nodes=man_upgrade_nodes)
    if len(orchestration_nodes) > 0:
        upgrade_helper.orchestration_upgrade_hosts(upgraded_hosts=man_upgrade_nodes,
                                                   orchestration_nodes=orchestration_nodes)
    if collect_kpi:
        if len(orchestration_nodes) > 0:
            upgrade_helper.collect_upgrade_orchestration_kpi(lab, collect_kpi)
        else:
            if upgrade_setup['cpe']:
                upgrade_helper.collected_upgrade_controller0_kpi(lab, collect_kpi)

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

    load_path = UpgradeVars.get_upgrade_var('TIS_BUILD_DIR')
    LOG.tc_step("Downloading heat templates to upgraded {} lab ".format(upgrade_version))
    install_helper.download_heat_templates(lab, bld_server, load_path)

    LOG.tc_step("Downloading lab config scripts to upgraded {} lab ".format(upgrade_version))
    install_helper.download_lab_config_files(lab, bld_server, load_path)
