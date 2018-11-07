import os
import re
import time

import pytest

from consts.auth import SvcCgcsAuto, HostLinuxCreds, Tenant
from consts.build_server import Server, get_build_server_info
from consts.cgcs import HostAvailState, HostOperState, HostAdminState, Prompt, IMAGE_BACKUP_FILE_PATTERN,\
    TIS_BLD_DIR_REGEX, TITANIUM_BACKUP_FILE_PATTERN, BackupRestore
from consts.filepaths import TiSPath, BuildServerPath, WRSROOT_HOME
from consts.proj_vars import InstallVars, RestoreVars, ProjVar
from consts.timeout import HostTimeout
from keywords import storage_helper, install_helper, cinder_helper, host_helper, system_helper, common
from setups import collect_tis_logs
from utils import cli, table_parser
from utils import node
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG
from utils import exceptions


def collect_logs(con_ssh=None, fail_ok=True):
    """
    Collect logs on the system by calling collect_tis_logs, backup logs under /scratch before head if any, so that there
    are enough disk space.

    Args:
        con_ssh:
            - ccurrent ssh connection to the target
        fail_ok:
            - True: do not break the whole test case if there's any error during collecting logs
              False: abort the entire test case if there's any eorr. True by default.

    Return:
        None
    """

    log_tarball = r'/scratch/ALL_NODES*'
    log_dir = r'~/collected-logs'
    old_log_dir = r'~/collected-logs/old-files'

    try:
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller()
        prep_cmd = 'mkdir {}; mkdir {}'.format(log_dir, old_log_dir)
        code, output = con_ssh.exec_cmd(prep_cmd, fail_ok=fail_ok)
        if code != 0:
            LOG.warn('failed to execute cmd:{}, code:{}'.format(prep_cmd, code))
            con_ssh.exec_sudo_cmd('rm -rf /scratch/ALL_NODES*', fail_ok=fail_ok)

        prep_cmd = 'mv -f {} {}'.format(log_tarball, old_log_dir)
        code, output = con_ssh.exec_sudo_cmd(prep_cmd, fail_ok=fail_ok)
        if code != 0:
            LOG.warn('failed to execute cmd:{}, code:{}'.format(prep_cmd, code))

            LOG.info('execute: rm -rf /scratch/ALL_NODES*')
            con_ssh.exec_sudo_cmd('rm -rf /scratch/ALL_NODES*', fail_ok=fail_ok)

            LOG.info('ok, removed /scratch/ALL_NODES*')

        else:
            LOG.info('ok, {} moved to {}'.format(log_tarball, old_log_dir))

        collect_tis_logs(con_ssh=con_ssh)
    except exceptions.ActiveControllerUnsetException:
        pass


