import pytest
import os
import re
import time
from utils.tis_log import LOG
from keywords import storage_helper, install_helper, cinder_helper, host_helper, system_helper, common
from consts.proj_vars import InstallVars, RestoreVars, ProjVar
from consts.cgcs import HostAvailabilityState, HostOperationalState, HostAdminState, Prompt, IMAGE_BACKUP_FILE_PATTERN,\
    TIS_BLD_DIR_REGEX, TITANIUM_BACKUP_FILE_PATTERN, BackupRestore
from utils.ssh import ControllerClient
from consts.filepaths import TiSPath, BuildServerPath, WRSROOT_HOME
from consts.build_server import Server, get_build_server_info
from consts.auth import SvcCgcsAuto, HostLinuxCreds
from utils import node


@pytest.fixture(scope='session', autouse=True)
def pre_restore_checkup():

    lab = InstallVars.get_install_var('LAB')
    LOG.info("Lab info; {}".format(lab))
    backup_build_id = RestoreVars.get_restore_var("BACKUP_BUILD_ID")
    controller_node = lab['controller-0']
    backup_src = RestoreVars.get_restore_var('backup_src'.upper())
    backup_src_path = RestoreVars.get_restore_var('backup_src_path'.upper())
    tis_backup_files = []
    extra_controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0
    controller_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                              initial_prompt=extra_controller_prompt,  fail_ok=True)

    LOG.info('backup_src={}, backup_src_path={}'.format(backup_src, backup_src_path))
    if backup_src.lower() == 'usb':
        if controller_conn:
            LOG.info("Connection established with controller-0 ....")
            ControllerClient.set_active_controller(ssh_client=controller_conn)

            LOG.tc_step("Checking if a USB flash drive with backup files is plugged in... ")
            usb_device_name = install_helper.get_usb_device_name(con_ssh=controller_conn)
            assert usb_device_name, "No USB found "
            LOG.tc_step("USB flash drive found, checking for backup files ... ")
            usb_part_info = install_helper.get_usb_device_partition_info(usb_device=usb_device_name,
                                                                         con_ssh=controller_conn)
            assert usb_part_info and len(usb_part_info) > 0, "No USB or partition found"

            usb_part_name = "{}2".format(usb_device_name)
            assert usb_part_name in usb_part_info.keys(), "No {} partition exist in USB"
            result, mount_point = install_helper.is_usb_mounted(usb_device=usb_part_name, con_ssh=controller_conn)
            if not result:
                assert install_helper.mount_usb(usb_device=usb_part_name, con_ssh=controller_conn), \
                    "Unable to mount USB partition {}".format(usb_part_name)

            tis_backup_files = install_helper.get_titanium_backup_filenames_usb(usb_device=usb_part_name,
                                                                                con_ssh=controller_conn)
            assert len(tis_backup_files) >= 2, "Missing backup files: {}".format(tis_backup_files)

            #extract build id from the file name
            file_parts = tis_backup_files[0].split('_')

            file_backup_build_id  = '_'.join([file_parts[3], file_parts[4]])

            assert re.match(TIS_BLD_DIR_REGEX, file_backup_build_id), \
                " Invalid build id format {} extracted from backup_file {}"\
                    .format(file_backup_build_id, tis_backup_files[0])

            if backup_build_id is not None:
                if backup_build_id != file_backup_build_id:
                    LOG.info(" The build id extracted from backup file is different than specified; "
                             "Using the extracted build id {} ....".format(file_backup_build_id))

                    backup_build_id = file_backup_build_id

            else:
                backup_build_id = file_backup_build_id

            RestoreVars.set_restore_var(backup_build_id=backup_build_id)

        else:

            LOG.info(" SSH connection not available yet with controller-0;  "
                     "USB will be checked after controller boot ....")
    else:
        # local_hostname = socket.gethostname()
        # ssh to test server
        test_server_attr = dict()
        test_server_attr['name'] = SvcCgcsAuto.HOSTNAME.split('.')[0]
        test_server_attr['server_ip'] = SvcCgcsAuto.SERVER
        test_server_attr['prompt'] = r'\[{}@{} {}\]\$ '\
            .format(SvcCgcsAuto.USER, test_server_attr['name'], SvcCgcsAuto.USER)

        test_server_conn = install_helper.establish_ssh_connection(test_server_attr['name'], user=SvcCgcsAuto.USER,
                                    password=SvcCgcsAuto.PASSWORD, initial_prompt=test_server_attr['prompt'])

        test_server_conn.set_prompt(test_server_attr['prompt'])
        test_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        test_server_attr['ssh_conn'] = test_server_conn
        test_server_obj = Server(**test_server_attr)
        RestoreVars.set_restore_var(backup_src_server=test_server_obj)

        # test if backup path for the lab exist in Test server
        if os.path.basename(backup_src_path) != lab['short_name']:
            backup_src_path = backup_src_path + '/{}'.format(lab['short_name'])
            RestoreVars.set_restore_var(backup_src_path=backup_src_path)

        assert not test_server_conn.exec_cmd("test -e {}".format(backup_src_path))[0], \
            "Missing backup files from source {}: {}".format(test_server_attr['name'], backup_src_path)

        tis_backup_files = install_helper.get_backup_files(TITANIUM_BACKUP_FILE_PATTERN, backup_src_path,
                                                              test_server_conn)

        assert len(tis_backup_files) >= 2, "Missing backup files: {}".format(tis_backup_files)

        #extract build id from the file name
        file_parts = tis_backup_files[0].split('_')

        file_backup_build_id  = '_'.join([file_parts[3], file_parts[4]])

        assert re.match(TIS_BLD_DIR_REGEX, file_backup_build_id), \
            " Invalid build id format {} extracted from backup_file {}"\
                .format(file_backup_build_id, tis_backup_files[0])

        if backup_build_id is not None:
            if backup_build_id != file_backup_build_id:
                LOG.info(" The build id extracted from backup file is different than specified; "
                         "Using the extracted build id {} ....".format(file_backup_build_id))

                backup_build_id = file_backup_build_id

        else:
            backup_build_id = file_backup_build_id

        RestoreVars.set_restore_var(backup_build_id=backup_build_id)

        if controller_conn:
            # Wipe disks in order to make controller-0 NOT boot from hard-disks
            # hosts = [k for k , v in lab.items() if isinstance(v, node.Node)]
            # install_helper.wipe_disk_hosts(hosts)
            LOG.info('Try to do wipedisk_via_helper on controller-0')
            install_helper.wipedisk_via_helper(controller_conn)

    assert backup_build_id, "The Build id of the system backup must be provided."


    return tis_backup_files


