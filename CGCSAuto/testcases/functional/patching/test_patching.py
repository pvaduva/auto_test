import os
import re
import time
import datetime

from pytest import fixture, skip, mark
# from pytest import mark

from consts.auth import HostLinuxCreds
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
from utils import lab_info

PATCH_ALARM_ID = '900.001'
PATCH_ALARM_REASON = 'Patching operation in progress'

patch_dir_in_lab = None


@fixture()
def check_alarms():
    pass


def is_reboot_required(patch_states):
    for patch in patch_states.keys():
        if patch_states[patch]['rr'] and patch_states[patch]['state'] not in ['Available', 'Applied', 'Removed']:
            return True

    return False


def install_impacted_hosts(patch_ids, cur_states=None, con_ssh=None, remove=False):
    LOG.debug('cur_states:{}, remove?:{}, patch_ids:{}'.format(cur_states, remove, patch_ids))
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

    expected_patch_states = ('Applied',) if not remove else ('Removed', 'Available')

    code, _ = patching_helper.wait_patch_states(
        patch_ids, expected_states=expected_patch_states, con_ssh=con_ssh, fail_on_nonexisting=True)

    assert 0 == code, 'Patch failed to reach states:{}'.format(expected_patch_states)

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

    if len(patch_ids) <= 0:
        skip("No patches can be removed")
        return

    LOG.info('OK, will remove patch IDs:{}'.format(patch_ids))

    patches = ' '.join(patch_ids)
    LOG.info('OK, will remove patches:{}'.format(patches))

    LOG.tc_step('Remove the patches:{}'.format(patches))
    patch_ids_removed = patching_helper.remove_patches(patches=patches, con_ssh=con_ssh)

    LOG.tc_step('Install impacted hosts after removing patch IDs:{}'.format(patch_ids_removed))
    states = patching_helper.get_patching_states(con_ssh=con_ssh, fail_ok=False)
    install_impacted_hosts(patch_ids_removed, cur_states=states, con_ssh=con_ssh, remove=True)

    return patch_ids_removed


def delete_patch(patch_id, con_ssh=None):
    """Delete the specified patch or all patches in Available status

    Args:
        patch_id: ID of the patch to remove. Use value of 'ALL' to remove all patches
        con_ssh:

    Returns:

    """
    LOG.tc_step('Get patch ids to delete')
    states = patching_helper.get_patching_states(con_ssh=con_ssh, fail_ok=False)
    patch_states = states['patch_states']

    expected_states = ['Available']
    if patch_id.upper() in ['ALL']:
        candidates = [pid for pid in patch_states.keys()
                      if patch_states[pid]['state'] in expected_states]
        if len(candidates) <= 0:
            skip('No patch can be deleted because none in {} status'.format(expected_states))
            return
    else:
        if patch_id not in patch_states:
            skip('patch with ID: {} is not in system'.format(patch_id))
            return

        if patch_states[patch_id]['state'] not in expected_states:
            skip('patch with ID:{} in status {} cannot be deleted'.format(patch_id, patch_states[patch_id]['state']))
            return

        candidates = [patch_id]

    patching_helper.delete_patches(candidates)


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
        err_msg = 'No patch files ready in direcotry :{} on the Patch Build server {}:\n{}'.format(
            patch_dir_or_file, build_server, output)
        LOG.warn(err_msg)

        LOG.warn('Check if {} is a patch file'.format(patch_dir_or_file))
        assert single_file_ok, err_msg

        rt_code = ssh_to_server.exec_cmd('test -f {}'.format(patch_dir_or_file), fail_ok=True)[0]
        assert 0 == rt_code, err_msg

    LOG.debug('Will use patch from {}:{}'.format(build_server, patch_dir_or_file))

    return patch_dir_or_file


def get_patches_dir_to_test(con_ssh=None, single_file_ok=False):
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
    rt_code, output = patching_helper.run_cmd('mkdir -p {}'.format(dest_path), con_ssh=con_ssh)
    assert 0 == rt_code, 'Failed to create patch dir:{} on the active-controller'.format(dest_path)

    LOG.info('Downloading patch files to lab:{} from:{}'.format(dest_path, patch_dir_or_files))

    ssh_to_server.rsync(patch_dir_or_files, html_helper.get_ip_addr(), dest_path,
                        dest_user=HostLinuxCreds.USER, dest_password=HostLinuxCreds.PASSWORD, timeout=900)

    LOG.info('OK, patch files were downloaded to: {}:{}, from: {} on server: {}'.format(
        html_helper.get_ip_addr(), dest_path, patch_dir_or_files, patch_build_server))

    # todo, skip failure patches for now
    patching_helper.run_cmd(
        'rm -rf {}/*FAILURE*.patch &> /dev/null'.format(dest_path), con_ssh=con_ssh)

    rt_code, output = patching_helper.run_cmd('ls {}/*.patch 2> /dev/null'.format(dest_path), con_ssh=con_ssh)
    assert 0 == rt_code, 'No patch files to test'.format(rt_code, output)
    if not output:
        skip('No patches to test, skip the reset of the test, supposed to test patch_files:{}'.format(
            patch_dir_or_files))
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

    US99792 Update patching to use matching test patch for specific load by default
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

    # patch_ids = _test_upload_patches_from_dir(con_ssh=con_ssh)

    # applied_patches = _test_apply_patches(patch_ids=patch_ids, apply_all=True, fail_if_patched=True, con_ssh=con_ssh)

    applied_patches = patching_helper.get_partial_applied(con_ssh=con_ssh) \
                      + patching_helper.get_partial_removed(con_ssh=con_ssh)

    _test_install_impacted_hosts(applied_patches, con_ssh=con_ssh)


@mark.usefixtures('check_alarms')
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


def test_delete_patch(con_ssh=None):
    """Delete patch(es). Note the patches need to be in Available status before being deleted

    Args:
        con_ssh:

    Returns:

    """
    delete_patch('all', con_ssh=con_ssh)


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
    LOG.info('Wait host: {} stablized into states: {}'.format(host, expected_state))
    code, state = patching_helper.wait_host_states(host, expected_states=expected_state, con_ssh=con_ssh)
    assert 0 == code, \
        'Host:{} failed to reach states, expected={}, actual={}'.format(host, expected_state, state)


@mark.parametrize('operation', [
     'apply',
     'remove'
])
def test_patch_nonapplicable(operation, con_ssh=None):

    """Verify the patching behavior during applying (removing) not-applicable patch(es)

        Because there is no easy way to know which patch(es) is(are) not-applicable for each releases, we choose
            storage-only patches, which are for sure not-applicable for non-storage lab.

        Due to sw-query and sw-patch query-host do NOT run quickly enough to catch the Partial-Apply, Partial-Remove
            or Pending states of patches and host, this TC will randomly failed to verify the state.
            In case it fails, check the log file for further verification.

    Args:
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
    LOG.info('Scuccessfully patched the system with NON-Applicable patches ')
