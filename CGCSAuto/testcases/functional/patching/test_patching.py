import datetime
import os

from pytest import fixture, skip, mark

from consts.auth import HostLinuxCreds
from consts.filepaths import WRSROOT_HOME
from consts.proj_vars import PatchingVars

from keywords import host_helper, patching_helper, system_helper, html_helper
from utils import lab_info
from utils import table_parser, cli
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG

PATCH_ALARM_ID = '900.001'
PATCH_ALARM_REASON = 'Patching operation in progress'
PATCH_FILE_DIR_LOCAL = 'patch-files'

patch_dir_in_lab = None


@fixture()
def check_alarms():
    pass


def is_reboot_required(patch_states):
    for patch in patch_states.keys():
        if patch_states[patch]['rr'] and patch_states[patch]['state'] not in ['Available', 'Applied', 'Removed']:
            return True

    return False


def install_impacted_hosts(patch_ids, current_states=None, con_ssh=None, remove=False):
    host_states = current_states['host_states']
    pre_states, pre_trace_backs = patching_helper.check_error_states(con_ssh=con_ssh, no_checking=True)

    computes = []
    storages = []
    controllers = []
    for host in host_states.keys():
        host = host.strip()
        if host_states[host]['patch-current'] == 'No':
            personality = patching_helper.get_personality(host, con_ssh=con_ssh)
            if 'storage' in personality:
                storages.append(host)
            elif 'compute' in personality and 'controller' not in personality:
                computes.append(host)
            elif 'controller' in personality:
                controllers.append(host)
            else:
                LOG.warning('Unknown personality:{} of host:{}'.format(personality, host))

    if not controllers and not storages and not computes:
        LOG.info('No hosts to install')
        return

    if computes:
        patching_helper.install_patches_async(computes, con_ssh=con_ssh)

    if storages:
        patching_helper.install_patches(storages[:1], con_ssh=con_ssh)
        if len(storages) > 1:
            patching_helper.install_patches_async(storages[1:], con_ssh=con_ssh)

    if controllers:
        patching_helper.install_patches(controllers, con_ssh=con_ssh)
        
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

    # pre_patches_states = patching_helper.get_patches_states()[1]
    applied_patches = patching_helper.get_patches_in_state(['Applied', 'Partial-Apply'])

    if patch_ids != ["ALL"]:
        for patch_id in patch_ids:
            if patch_id not in applied_patches:
                patches_to_remove.remove(patch_id)
    else:
        patches_to_remove = applied_patches

    if not patches_to_remove:
        LOG.info("No patches to remove. All patches have 'Available' state.")
        return []

    patches = ' '.join(patches_to_remove)

    LOG.info('Removing patches: {}'.format(patches))
    patch_ids_removed = patching_helper.remove_patches(patch_ids=patches, con_ssh=con_ssh)

    LOG.info('Install impacted hosts to uninstall patches: {}'.format(patch_ids_removed))
    states = patching_helper.get_system_patching_states(con_ssh=con_ssh, fail_ok=False)
    install_impacted_hosts(patch_ids_removed, current_states=states, con_ssh=con_ssh, remove=True)

    return patch_ids_removed


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
        LOG.warning(err_msg)

        LOG.warning('Check if {} is a patch file'.format(patch_dir_or_file))
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
    remote_patch_dir = PatchingVars.get_patching_var('patch_dir')
    local_patch_dir = os.path.join(WRSROOT_HOME, PATCH_FILE_DIR_LOCAL)

    rt_code, output = patching_helper.run_cmd('mkdir -p {}'.format(local_patch_dir), con_ssh=con_ssh)
    assert 0 == rt_code, 'Failed to create patch dir:{} on the active-controller'.format(local_patch_dir)

    with host_helper.ssh_to_build_server(patch_build_server) as ssh_to_server:

        patch_dir_or_files = find_patches_on_server(remote_patch_dir,
                                                    ssh_to_server,
                                                    single_file_ok=single_file_ok,
                                                    build_server=patch_build_server)

        LOG.info('Downloading patch files to lab:{} from:{}:{}'.format(local_patch_dir, patch_build_server,
                                                                       patch_dir_or_files))
        ssh_to_server.rsync(patch_dir_or_files, html_helper.get_ip_addr(), local_patch_dir, timeout=1200,
                            dest_user=HostLinuxCreds.get_user(), dest_password=HostLinuxCreds.get_password())

    LOG.info('OK, patch files were downloaded to: {}:{}, from: {} on server: {}'.format(
        html_helper.get_ip_addr(), local_patch_dir, patch_dir_or_files, patch_build_server))

    rt_code, output = patching_helper.run_cmd('\ls {}/*.patch 2> /dev/null'.format(local_patch_dir), con_ssh=con_ssh)
    assert 0 == rt_code, 'No patch files to test'.format(rt_code, output)

    if not output.strip():
        skip('No patch files to test'.format(rt_code, output))

    LOG.info('Successfully downloaded patch files to: {}, from: {}:{}'.format(
        local_patch_dir, patch_build_server, remote_patch_dir))

    return local_patch_dir


