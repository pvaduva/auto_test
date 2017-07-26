import os
import re
import time
import datetime
import random

from pytest import fixture, skip, mark

from consts.auth import HostLinuxCreds
from consts.filepaths import WRSROOT_HOME
from consts.proj_vars import PatchingVars
from keywords import host_helper
from keywords import html_helper
from keywords import patching_helper
from keywords import system_helper
from utils import local_host
from utils import table_parser, cli
from utils.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG
from utils import lab_info

PATCH_ALARM_ID = '900.001'
PATCH_ALARM_REASON = 'Patching operation in progress'
PATCH_FILE_DIR_LOCAL = 'test-patches'
PATCH_PASSING_DIR_LOCAL = 'passing'
PATCH_FAILING_DIR_LOCAL = 'failing'

patch_dir_in_lab = None


def get_patch_dir_local(all_patches=False):
    directories = [os.path.join(WRSROOT_HOME, PATCH_FILE_DIR_LOCAL, PATCH_PASSING_DIR_LOCAL)]

    if all_patches:
        directories.append(os.path.join(WRSROOT_HOME, PATCH_FILE_DIR_LOCAL, PATCH_FAILING_DIR_LOCAL))

    return directories


def get_patch_files_downloaded(all_patches=False, con_ssh=None, fail_on_not_found=False):
    directories = get_patch_dir_local(all_patches=all_patches)

    files_downloaded = []
    for directory in directories:
        code, output = patching_helper.run_cmd("ls {} 2>/dev/null".format(
                os.path.join(directory, '*.patch'), con_ssh=con_ssh))

        if 0 == code and output.strip():
            files_downloaded += re.split('\s+', output.strip())
        else:
            if fail_on_not_found:
                assert False, 'Failed to list patch directory:{} on the active controller'.format(directory)

    return files_downloaded


def find_existing_patch_files(file_name_keyword, including_patches_apply_to_all=True, con_ssh=None):
    including_failing_patches = True if 'FAILURE' in file_name_keyword else False

    all_files = get_patch_files_downloaded(all_patches=including_failing_patches,
                                           fail_on_not_found=False,
                                           con_ssh=con_ssh)
    if not all_files:
        LOG.warn('No patch files found for: "{}"'.format(file_name_keyword))
        return []

    names = []
    matching_files = []
    if ',' not in file_name_keyword:
        if file_name_keyword.upper() == 'ALL':
            matching_files = list(all_files)
        else:
            name = file_name_keyword.strip().upper()
            names = [name] if name else []
    else:
        names = [n.strip() for n in file_name_keyword.split(',') if n.strip()]

    if not matching_files:
        if including_patches_apply_to_all:
            names += ['ALL']

        for file in all_files:
            base_patch_name = os.path.basename(file).strip().strip('.patch').upper()
            for name in names:
                if name == file or name in base_patch_name or name == file:
                    matching_files.append(file)

    matching_files = list(set(matching_files))

    con_ssh = ControllerClient.get_active_controller()
    build_id = lab_info.get_build_id(con_ssh=con_ssh)
    if not build_id:
        LOG.warn('Failed to get build-id')
    else:
        for file in matching_files:
            if build_id not in file:
                LOG.warn('wrong naming for patch file:{}'.format(file))

    if not matching_files:
        LOG.warn('No patch files download found for: "{}"'.format(file_name_keyword))

    return matching_files


def find_patch_files(type_or_name_keywords, download_first=False, download_if_not_found=True, con_ssh=None):

    if download_first:
        download_patch_files(con_ssh=con_ssh, single_file_ok=True)

    for _ in range(2):
        patch_files = find_existing_patch_files(type_or_name_keywords, con_ssh=con_ssh)

        if len(patch_files) > 0:
            return patch_files

        elif download_first:
            LOG.error('No matching patching files found after attempted to download')
            break

        elif not download_if_not_found:
            LOG.error('No matching patching files found while downloading is disabled')
            return []

        download_patch_files(con_ssh=con_ssh, single_file_ok=True)

    LOG.warn('Cannot find matching patch files and failed to download from Patch Build Server')
    return []