@pytest.fixture(scope='session', autouse=True)
def pre_restore_checkup():
    """
    Fixture to check the system states before doing system restore, including:
        - collect logs
        - check if backup files exist on the backup media
        - check if the build-ids match with each other
        - wipe disks

    Args:

    Return:
        backup files:
            - the backup files to restore with
    """

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

    LOG.info('Collect logs before restore')
    if controller_conn:
        collect_logs(controller_conn)
        ControllerClient.set_active_controller(controller_conn)
    else:
        LOG.info('Cannot collect logs because no ssh connection to the lab')

    if not controller_conn:
        LOG.warn('failed to collect logs because no ssh connection established to controller-0 of lab:{}'.format(
            controller_node.host_ip))
    else:
        pass

    LOG.info('backup_src={}, backup_src_path={}'.format(backup_src, backup_src_path))
    if backup_src.lower() == 'usb':
        if controller_conn:
            LOG.info("Connection established with controller-0 ....")
            ControllerClient.set_active_controller(ssh_client=controller_conn)

            LOG.info("Checking if a USB flash drive with backup files is plugged in... ")
            usb_device_name = install_helper.get_usb_device_name(con_ssh=controller_conn)
            assert usb_device_name, "No USB found "
            LOG.info("USB flash drive found, checking for backup files ... ")
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

            # extract build id from the file name
            file_parts = tis_backup_files[0].split('_')

            file_backup_build_id = '_'.join([file_parts[3], file_parts[4]])

            assert re.match(TIS_BLD_DIR_REGEX,
                            file_backup_build_id), " Invalid build id format {} extracted from backup_file {}".format(
                file_backup_build_id, tis_backup_files[0])

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
        test_server_attr = dict()
        test_server_attr['name'] = SvcCgcsAuto.HOSTNAME.split('.')[0]
        test_server_attr['server_ip'] = SvcCgcsAuto.SERVER
        test_server_attr['prompt'] = r'\[{}@{} {}\]\$ '\
            .format(SvcCgcsAuto.USER, test_server_attr['name'], SvcCgcsAuto.USER)

        test_server_conn = install_helper.establish_ssh_connection(test_server_attr['name'], user=SvcCgcsAuto.USER,
                                                                   password=SvcCgcsAuto.PASSWORD,
                                                                   initial_prompt=test_server_attr['prompt'])

        test_server_conn.set_prompt(test_server_attr['prompt'])
        test_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        test_server_attr['ssh_conn'] = test_server_conn
        test_server_obj = Server(**test_server_attr)
        RestoreVars.set_restore_var(backup_src_server=test_server_obj)

        # test if backup path for the lab exist in Test server
        if os.path.basename(backup_src_path) != lab['short_name']:
            backup_src_path += '/{}'.format(lab['short_name'])
            RestoreVars.set_restore_var(backup_src_path=backup_src_path)

        assert not test_server_conn.exec_cmd("test -e {}".format(backup_src_path))[0], \
            "Missing backup files from source {}: {}".format(test_server_attr['name'], backup_src_path)

        tis_backup_files = install_helper.get_backup_files(TITANIUM_BACKUP_FILE_PATTERN, backup_src_path,
                                                           test_server_conn)

        assert len(tis_backup_files) >= 2, "Missing backup files: {}".format(tis_backup_files)

        # extract build id from the file name
        file_parts = tis_backup_files[0].split('_')

        file_backup_build_id = '_'.join([file_parts[3], file_parts[4]])

        assert re.match(TIS_BLD_DIR_REGEX,
                        file_backup_build_id), "Invalid build id format {} extracted from backup_file {}".format(
            file_backup_build_id, tis_backup_files[0])

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
            if not RestoreVars.get_restore_var('skip_reinstall'):
                LOG.info('Try to do wipedisk_via_helper on controller-0')
                install_helper.wipedisk_via_helper(controller_conn)

    assert backup_build_id, "The Build id of the system backup must be provided."

    return tis_backup_files