@pytest.fixture(scope='session')
def restore_setup(pre_restore_checkup):

    lab = InstallVars.get_install_var('LAB')
    LOG.info("Lab info; {}".format(lab))
    hostnames = [ k for k, v in lab.items() if  isinstance(v, node.Node)]
    LOG.info("Lab hosts; {}".format(hostnames))
    bld_server = get_build_server_info(InstallVars.get_install_var('BUILD_SERVER'))
    backup_build_id = RestoreVars.get_restore_var("BACKUP_BUILD_ID")
    output_dir = ProjVar.get_var('LOG_DIR')

    LOG.info("Connecting to Build Server {} ....".format(bld_server['name']))
    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    bld_server_attr['prompt'] = r'{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, bld_server['name'])

    bld_server_conn = install_helper.establish_ssh_connection(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])

    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)

    # If controller is accessible, check if USB with backup files is avaialble
    controller_node = lab['controller-0']

    load_path = os.path.join(BuildServerPath.DEFAULT_WORK_SPACE, RestoreVars.get_restore_var("BACKUP_BUILDS_DIR"),
                             backup_build_id)

    InstallVars.set_install_var(tis_build_dir=load_path)

    # set up feed for controller
    LOG.tc_step("Setting install feed in tuxlab for controller-0 ... ")
    if not 'vbox' in lab['name']:
        assert install_helper.set_network_boot_feed(bld_server_conn, load_path), "Fail to set up feed for controller"

    # power off hosts
    LOG.tc_step("Powring off system hosts ... ")
    install_helper.power_off_host(hostnames)

    LOG.tc_step("Booting controller-0 ... ")
    install_helper.boot_controller(bld_server_conn, load_path)

    # establish ssh connection with controller
    LOG.tc_step("Establishing ssh connection with controller-0 after install... ")
    controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0

    controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                       initial_prompt=controller_prompt)
    controller_node.ssh_conn.deploy_ssh_key()

    ControllerClient.set_active_controller(ssh_client=controller_node.ssh_conn)
    con_ssh = controller_node.ssh_conn
    tis_backup_files = pre_restore_checkup
    backup_src = RestoreVars.get_restore_var('backup_src'.upper())
    backup_src_path = RestoreVars.get_restore_var('backup_src_path'.upper())
    if backup_src.lower() == 'local':
        LOG.tc_step("Transferring system backup file to controller-0 {} ... ".format(WRSROOT_HOME))

        system_backup_file = [file for file in tis_backup_files if "system.tgz" in file].pop()
        common.scp_from_test_server_to_active_controller("{}/{}".format(backup_src_path, system_backup_file),
                                                         WRSROOT_HOME)

        assert con_ssh.exec_cmd("ls {}{}".format(WRSROOT_HOME, system_backup_file))[0] == 0, \
            "Missing backup file {} in dir {}".format(system_backup_file, WRSROOT_HOME)

    elif backup_src.lower() == 'usb':
        tis_backup_files = pre_restore_checkup
        usb_device_name = install_helper.get_usb_device_name(con_ssh=con_ssh)
        usb_part_name = "{}2".format(usb_device_name)
        assert usb_device_name, "No USB found "
        LOG.tc_step("USB flash drive found, checking for backup files ... ")

        if len(tis_backup_files) == 0:
            LOG.tc_step("Checking for backup files in USB ... ")
            usb_part_info = install_helper.get_usb_device_partition_info(usb_device=usb_device_name,
                                                                         con_ssh=con_ssh)
            assert usb_part_info and len(usb_part_info) > 0, "No USB or partition found"
            assert usb_part_name in usb_part_info.keys(), "No {} partition exist in USB"

            result, mount_point = install_helper.is_usb_mounted(usb_device=usb_part_name)
            if not result:
                assert install_helper.mount_usb(usb_device=usb_part_name, con_ssh=con_ssh), \
                    "Unable to mount USB partition {}".format(usb_part_name)

            tis_backup_files = install_helper.get_titanium_backup_filenames_usb(usb_device=usb_part_name)
            assert len(tis_backup_files) >= 2, "Missing backup files: {}".format(tis_backup_files)
        else:
            result, mount_point = install_helper.is_usb_mounted(usb_device=usb_part_name)
            if not result:
                assert install_helper.mount_usb(usb_device=usb_part_name, con_ssh=con_ssh), \
                    "Unable to mount USB partition {}".format(usb_part_name)

    _restore_setup = {'lab': lab, 'output_dir': output_dir,
                      'build_server': bld_server_obj,
                      'tis_backup_files': tis_backup_files }

    return _restore_setup