def get_candidate_patches(expected_states=None,
                          patch_type='ALL',
                          upload_if_needed=True,
                          include_patches_apply_to_all=True,
                          con_ssh=None):
    including_all_patches = False
    id_filters = []

    if ',' in patch_type:
        id_filters = [patch_id.strip().upper() for patch_id in patch_type.split(',') if patch_id.strip()]

    elif patch_type.upper() == 'ALL':
        including_all_patches = True
        id_filters += ['ALL']

    else:
        id_filters = [patch_type.strip().upper()] if patch_type.strip() else []

    if not id_filters:
        LOG.warn('No patch type specified, will include all patches')
        including_all_patches = True
        id_filters += ['ALL']

    patch_ids = []
    patches_states = {}
    for _ in range(2):
        _, patches_states = patching_helper.get_patches_states(con_ssh=con_ssh, fail_ok=False)

        all_patches = list(patches_states.keys())
        if 'ALL' in id_filters:
            patch_ids = all_patches

        else:
            patch_ids = []
            for id_filter in id_filters:
                patches_for_filter = [p for p in all_patches if id_filter in p]
                if not patches_for_filter:
                    LOG.warn('No patches for: "{}"'.format(id_filter))
                else:
                    patch_ids += patches_for_filter

        if include_patches_apply_to_all:
            patch_ids += [p for p in all_patches if 'ALL' in p]

        patch_ids = list(set(patch_ids))

        if len(patch_ids) <= 0:
            LOG.info('No patches for type:{}'.format(patch_type))
            if upload_if_needed and 'Available' in expected_states:
                LOG.info('No patches in Available state for type:{}, will download patch files'.format(patch_type))
                _test_upload_patches_from_dir(con_ssh=con_ssh, reuse_local_patches=False)
            else:
                return [], False

    candidate_patches = []
    for patch_id in patch_ids:
        if patch_id in patches_states and patches_states[patch_id]['state'] in expected_states:
            candidate_patches.append(patch_id)

    if len(candidate_patches) <= 0:
        LOG.warn('No patches for type: "{}" in states: "{}"'.format(patch_type, expected_states))

    return candidate_patches, including_all_patches


@fixture()
def check_alarms():
    pass


def is_reboot_required(patch_states):
    for patch in patch_states.keys():
        if patch_states[patch]['rr'] and patch_states[patch]['state'] not in ['Available', 'Applied', 'Removed']:
            return True

    return False


def install_impacted_hosts(patch_ids, cur_states=None, con_ssh=None, remove=False):
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
        else:
            patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)

    if reboot_required and active_controller is not None:
        code, output = host_helper.swact_host(active_controller, fail_ok=False, con_ssh=con_ssh)
        assert 0 == code, 'Failed to swact host: from {}'.format(active_controller)
        # need to wait for some time before the system in stable status after swact
        time.sleep(60)

    if active_controller is not None:
        patching_helper.host_install(active_controller, reboot_required=reboot_required, con_ssh=con_ssh)

    expected_patch_states = ['Applied'] if not remove else ['Removed', 'Available']

    code, _ = patching_helper.wait_patch_states(
        patch_ids, expected_states=expected_patch_states, con_ssh=con_ssh, fail_on_nonexisting=True)

    assert 0 == code, 'Patch failed to reach states:{}'.format(expected_patch_states)

    patching_helper.check_error_states(
        con_ssh=con_ssh, no_checking=False, pre_states=pre_states, pre_trace_backs=pre_trace_backs)


def remove_patches(patch_ids, con_ssh=None):
    """ Remove the specified patch or all patches

    Args:
        patch_ids: ID of the patch to remove. Use value of 'ALL' to remove all patches
        con_ssh:

    Returns:

    """

    patches = ' '.join(patch_ids)
    LOG.info('OK, will remove patches:{}'.format(patches))

    LOG.tc_step('Remove the patches:{}'.format(patches))
    patch_ids_removed = patching_helper.remove_patches(patches=patches, con_ssh=con_ssh)

    LOG.info('OK, removed patches: "{}"'.format(patch_ids_removed))

    LOG.tc_step('Install impacted hosts after removing patch IDs:{}'.format(patch_ids_removed))
    states = patching_helper.get_system_patching_states(con_ssh=con_ssh, fail_ok=False)

    install_impacted_hosts(patch_ids_removed, cur_states=states, con_ssh=con_ssh, remove=True)

    LOG.info('OK, successfully removed patches and installed impacted hosts for patch: "{}"'.format(patch_ids))

    return patch_ids_removed