@pytest.fixture(scope='session')
def restore_setup(pre_restore_checkup):
    """
    Fixture to do preparation before system restore.

    Args:
        pre_restore_checkup:
            - actions done prior to this

    Returen:
        a dictionary
            - containing infromation about target system, output directory,
                build server and backup files.
    """

    LOG.debug('Restore with settings:\n{}'.format(RestoreVars.get_restore_vars()))
    lab = InstallVars.get_install_var('LAB')
    LOG.info("Lab info; {}".format(lab))
    hostnames = [k for k, v in lab.items() if isinstance(v, node.Node)]
    LOG.info("Lab hosts; {}".format(hostnames))

    backup_build_id = RestoreVars.get_restore_var("BACKUP_BUILD_ID")
    output_dir = ProjVar.get_var('LOG_DIR')
    controller_node = lab['controller-0']

    controller_prompt = ''
    extra_controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0

    if RestoreVars.get_restore_var('skip_reinstall'):
        LOG.info('Skip reinstall as instructed')
        LOG.info('Connect to controller-0 now')
        controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                           initial_prompt=extra_controller_prompt,
                                                                           fail_ok=True)
        bld_server_obj = None
    else:
        # bld_server = get_build_server_info(InstallVars.get_install_var('BUILD_SERVER'))
        bld_server = get_build_server_info(RestoreVars.get_restore_var('BUILD_SERVER'))

        LOG.info("Connecting to Build Server {} ....".format(bld_server['name']))
        bld_server_attr = dict()
        bld_server_attr['name'] = bld_server['name']
        bld_server_attr['server_ip'] = bld_server['ip']
        bld_server_attr['prompt'] = r'{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, bld_server['name'])

        bld_server_conn = install_helper.establish_ssh_connection(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                                                  password=SvcCgcsAuto.PASSWORD,
                                                                  initial_prompt=bld_server_attr['prompt'])

        bld_server_conn.exec_cmd("bash")
        bld_server_conn.set_prompt(bld_server_attr['prompt'])
        bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        bld_server_attr['ssh_conn'] = bld_server_conn
        bld_server_obj = Server(**bld_server_attr)

        # If controller is accessible, check if USB with backup files is avaialble

        load_path = os.path.join(BuildServerPath.DEFAULT_WORK_SPACE, RestoreVars.get_restore_var("BACKUP_BUILDS_DIR"),
                                 backup_build_id)

        InstallVars.set_install_var(tis_build_dir=load_path)

        # set up feed for controller
        LOG.fixture_step("Setting install feed in tuxlab for controller-0 ... ")
        if 'vbox' not in lab['name'] and not RestoreVars.get_restore_var('skip_setup_feed'):
            assert install_helper.set_network_boot_feed(bld_server_conn,
                                                        load_path), "Fail to set up feed for controller"

        if not RestoreVars.get_restore_var('skip_reinstall'):
            # power off hosts
            LOG.fixture_step("Powring off system hosts ... ")
            install_helper.power_off_host(hostnames)

            LOG.fixture_step("Booting controller-0 ... ")
            is_cpe = (lab.get('system_type', 'Standard') == 'CPE')
            low_latency = RestoreVars.get_restore_var('low_latency')

            os.environ['XTERM'] = 'xterm'
            install_helper.boot_controller(small_footprint=is_cpe, system_restore=True, low_latency=low_latency)

            # establish ssh connection with controller
            LOG.fixture_step("Establishing ssh connection with controller-0 after install...")

            node_name_in_ini = '{}.*\~\$ '.format(install_helper.get_lab_info(controller_node.barcode)['name'])
            controller_prompt = re.sub(r'([^\d])0*(\d+)', r'\1\2', node_name_in_ini)

    controller_prompt = controller_prompt + '|' + Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0

    LOG.info('initial_prompt=' + controller_prompt)
    controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                       initial_prompt=controller_prompt)
    LOG.info('Deploy ssh key')
    controller_node.ssh_conn.deploy_ssh_key()

    ControllerClient.set_active_controller(ssh_client=controller_node.ssh_conn)
    con_ssh = controller_node.ssh_conn
    tis_backup_files = pre_restore_checkup
    backup_src = RestoreVars.get_restore_var('backup_src'.upper())
    backup_src_path = RestoreVars.get_restore_var('backup_src_path'.upper())
    if backup_src.lower() == 'local':
        LOG.fixture_step("Transferring system backup file to controller-0 {} ... ".format(WRSROOT_HOME))

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
        LOG.fixture_step("USB flash drive found, checking for backup files ... ")

        if len(tis_backup_files) == 0:
            LOG.fixture_step("Checking for backup files in USB ... ")
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
                      'tis_backup_files': tis_backup_files}

    return _restore_setup