def test_restore_from_backup(restore_setup):

    controller1 = 'controller-1'
    controller0 = 'controller-0'

    lab = restore_setup["lab"]
    tis_backup_files = restore_setup['tis_backup_files']
    backup_src = RestoreVars.get_restore_var('backup_src'.upper())
    backup_src_path = RestoreVars.get_restore_var('backup_src_path'.upper())

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
    system_backup_file = [file for file in tis_backup_files if "system.tgz" in file].pop()
    images_backup_file = [file for file in tis_backup_files if "images.tgz" in file].pop()

    LOG.tc_step("Restoring {}".format(controller0))

    LOG.info("System config restore from backup file {} ...".format(system_backup_file))
    if backup_src.lower() == 'usb':

        system_backup_path = "{}/{}".format(BackupRestore.USB_BACKUP_PATH, system_backup_file)
    else:
        system_backup_path = "{}{}".format(WRSROOT_HOME, system_backup_file)

    install_helper.restore_controller_system_config(system_backup=system_backup_path,
                                                    tel_net_session=controller_node.telnet_conn)

    LOG.info("Source Keystone user admin environment ...")

    controller_node.telnet_conn.exec_cmd("cd; source /etc/nova/openrc")

    # re-establish ssh connection to controller
    con_ssh.close()
    con_ssh = install_helper.establish_ssh_connection(controller_node.host_ip)
    controller_node.ssh_conn = con_ssh
    ControllerClient.set_active_controller(con_ssh)

    if backup_src.lower() == 'local':
        images_backup_path = "{}{}".format(WRSROOT_HOME, images_backup_file)
        common.scp_from_test_server_to_active_controller("{}/{}".format(backup_src_path, images_backup_file),
                                                         WRSROOT_HOME)
    else:
        images_backup_path = "{}/{}".format(BackupRestore.USB_BACKUP_PATH, images_backup_file)

    LOG.info("Images restore from backup file {} ...".format(images_backup_file))

    new_prompt = '{}.*~.*\$ '.format(lab['name'].split('_')[0]) + '|controller\-0.*~.*\$ '
    LOG.info('set prompt to:{}'.format(new_prompt))
    con_ssh.set_prompt(new_prompt)
    install_helper.restore_controller_system_images(images_backup=images_backup_path,
                                                    tel_net_session=controller_node.telnet_conn)

    # this is a workaround for CGTS-8190
    install_helper.update_auth_url(con_ssh)

    LOG.tc_step("Verifying  restoring controller-0 is complete and is in available state ...")
    LOG.debug('Wait for system ready in 60 seconds')
    time.sleep(60)

    host_helper.wait_for_hosts_states(controller0, availability=HostAvailabilityState.AVAILABLE, fail_ok=False)

    # delete the system backup files from wrsroot home
    LOG.tc_step("Copying backup files to /opt/backups ... ")
    if backup_src.lower() == 'local':
        con_ssh.exec_cmd("rm -f {} {}".format(system_backup_path, images_backup_path))

        # transfer all backup files to /opt/backups from test server
        con_ssh.scp_files(backup_src_path + "/*", TiSPath.BACKUPS + '/', source_server=SvcCgcsAuto.SERVER,
                          source_user=SvcCgcsAuto.USER, source_password=SvcCgcsAuto.PASSWORD,
                          dest_password=HostLinuxCreds.get_password(),  sudo=True,
                          sudo_password=HostLinuxCreds.get_password())

    else:
        # copy all backupfiles from USB to /opt/backups
        cmd = " cp  {}/* {}".format(BackupRestore.USB_BACKUP_PATH, TiSPath.BACKUPS)
        con_ssh.exec_sudo_cmd(cmd, expect_timeout=600)

    LOG.tc_step("Checking if backup files are copied to /opt/backups ... ")
    assert  int(con_ssh.exec_cmd("ls {} | wc -l".format(TiSPath.BACKUPS))[1]) >= 2, \
        "Missing backup files in {}".format(TiSPath.BACKUPS)


    boot_interfaces = lab['boot_device_dict']
    LOG.tc_step("Restoring {}".format(controller1))
    install_helper.open_vlm_console_thread(controller1, boot_interface=boot_interfaces, vlm_power_on=True)

    LOG.info("Verifying {} is Locked, Disabled and Online ...".format(controller1))
    host_helper.wait_for_hosts_states(controller1, administrative=HostAdminState.LOCKED,
                                      operational=HostOperationalState.DISABLED,
                                      availability=HostAvailabilityState.ONLINE)

    LOG.info("Unlocking {} ...".format(controller1))
    rc, output = host_helper.unlock_host(controller1, available_only=True)

    assert rc == 0, "Host {} failed to unlock: rc = {}, msg: {}".format(controller1, rc, output)

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
        image_backup_files = install_helper.get_backup_files(IMAGE_BACKUP_FILE_PATTERN, TiSPath.BACKUPS,  con_ssh)
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

    LOG.tc_step("Delete backup files from {} ....".format(TiSPath.BACKUPS))
    con_ssh.exec_sudo_cmd("rm -rf {}/*".format(TiSPath.BACKUPS))

    LOG.tc_step("Waiting until all alarms are cleared ....")
    system_helper.wait_for_all_alarms_gone(timeout=300)

    LOG.tc_step("Verifying system health after restore ...")
    rc, failed = system_helper.get_system_health_query(con_ssh=con_ssh)
    assert rc == 0, "System health not OK: {}".format(failed)