def connect_to_build_server(server=None, username='', password='', prompt=''):
    public_ssh_key = local_host.get_ssh_key()
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
    ssh_to_server.deploy_ssh_key(public_ssh_key)

    LOG.info('ssh connection to server:{} established: {}'.format(server, ssh_to_server))
    return ssh_to_server


def find_patches_on_server(patch_dir, ssh_to_server, single_file_ok=False, build_server=None):
    patch_dir_or_file = patch_dir
    patch_base_dir = PatchingVars.get_patching_var('def_patch_build_base_dir')

    # if an absolute path is specified, we do not need to guess the location of patch file(s),
    # otherwise, we need to deduce where they are based on the build information
    if patch_dir is None:
        patch_dir_or_file = os.path.join(patch_base_dir, lab_info.get_build_id())

    elif not os.path.abspath(patch_dir):
        patch_dir_or_file = os.path.join(patch_base_dir, patch_dir)

    else:
        pass

    rt_code, output = ssh_to_server.exec_cmd(
        'ls -ld {} 2>/dev/null'.format(os.path.join(patch_dir_or_file, '*.patch')),
        fail_ok=True)

    if 0 == rt_code and output:
        patch_dir_or_file = os.path.join(patch_dir_or_file, '*.patch')

    else:
        err_msg = 'No patch files ready in directory :{} on the Patch Build server {}:\n{}'.format(
            patch_dir_or_file, build_server, output)
        LOG.warn(err_msg)

        LOG.warn('Check if {} is a patch file'.format(patch_dir_or_file))
        assert single_file_ok, err_msg

        rt_code = ssh_to_server.exec_cmd('test -f {}'.format(patch_dir_or_file), fail_ok=True)[0]
        assert 0 == rt_code, err_msg

    LOG.debug('Will use patch from {}:{}'.format(build_server, patch_dir_or_file))

    return patch_dir_or_file


def download_patch_files(con_ssh=None, single_file_ok=False):
    """Download the patches from specified server:path and store them on to the lab under test

        e.g. patch build server/path:
        yow-cgts4-lx.wrs.com:/localdisk/loadbuild/jenkins/CGCS_4.0_Test_Patch_Build/latest_build
        yow-cgts4-lx.wrs.com:/localdisk/loadbuild/jenkins/CGCS_4.0_Test_Patch_Build/2016-12-07_16-48-53

        or for 17.07
        yow-cgts4-lx.wrs.com:/localdisk/loadbuild/jenkins/CGCS_5.0_Test_Patch_Build/2017-07-08_22-07-06

    Args:
        con_ssh:
        single_file_ok: Flag indicating if single file is accepted. By default, directory is expected.

    Returns: the path on the active controller where the downloaded patch files saved

    Notes:
        To save time for downloading patch files from remote patch build server, the files are download once only in a
        test session and reused.

    US99792 Update patching to use matching test patch for specific load by default
    """

    global patch_dir_in_lab
    if patch_dir_in_lab:
        return patch_dir_in_lab

    patch_build_server = PatchingVars.get_patching_var('patch_build_server')
    patch_dir = PatchingVars.get_patching_var('patch_dir')

    ssh_to_server = connect_to_build_server(server=patch_build_server)

    patch_dir_or_files = find_patches_on_server(patch_dir,
                                                ssh_to_server,
                                                single_file_ok=single_file_ok,
                                                build_server=patch_build_server)

    dest_path = os.path.join(WRSROOT_HOME, 'patch-files-' + datetime.datetime.utcnow().isoformat())
    passing_patch_dir = os.path.join(dest_path, PATCH_PASSING_DIR_LOCAL)
    failing_patch_dir = os.path.join(dest_path, PATCH_FAILING_DIR_LOCAL)

    rt_code, output = patching_helper.run_cmd(
        'mkdir -p {} {}'.format(passing_patch_dir, failing_patch_dir), con_ssh=con_ssh)
    assert 0 == rt_code, 'Failed to create patch dir:{} on the active-controller'.format(dest_path)

    LOG.info('Downloading patch files to lab:{} from:{}{}'.format(dest_path, patch_build_server, patch_dir_or_files))

    ssh_to_server.rsync(patch_dir_or_files, html_helper.get_ip_addr(), passing_patch_dir,
                        dest_user=HostLinuxCreds.USER, dest_password=HostLinuxCreds.PASSWORD, timeout=1200)

    LOG.info('OK, patch files were downloaded to: {}:{}, from: {} on server: {}'.format(
        html_helper.get_ip_addr(), passing_patch_dir, patch_dir_or_files, patch_build_server))

    LOG.info('Creating local patch directory:{}'.format(PATCH_FILE_DIR_LOCAL))

    rt_code, output = patching_helper.run_cmd('cd {}; cd ..; rm -rf {}; ln -s {} {}; echo'.format(
        dest_path, PATCH_FILE_DIR_LOCAL, dest_path, PATCH_FILE_DIR_LOCAL),
        con_ssh=con_ssh)

    LOG.info('Created local patch directory:{}'.format(PATCH_FILE_DIR_LOCAL))

    assert 0 == rt_code, 'Failed to create symbolic link: {} to {} on the active-controller'.format(
        PATCH_FILE_DIR_LOCAL, dest_path)

    # todo, skip failure patches for now
    patching_helper.run_cmd(
        'mv -f {}/*FAILURE*.patch {} &> /dev/null'.format(passing_patch_dir, failing_patch_dir), con_ssh=con_ssh)

    rt_code, output = patching_helper.run_cmd('ls {}/*.patch 2> /dev/null'.format(passing_patch_dir), con_ssh=con_ssh)
    assert 0 == rt_code, 'No patch files to test'.format(rt_code, output)
    if not output.strip():
        skip('No patch files to test'.format(rt_code, output))

    patch_dir_in_lab = dest_path

    LOG.info('Successfully downloaded patch files to: {}, from: {}:{}'.format(
        patch_dir_in_lab, patch_build_server, patch_dir))

    return passing_patch_dir