@fixture(scope='module', autouse=True)
def check_if_ready_for_patching():
    if not system_helper.are_hosts_unlocked():
        skip('Not all hosts are unlocked, skip patch testing')
        return

    alarm_table = table_parser.table(cli.fm('alarm-list'))
    alarm_severity_list = table_parser.get_column(alarm_table, 'Severity')
    assert 'major' or 'critical' not in alarm_severity_list, \
        'There are active alarms:{}, skip patch testing'


def _apply_patches(patch_ids=None, con_ssh=None, apply_all=False, fail_if_patched=True, fail_ok=False):
    if not patch_ids:
        return []

    apply_all = apply_all or patch_ids is None

    msg = 'Apply '
    msg += 'all' if apply_all else ''
    msg += ' patches'
    msg += '' if apply_all else ' :{}'.format(patch_ids)

    LOG.info(msg)

    applied_patches = patching_helper.apply_patches(
        patch_ids=patch_ids, apply_all=apply_all, fail_if_patched=fail_if_patched, con_ssh=con_ssh, fail_ok=fail_ok)

    return applied_patches


def _install_impacted_hosts(applied_patches, con_ssh=None):

    LOG.info('Get the current states of the patches and hosts')
    states = patching_helper.get_system_patching_states(con_ssh=con_ssh, fail_ok=False)

    LOG.info('Check the current states of hosts')
    all_hosts = states['host_states'].keys()
    hosts_need_install = [h for h in all_hosts if states['host_states'][h]['patch-current'] == 'No']

    if not hosts_need_install:
        LOG.info('All hosts are "patch-current", no need to install, states:\n"{}"'.format(states))
        if not applied_patches:
            LOG.info('OK, test is done, no patches applied hence no hosts need to be installed')
        else:
            LOG.warning('No patches applied but there are hosts need to install, hosts:\n"{}"'.format(hosts_need_install))
    else:
        if not applied_patches:
            LOG.warning('No patches applied but there are hosts need to install, hosts:\n"{}"'.format(hosts_need_install))

        LOG.info('Install impacted hosts')
        install_impacted_hosts(applied_patches, current_states=states, con_ssh=con_ssh)

        LOG.info('OK, hosts are installed')


