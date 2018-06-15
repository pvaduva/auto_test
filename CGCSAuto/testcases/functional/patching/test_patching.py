import datetime
import os
import re

from pytest import fixture, skip, mark

from consts.auth import HostLinuxCreds
from consts.filepaths import WRSROOT_HOME
from consts.proj_vars import PatchingVars
from keywords import host_helper, patching_helper, system_helper, common, html_helper
from utils import lab_info
from utils import local_host
from utils import table_parser, cli
from utils.clients.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG

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
        code, output = patching_helper.run_cmd("\ls {} 2>/dev/null".format(
                os.path.join(directory, '*.patch'), con_ssh=con_ssh))

        if 0 == code and output.strip():
            files_downloaded += re.split('\s+', output.strip())
        else:
            if fail_on_not_found:
                assert False, 'Failed to list patch directory:{} on the active controller'.format(directory)

    return files_downloaded


def find_existing_patch_files(file_name_keyword, including_patches_apply_to_all=False, con_ssh=None):

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
                          include_patches_apply_to_all=False,
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
            extra_filtering = ''

            if any('RR' in id_filter for id_filter in id_filters):
                extra_filtering = 'RR'

            elif any('INSVC' in id_filter for id_filter in id_filters):
                extra_filtering = 'INSVC'

            if extra_filtering:
                patch_ids += [p for p in all_patches if ('ALL' in p and extra_filtering in p)]
            else:
                patch_ids += [p for p in all_patches if 'ALL' in p]

        patch_ids = list(set(patch_ids))

        if len(patch_ids) <= 0:
            LOG.info('No patches for type:{}'.format(patch_type))
            if upload_if_needed and 'Available' in expected_states:
                LOG.info('No patches in Available state for type:{}, will download patch files'.format(patch_type))
                _upload_patches_from_dir(con_ssh=con_ssh, reuse_local_patches=False)
            else:
                return [], False

    candidate_patches = []
    for patch_id in patch_ids:
        if patch_id in patches_states and patches_states[patch_id]['state'] in expected_states:
            candidate_patches.append(patch_id)

    if len(candidate_patches) <= 0:
        LOG.warn('No patches for type: "{}" in states: "{}"\npatch_ids:"{}"'.format(
            patch_type, expected_states, patch_ids))

    return candidate_patches, including_all_patches


@fixture()
def check_alarms():
    pass


def is_reboot_required(patch_states):
    for patch in patch_states.keys():
        if patch_states[patch]['rr'] and patch_states[patch]['state'] not in ['Available', 'Applied', 'Removed']:
            return True

    return False


def install_impacted_hosts(patch_ids, current_states=None, con_ssh=None, remove=False):
    patch_states = current_states['patch_states']
    host_states = current_states['host_states']
    reboot_required = is_reboot_required(patch_states)

    pre_states, pre_trace_backs = patching_helper.check_error_states(con_ssh=con_ssh, no_checking=True)

    computes = []
    storages = []
    controllers = []
    for host in host_states.keys():
        host = host.strip()
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

    if not controllers and not storages and not computes:
        LOG.info('No hosts to install')
        return

    for host in computes:
        patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)

    for host in storages:
        patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)

    while len(controllers) > 1:
        host = controllers.pop()

        if not host_helper.is_active_controller(host, con_ssh=con_ssh):
            patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)
        else:
            controllers.append(host)

    if controllers:
        host = controllers.pop()

        if not host_helper.is_active_controller(host, con_ssh=con_ssh):
            LOG.error('The only controller is not active controller?!!, host:{}'.format(host))

        if not system_helper.is_simplex():
            host_helper.swact_host(host)

        patching_helper.host_install(host, reboot_required=reboot_required, con_ssh=con_ssh)
        
    if patch_ids:

        expected_patch_states = ['Applied'] if not remove else ['Removed', 'Available']

        code, _ = patching_helper.wait_patch_states(
            patch_ids, expected_states=expected_patch_states, con_ssh=con_ssh, fail_on_not_found=True)

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

    if isinstance(patch_ids, str):
        patch_ids = [patch_ids]
    patches_to_remove = list(patch_ids)

    pre_patches_states = patching_helper.get_patches_states()[1]
    for patch_id in patch_ids:
        if pre_patches_states[patch_id]['state'] == 'Available':
            patches_to_remove.remove(patch_id)

    patches = ' '.join(patches_to_remove)
    LOG.info('OK, will remove patches:{}'.format(patches))

    LOG.info('Remove the patches:{}'.format(patches))
    patch_ids_removed = patching_helper.remove_patches(patch_ids=patches, con_ssh=con_ssh)

    LOG.info('OK, removed patches: "{}"'.format(patch_ids_removed))

    LOG.info('Install impacted hosts after removing patch IDs:{}'.format(patch_ids_removed))
    states = patching_helper.get_system_patching_states(con_ssh=con_ssh, fail_ok=False)

    install_impacted_hosts(patch_ids_removed, current_states=states, con_ssh=con_ssh, remove=True)

    LOG.info('OK, successfully removed patches and installed impacted hosts for patch: "{}"'.format(patch_ids))

    return patch_ids_removed

