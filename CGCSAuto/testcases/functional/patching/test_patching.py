from pytest import fixture, skip, mark

from consts.proj_vars import ProjVar
from consts.cgcs import PatchState, VMStatus
from utils.tis_log import LOG
from keywords import patching_helper, system_helper, vm_helper, cinder_helper, nova_helper, orchestration_helper

PATCH_ALARM_ID = '900.001'
PATCH_ALARM_REASON = 'Patching operation in progress'


@fixture(scope='function', autouse=True)
def check_alarms():
    affecting_alarms = patching_helper.get_affecting_alarms()
    if affecting_alarms:
        skip('Affecting alarms on system: {}'.format(affecting_alarms))


def is_reboot_required(patch_states):
    for patch in patch_states.keys():
        if patch_states[patch]['rr'] and patch_states[patch]['state'] not in ['Available', 'Applied', 'Removed']:
            return True

    return False


def get_test_patches(state=None):
    test_patch_name = ProjVar.get_var('BUILD_ID') + '_'
    test_patches = patching_helper.get_patches_in_state(expected_states=state)
    test_patches = [p.strip() for p in test_patches if p.startswith(test_patch_name)]
    return test_patches


def remove_test_patches(delete=True, failure_patch=False):
    applied = get_test_patches(state=(PatchState.PARTIAL_APPLY, PatchState.APPLIED))
    if applied:
        LOG.info("Remove applied test patch {}".format(applied))
        patching_helper.remove_patches(patch_ids=applied)

    LOG.info("Install hosts to remove test patch if needed")
    code, installed, failed = patching_helper.install_patches(remove=True, fail_ok=True)

    unavail_patches = get_test_patches(state=(PatchState.PARTIAL_REMOVE, PatchState.PARTIAL_APPLY, PatchState.APPLIED))

    if delete:
        available_patches = get_test_patches(state=PatchState.AVAILABLE)
        if available_patches:
            LOG.info("Delete available test patches: {}".format(available_patches))
            patching_helper.delete_patches(available_patches)

    patching_helper.wait_for_affecting_alarms_gone()

    # Verify patch removal succeeded
    if not failure_patch:
        assert code <= 0, "Patches failed to install after removal: {}".format(failed)

    assert not unavail_patches, "Patches not in available state: {}".format(unavail_patches)


@fixture(scope='module', autouse=True)
def patching_setup():

    LOG.fixture_step("Remove test patches (if any) and check system health")
    orchestration_helper.delete_strategy('patch')
    remove_test_patches()
    code, failed = patching_helper.check_system_health(fail_on_disallowed_failure=False)
    if code > 1:
        skip('Patching cannot be run with failures: {}'.format(failed))

    LOG.fixture_step("Copy test patches from build server to system")
    patch_dir, patches = patching_helper.download_test_patches()

    LOG.fixture_step("Delete existing vms and launch a boot-from-volume vm and a boot-from-image vm")
    vm_helper.delete_vms()
    cinder_helper.delete_volumes()

    for source in ('volume', 'image'):
        vm_id = vm_helper.boot_vm(name='patch_{}'.format(source), source=source, cleanup='module')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    controllers, computes, storages = system_helper.get_hosts_by_personality()
    return patches, controllers, computes, storages


@fixture(scope='function')
def patch_function_check(request):
    available_patches = get_test_patches(state=PatchState.AVAILABLE)
    if available_patches:
        LOG.info("Delete test patches: {}".format(available_patches))
        patching_helper.delete_patches(available_patches)

    LOG.info("Check vms status, delete and create new if in bad state")
    vms = nova_helper.get_vms(name='patch_', strict=False)
    boot_vm = False if len(vms) == 2 else True
    if not boot_vm:
        for vm in vms:
            if nova_helper.get_vm_status(vm) != VMStatus.ACTIVE or not vm_helper.ping_vms_from_natbox(vm, fail_ok=True):
                boot_vm = True
                break
    if boot_vm:
        if vms:
            vm_helper.delete_vms(vms, remove_cleanup='module')
        vms = []
        for source in ('volume', 'image'):
            vms.append(vm_helper.boot_vm(name='patch_{}'.format(source), source=source, cleanup='module')[1])

    def remove_on_teardown():
        for vm_ in vms:
            if nova_helper.get_vm_status(vm_) != VMStatus.ACTIVE:
                LOG.info("Delete inactive vm {} before test patch removal".format(vm_))
                vm_helper.delete_vms(vm_, remove_cleanup='module')

        LOG.fixture_step("Remove and delete test patches if any")
        remove_test_patches()
    request.addfinalizer(remove_on_teardown)

    return vms


