import time

from utils.tis_log import LOG
from keywords import install_helper,upgrade_helper, system_helper, common
from consts.proj_vars import RestoreVars
from consts.cgcs import Prompt,BackupRestore
from utils.clients.ssh import ControllerClient
from consts.filepaths import TiSPath, WRSROOT_HOME
from consts.auth import SvcCgcsAuto, HostLinuxCreds
from tc_bnr.restore.test_restore import restore_setup,pre_restore_checkup, restore_volumes      # Don't remove

def test_upgrade_restore(restore_setup):

    # This restore setup called from test_restore to setup the restore enviorment and files.

    controller0 = 'controller-0'
    lab = restore_setup["lab"]

    tis_backup_files = restore_setup['tis_backup_files']
    backup_src = RestoreVars.get_restore_var('backup_src'.upper())
    backup_src_path = RestoreVars.get_restore_var('backup_src_path'.upper())

    controller_node = lab[controller0]
    con_ssh = ControllerClient.get_active_controller(name=lab['short_name'], fail_ok=True)

    if not con_ssh:
        LOG.info ("Establish ssh connection with {}".format(controller0))
        controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0
        controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                           initial_prompt=controller_prompt)
        controller_node.ssh_conn.deploy_ssh_key()
        con_ssh = controller_node.ssh_conn


    LOG.info ("Restore system from backup....")
    system_backup_file = [file for file in tis_backup_files if "system.tgz" in file].pop()
    images_backup_file = [file for file in tis_backup_files if "images.tgz" in file].pop()

    LOG.tc_step("Restoring controller 0 ")

    LOG.info("System config restore from backup file {} ...".format(system_backup_file))
    if backup_src.lower() == 'usb':

        system_backup_path = "{}/{}".format(BackupRestore.USB_BACKUP_PATH, system_backup_file)
    else:
        system_backup_path = "{}{}".format(WRSROOT_HOME, system_backup_file)

    LOG.tc_step("Restoring the backup system files ")
    rc1, output = install_helper.upgrade_controller_simplex(system_backup=system_backup_path,
                                                    tel_net_session=controller_node.telnet_conn,fail_ok=True)


    LOG.info('re-connect to the active controller using ssh')
    con_ssh.close()
    time.sleep(60)
    con_ssh = install_helper.establish_ssh_connection(controller_node.host_ip,retry=True)
    controller_node.ssh_conn = con_ssh
    ControllerClient.set_active_controller(con_ssh)

    if backup_src.lower() == 'local':
        images_backup_path = "{}{}".format(WRSROOT_HOME, images_backup_file)
        common.scp_from_test_server_to_active_controller("{}/{}".format(backup_src_path, images_backup_file),
                                                         WRSROOT_HOME)
    else:
        images_backup_path = "{}/{}".format(BackupRestore.USB_BACKUP_PATH, images_backup_file)

    LOG.tc_step("Images restore from backup file {} ...".format(images_backup_file))
    new_prompt = '{}.*~.*\$ '.format(lab['name'].split('_')[0]) + '|controller\-0.*~.*\$ '
    LOG.info('set prompt to:{}'.format(new_prompt))
    con_ssh.set_prompt(new_prompt)

    install_helper.restore_controller_system_images(images_backup=images_backup_path,
                                                    tel_net_session=controller_node.telnet_conn, fail_ok=True)

    LOG.debug('Wait for system ready in 60 seconds')
    time.sleep(60)

    LOG.tc_step("Copying backup files to /opt/backups ... ")
    if backup_src.lower() == 'local':
        con_ssh.exec_cmd("rm -f {} {}".format(system_backup_path, images_backup_path))

        cmd_rm_known_host = r'sed -i "s/^[^#]\(.*\)"/#\1/g /etc/ssh/ssh_known_hosts; \sync'
        con_ssh.exec_sudo_cmd(cmd_rm_known_host)

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
    assert int(con_ssh.exec_cmd("ls {} | wc -l".format(TiSPath.BACKUPS))[1]) >= 2, \
        "Missing backup files in {}".format(TiSPath.BACKUPS)

    LOG.tc_step("Restoring Cinder Volumes ...")
    restore_volumes()

    LOG.tc_step("Delete backup files from {} ....".format(TiSPath.BACKUPS))
    con_ssh.exec_sudo_cmd("rm -rf {}/*".format(TiSPath.BACKUPS))
    LOG.tc_step("Restoring compute  ")
    install_helper.restore_compute(tel_net_session=controller_node.telnet_conn)

    # Activate the upgrade
    LOG.tc_step("Activating upgrade....")
    upgrade_helper.activate_upgrade()

    # LOG.info("Upgrade activate complete.....")

    # Complete upgrade
    LOG.tc_step("Completing upgrade")
    upgrade_helper.complete_upgrade()
    LOG.info("Upgrade is complete......")

    LOG.info("Lab: {} upgraded successfully".format(lab['name']))

    # Delete the previous load
    LOG.tc_step("Deleting  imported load... ")
    system_helper.delete_imported_load()