#
# def connect_to_build_server(server=None, username='', password='', prompt=''):
#     public_ssh_key = local_host.get_ssh_key()
#     server = server or PatchingVars.get_patching_var('build_server')
#     LOG.info('patch_server={}'.format(server))
#
#     username = username or PatchingVars.get_patching_var('username')
#     password = password or PatchingVars.get_patching_var('password')
#
#     LOG.info('username={}, password={}'.format(username, password))
#
#     prompt = prompt or r'.*yow\-cgts[3-4]\-lx.*~\]\$'
#     LOG.info('prompt={}'.format(prompt))
#
#     ssh_to_server = SSHClient(server, user=username, password=password, initial_prompt='.*\$ ')
#     ssh_to_server.connect()
#     ssh_to_server.exec_cmd("bash")
#     ssh_to_server.set_prompt(prompt)
#     ssh_to_server.deploy_ssh_key(public_ssh_key)
#
#     LOG.info('ssh connection to server:{} established: {}'.format(server, ssh_to_server))
#     return ssh_to_server


def find_patches_on_server(patch_dir, ssh_to_server, single_file_ok=False, build_server=None):
    patch_dir_or_file = patch_dir
    patch_base_dir = PatchingVars.get_patching_var('patch_base_dir')

    # if an absolute path is specified, we do not need to guess the location of patch file(s),
    # otherwise, we need to deduce where they are based on the build information
    build_id = lab_info.get_build_id()

    if patch_dir is None:
        patch_dir_or_file = os.path.join(patch_base_dir, build_id)

    elif not os.path.isabs(patch_dir):
        patch_dir_or_file = os.path.join(patch_base_dir, patch_dir)

    else:
        if patch_base_dir:
            LOG.info('patch-dir is an absolute path, while patch-base-dir is also provided'
                     '\npatch-dir:{}\npatch-base-dir:{}'.format(patch_dir, patch_base_dir))
            LOG.info('ignore the patch_base_dir:{}'.format(patch_base_dir))

    if patching_helper.is_dir(patch_dir_or_file, ssh_to_server):

        rt_code, output = ssh_to_server.exec_cmd(
            'ls -ld {} 2>/dev/null'.format(os.path.join(patch_dir_or_file, '*.patch')), fail_ok=True)

        if 0 == rt_code and output:
            patch_dir_or_file = os.path.join(patch_dir_or_file, '*.patch')

    else:
        err_msg = 'Not a directory:{}'.format(patch_dir_or_file)
        LOG.warn(err_msg)

        LOG.warn('Check if {} is a patch file'.format(patch_dir_or_file))
        assert single_file_ok, err_msg + ', but not single patch file is not allowed'

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
    dest_path = os.path.join(WRSROOT_HOME, 'patch-files-' + datetime.datetime.utcnow().isoformat())
    passing_patch_dir = os.path.join(dest_path, PATCH_PASSING_DIR_LOCAL)
    failing_patch_dir = os.path.join(dest_path, PATCH_FAILING_DIR_LOCAL)

    rt_code, output = patching_helper.run_cmd(
            'mkdir -p {} {}'.format(passing_patch_dir, failing_patch_dir), con_ssh=con_ssh)
    assert 0 == rt_code, 'Failed to create patch dir:{} on the active-controller'.format(dest_path)

    with host_helper.ssh_to_build_server(patch_build_server) as ssh_to_server:
        # ssh_to_server = connect_to_build_server(server=patch_build_server)
        patch_dir_or_files = find_patches_on_server(patch_dir,
                                                    ssh_to_server,
                                                    single_file_ok=single_file_ok,
                                                    build_server=patch_build_server)

        LOG.info('Downloading patch files to lab:{} from:{}:{}'.format(dest_path, patch_build_server,
                                                                       patch_dir_or_files))
        ssh_to_server.rsync(patch_dir_or_files, html_helper.get_ip_addr(), passing_patch_dir, timeout=1200,
                            dest_user=HostLinuxCreds.get_user(), dest_password=HostLinuxCreds.get_password())

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

    rt_code, output = patching_helper.run_cmd('\ls {}/*.patch 2> /dev/null'.format(passing_patch_dir), con_ssh=con_ssh)
    assert 0 == rt_code, 'No patch files to test'.format(rt_code, output)
    if not output.strip():
        skip('No patch files to test'.format(rt_code, output))

    patch_dir_in_lab = dest_path

    LOG.info('Successfully downloaded patch files to: {}, from: {}:{}'.format(
        patch_dir_in_lab, patch_build_server, patch_dir))

    return passing_patch_dir