@fixture(scope='module', autouse=True)
def check_if_ready_for_patching():
    assert system_helper.are_hosts_unlocked(), \
        'Not all hosts are unlocked, skip patch testing'

    alarm_table = table_parser.table(cli.system('alarm-list'))
    alarm_severity_list = table_parser.get_column(alarm_table, 'Severity')
    assert 'major' or 'critical' not in alarm_severity_list, \
        'There are active alarms:{}, skip patch testing'


def _test_upload_patches_from_dir(patch_dir=None, con_ssh=None, reuse_local_patches=True):
    """Test upload patch files from the specified directory on the specified remote server

    Args:
        con_ssh:
    Returns:

    US99792 Update patching to use matching test patch for specific load by default
    """

    LOG.tc_step('Check if to use local patch files and they exist')
    if reuse_local_patches:
        LOG.info('')
        patch_dir = download_patch_files(con_ssh=con_ssh, single_file_ok=True)
        LOG.info('-Patch files are downloaded to directory:{} on the active controller'.format(patch_dir))

    LOG.tc_step('Upload the directory{}'.format(patch_dir))
    patch_ids = patching_helper.upload_patch_dir(patch_dir=patch_dir, con_ssh=con_ssh)[0]
    LOG.info('-Patches are uploaded to system:{}'.format(patch_ids))

    return patch_ids


def _test_apply_patches(patch_ids=None, con_ssh=None, apply_all=True, fail_if_patched=True):
    apply_all = apply_all or patch_ids is None

    msg = 'Apply ' + 'all' if apply_all else ''
    msg += ' patches'
    msg += '' if apply_all else ' :{}'.format(patch_ids)
    LOG.tc_step(msg)

    applied_patches = patching_helper.apply_patches(
        patch_ids=patch_ids, apply_all=apply_all, fail_if_patched=fail_if_patched, con_ssh=con_ssh)

    LOG.info('OK, patches are applied:{}'.format(applied_patches))
    return applied_patches


def _test_install_impacted_hosts(applied_patches, con_ssh=None):
    LOG.tc_step('Get patching states of the system')
    states = patching_helper.get_system_patching_states(con_ssh=con_ssh, fail_ok=False)

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
    LOG.tc_step('Find if patches in Partial "Partial-Apply" or "Partial-Remove" states')
    partial_applied_patches = patching_helper.get_partial_applied(con_ssh=con_ssh)
    partial_applied_patches += patching_helper.get_partial_removed(con_ssh=con_ssh)

    LOG.info('OK, patches in "Partial-Apply/Remove" states: "{}"'.format(partial_applied_patches))

    if not partial_applied_patches:
        LOG.warn('No patches in "Partial-Apply" nor "Partial-Remove" states, '
                 'continue to check if any host needs to install')

    _test_install_impacted_hosts(partial_applied_patches, con_ssh=con_ssh)


