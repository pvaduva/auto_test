import time

from consts.auth import Tenant, SvcCgcsAuto
from consts.timeout import VolumeTimeout
from keywords import cinder_helper, glance_helper, common, system_helper
from utils import table_parser, cli, exceptions
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def wait_for_volume_state(vol_id, field, field_value, timeout=VolumeTimeout.STATUS_CHANGE, fail_ok=True,
                          check_interval=3, con_ssh=None, auth_info=None):

    """

    Args:
        vol_id (str):
        field (str):
        field_value (str):
        timeout (int):
        fail_ok (bool):
        check_interval (int):
        con_ssh (str):
        auth_info (dict):

    Returns:
        True if the status of the volume is same as the status(str) that was passed into the function \n
        false if timed out or otherwise

    """

    end_time = time.time() + timeout
    current_status = ''
    while time.time() < end_time:
        table_ = table_parser.table(cli.cinder('show', vol_id, ssh_client=con_ssh, auth_info=auth_info))
        current_status = table_parser.get_value_two_col_table(table_, field, strict=False)
        if current_status in field_value:
            return True

        time.sleep(check_interval)
    else:
        if fail_ok:
            return False
        raise exceptions.TimeoutException("Timed out waiting for volume {} status to reach status: {}. "
                                          "Actual status: {}".format(vol_id, field_value, current_status))


#@mark.parametrize('lab_type', [
#    mark.p1('normal'),
#    mark.p1('storage'),
#])
def test_create_backup(con_ssh=None):
    """
    Test create backup on the system and it's avaliable and in-use volumes

    Args:


    Setup:
        - create system backup use config_controller (create system,image tgz)
        - backup image separately if its storage lab that use CEPH
        - back up all available and in-use volumes from the lab

    Test Steps:
        - check system and img tgz are created for system backup
        - check all images are back up in storage
        - check all volumes tgz are created for backup

    Teardown:
        - Delete vm if booted
        - Delete created flavor (module)

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    dest_dir = SvcCgcsAuto.HOME + '/backup_restore/'

    # execute backup command
    LOG.tc_step("Create backup system and image tgz file under /opt/backups")
    date = time.strftime("%Y%m%d%H%M")
    cmd = 'sudo config_controller --backup titanium_backup_'+date
    # max wait 1800 seconds for config controller backup to finish
    con_ssh.exec_cmd(cmd, expect_timeout=1800, fail_ok=False)

    # scp backup files to test server
    LOG.tc_step("SCP system and image tgz file into testserver /home/svc-cgcsauto/backup_restore")
    source_file = '/opt/backups/titanium_backup_'+date+'_system.tgz /opt/backups/titanium_backup_'+date+'_images.tgz '

    common.scp_from_active_controller_to_test_server(source_file, dest_dir, is_dir=False, multi_files=True)

    # delete backupfiles from ~/opt/backups
    LOG.tc_step("delete system and image tgz file from tis server ~/opt/backups folder ")
    cmd = 'rm -f ' + source_file
    con_ssh.exec_sudo_cmd(cmd, fail_ok=False)

    # storage lab start backup image files separately if it's a storage lab
    # if number of storage nodes is greater than 0
    if len(system_helper.get_storage_nodes()) > 0:

        LOG.tc_step("Storage lab detected. copy images to backup.")

        image_ids = glance_helper.get_images()
        img_file = ''
        for img_id in image_ids:
            img_backup_cmd = 'image-backup export ' + img_id
            # temp sleep wait for image-backup to complete
            con_ssh.exec_sudo_cmd(img_backup_cmd, expect_timeout=300, fail_ok=False)

            img_file = img_file + '/opt/backups/image_'+img_id+'.tgz '

        # copy all image files to test server
        common.scp_from_active_controller_to_test_server(img_file, dest_dir, is_dir=False, multi_files=True)
        # delete for storage image file
        cmd = 'rm -f ' + img_file
        con_ssh.exec_sudo_cmd(cmd, fail_ok=False)
    # storage lab end

    # execute backup available volume command
    vol_ids = cinder_helper.get_volumes(auth_info=Tenant.ADMIN)
    vol_files = ''
    for vol_id in vol_ids:
        print('hi: '+vol_id+cinder_helper.get_volume_states(vol_id, 'status')['status'])
        if cinder_helper.get_volume_states(vol_id, 'status')['status'] == 'available':
            # export available volume to ~/opt/backups
            LOG.tc_step("export available volumes ")
            table_ = table_parser.table(cli.cinder('export', vol_id, auth_info=Tenant.ADMIN))

            # wait for volume copy to complete
            wait_for_volume_state(vol_id, 'volume:backup_status', 'Export completed', timeout=100, fail_ok=True,
                                  check_interval=3, auth_info=Tenant.ADMIN)

            # copy it to the test server
            vol_files = vol_files + '/opt/backups/volume-' + vol_id + '* '

        # execute backup in-use volume command
        if cinder_helper.get_volume_states(vol_id, 'status')['status'] == 'in-use':
            LOG.tc_step("export in use volumes volumes ")
            snapshot_name = 'snapshot_'+vol_id
            cli_args = '--force True --name '+snapshot_name+' '+vol_id
            table_ = table_parser.table(cli.cinder('snapshot-create', cli_args, auth_info=Tenant.ADMIN))
            snap_shot_id = table_parser.get_values(table_, 'Value', Property='id')
            print(snap_shot_id)
            # temp sleep wait for snap-shot creation finish
            time.sleep(120)
            # export in-use volume snapshot to ~/opt/backups
            table_ = table_parser.table(cli.cinder('snapshot-export', snap_shot_id, auth_info=Tenant.ADMIN))
            # temp sleep wait for snap-export to finish
            time.sleep(120)
            # copy it to the test server
            vol_files = vol_files + '/opt/backups/volume-' + vol_id + '* '
            # TODO: delete created snapshot after the are in /opt/backups folder

    # copy vol file if vol_files not empty dest_dir = SvcCgcsAuto.HOME + '/backup_restore'
    if vol_files:
        common.scp_from_active_controller_to_test_server(vol_files, dest_dir, is_dir=False, multi_files=True)

    # delete all volumes files from /opt/backups on tis server
    LOG.tc_step("delete volume tgz file from tis server /opt/backups folder ")
    cmd = 'rm -f ' + vol_files
    con_ssh.exec_sudo_cmd(cmd, fail_ok=False)




