import time

from utils.tis_log import LOG
from keywords import storage_helper, install_helper, cinder_helper, host_helper, system_helper
from consts.proj_vars import InstallVars, RestoreVars
from consts.cgcs import HostAvailabilityState, HostOperationalState, HostAdminState, Prompt, EventLogID
from utils.ssh import ControllerClient


def test_restore_from_backup(restore_setup):

    controller1 = 'controller-1'
    controller0 = 'controller-0'

    lab = restore_setup["lab"]
    controller_node = lab[controller0]
    con_ssh = ControllerClient.get_active_controller(lab_name=lab['short_name'], fail_ok=True)

    if not con_ssh:
        LOG.info ("Establish ssh connection with {}".format(controller0))
        controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0
        controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                       initial_prompt=controller_prompt)
        controller_node.ssh_conn.deploy_ssh_key()
        con_ssh = controller_node.ssh_conn
        ControllerClient.set_active_controller(con_ssh)

    LOG.info ("Restore system from backup....")
    LOG.tc_step("Checking for USB flash drive with backup files ... ")
    usb_device_name = install_helper.get_usb_device_name(con_ssh=con_ssh)
    assert usb_device_name, "No USB found "
    LOG.tc_step("USB flash drive found, checking for backup files ... ")
    usb_part_info = install_helper.get_usb_device_partition_info(usb_device=usb_device_name,
                                                                 con_ssh=con_ssh)

    assert usb_part_info and len(usb_part_info) > 0, "No USB or partition found"

    usb_part_name = "{}2".format(usb_device_name)
    assert usb_part_name in usb_part_info.keys(), "No {} partition exist in USB"
    result, mount_point = install_helper.is_usb_mounted(usb_device=usb_part_name)
    if not result:
        assert install_helper.mount_usb(usb_device=usb_part_name, con_ssh=con_ssh), \
            "Unable to mount USB partition {}".format(usb_part_name)

    tis_backup_files = install_helper.get_titanium_backup_filenames_usb(usb_device=usb_part_name)
    assert len(tis_backup_files) >= 2, "Missing backup files: {}".format(tis_backup_files)

    system_backup_file = [file for file in tis_backup_files if "system.tgz" in file].pop()
    images_backup_file = [file for file in tis_backup_files if "images.tgz" in file].pop()

    LOG.tc_step("Restoring {}".format(controller0))

    LOG.info("System config restore from backup file {} ...".format(system_backup_file))
    system_backup_path = "/media/wrsroot/backups/{}".format(system_backup_file)
    install_helper.restore_controller_system_config(system_backup=system_backup_path,
                                                    tel_net_session=controller_node.telnet_conn)

    LOG.info("Source Keystone user admin environment ...")

    controller_node.telnet_conn.exec_cmd("cd; source /etc/nova/openrc")

    image_backup_path = "/media/wrsroot/backups/{}".format(images_backup_file)
    LOG.info("Images restore from backup file {} ...".format(image_backup_path))
    install_helper.restore_controller_system_images(images_backup=image_backup_path,
                                                    tel_net_session=controller_node.telnet_conn)

    time.sleep(30)
    # re-establish ssh connection to controller
    con_ssh.close()
    con_ssh = install_helper.establish_ssh_connection(controller_node.host_ip)
    controller_node.ssh_conn = con_ssh
    ControllerClient.set_active_controller(con_ssh)

    LOG.tc_step("Verifying  restoring controller-0 is complete and is in available state ...")

    host_helper.wait_for_hosts_states(controller0, availability=HostAvailabilityState.AVAILABLE, fail_ok=False)

    boot_interfaces = lab['boot_device_dict']
    LOG.tc_step("Restoring {}".format(controller1))
    install_helper.open_vlm_console_thread(controller1, boot_interface=boot_interfaces, vlm_power_on=True)

    LOG.info("Verifying {} is Locked, Disabled and Online ...".format(controller1))
    host_helper.wait_for_hosts_states(controller1, administrative=HostAdminState.LOCKED,
                                      operational=HostOperationalState.DISABLED,
                                      availability=HostAvailabilityState.ONLINE)

    LOG.info("Unlocking {} ...".format(controller1))
    rc, output = host_helper.unlock_host(controller1, available_only=True)

    assert rc == 0, "Host {} failed to unlock: rc = {}, msg: {}".format(rc, output)

    #hostnames = system_helper.get_hostnames(con_ssh=con_ssh)
    hostnames = system_helper.get_hostnames()
    storage_hosts = [host for host in hostnames if 'storage' in host]
    compute_hosts = [host for host in hostnames if 'storage' not in host and 'controller' not in host]

    if len(storage_hosts) > 0:
        for storage_host in storage_hosts:
            LOG.tc_step("Restoring {}".format(storage_host))
            install_helper.open_vlm_console_thread(storage_host, boot_interface=boot_interfaces, vlm_power_on=True)

            LOG.info("Verifying {} is Locked, Diabled and Online ...".format(storage_host))
            host_helper.wait_for_hosts_states(storage_host, administrative=HostAdminState.LOCKED,
                                            operational=HostOperationalState.DISABLED,
                                            availability=HostAvailabilityState.ONLINE)

            LOG.info("Unlocking {} ...".format(storage_host))
            rc, output = host_helper.unlock_host(storage_host, available_only=True)
            assert rc == 0, "Host {} failed to unlock: rc = {}, msg: {}".format(storage_host, rc, output)

        LOG.info("Veryifying the Ceph cluster is healthy ...")
        storage_helper.wait_for_ceph_health_ok(timeout=600)

        LOG.info("Importing images ...")
        image_backup_files = install_helper.get_image_backup_filenames_usb()
        LOG.info("Image backup found: {}".format(image_backup_files))
        imported = install_helper.import_image_from_backup(image_backup_files)
        LOG.info("Images successfully imported: {}".format(imported))


    LOG.tc_step("Restoring Cinder Volumes ...")
    # Getting all registered cinder volumes
    volumes = cinder_helper.get_volumes()

    if len(volumes) > 0:
        LOG.info("System has {} registered volumes: {}".format(len(volumes), volumes))
        rc, restored_vols = install_helper.restore_cinder_volumes_from_backup()
        assert rc == 0, "All or some volumes has failed import: Restored volumes {}; Expected volumes {}"\
            .format(restored_vols, volumes)
    else:
        LOG.info("System has {} NO registered volumes; skipping cinder volume restore")


    LOG.tc_step("Restoring Compute Nodes ...")

    if len(compute_hosts) > 0:
        for compute_host in compute_hosts:
            LOG.tc_step("Restoring {}".format(compute_host))
            install_helper.open_vlm_console_thread(compute_host, boot_interface=boot_interfaces, vlm_power_on=True)

            LOG.info("Verifying {} is Locked, Diabled and Online ...".format(compute_host))
            host_helper.wait_for_hosts_states(compute_host, administrative=HostAdminState.LOCKED,
                                            operational=HostOperationalState.DISABLED,
                                            availability=HostAvailabilityState.ONLINE)
            LOG.info("Unlocking {} ...".format(compute_host))
            rc, output = host_helper.unlock_host(compute_host, available_only=True)
            assert rc == 0, "Host {} failed to unlock: rc = {}, msg: {}".format(compute_host, rc, output)

    LOG.info("All nodes {} are restored ...".format(hostnames))

    LOG.tc_step("Waiting until all alarms are cleared ....")
    system_helper.wait_for_all_alarms_gone(timeout=300)

    LOG.tc_step("Verifying system health after restore ...")
    rc, failed = system_helper.get_system_health_query(con_ssh=con_ssh)
    assert rc == 0, "System health not OK: {}".format(failed)