@mark.usefixtures('check_alarms')
@mark.parametrize('patch_type', [
    mark.p1(('all')),
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
])
def test_apply_patches(patch_type, con_ssh=None):
    """Apply the specified type of patches

    Args:

        patch_type:     type of patches to apply
            all         - all patches
            compute     - compute-only patches
            controller  - controller-only patches
            storage     - storage-only patches
            nova        - nova patches

        con_ssh:

    Returns:

    Steps:
        1   Upload the patch files into the patching system on the lab
            - download patch files first from the specified directory on the specified server.
            The directory and server are specified using py.test command line options.

        2   Apply all the patches uploaded
    """

    expected_states = ['Available', 'Partial-Remove']

    LOG.tc_step('Get patches to apply for: "{}" (in status: "{}")'.format(patch_type, expected_states))

    patches_to_apply, apply_all = get_candidate_patches(
        expected_states=expected_states, patch_type=patch_type, con_ssh=con_ssh)

    if not patches_to_apply:
        skip('No patches ready to apply for type: "{}"'.format(patch_type))
        return

    LOG.info('OK, found patches to apply:{}, (apply all?: {})'.format(patches_to_apply, apply_all))

    LOG.tc_step('Applying patches:{}'.format(patches_to_apply))
    _test_apply_patches(patch_ids=patches_to_apply, apply_all=apply_all, fail_if_patched=True, con_ssh=con_ssh)

    LOG.info('OK, successfully applied {} type patches:{}'.format(patch_type, patches_to_apply))


@mark.parametrize('patch_types', [
    mark.p1(('all')),
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
])
def test_upload_patch_files(patch_types, download_if_not_found=True, con_ssh=None):
    """Upload the patch files into the patching system on the lab.

    Args:
        download_if_not_found:  whether to download patch files if they are not the active controller
        patch_types:   name (or keyword) of the patch files to upload, which .
                            'all' means all patch files in the default directory
        con_ssh:

    Returns:

    Steps:
        1   if the file is not accessible on the active controller,
            download patch files first from the specified directory on the specified server.
            The directory and server are specified using py.test command line options.

        2   upload the patches into the patching system of the lab

    """
    LOG.tc_step('Find the patch files, download from build server if not')

    patch_files = find_patch_files(patch_types, download_if_not_found=download_if_not_found, con_ssh=con_ssh)
    if not patch_files:
        skip('Cannot access patch files:{} and failed to download from {}'.format(
            patch_types, PatchingVars.get_patching_var('patch_build_server')
        ))

    LOG.info('OK, patch files existing (or downloaded)')

    LOG.tc_step('Upload the patch files')
    patching_helper.upload_patch_files(files=patch_files, con_ssh=con_ssh)

    LOG.info('Successfully uploaded patch files:{}'.format(patch_files))


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


@mark.parametrize('patch_type', [
    mark.p1(('all')),
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
])
def test_remove_patches(patch_type, con_ssh=None):
    """Remove all patches currently applied in the system

    Args:
        patch_type:     type of patches to apply
            all         - all patches
            compute     - compute-only patches
            controller  - controller-only patches
            storage     - storage-only patches
            nova        - nova patches

        con_ssh: SSH connection to the active controller

    Returns:

    Steps:
        1   Remove all applied patches in Applied or Partial-Applied states
        2   Do host-install on all impacted hosts in the order: compute, storage, standby-controller
            and active-controller

    """
    LOG.tc_step('Get patches ready to remove for type:{}'.format(patch_type))

    expected_states = ('Applied', 'Partial-Apply')
    to_remove_list, _ = get_candidate_patches(
        expected_states=expected_states, patch_type=patch_type, con_ssh=con_ssh)

    if not to_remove_list:
        skip('No patches ready to remove')
        return

    LOG.info('OK, found patches ready to remove: {} for type: {}'.format(to_remove_list, patch_type))

    LOG.tc_step('Removing patches:{}'.format(to_remove_list))

    actual_removed = remove_patches(to_remove_list, con_ssh=con_ssh)

    LOG.tc_step('Successfully removed patches:{}'.format(actual_removed))


