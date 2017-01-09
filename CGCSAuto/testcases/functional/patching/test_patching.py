import os
# import random
import datetime

from pytest import fixture, skip
# from pytest import mark

from consts.auth import Host
from consts.filepaths import WRSROOT_HOME
from consts.proj_vars import PatchingVars
from keywords import host_helper
from keywords import html_helper
from keywords import patching_helper
from keywords import system_helper
from utils import local_host
from utils import table_parser, cli
from utils.ssh import SSHClient
from utils.tis_log import LOG

PUBLIC_SSH_KEY = local_host.get_ssh_key()
PATCH_ALARM_ID = '900.001'
PATCH_ALARM_REASON = 'Patching operation in progress'

patch_dir_in_lab = None


def is_reboot_required(patch_states):
    for patch in patch_states.keys():
        if patch_states[patch]['rr'] and patch_states[patch]['state'] not in ['Available', 'Applied', 'Removed']:
            return True

    return False


def install_impacted_hosts(patch_ids, cur_states=None, con_ssh=None, remove=False):
    LOG.info('cur_states:{}, remove?:{}, patch_ids:{}'.format(cur_states, remove, patch_ids))
    patch_states = cur_states['patch_states']
    host_states = cur_states['host_states']
    reboot_required = is_reboot_required(patch_states)

    pre_states, pre_trace_backs = patching_helper.check_error_states(con_ssh=con_ssh, no_checking=True)

    computes = []
    storages = []
    controllers = []
    for host in host_states.keys():
        if not host_states[host]['patch-current']:
            personality = patching_helper.get_personality(host, con_ssh=con_ssh)
            if 'storage' in personality:
                storages.append(host)
            elif 'compute' in personality and 'controller' not in personality:
                computes.append(host)
            elif 'controller' in personality:
                controllers.append(host)
            else:
                LOG.warn('Unknown personality:{} of host:{}'.format(personality, host))

    for host in computes:
        patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)

    for host in storages:
        patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)

    active_controller = None
    for host in controllers:
        if host_helper.is_active_controller(host, con_ssh=con_ssh):
            active_controller = host
            continue

        patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)

    if reboot_required and active_controller is not None:
        code, output = host_helper.swact_host(active_controller, fail_ok=False, con_ssh=con_ssh)
        assert 0 == code, 'Failed to swact host: from {}'.format(active_controller)

    if active_controller is not None:
        patching_helper.host_install(active_controller, reboot_required=reboot_required, con_ssh=con_ssh)

    expected_patch_states = ('Applied',) if not remove else ('Removed', 'Available')

    patching_helper.wait_patch_states(
        patch_ids, expected_states=expected_patch_states, con_ssh=con_ssh, fail_on_nonexisting=True)

    patching_helper.check_error_states(
        con_ssh=con_ssh, no_checking=False, pre_states=pre_states, pre_trace_backs=pre_trace_backs)


def remove_patch(patch_id, con_ssh=None):
    """ Remove the specified patch or all patches

    Args:
        patch_id: ID of the patch to remove. Use value of 'ALL' to remove all patches
        con_ssh:

    Returns:

    """

    LOG.tc_step('Get patch ids to remove')
    states = patching_helper.get_patching_states(con_ssh=con_ssh, fail_ok=False)
    patch_states = states['patch_states']

    patch_ids = []
    if patch_id.upper() in ['ALL']:
        patch_ids = [pid for pid in patch_states.keys()
                     if patch_states[pid]['state'] in ['Applied', 'Parital-Apply']]
    else:
        if patch_id not in patch_states:
            msg = 'Cannot found patch: {} '.format(patch_id)
            LOG.error(msg)
            assert False, msg

        if patch_states[patch_id]['state'] in ['Applied', 'Parital-Apply']:
            patch_ids = [patch_id]

    assert patch_ids, 'No patches can be removed'
    LOG.info('OK, will remove patch IDs:{}'.format(patch_ids))

    patches = ' '.join(patch_ids)
    LOG.info('OK, will remove patches:{}'.format(patches))

    LOG.tc_step('Remove the patches:{}'.format(patches))
    patch_ids_removed = patching_helper.remove_patches(patches=patches, con_ssh=con_ssh)

    LOG.tc_step('Install impacted hosts after removing patch IDs:{}'.format(patch_ids_removed))
    states = patching_helper.get_patching_states(con_ssh=con_ssh, fail_ok=False)
    install_impacted_hosts(patch_ids_removed, cur_states=states, con_ssh=con_ssh, remove=True)

    return patch_ids_removed