def upload_test_patches(search_str, downloaded_patches, failure_patch=False):

    search_str = search_str + '$' if 'A-C' in search_str else search_str
    prefix_build = True if 'A-C' in search_str else False
    patches = patching_helper.parse_test_patches(downloaded_patches, search_str=search_str, failure_patch=failure_patch,
                                                 prefix_build_id=prefix_build)
    if not patches:
        skip("No patches with pattern {} available".format(search_str))

    patch_files = [downloaded_patches[patch] for patch in patches]

    LOG.tc_step("Upload patch file {}".format(patch_files))
    uploaded_ids = patching_helper.upload_patches(patch_files)[1]
    LOG.info("Patch {} uploaded".format(uploaded_ids))

    return uploaded_ids


def check_vms(vms):
    for vm in vms:
        assert nova_helper.get_vm_status(vm) == VMStatus.ACTIVE
        vm_helper.ping_vms_from_natbox(fail_ok=False)


def test_patch_dependency(patching_setup, patch_function_check):
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
    downloaded_patches, controllers, computes, storages = patching_setup
    vms = patch_function_check

    patch_ids = upload_test_patches(downloaded_patches=downloaded_patches, search_str='_[A-C]')
    if len(patch_ids) < 3:
        skip("A, B, and C patch(es) not found.")

    LOG.tc_step("Attempt to apply patch B without dependent A applied, and check it fails")
    code, output = patching_helper.apply_patches(patch_ids[1], fail_ok=True)
    assert 1 == code, "Patch applied without required dependency: {}".format(output)

    LOG.tc_step("Apply patches in the correct dependency order")
    applied_patches = patching_helper.apply_patches(patch_ids)[1]

    LOG.tc_step("Attempt to remove patch A that B,C are depend on, and check it fails")
    code, removed = patching_helper.remove_patches(patch_ids[0], fail_ok=True)
    assert 1 == code, "Patch A removal succeeded while B&C still on system"

    patch_ids.reverse()
    LOG.tc_step("Remove patches in the correct dependency order: {}".format(patch_ids))
    removed_patches = patching_helper.remove_patches(patch_ids)

    assert sorted(applied_patches) == sorted(removed_patches), "Not all applied patches were removed."
    check_vms(vms)


@mark.parametrize('patch_type', [
    'ALLNODES',
    'CONTROLLER',
    'NOVA',
    'COMPUTE',
    'STORAGE',
    'LARGE'
])
def test_patch_host_correlations(patching_setup, patch_function_check, patch_type):
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
    downloaded_patches, controllers, computes, storages = patching_setup
    vms = patch_function_check

    patch_ids = upload_test_patches(downloaded_patches=downloaded_patches, search_str=patch_type)

    for patch_id in patch_ids:
        LOG.tc_step("Apply patch: {}".format(patch_ids))
        patching_helper.apply_patches(patch_ids)

        LOG.tc_step("Remove patch {}".format(patch_id))
        remove_test_patches(delete=False)

    LOG.tc_step("Check vms after apply and remove {} test patches".format(patch_type))
    check_vms(vms)


@mark.parametrize(('patch_type', 'install_type'), [
    ('INSVC_', 'sync'),
    ('RR_', 'async'),
    ('LARGE', 'sync'),
])
def test_patch_process(patching_setup, patch_function_check, patch_type, install_type):
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

    downloaded_patches, controllers, computes, storages = patching_setup
    vms = patch_function_check
    patch_ids = upload_test_patches(downloaded_patches=downloaded_patches, search_str=patch_type)

    LOG.tc_step("Apply patch(es): {}".format(patch_ids))
    patching_helper.apply_patches(patch_ids=patch_ids)

    LOG.tc_step("Install patch(es): {}".format(patch_ids))
    async = True if install_type == 'async' else False
    patching_helper.install_patches(async=async)

    LOG.tc_step("Check vms are in good state after install patches: {}".format(patch_ids))
    check_vms(vms)

    LOG.tc_step("Remove and delete test patches: {}".format(patch_ids))
    remove_test_patches()

    LOG.tc_step("Check vms are in good state after remove patches: {}".format(patch_ids))
    check_vms(vms)