@mark.parametrize('patch_type', [
    mark.p1('all'),
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
])
def test_delete_patches(patch_type, con_ssh=None):
    """Delete patch(es). Note the patches need to be in Available status before being deleted

    Args:
        patch_type:  ID or type which covered the patches to delete.
                    'all' - delete all patches in 'available' status
        con_ssh:

    Returns:

    """
    LOG.tc_step('Get all patches in system ready to delete')

    expected_states = 'Available'
    to_delete_list, _ = get_candidate_patches(
        expected_states=expected_states, patch_type=patch_type, upload_if_needed=False, con_ssh=con_ssh)

    if to_delete_list and len(to_delete_list) > 0:
        LOG.info('Will delete all these patches:{} for type: {}'.format(to_delete_list, patch_type))

        patching_helper.delete_patches(to_delete_list)
        LOG.info('OK, successfully deleted all patches:{}'.format(to_delete_list))

        assert patching_helper.check_if_patches_exisit(
            patch_ids=to_delete_list, expecting_exist=False, con_ssh=con_ssh)

        LOG.info('OK, patches are confirmed deleted')

    else:
        skip('No patches in states: "{}" can be deleted for type: "{}"'.format(expected_states, patch_type))


def get_host_states(output):
    # header = re.compile('\s* Hostname\s* IP Address\s* Patch Current\s* Reboot Required\s* Release\s* State\s*')
    pattern = re.compile('([^\s]+)\s* ([^\s]+)\s* ([^\s]+)\s* (Yes|No)\s* ([^\s]+)\s* ([^\s]+)\s*')
    host_states = []
    for line in output.splitlines():
        found = pattern.match(line)
        if found and len(found.groups()) == 6:
            host_states.append((found.group(1), found.group(3)))

    assert len(host_states) > 0, 'Failed to get host patching states, raw output{}'.format(output)

    return host_states


def get_patch_states(output):
    pattern = re.compile('([^\s]+)\s* (Y|N)\s* ([^\s]+)\s* ([^\s]+)\s*')
    patch_states = []
    for line in output.splitlines():
        found = pattern.match(line)
        if found and len(found.groups()) == 4:
            patch_states.append((found.group(1), found.group(4)))

    assert len(patch_states) > 0, 'Failed to get patch states, raw output{}'.format(output)

    return patch_states


def wait_hosts_in_stable_states(hosts, con_ssh=None):
    expected_state = {'patch-current': True,
                      'rr': False,
                      'state': 'idle'}

    for host in hosts:
        wait_host_in_stable_states(host, expected_state, con_ssh=con_ssh)


def wait_host_in_stable_states(host, expected_state, con_ssh=None):
    LOG.info('Wait host: {} stabilized into states: {}'.format(host, expected_state))
    code, state = patching_helper.wait_host_states(host, expected_states=expected_state, con_ssh=con_ssh)
    assert 0 == code, \
        'Host:{} failed to reach states, expected={}, actual={}'.format(host, expected_state, state)