def connect_to_build_server(server=None, username='', password='', prompt=''):
    server = server or PatchingVars.get_patching_var('build_server')
    LOG.info('patch_server={}'.format(server))

    username = username or PatchingVars.get_patching_var('username')
    password = password or PatchingVars.get_patching_var('password')

    LOG.info('username={}, password={}'.format(username, password))

    prompt = prompt or r'.*yow\-cgts[3-4]\-lx.*~\]\$'
    LOG.info('prompt={}'.format(prompt))

    ssh_to_server = SSHClient(server, user=username, password=password, initial_prompt='.*\$ ')
    ssh_to_server.connect()
    ssh_to_server.exec_cmd("bash")
    ssh_to_server.set_prompt(prompt)
    ssh_to_server.deploy_ssh_key(PUBLIC_SSH_KEY)

    LOG.info('ssh connection to server:{} established: {}'.format(server, ssh_to_server))
    return ssh_to_server


def get_patches_dir_to_test(con_ssh=None, single_file_ok=False):
    """Download the patches from specified server:path and store them on to the lab under test

        e.g. patch build server/path:
        yow-cgts4-lx.wrs.com:/localdisk/loadbuild/jenkins/CGCS_4.0_Test_Patch_Build/latest_build
        yow-cgts4-lx.wrs.com:/localdisk/loadbuild/jenkins/CGCS_4.0_Test_Patch_Build/2016-12-07_16-48-53

    Args:
        con_ssh:
        single_file_ok: Flag indicating if single file is accepted. By default, only directory is accepted.

    Returns: the path on the active controller where the downloaded patch files saved

    Notes:
        To save time for downloading patch files from remote patch build server, the files are download once only in a
        test session and reused.
    """

    global patch_dir_in_lab
    if patch_dir_in_lab:
        return patch_dir_in_lab

    patch_build_server = PatchingVars.get_patching_var('patch_build_server')
    patch_dir = PatchingVars.get_patching_var('patch_dir')
    patch_files = os.path.join(patch_dir, '*.patch')

    ssh_to_server = connect_to_build_server(server=patch_build_server)

    rt_code, output = ssh_to_server.exec_cmd('ls {} 2>/dev/null'.format(patch_files), fail_ok=True)
    if 0 != rt_code or not output:
        err_msg = 'No patch files ready on:{} on directory of Patch Build server:{}:{}'.format(
            patch_files, patch_build_server, output)
        LOG.warn(err_msg)

        LOG.warn('Check if {} is patch file'.format(patch_dir))
        assert single_file_ok, err_msg

        rt_code = ssh_to_server.exec_cmd('test -f {}'.format(patch_dir), fail_ok=True)[0]
        assert 0 == rt_code, err_msg
        patch_files = patch_dir

    dest_path = os.path.join(WRSROOT_HOME, 'patch-files-' + datetime.datetime.utcnow().isoformat())
    rt_code, output = patching_helper.run_cmd('mkdir -p {}'.format(dest_path), con_ssh=con_ssh)
    assert 0 == rt_code, 'Failed to create patch dir:{} on the active-controller'.format(dest_path)

    LOG.info('Downloading patch files to lab:{} from:{}'.format(dest_path, patch_files))

    ssh_to_server.rsync(patch_files, html_helper.get_ip_addr(), dest_path,
                        dest_user=Host.USER, dest_password=Host.PASSWORD, timeout=900)

    LOG.info('OK, patch files were downloaded to: {}:{}, from: {} on server: {}'.format(
        html_helper.get_ip_addr(), dest_path, patch_files, patch_build_server))

    # todo, skip failure patches for now
    patching_helper.run_cmd(
        'rm -rf {}/*FAILURE*.patch &> /dev/null'.format(dest_path), con_ssh=con_ssh)

    rt_code, output = patching_helper.run_cmd('ls {}/*.patch 2> /dev/null'.format(dest_path), con_ssh=con_ssh)
    assert 0 == rt_code, 'No patch files to test'.format(rt_code, output)
    if not output:
        skip('No patches to test, skip the reset of the test, supposed to test patch_files:{}'.format(patch_files))
        return dest_path

    patch_dir_in_lab = dest_path

    return dest_path


@fixture(scope='module', autouse=True)
def check_if_ready_for_patching():
    assert system_helper.are_hosts_unlocked(), \
        'Not all hosts are unlocked, skip patch testing'

    alarm_table = table_parser.table(cli.system('alarm-list'))
    alarm_severity_list = table_parser.get_column(alarm_table, 'Severity')
    assert 'major' or 'critical' not in alarm_severity_list, \
        'There are active alarms:{}, skip patch testing'

    # alarm_ids = table_parser.get_column(alarm_table, 'Alarm ID')
    # assert PATCH_ALARM_ID not in alarm_ids, \
    #     'The system is under patching, skip patch testing'


