import time

from utils.tis_log import LOG
from keywords import system_helper, install_helper, common, upgrade_helper, cinder_helper
from consts.auth import Tenant
from consts.proj_vars import BackupVars
from consts.auth import SvcCgcsAuto
from consts.build_server import Server
from consts.stx import BACKUP_FILE_DATE_STR, PREFIX_BACKUP_FILE


def test_system_upgrade_simplex(upgrade_setup, check_system_health_query_upgrade):
    """
     This script starts the upgrade with creating a backup file which is wipes the disk at the end of the execution .
      to complete the upgrade test_upgrade_simplex_restore.py need to be executed with the backup file path.
    Args:
        upgrade_setup:   This will check parameters ftp upload load and patches
        check_system_health_query_upgrade: Check the health of system for upgrade
    Example
        To Execute

         check_system_health_query_upgrade: Checks the upgrade health .
        steps:

         1. FTP load and patches and loads to system.
         2. Checks the health of the upgrade
         3. Start upgrade
         4. Checks the backup files.
         5. Backup the volume and images
         6. Execute host-upgrade
         7. Ftp backup files

    teardown:
         flush ssh.

    """
    lab = upgrade_setup['lab']

    current_version = upgrade_setup['current_version']
    upgrade_version = upgrade_setup['upgrade_version']

    if not system_helper.is_aio_simplex():
        assert False, "This lab is not simplex to start upgrade"
    force = False
    controller0 = lab['controller-0']

    backup_dest_path = BackupVars.get_backup_var('BACKUP_DEST_PATH')
    backup_dest_full_path = '{}/{}/'.format(backup_dest_path, lab['short_name'])
    date = time.strftime(BACKUP_FILE_DATE_STR)
    build_id = system_helper.get_build_info()['BUILD_ID']
    lab_system_name = lab['name']
    backup_file_name = "{}{}_{}_{}".format(PREFIX_BACKUP_FILE, date, build_id, lab_system_name)
    print('Backup_File_Name', backup_file_name)
    # ssh to test server
    test_server_attr = dict()
    test_server_attr['name'] = SvcCgcsAuto.HOSTNAME.split('.')[0]
    test_server_attr['server_ip'] = SvcCgcsAuto.SERVER
    test_server_attr['prompt'] = r'\[{}@{} {}\]\$ ' \
        .format(SvcCgcsAuto.USER, test_server_attr['name'], SvcCgcsAuto.USER)

    test_server_conn = install_helper.establish_ssh_connection(test_server_attr['name'],
                                                               user=SvcCgcsAuto.USER,
                                                               password=SvcCgcsAuto.PASSWORD,
                                                               initial_prompt=test_server_attr['prompt'])

    test_server_conn.set_prompt(test_server_attr['prompt'])
    test_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    test_server_attr['ssh_conn'] = test_server_conn
    test_server_obj = Server(**test_server_attr)
    dest_server = test_server_obj
    # test if backup path for the lab exist in Test server
    if test_server_conn.exec_cmd("test -e {}".format(backup_dest_full_path))[0]:
        test_server_conn.exec_cmd("mkdir -p {}".format(backup_dest_full_path))
    LOG.tc_step("Checking system health for upgrade .....")
    if check_system_health_query_upgrade[0] == 0:
        LOG.info("System health OK for upgrade......")
    if check_system_health_query_upgrade[0] == 1:
        assert False, "System health query upgrade failed: {}".format(check_system_health_query_upgrade[1])

    if check_system_health_query_upgrade[0] == 3 or check_system_health_query_upgrade[0] == 2:
        LOG.info("System health indicate minor alarms; using --force option to start upgrade......")
        force = True

    vol_ids = cinder_helper.get_volumes(auth_info=Tenant.get('admin'))
    if len(vol_ids) > 0:
        LOG.info("Exporting cinder volumes: {}".format(vol_ids))
        exported = install_helper.export_cinder_volumes(backup_dest='local', backup_dest_path=backup_dest_full_path,
                                                        dest_server=dest_server)

        assert len(exported) > 0, "Fail to export all volumes"
        assert len(exported) == len(vol_ids), "Some volumes failed export: {}".format(set(vol_ids) - set(exported))
    else:
        LOG.info("No cinder volumes are avaialbe in the system; skipping cinder volume export...")

    LOG.tc_step("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
    upgrade_helper.system_upgrade_start(force=force)
    upgrade_helper.wait_for_upgrade_states('started', timeout=1360, check_interval=30, fail_ok=True)

    LOG.info("upgrade started successfully......")

    # scp backup files to test server
    LOG.tc_step("SCP system and image tgz file into test server {} ", backup_dest_full_path)

    source_file = '/opt/backups/upgrade_data_*system.tgz '
    backup_dest_full_path_image=backup_dest_full_path
    backup_dest_full_path = backup_dest_full_path + "/" + backup_file_name + "_system.tgz"
    common.scp_from_active_controller_to_test_server(source_file, backup_dest_full_path, is_dir=False)
    backup_dest_full_path_image = backup_dest_full_path_image + "/" + backup_file_name + "_images.tgz"
    source_file = '/opt/backups/upgrade_data_*images.tgz '
    common.scp_from_active_controller_to_test_server(source_file, backup_dest_full_path_image, is_dir=False)
    LOG.info("Starting {} upgrade.....".format(controller0.name))
    # Below line will wipe disk
    # upgrade_helper.upgrade_host(controller0.name, lock=True)

    LOG.tc_step("Host Upgrade executed .This will wipe the disk reboot controller-0 .")
    time.sleep(3)
    # open vlm console for controller-0 for boot through mgmt interface
    LOG.info("Upgrade simpelx backup is complete . Resotore script should be run on this backup to compelte  upgrade ")