def make_sure_all_hosts_locked(con_ssh, max_tries=5):
    """
    Make sure all the hosts are locked before doing system restore.

    Args:
        con_ssh:
            - ssh connection to the target lab

        max_tries:
            - number of times to try before fail the entire test case when any hosts keep failing to lock.

    Return:
        None

    """

    LOG.info('System restore procedure requires to lock all nodes except the active controller/controller-0')

    base_cmd = 'host-lock'
    locked_offline = {'administrative': HostAdminState.LOCKED, 'availability': HostAvailState.OFFLINE}

    for tried in range(1, max_tries+1):
        hosts = [h for h in host_helper.get_hosts(con_ssh=con_ssh, administrative='unlocked') if h != 'controller-0']
        if not hosts:
            LOG.info('all hosts all locked except the controller-0 after tried:{}'.format(tried))
            break

        cmd = base_cmd
        if tried > 1:
            cmd = base_cmd + ' -f'

        locking = [] 
        already_locked = 0
        for host in hosts:
            LOG.info('try:{} locking:{}'.format(tried, host))
            admin_state = host_helper.get_hostshow_value(host, 'administrative', con_ssh=con_ssh)
            if admin_state != 'locked':
                code, output = cli.system(cmd + ' ' + host, ssh_client=con_ssh, fail_ok=True, rtn_list=True)
                if 0 != code:
                    LOG.warn('Failed to lock host:{} using CLI:{}'.format(host, cmd))
                else:
                    locking.append(host)
            else:
                already_locked += 1

        if locking:
            LOG.info('Wating for those accepted locking instructions to be locked:  try:{}'.format(tried))
            host_helper.wait_for_hosts_states(locking, con_ssh=con_ssh, timeout=600, **locked_offline)

        elif already_locked == len(hosts):
            LOG.info('all hosts all locked except the controller-0 after tried:{}'.format(tried))
            break

        else:
            LOG.info('All hosts were rejecting to lock after tried:{}'.format(tried))
    else:
        cli.system('host-list', con_ssh=con_ssh)
        LOG.info('Failed to lock or force-lock some of the hosts')
        assert False, 'Failed to lock or force-lock some of the hosts after tried:{} times'.format(tried)

    cli.system('host-list', con_ssh=con_ssh)
            

    code, output = cli.system('host-list', ssh_client=con_ssh, fail_ok=True, rtn_list=True)
    LOG.debug('code:{}, output:{}'.format(code, output))


def install_non_active_node(node_name, lab):
    """
    Install the non-active controller node, usually it is controller-1, the second controller
        on a non-AIO SX system.

    Args:
        node_name:
            - the name of the host/node, usually 'controller-1'
        lab:
            - lab to test
    """

    boot_interfaces = lab['boot_device_dict']
    LOG.tc_step("Restoring {}".format(node_name))
    install_helper.open_vlm_console_thread(node_name, boot_interface=boot_interfaces, vlm_power_on=True)

    LOG.info("Verifying {} is Locked, Disabled and Online ...".format(node_name))
    host_helper.wait_for_hosts_states(node_name, administrative=HostAdminState.LOCKED,
                                      operational=HostOperState.DISABLED,
                                      availability=HostAvailState.ONLINE)

    LOG.info("Unlocking {} ...".format(node_name))
    rc, output = host_helper.unlock_host(node_name, available_only=False)

    assert rc == 0 or rc == 4, "Host {} failed to unlock: rc = {}, msg: {}".format(node_name, rc, output)

    if rc == 4:
        LOG.warn('{} now is in degraded status'.format(node_name))

    LOG.info('{} is installed'.format(node_name))


def get_backup_list(con_ssh):
    """
    Get a list of all the cinder-backups.

    Args:
        con_ssh:
            - the current ssh connection to the target

    Return:
        list of ID and Volume ID for the current cinder-backups

    """

    rc, output = con_ssh.exec_cmd('cinder backup-list')
    table_ = table_parser.table(output)
    LOG.info('cinder backups: {}'.format(table_))

    backup_volumes = table_parser.get_columns(table_, ['ID', 'Volume ID'])
    LOG.info('TODO: backup and volumes: {}'.format(backup_volumes))

    return backup_volumes