@mark.parametrize('operation', [
     'apply',
     'remove'
])
def test_patch_notapplicable(operation, con_ssh=None):

    """Verify the patching behavior during applying (removing) not-applicable patch(es)

        Because there is no easy way to know which patch(es) is(are) not-applicable for each releases, we choose
            storage-only patches, which are for sure not-applicable for non-storage lab.

        Due to sw-query and sw-patch query-host do NOT run quickly enough to catch the Partial-Apply, Partial-Remove
            or Pending states of patches and host, this TC will randomly failed to verify the state.
            In case it fails, check the log file for further verification.

    Args:
        operation:
            apply - will test applying the patches
            remove - will test removing the patches

        con_ssh:

    Returns:

    User Stories:
        US100411 US93673 US94532    not in XStudio
    """

    LOG.tc_step('Check if the lab is a NON-storage lab, because only patches known not applicable '
                'are storage-only patches')
    if len(system_helper.get_storage_nodes(con_ssh=con_ssh)) > 0:
        skip('current patches will impact at least one type of host in a storage-lab')
        return

    patch_ops = {
        'apply': {
            'op': 'apply', 'expected_state': 'Partial-Apply', 'initial_state': 'Available', 'final_state': 'Applied'
        },
        'remove': {
            'op': 'remove', 'expected_state': 'Partial-Remove', 'initial_state': 'Applied', 'final_state': 'Available'
        }
    }

    LOG.info('The lab is NON-storage lab and can be tested with storage-only patches')

    LOG.tc_step('Check if there is Storage-only patches in "Available" states')
    candidate_patches = patching_helper.get_all_patch_ids(
        con_ssh=con_ssh, expected_states=[patch_ops[operation]['initial_state']])

    if len(candidate_patches) <= 0:
        skip('no patches in "{}" states'.format(patch_ops[operation]['initial_state']))

    storage_patches = [patch_id for patch_id in candidate_patches if 'STORAGE' in patch_id.upper()]
    patch_ids = ' '.join(storage_patches)

    LOG.tc_step('{} the Storage-only patches and check the states of both the patches and hosts'.format(operation))
    cmd = 'date; sudo sw-patch {} {} && sudo sw-patch query && sudo sw-patch query-hosts'.format(
        patch_ops[operation]['op'], patch_ids)

    _, output = patching_helper.run_sudo_cmd(cmd, fail_ok=False)
    LOG.debug('output={}'.format(output))

    LOG.info('OK, {} storage-only patches'.format(patch_ops[operation]['op']))

    host_states = get_host_states(output)
    patch_states = get_patch_states(output)

    expected_host_state = ['Pending']
    LOG.tc_step('Verify the hosts are in {} state'.format(expected_host_state))

    for host, state in host_states:
        assert state in expected_host_state, \
            'Host "{}" is NOT in "{}" as expected, but actually in "{}" state'.format(
                host, expected_host_state, state)

        LOG.info('OK, Host "{}" is in "{}" as expected'.format(host, expected_host_state))

    expected_patch_state = patch_ops[operation]['expected_state']
    LOG.tc_step('Verify the patches are in {} state'.format(expected_patch_state))
    for patch, state in patch_states:
        if patch not in patch_ids:
            continue
        msg = 'Patch "{}" is NOT in "{}" as expected, but actually in "{}" state'.format(
                patch, expected_patch_state, state)

        assert state in expected_patch_state, msg
        LOG.info('OK, Patch "{}" is in "{}" as expected'.format(patch, expected_patch_state))

    LOG.tc_step('Verify the hosts reach stable states finally')
    hosts = [host for host, _ in host_states]
    wait_hosts_in_stable_states(hosts, con_ssh=con_ssh)

    LOG.tc_step('Verify the patches reach state {} finally'.format(patch_ops[operation]['final_state']))

    patches = [patch for patch, _ in patch_states]
    patching_helper.wait_for_patch_states(patches, expected=[patch_ops[operation]['final_state']])
    LOG.info('Successfully patched the system with NON-Applicable patches ')


def get_large_available_patch(con_ssh=None):
    available_patches = patching_helper.get_available_patches(con_ssh=con_ssh)
    if len(available_patches) > 0:
        large_patches = [patch for patch in available_patches if 'LARGE' in patch]
        if len(large_patches) > 0:
            return large_patches[0]

    return None


def select_host(con_ssh):
    all_hosts = patching_helper.get_hosts_in_idle(con_ssh=con_ssh)

    if len(all_hosts) > 0:

        active_controller = system_helper.get_active_standby_controllers(con_ssh=con_ssh)

        if len(all_hosts) > 1:
            return active_controller, random.choice([h for h in all_hosts if h != active_controller])
        elif len(all_hosts) == 1:
            return active_controller, all_hosts[0]

    return None, None


def test_reboot_during_patching(con_ssh):
    """
    Verify the expected behavior for state transfer when rebooting a host at the time of the patching operation.
        - host should go to "Pending" state
        - host should stay there until the node recovers and replies
        - host should change to state:? after recovers

    In order to avoid timing issue, will use LARGE PATCH

    Args:
        con_ssh:

    Returns:

    """

    LOG.tc_step('Check if LARGE PATH existing and in "Available" state')
    large_patch = get_large_available_patch(con_ssh=con_ssh)

    if not large_patch:
        skip('no LARGE patch in "Available" status')
        return

    LOG.info('found large patch {} in "Available" status')

    LOG.tc_step('Chose a host in Patch Current states')
    active_controller, target_host = select_host(con_ssh)

    if not active_controller or not target_host:
        skip('no HOST in idle state to patch')
        return

    LOG.info('Select to test host: {}'.format(target_host))
    if target_host == active_controller:
        LOG.info('will test on the active controller, swact first')
        host_helper.swact_host(active_controller)
        time.sleep(60)

    LOG.tc_step('Apply the large-path:{} and reboot the host:{}'.format(large_patch, target_host))
    patching_helper.apply_patches(con_ssh=con_ssh, patch_ids=[large_patch], apply_all=False)