@fixture(scope='module', autouse=True)
def check_if_ready_for_patching():
    if not system_helper.are_hosts_unlocked():
        skip('Not all hosts are unlocked, skip patch testing')
        return

    alarm_table = table_parser.table(cli.system('alarm-list'))
    alarm_severity_list = table_parser.get_column(alarm_table, 'Severity')
    assert 'major' or 'critical' not in alarm_severity_list, \
        'There are active alarms:{}, skip patch testing'


def _upload_patches_from_dir(patch_dir=None, con_ssh=None, reuse_local_patches=True):
    """Test upload patch files from the specified directory on the specified remote server

    Args:
        con_ssh:
    Returns:

    US99792 Update patching to use matching test patch for specific load by default
    """

    LOG.info('Check if to use local patch files and they exist\n')
    if reuse_local_patches:
        patch_dir = download_patch_files(con_ssh=con_ssh, single_file_ok=True)
        LOG.info('-Patch files are downloaded to directory:{} on the active controller'.format(patch_dir))

    LOG.info('Upload the directory{}'.format(patch_dir))
    patch_ids = patching_helper.upload_patch_dir(patch_dir=patch_dir, con_ssh=con_ssh)[1]

    return patch_ids


def _apply_patches(patch_ids=None, con_ssh=None, apply_all=False, fail_if_patched=True):
    if not patch_ids:
        return []

    apply_all = apply_all or patch_ids is None

    msg = 'Apply '
    msg += 'all' if apply_all else ''
    msg += ' patches'
    msg += '' if apply_all else ' :{}'.format(patch_ids)

    LOG.info(msg)

    applied_patches = patching_helper.apply_patches(
        patch_ids=patch_ids, apply_all=apply_all, fail_if_patched=fail_if_patched, con_ssh=con_ssh)

    LOG.info('Install impacted hosts after applied patch, IDs:{}'.format(patch_ids))
    states = patching_helper.get_system_patching_states(con_ssh=con_ssh, fail_ok=False)

    # install_impacted_hosts(patch_ids, current_states=states, con_ssh=con_ssh, remove=False)

    LOG.info('OK, patches are applied:{}, impacted host installed'.format(applied_patches))
    return applied_patches


def _install_impacted_hosts(applied_patches, con_ssh=None):

    LOG.info('Get the current states of the patches and hosts')
    states = patching_helper.get_system_patching_states(con_ssh=con_ssh, fail_ok=False)

    LOG.info('Check the current states of hosts')
    all_hosts = states['host_states'].keys()
    hosts_need_install = [h for h in all_hosts if not states['host_states'][h]['patch-current']]

    if not hosts_need_install:
        LOG.info('All hosts are "patch-current", no need to install, states:\n"{}"'.format(states))
        if not applied_patches:
            LOG.info('OK, test is done, no patches applied hence no hosts need to be installed')
        else:
            LOG.warn('No patches applied but there are hosts need to install, hosts:\n"{}"'.format(hosts_need_install))
    else:
        if not applied_patches:
            LOG.warn('No patches applied but there are hosts need to install, hosts:\n"{}"'.format(hosts_need_install))

        LOG.info('Install impacted hosts')
        install_impacted_hosts(applied_patches, current_states=states, con_ssh=con_ssh)

        LOG.info('OK, hosts are installed')


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
    LOG.tc_step('Check if any patches are in Partial "Partial-Apply" or "Partial-Remove" states')
    partial_applied_patches = patching_helper.get_partial_applied(con_ssh=con_ssh)
    partial_applied_patches += patching_helper.get_partial_removed(con_ssh=con_ssh)

    if not partial_applied_patches:
        LOG.warn('No patches in "Partial-Apply" nor "Partial-Remove" states, '
                 'continue to check if any host needs to install')
    else:
        LOG.info('OK, found patches in "Partial-Apply/Remove" states: "{}"'.format(partial_applied_patches))

    pre_controller_states = None
    if any('INSVC_NOVA' in patch for patch in partial_applied_patches):
        pre_controller_states = patching_helper.get_active_controller_state(action='APPLY',
                                                                            patch_type='INSVC_NOVA',
                                                                            including_logs=False, con_ssh=con_ssh)
    previous_time = patching_helper.lab_time_now()[0]

    _install_impacted_hosts(partial_applied_patches, con_ssh=con_ssh)

    if pre_controller_states:
        patching_helper.check_active_controller_state(action='APPLY',
                                                      previous_state=pre_controller_states,
                                                      patch_type='INSVC_NOVA',
                                                      start_time=previous_time,
                                                      con_ssh=con_ssh)