def wait_for_backup_status(backup_id,
                           target_status='available',
                           timeout=1800,
                           wait_between_check=30,
                           fail_ok=False,
                           con_ssh=None):
    """
    Wait the specified cinder-backup to reach certain status.

    Args:
        backup_id:
            - id of the cinder-backup

        target_status:
            - the expected status to wait, by default it's 'available'

        timeout:
            - how long to wait if the cinder-backup does not reach expected status,
                1800 seconds by default

        wait_between_check:
            - interval between checking the status, 30 seconds by default

        fail_ok:
            - if the test case should be failed if any error occurs, False by default

        con_ssh:
            - current ssh connection the lab

    Return:
        error-code:
            -   0   -- success
            -   1   -- failed
        error-msg:
            -   message about the reason of failure
    """

    cmd = 'cinder backup-show ' + backup_id
    end_time = time.time() + timeout

    output = ''
    while time.time() < end_time:
        rc, output = con_ssh.exec_cmd(cmd)
        table_ = table_parser.table(output)
        status = table_parser.get_value_two_col_table(table_, 'status')
        if status.lower() == target_status.lower():
            break
        time.sleep(wait_between_check)

    else:
        msg = 'Backup:{} did not reach status:{} in {} seconds'.format(backup_id, target_status, timeout)
        LOG.warn(msg + 'output:' + output)
        assert fail_ok, msg
        return 1, msg

    return 0, 'all cinder backup:{} reached status:{} after {} seconds'.format(backup_id, target_status, timeout)


def restore_cinder_backup(backup_id, volume_id, con_ssh):
    """
    Restore a cinder volume with the specified backup id and volume id

    Args:
        backup_id:
            - the cinder-backup id

        volume_id:
            - the cinder volume id

        con_ssh:
            - the ssh connection to the target host

    Return:
        error-code:
            - 0 --  success

        message:
            - more detailed message about the final status of volume to restore
    """

    LOG.info('new cinder backup CLI: backupid={}, volume_id={}'.format(backup_id, volume_id))

    cmd = 'cinder backup-restore --volume {} {}'.format(volume_id, backup_id)
    rc, output = con_ssh.exec_cmd(cmd)
    
    LOG.info('TODO: output: {}\ncmd:{}'.format(output, cmd))
    wait_for_backup_status(backup_id, target_status='available', con_ssh=con_ssh)

    target_volume_status = ['available', 'in-use']
    cinder_helper.wait_for_volume_status(volume_id, status=target_volume_status, con_ssh=con_ssh,
                                         auth_info=Tenant.ADMIN)

    return 0, 'Volume reached status: {}'.format(target_volume_status)


def restore_from_cinder_backups(volumes, con_ssh):
    """
    Restore specified cinder volumes using cinder-backup CLIs

    Args:
        volumes:
            - ID of cinder volumes to restore

        con_ssh:
            - ssh connection to the target lab

    Return:
        code, volume IDs
    """

    LOG.info('Restore volumes using new cinder backup CLI')
    backup_volumes = {volume_id: backup_id for backup_id, volume_id in get_backup_list(con_ssh)}

    LOG.info('TODO: restoring backup: {}'.format(backup_volumes))
    for volume_id in volumes:
        if volume_id in backup_volumes:
            backup_id = backup_volumes[volume_id]
            LOG.info('TODO: RESTORING volume: ' + volume_id)
            rc, output = restore_cinder_backup(backup_id, volume_id, con_ssh)
            assert rc == 0, 'Failed to restore backup, rc={}, output={}'.format(rc, output)
            LOG.info('TODO Volume is successfully restored from backup:{}, volume:{}'.format(backup_id, volume_id))
        else:
            LOG.warning('No "cinder backup" for volume {}'.format(volume_id))

    return 0, volumes


def create_dummy_rbd_images(volumes, con_ssh):
    LOG.info('Creating RBD image for all cinder volumes, volumes:{}'.format(volumes))

    in_use_volumes = []

    for volume_id in volumes:
        volume_size = cinder_helper.get_volume_states(volume_id, fields='size', con_ssh=con_ssh)['size']
        volume_status = cinder_helper.get_volume_states(volume_id, fields='status', con_ssh=con_ssh)['status']

        if volume_status == 'in-use':
            in_use_volumes.append(volume_id)
            con_ssh.exec_cmd('cinder reset-state --state available ' + volume_id, fail_ok=False)
            
        cmd = 'rbd create --pool cinder-volumes --image volume-{} --size {}G'.format(volume_id, volume_size)
        con_ssh.exec_cmd(cmd, fail_ok=False)

        if volume_status == 'in_use':
            con_ssh.exec_cmd('cinder reset-state --state in-use ' + volume_id, fail_ok=False)

    return in_use_volumes