def _test_upload_patches_from_dir(con_ssh=None):
    """Test upload patch files from the specified directory on the specified remote server

    Args:
        con_ssh:
    Returns:

    """
    LOG.tc_step('Download patch files from specified location')
    patch_dir = get_patches_dir_to_test(con_ssh=con_ssh, single_file_ok=True)
    LOG.info('-Patch files are downloaded to directory:{} on the active controller'.format(patch_dir))

    LOG.tc_step('Upload the directory{}'.format(patch_dir))
    patch_ids = patching_helper.upload_patch_dir(patch_dir=patch_dir, con_ssh=con_ssh)[0]
    LOG.info('-Patches are uploaded to system:{}'.format(patch_ids))

    return patch_ids


def _test_apply_patches(patch_ids=None, con_ssh=None, apply_all=True, fail_if_patched=True):
    apply_all = apply_all or patch_ids is not None

    msg = 'Apply ' + 'all' if apply_all else ''
    msg += ' patches'
    msg += '' if apply_all else ':{}'.format(patch_ids)
    LOG.tc_step(msg)

    applied_patches = patching_helper.apply_patches(
        patch_ids=patch_ids, apply_all=apply_all, fail_if_patched=fail_if_patched, con_ssh=con_ssh)

    LOG.info('-Patches are applied:{}'.format(applied_patches))
    return applied_patches


def _test_install_impacted_hosts(applied_patches, con_ssh=None):
    LOG.tc_step('Install all patches')
    states = patching_helper.get_patching_states(con_ssh=con_ssh, fail_ok=False)
    install_impacted_hosts(applied_patches, cur_states=states, con_ssh=con_ssh)
    LOG.info('-Patches are installed')


def test_install_impacted_hosts(con_ssh=None):
    """Install patches on each impacted nodes


    Args:
        con_ssh:

    Returns:

    Test Steps:
        1   Upload the patch files into the patching system on the lab
            - download patch files first from the specified directory on the specified server.
            The directory and server are specified using py.test command line options.

        2   Apply all the patches uploaded

        3   Do host-install on all the hosts impacted

    """

    patch_ids = _test_upload_patches_from_dir(con_ssh=con_ssh)

    applied_patches = _test_apply_patches(patch_ids=patch_ids, apply_all=True, fail_if_patched=True, con_ssh=con_ssh)

    _test_install_impacted_hosts(applied_patches, con_ssh=con_ssh)


def test_apply_patches(con_ssh=None):
    """Apply all the patches uploaded

    Args:
        con_ssh:

    Returns:

    Steps:
        1   Upload the patch files into the patching system on the lab
            - download patch files first from the specified directory on the specified server.
            The directory and server are specified using py.test command line options.

        2   Apply all the patches uploaded
    """

    patch_ids = _test_upload_patches_from_dir(con_ssh=con_ssh)

    _test_apply_patches(patch_ids=patch_ids, apply_all=True, fail_if_patched=True, con_ssh=con_ssh)


def test_upload_patch_dir_file(con_ssh=None):
    """Upload the patch files into the patching system on the lab

    Args:
        con_ssh:

    Returns:

    Steps:
        1   download patch files first from the specified directory on the specified server.
                The directory and server are specified using py.test command line options.
        2   upload the patches into the patching system of the lab

    """

    _test_upload_patches_from_dir(con_ssh=con_ssh)


def test_install_patch_dir_file(con_ssh=None):
    """Test install patches from the specified directory on the specified server.

    Args:
        con_ssh:

    Returns:

    Test Steps:
        1   Upload the patch files into the patching system on the lab
            - download patch files first from the specified directory on the specified server.
            The directory and server are specified using py.test command line options.

        2   Apply all the patches uploaded

        3   Do host-install on all the hosts impacted

    """

    patch_ids = _test_upload_patches_from_dir(con_ssh=con_ssh)

    applied_patches = _test_apply_patches(patch_ids=patch_ids, apply_all=True, fail_if_patched=True, con_ssh=con_ssh)

    _test_install_impacted_hosts(applied_patches, con_ssh=con_ssh)


def test_remove_patch(con_ssh=None):
    """Remove all patches currently applied in the system

    Args:
        con_ssh: SSH connection to the active controller

    Returns:

    Steps:
        1   Remove all applied patches in Applied or Partial-Applied states
        2   Do host-install on all impacted hosts in the order: compute, storage, standby-controller
            and active-controller

    """
    remove_patch('all', con_ssh=con_ssh)