class TestPatches:
    @fixture(scope='class')
    def upload_test_patches(self, request):
        LOG.fixture_step("Download test patches to system disk")
        patch_dir = download_patch_files(single_file_ok=True)
        patch_ids = patching_helper.get_patch_ids_from_dir(patch_dir)

        if not patch_ids:
            skip("No patches on system")

        def delete_test_patches():
            LOG.fixture_step("Delete test patches from system disk")
            con_ssh = ControllerClient.get_active_controller()
            con_ssh.exec_sudo_cmd("rm -rf {}".format(patch_dir))
        request.addfinalizer(delete_test_patches)

        return patch_dir, patch_ids

    @fixture(scope='function', autouse=True)
    def remove_patches_if_applied(self, upload_test_patches, request):
        def remove():
            LOG.fixture_step("Cleaning up system")
            remove_patches("ALL")
            patches_to_remove = patching_helper.get_all_patch_ids()
            patching_helper.delete_patches(patches_to_remove)
            LOG.info("Patches removed and system is patch current")

        request.addfinalizer(remove)

    def test_patch_dependencies(self, upload_test_patches):
        """
        Test patches that depend on other patches. (C requires B requires A)

        Setup Steps:
            1   Upload the patch files into the patching system on the lab
                - download patch files first from the specified directory on the specified server.
                The directory and server are specified using py.test command line options.

        Test Steps:
            1   Attempt to apply patches B and C. Expected to fail because the required patch A is not applied.
            2   Apply patches in the correct dependency order (First-A, Second-B, Third-C)
            3   Attempt to remove patches A and B. Expected to fail because C is still applied and requires A and B.
            4   Remove patches in the correct dependency order (First-C, Second-B, Third-A)
            5   Verify that the list of all applied patches is the same as all patches removed

        Teardown Steps:
            1   Delete patch files from patching system on the lab
        """
        patch_dir, all_patches = upload_test_patches
        patch_ids = []

        LOG.info("Finding required patches and uploading them to the software system")
        for letter in ['A', 'B', 'C']:
            for patch_id in all_patches:
                if patch_id.endswith('_{}'.format(letter)):
                    patching_helper.upload_patch_file("{}/{}.patch".format(patch_dir, patch_id))
                    patch_ids.append(patch_id)

        if len(patch_ids) < 3:
            skip("A, B, and C patch(es) not found.")

        LOG.tc_step("Attempt to apply patches without patch dependencies applied")
        for index in [1, 2]:
            assert not _apply_patches([patch_ids[index]], fail_ok=True), "Patch applied without required dependency"

        LOG.tc_step("Apply patches in the correct dependency order")
        applied_patches = _apply_patches(patch_ids)

        LOG.tc_step("Attempt to remove patches that are a dependency for other installed patches")
        for index in [0, 1]:
            assert not patching_helper.remove_patches(patch_ids[index], fail_ok=True), "Required patch dependency " \
                                                                                       "removed"

        LOG.tc_step("Remove patches in the correct dependency order")
        removed_patches = patching_helper.remove_patches(' '.join(list(reversed(patch_ids))))

        assert applied_patches == removed_patches, "Not all applied patches were removed."

    @mark.parametrize(('patch', 'affected_hosts'), [
        ('ALLNODES', ['controller', 'compute', 'storage']),
        ('CONTROLLER', ['controller']),
        ('COMPUTE', ['compute']),
        ('STORAGE', ['storage']),
        ('NOVA', ['controller', 'compute', 'storage']),
        ('LARGE', ['controller', 'compute', 'storage'])
    ])
    def test_patch_host_correlations(self, upload_test_patches, patch, affected_hosts):
        """
        Test that compute patches only effect compute nodes, storage patches only effect storage nodes, etc...

        Setup Steps:
            1   Upload the patch files into the patching system on the lab
                - download patch files first from the specified directory on the specified server.
                The directory and server are specified using py.test command line options.

        Test Steps:
            1   Verify all patches are in the available state and all hosts are patch current
            2   Apply specified patch (ALLNODES, COMPUTE, CONTROLLER, etc...)
            3   Verify the host(s) related to the patch are no longer patch current and all other hosts that are not
                related to the patch are still patch current.
            4   Remove patch so it is back into the available state

        Teardown Steps:
            1   Delete patch files from patching system on the lab
        """
        patch_dir, all_patches = upload_test_patches

        patch_ids = []
        for patch_id in all_patches:
            if patch in patch_id and "FAILURE" not in patch_id:
                patching_helper.upload_patch_file("{}/{}.patch".format(patch_dir, patch_id))
                patch_ids.append(patch_id)

        if not patch_ids:
            skip("Requested patch(es) {} not found.".format(patch))

        # In an AIO system all patches except storage effect the controller nodes
        if system_helper.is_small_footprint():
            if 'STORAGE' not in patch:
                affected_hosts = ['controller']

        controllers, computes, storages = system_helper.get_hosts_by_personality()

        for patch_id in patch_ids:
            LOG.tc_step("Verify system patch state is normal")

            LOG.info("Verifying all hosts are patch current")
            _, output = patching_helper.get_hosts_states()
            for key, value in output.items():
                assert value['patch-current'] == 'Yes', "{} is not patch current".format(key)

            LOG.info("Verifying all patches are in Available state")
            _, output = patching_helper.get_patches_states()
            for key, value in output.items():
                assert value['state'] == "Available", "{} patch is not in the Available state".format(patch)

            LOG.tc_step("Apply patch {}".format(patch_id))
            applied_patch = _apply_patches([patch_id])
            assert applied_patch, "Patch was not applied"

            patching_helper.wait_for_hosts_to_check_patch_current()

            LOG.tc_step("Verify the patch only affects the correct host(s)")
            hosts_states = patching_helper.get_hosts_states()[1]
            for controller in controllers:
                LOG.info("Verifying patch-current state on {}".format(controller))
                if 'controller' in affected_hosts:
                    assert hosts_states[controller]['patch-current'] == 'No', \
                        "{} was patch-current. Expected not patch-current.".format(controller)
                else:
                    assert hosts_states[controller]['patch-current'] == 'Yes', \
                        "{} was not patch-current. Expected patch-current".format(controller)

            for compute in computes:
                LOG.info("Verifying patch-current state on {}".format(compute))
                if 'compute' in affected_hosts:
                    assert hosts_states[compute]['patch-current'] == 'No', \
                        "{} was patch-current. Expected not patch-current.".format(compute)
                else:
                    assert hosts_states[compute]['patch-current'] == 'Yes', \
                        "{} was not patch-current. Expected patch-current".format(compute)

            for storage in storages:
                LOG.info("Verifying patch-current state on {}".format(storage))
                if 'storage' in affected_hosts:
                    assert hosts_states[storage]['patch-current'] == 'No', \
                        "{} was patch-current. Expected not patch-current.".format(storage)
                else:
                    assert hosts_states[storage]['patch-current'] == 'Yes', \
                        "{} was not patch-current. Expected patch-current".format(storage)

            LOG.tc_step("Remove patch {}".format(patch_id))
            remove_patches(patch_id)

    @mark.parametrize('patch', [
        'INSVC_',
        'RR_',
        'LARGE'
    ])
    def test_patch_process(self, upload_test_patches, patch):
        """
        Test install test patches from build server.

        Setup Steps:
            1   Upload the patch files into the patching system on the lab
                - download patch files first from the specified directory on the specified server.
                The directory and server are specified using py.test command line options.

        Test Steps:
            1   Apply specified patches
            2   Install patches on required hosts (No reboot required for INSVC patches)
            3   Verify patches are correctly installed (Host(s) are patch current and patches are applied)
            4   Uninstall patches on required hosts (Requires reboot regardless of patch type)
            5   Verify patches are correctly uninstalled (Host(s) are patch current and patches are available)

        Teardown Steps:
            1   Delete patch files from patching system on the lab
        """

        patch_dir, all_patches = upload_test_patches
        patch_ids = []

        for patch_id in all_patches:
            if patch in patch_id and "FAILURE" not in patch_id:
                patching_helper.upload_patch_file("{}/{}.patch".format(patch_dir, patch_id))
                patch_ids.append(patch_id)

        if not patch_ids:
            skip("Requested patch(es) {} not found.".format(patch))

        LOG.tc_step("Apply patch(es): {}".format(patch_ids))
        applied_patches = _apply_patches(patch_ids=patch_ids, apply_all=False, fail_if_patched=True)
        if not applied_patches:
            skip("No patches were applied")

        LOG.tc_step("Install patch(es): {}".format(patch_ids))
        _install_impacted_hosts(applied_patches)

        LOG.tc_step("Remove patch(es): {}".format(patch_ids))
        remove_patches(patch_ids=patch_ids)