def restore_volumes(con_ssh=None):
    LOG.info('Restore cinder volumes using new (UPSTREAM) cinder-backup CLIs')
    # Getting all registered cinder volumes

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    using_cinder_backup = RestoreVars.get_restore_var('cinder_backup')
    volumes = cinder_helper.get_volumes()

    in_use_volumes = []
    if len(volumes) > 0:
        LOG.info("System has {} registered volumes: {}".format(len(volumes), volumes))
        if not using_cinder_backup:
            rc, restored_vols = install_helper.restore_cinder_volumes_from_backup()
        else:
            in_use_volumes = create_dummy_rbd_images(volumes, con_ssh=con_ssh)
            rc, restored_vols = restore_from_cinder_backups(volumes, con_ssh)

        assert rc == 0, "All or some volumes has failed import: Restored volumes {}; Expected volumes {}"\
            .format(restored_vols, volumes)
        LOG.info('all {} volumes are imported'.format(len(restored_vols)))

        LOG.info('set back their original status for all in-use volumes: {}'.format(in_use_volumes))
        for volume_id in in_use_volumes:
            con_ssh.exec_cmd('cinder reset-state --state in-use ' + volume_id)
    else:
        LOG.info("System has {} NO registered volumes; skipping cinder volume restore")


def test_restore(restore_setup):
    controller1 = 'controller-1'
    controller0 = 'controller-0'

    lab = restore_setup["lab"]
    is_aio_lab = lab.get('system_type', 'Standard') == 'CPE'
    is_sx = is_aio_lab and (len(lab['controller_nodes']) < 2)

    tis_backup_files = restore_setup['tis_backup_files']
    backup_src = RestoreVars.get_restore_var('backup_src'.upper())
    backup_src_path = RestoreVars.get_restore_var('backup_src_path'.upper())

    controller_node = lab[controller0]
    con_ssh = ControllerClient.get_active_controller(name=lab['short_name'], fail_ok=True)
    controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0

    if not con_ssh:
        LOG.info("Establish ssh connection with {}".format(controller0))
        controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                           initial_prompt=controller_prompt)
        controller_node.ssh_conn.deploy_ssh_key()
        con_ssh = controller_node.ssh_conn
        ControllerClient.set_active_controller(con_ssh)

    LOG.info("Restore system from backup....")
    system_backup_file = [file for file in tis_backup_files if "system.tgz" in file].pop()
    images_backup_file = [file for file in tis_backup_files if "images.tgz" in file].pop()

    LOG.tc_step("Restoring {}".format(controller0))

    LOG.info("System config restore from backup file {} ...".format(system_backup_file))
    if backup_src.lower() == 'usb':
        system_backup_path = "{}/{}".format(BackupRestore.USB_BACKUP_PATH, system_backup_file)
    else:
        system_backup_path = "{}{}".format(WRSROOT_HOME, system_backup_file)

    compute_configured = install_helper.restore_controller_system_config(
        system_backup=system_backup_path,
        tel_net_session=controller_node.telnet_conn, is_aio=is_aio_lab)[2]

    # return

    LOG.info("Source Keystone user admin environment ...")
    controller_node.telnet_conn.exec_cmd("cd; source /etc/nova/openrc")

    LOG.info('re-connect to the active controller using ssh')
    con_ssh.close()
    controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                       initial_prompt=controller_prompt)

    con_ssh = install_helper.establish_ssh_connection(controller_node.host_ip)
    controller_node.ssh_conn = con_ssh
    ControllerClient.set_active_controller(con_ssh)

    make_sure_all_hosts_locked(con_ssh)

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

    timeout = HostTimeout.REBOOT + 60
    availability = HostAvailState.AVAILABLE
    is_available = host_helper.wait_for_hosts_states(controller0,
                                                     availability=HostAvailState.AVAILABLE,
                                                     fail_ok=True,
                                                     timeout=timeout)
    if not is_available:
        LOG.warn('After {} seconds, the first node:{} does NOT reach {}'.format(timeout, controller0, availability))
        LOG.info('Check if drbd is still synchronizing data')
        con_ssh.exec_sudo_cmd('drbd-overview')
        is_degraded = host_helper.wait_for_hosts_states(controller0,
                                                        availability=HostAvailState.DEGRADED,
                                                        fail_ok=True,
                                                        timeout=300)
        if is_degraded:
            LOG.warn('Node: {} is degraded: {}'.format(controller0, HostAvailState.DEGRADED))
            con_ssh.exec_sudo_cmd('drbd-overview')
        else:
            LOG.fatal('Node:{} is NOT in Available nor Degraded status')
            # the customer doc does have wording regarding this situation, continue
            # assert False, 'Node:{} is NOT in Available nor Degraded status'

    # delete the system backup files from wrsroot home
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

    if is_aio_lab:
        LOG.tc_step("Restoring Cinder Volumes ...")
        restore_volumes()

        if not compute_configured:
            LOG.tc_step('Latest 18.07 EAR1 or Old-load on AIO/CPE lab: config its compute functionalities')
            # install_helper.run_cpe_compute_config_complete(controller_node, controller0)

            LOG.info('closing current ssh connection')
            con_ssh.close()

            LOG.tc_step('Run restore-complete (CGTS-9756)')
            controller_node.telnet_conn.login()

            cmd = 'echo "{}" | sudo -S config_controller --restore-complete'.format(HostLinuxCreds.get_password())
            controller_node.telnet_conn.exec_cmd(cmd, extra_expects=' will reboot ')
            controller_node.telnet_conn.close()

            LOG.info('Wait until "config_controller" reboot the active controller')
            time.sleep(180)

            controller_node.telnet_conn = install_helper.open_telnet_session(controller_node,
                                                                             ProjVar.get_var('LOG_DIR'))
            controller_node.telnet_conn.login()
            time.sleep(120)

            con_ssh = install_helper.establish_ssh_connection(controller_node.host_ip)
            controller_node.ssh_conn = con_ssh
            ControllerClient.set_active_controller(con_ssh)

            host_helper.wait_for_hosts_ready(controller0)

        LOG.tc_step('Install the standby controller: {}'.format(controller1))
        if not is_sx:
            install_non_active_node(controller1, lab)

    elif len(lab['controller_nodes']) >= 2:
        LOG.tc_step('Install the standby controller: {}'.format(controller1))
        install_non_active_node(controller1, lab)

        boot_interfaces = lab['boot_device_dict']

        hostnames = system_helper.get_hostnames()
        storage_hosts = [host for host in hostnames if 'storage' in host]
        compute_hosts = [host for host in hostnames if 'storage' not in host and 'controller' not in host]

        if len(storage_hosts) > 0:
            # con_ssh.exec_sudo_cmd('touch /etc/ceph/ceph.client.None.keyring')
            for storage_host in storage_hosts:
                LOG.tc_step("Restoring {}".format(storage_host))
                install_helper.open_vlm_console_thread(storage_host, boot_interface=boot_interfaces, vlm_power_on=True)

                LOG.info("Verifying {} is Locked, Diabled and Online ...".format(storage_host))
                host_helper.wait_for_hosts_states(storage_host, administrative=HostAdminState.LOCKED,
                                                  operational=HostOperState.DISABLED,
                                                  availability=HostAvailState.ONLINE)

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
        restore_volumes()

        LOG.tc_step('Run restore-complete (CGTS-9756), regular lab')
        controller_node.telnet_conn.login()
        cmd = 'echo "{}" | sudo -S config_controller --restore-complete'.format(HostLinuxCreds.get_password())
        controller_node.telnet_conn.exec_cmd(cmd, extra_expects='controller-0 login:')

        LOG.info('rebuild ssh connection')
        con_ssh = install_helper.establish_ssh_connection(controller_node.host_ip)
        controller_node.ssh_conn = con_ssh

        LOG.tc_step("Restoring Compute Nodes ...")
        if len(compute_hosts) > 0:
            for compute_host in compute_hosts:
                LOG.tc_step("Restoring {}".format(compute_host))
                install_helper.open_vlm_console_thread(compute_host, boot_interface=boot_interfaces, vlm_power_on=True)

                LOG.info("Verifying {} is Locked, Diabled and Online ...".format(compute_host))
                host_helper.wait_for_hosts_states(compute_host, administrative=HostAdminState.LOCKED,
                                                  operational=HostOperState.DISABLED,
                                                  availability=HostAvailState.ONLINE)
                LOG.info("Unlocking {} ...".format(compute_host))
                rc, output = host_helper.unlock_host(compute_host, available_only=True)
                assert rc == 0, "Host {} failed to unlock: rc = {}, msg: {}".format(compute_host, rc, output)

        LOG.info("All nodes {} are restored ...".format(hostnames))
    else:
        LOG.warn('Only 1 controller, but not AIO lab!!??')

    LOG.tc_step("Delete backup files from {} ....".format(TiSPath.BACKUPS))
    con_ssh.exec_sudo_cmd("rm -rf {}/*".format(TiSPath.BACKUPS))

    LOG.tc_step('Perform post-restore testing/checking')
    post_restore_test(con_ssh)

    LOG.tc_step("Waiting until all alarms are cleared ....")
    timeout = 300
    healthy, alarms = system_helper.wait_for_all_alarms_gone(timeout=timeout, fail_ok=True)
    if not healthy:
        LOG.warn('Alarms exist: {}, after waiting {} seconds'.format(alarms, timeout))
        rc, message = con_ssh.exec_sudo_cmd('drbd-overview')

        if rc != 0 or (r'[===>' not in message and r'] sync\'ed: ' not in message):
            LOG.warn('Failed to get drbd-overview information')

        LOG.info('Wait for the system to be ready in {} seconds'.format(HostTimeout.REBOOT))
        system_helper.wait_for_all_alarms_gone(timeout=HostTimeout.REBOOT, fail_ok=False)

    LOG.tc_step("Verifying system health after restore ...")
    rc, failed = system_helper.get_system_health_query(con_ssh=con_ssh)
    assert rc == 0, "System health not OK: {}".format(failed)

    collect_logs()