@mark.usefixtures('check_alarms')
@mark.parametrize('patch_type', [
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
    mark.p1(('large')),
    mark.p1(('insvc_nova')),
    mark.p1(('insvc_controller')),
    mark.p1(('all')),
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

    User Story:
        US100410 TESTAuto: No Reboot Patching for Nova
    """

    expected_states = ['Available', 'Partial-Remove']

    LOG.tc_step('Get patches to apply for: "{}" (in status: "{}")'.format(patch_type, expected_states))

    patches_to_apply, apply_all = get_candidate_patches(
        expected_states=expected_states, patch_type=patch_type, con_ssh=con_ssh)

    if not patches_to_apply:
        skip('No patches ready to apply for type: "{}"'.format(patch_type))
        return

    LOG.info('OK, found patches to apply:{}{}'.format(patches_to_apply, ' apply all' if apply_all else ''))

    LOG.tc_step('Applying patches:{}'.format(patches_to_apply))
    _apply_patches(patch_ids=patches_to_apply, apply_all=apply_all, fail_if_patched=True, con_ssh=con_ssh)

    LOG.info('OK, successfully applied and installed {} type patches:{}'.format(patch_type, patches_to_apply))


@mark.parametrize('patch_types', [
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
    mark.p1(('large')),
    mark.p1(('insvc_nova')),
    mark.p1(('insvc_controller')),
    mark.p1(('all')),
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

    LOG.info('OK, found patch files (or downloaded): \n{}\n'.format(patch_files))

    LOG.tc_step('Uploading the patch files:\n{}\n'.format(patch_files))
    uploaded_patch_ids = patching_helper.upload_patch_files(files=patch_files, con_ssh=con_ssh)

    if uploaded_patch_ids:
        LOG.info('Successfully uploaded patch files:{}'.format(patch_files))
    else:
        LOG.info('No patch files uploaded for: "{}"'.format(patch_types))


def test_install_patch_dir_file():
    """Test install patches from the specified directory on the specified server.

    Test Steps:
        1   Upload the patch files into the patching system on the lab
            - download patch files first from the specified directory on the specified server.
            The directory and server are specified using py.test command line options.

        2   Apply all the patches uploaded

        3   Do host-install on all the hosts impacted

    """

    patch_ids = _upload_patches_from_dir()

    applied_patches = _apply_patches(patch_ids=patch_ids, apply_all=False, fail_if_patched=True)

    if applied_patches:
        _install_impacted_hosts(applied_patches)


class TestPatches:
    @fixture(scope='class')
    def upload_test_patches(self, request):
        LOG.fixture_step("Upload test patches to system")
        patch_ids = _upload_patches_from_dir()
        if not patch_ids:
            skip("No patches to upload")

        def remove_test_patches():
            LOG.fixture_step("Delete test patches from system")
            remove_patches(patch_ids=patch_ids)
            patching_helper.delete_patches(patch_ids=patch_ids)
        request.addfinalizer(remove_test_patches)

        return patch_ids

    @mark.parametrize('patch', [
        'INSVC_ALLNODES',
        'RR_ALLNODES',
        'other'
    ])
    def test_patching(self, upload_test_patches, patch):
        """Test install test patches from build server.

        Test Steps:
            1   Upload the patch files into the patching system on the lab
                - download patch files first from the specified directory on the specified server.
                The directory and server are specified using py.test command line options.

            2   Apply all the patches uploaded

            3   Do host-install on all the hosts impacted

        """

        all_patches = upload_test_patches
        patch_ids = []

        if patch != 'other':
            for patch_id in all_patches:
                if patch in patch_id:
                    patch_ids.append(patch_id)
        else:
            for patch_id in all_patches:
                if 'INSVC_ALLNODES' not in patch_id and 'RR_ALLNODES' not in patch_id:
                    patch_ids.append(patch_id)
        if not patch_ids:
            skip("Requested patch(es) {} not found.".format(patch))

        LOG.tc_step("Apply patch(es): {}".format(patch_ids))
        applied_patches = _apply_patches(patch_ids=patch_ids, apply_all=False, fail_if_patched=True)
        if applied_patches:
            LOG.tc_step("Install patch(es): {}".format(patch_ids))
            _install_impacted_hosts(applied_patches)

        LOG.tc_step("Remove patch(es): {}".format(patch_ids))
        remove_patches(patch_ids=patch_ids)


@mark.parametrize('patch_type', [
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
    mark.p1(('large')),
    mark.p1(('insvc_nova')),
    mark.p1(('insvc_controller')),
    mark.p1(('all')),
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
    mark.p1(('compute')),
    mark.p1(('controller')),
    mark.p1(('storage')),
    mark.p1(('nova')),
    mark.p1(('large')),
    mark.p1(('insvc_nova')),
    mark.p1(('insvc_controller')),
    mark.p1('all'),
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