def check_volumes_spaces(con_ssh):
    from keywords import cinder_helper
    LOG.info('Checking cinder volumes and space usage')
    usage_threshold = 0.70
    free_space, total_space, unit = cinder_helper.get_lvm_usage(con_ssh)

    if total_space and free_space < usage_threshold * total_space:
        if total_space:
            LOG.info('cinder LVM over-used: free:{}, total:{}, ration:{}%'.format(
                free_space, total_space, free_space/total_space * 100))

        LOG.info('Deleting known LVM alarms')

        expected_reason = 'Cinder LVM .* Usage threshold exceeded; threshold: (\d+(\.\d+)?)%, actual: (\d+(\.\d+)?)%'
        expected_entity = 'host=controller'
        value_titles = ('UUID', 'Alarm ID', 'Reason Text', 'Entity ID')
        lvm_pool_usage = system_helper.get_alarms(rtn_vals=value_titles, con_ssh=con_ssh)

        if not lvm_pool_usage:
            LOG.warn('Cinder LVM pool is used up to 75%, but no alarm for it')
        else:
            if len(lvm_pool_usage) > 1:
                LOG.warn('More than one alarm existing for Cinder LVM over-usage')
            elif len(lvm_pool_usage) < 1:
                LOG.warn('No LVM cinder over-used alarms, got:{}'.format(lvm_pool_usage))

            for lvm_alarm in lvm_pool_usage:
                alarm_uuid, alarm_id, reason_text, entity_id = lvm_alarm.split('::::')

                if re.match(expected_reason, reason_text) and re.search(expected_entity, entity_id):
                    LOG.info('Expected alarm:{}, reason:{}'.format(alarm_uuid, reason_text))
                    LOG.info('Deleting it')
                    system_helper.delete_alarms(alarms=alarm_uuid)


def post_restore_test(con_ssh):
    LOG.info('Perform system testing and checking after the system is restored')
    check_volumes_spaces(con_ssh)

