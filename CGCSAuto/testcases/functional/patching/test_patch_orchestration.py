import time

from pytest import mark, skip, fixture

from utils.tis_log import LOG
from consts.proj_vars import ProjVar
from consts.cgcs import PatchState, VMStatus
from testfixtures.recover_hosts import HostsToRecover
from keywords import system_helper, host_helper, patching_helper, orchestration_helper, nova_helper, vm_helper, \
    cinder_helper


@fixture(scope='function', autouse=True)
def check_alarms():
    affecting_alarms = patching_helper.get_affecting_alarms()
    if affecting_alarms:
        skip('Affecting alarms on system: {}'.format(affecting_alarms))


@fixture(scope='module', autouse=True)
def patch_orchestration_setup():
    LOG.fixture_step("Remove test patches (if any) and check system health")
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
    vms = nova_helper.get_vms(name='patch', strict=False)
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
        LOG.info("Check vm status and delete if in bad state")
        for vm_ in vms:
            if nova_helper.get_vm_status(vm_) != VMStatus.ACTIVE:
                vm_helper.delete_vms(vm_, remove_cleanup='module')

        LOG.fixture_step("Remove test patches")
        remove_test_patches()
    request.addfinalizer(remove_on_teardown)

    return vms


def get_test_patches(state=None):
    test_patch_name = ProjVar.get_var('BUILD_ID') + '_'
    test_patches = patching_helper.get_patches_in_state(expected_states=state)
    test_patches = [p.strip() for p in test_patches if p.startswith(test_patch_name)]
    return test_patches


def remove_test_patches(failure_patch=False):

    LOG.info("Delete patch orchestration strategy")
    orchestration_helper.delete_strategy("patch")

    applied = get_test_patches(state=(PatchState.PARTIAL_APPLY, PatchState.APPLIED))
    if applied:
        LOG.info("Remove applied test patch {}".format(applied))
        patching_helper.remove_patches(patch_ids=applied)

    partial_removed = get_test_patches(state=PatchState.PARTIAL_REMOVE)
    if partial_removed and not patching_helper.get_affecting_alarms():
        LOG.info("Partial-Removed patches to be installed via patch orch: {}".format(partial_removed))
        run_patch_orchestration_strategy(alarm_restrictions='relaxed')

    # Install if needed
    install_code, installed, failed = patching_helper.install_patches(remove=True, fail_ok=True)

    available_patches = get_test_patches(state=PatchState.AVAILABLE)
    if available_patches:
        LOG.info("Delete test patches: {}".format(available_patches))
        patching_helper.delete_patches(available_patches)

    patching_helper.wait_for_affecting_alarms_gone()

    if not failure_patch:
        assert install_code <= 0, "Patches failed to install on removal: {}".format(failed)


def check_vms(vms):
    for vm in vms:
        assert nova_helper.get_vm_status(vm) == VMStatus.ACTIVE
        vm_helper.ping_vms_from_natbox(fail_ok=False)


def run_patch_orchestration_strategy(controller_apply_type=None, storage_apply_type=None,
                                     compute_apply_type=None, max_parallel_computes=2,
                                     instance_action=None, alarm_restrictions=None):

    patches_ids = patching_helper.get_patches_in_state((PatchState.PARTIAL_APPLY, PatchState.PARTIAL_REMOVE))

    LOG.info("Run patch orchestration with parameters: {}".format(locals()))
    patching_helper.orchestration_patch_hosts(
            controller_apply_type=controller_apply_type,
            storage_apply_type=storage_apply_type,
            compute_apply_type=compute_apply_type,
            max_parallel_computes=max_parallel_computes,
            instance_action=instance_action,
            alarm_restrictions=alarm_restrictions)

    LOG.info("Apply Patch orchestration strategy completed for {}".format(patches_ids))


@mark.parametrize('test_patch_type', [
    '_RR_',
    '_INSVC_',
    '_LARGE',
    '_[A-C]'
])
def test_patch_orch_process(patch_orchestration_setup, patch_function_check, test_patch_type):
    """
    Verifies apply/remove rr and in-service test patches through patch orchestration
    Args:
        patch_orchestration_setup:
        patch_function_check
        test_patch_type:

    Returns:

    """
    downloaded_patches, controllers, computes, storages = patch_orchestration_setup
    vms = patch_function_check

    test_patch_type = test_patch_type + '$' if 'A-C' in test_patch_type else test_patch_type
    patches = patching_helper.parse_test_patches(downloaded_patches, search_str=test_patch_type)
    if not patches:
        skip("No patches with pattern {} available".format(test_patch_type))

    patch_files = [downloaded_patches[patch] for patch in patches]

    LOG.tc_step("Upload patch file {}".format(patch_files))
    uploaded_ids = patching_helper.upload_patches(patch_files)[1]
    LOG.info("Patch {} uploaded".format(uploaded_ids))

    LOG.tc_step("Apply patch {}".format(uploaded_ids))
    applied = patching_helper.apply_patches(apply_all=True)[1]
    LOG.info("Patch {} applied".format(applied))

    compute_count = len(computes)
    storage_count = len(storages)
    compute_apply_type = 'parallel' if compute_count > 2 else 'serial'
    max_parallel_computes = 4 if compute_count > 5 else 2
    storage_apply_type = 'parallel' if storage_count / 2 >= 2 else 'serial'

    LOG.tc_step("Install patches through orchestration.")
    patching_helper.wait_for_affecting_alarms_gone()
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, alarm_restrictions='relaxed')
    LOG.info("Install patch through orchestration completed for patches {}".format(applied))

    LOG.tc_step("Check vms are in good state after installing patches {}".format(applied))
    check_vms(vms)

    LOG.tc_step("Remove test patch {}".format(applied))
    patching_helper.remove_patches(patch_ids=applied)

    LOG.tc_step("Remove patches through orchestration: {}".format(applied))
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, alarm_restrictions='relaxed')
    LOG.info("Patches successfully removed via orchestration: {}".format(applied))

    LOG.tc_step("Check vms are in good state after removing patches {}".format(applied))
    check_vms(vms)


@mark.parametrize('storage_apply_type, compute_apply_type, max_parallel_computes, instance_action, test_patch', [
    ('serial', 'serial', 2, 'migrate', 'INSVC_COMPUTE'),
    ('serial', 'serial', 2, 'stop_start', 'INSVC_ALLNODES'),
    ('serial', 'parallel', 2, 'migrate', 'INSVC_NOVA'),
    ('serial', 'parallel', 2, 'migrate', 'RR_COMPUTE'),
    ('serial', 'parallel', 4, 'stop_start', 'INSVC_COMPUTE'),
    ('serial', 'parallel', 4, 'stop_start', 'RR_NOVA'),
    ('parallel', 'parallel', 2, 'migrate', 'INSVC_ALLNODES'),
])
def test_patch_orch_strategy(patch_orchestration_setup, storage_apply_type, patch_function_check,
                             compute_apply_type, max_parallel_computes, instance_action, test_patch):
    """
    This test verifies the patch orchestration strategy options

    Args:
        patch_orchestration_setup:
        patch_function_check
        storage_apply_type:
        compute_apply_type:
        max_parallel_computes:
        instance_action:
        test_patch:

    Returns:

    """
    instance_action = instance_action.replace('_', '-')
    vms = patch_function_check
    patches, controllers, computes, storages = patch_orchestration_setup

    if 'STORAGE' in test_patch and not system_helper.is_storage_system():
        skip('Skip STORAGE patch test for non-storage system')
    if "parallel"in storage_apply_type and len(storages) < 4:
        skip("At least two pairs tier storage nodes required for this test: {}".format(storages))
    if "parallel"in compute_apply_type and len(computes) < (max_parallel_computes + 1):
        skip("At least {} computes are required for this test".format(1+max_parallel_computes))

    patch_id = patching_helper.parse_test_patches(patch_ids=patches, search_str=test_patch)[0]
    patch_file = patches[patch_id]
    LOG.tc_step("Upload patch file {}".format(patch_file))
    uploaded_id = patching_helper.upload_patches(patch_files=patch_file)[1][0]
    assert patch_id == uploaded_id, "Expected patch {} and uploaded patch {} mismatch"\
        .format(patch_id, uploaded_id)
    LOG.info("Patch {} uploaded".format(uploaded_id))

    LOG.tc_step("Apply patch {}".format(patch_id))
    applied = patching_helper.apply_patches(patch_ids=[patch_id])[1]
    assert applied == [patch_id]
    LOG.info("Patch {} applied".format(patch_id))

    LOG.tc_step("Install patches through orchestration for patch {}".format(applied))
    patching_helper.wait_for_affecting_alarms_gone()
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, instance_action=instance_action,
                                     alarm_restrictions='relaxed')

    LOG.info("Install patch through orchestration completed for patch {}".format(applied))
    time.sleep(20)

    LOG.tc_step("Check vms after patch applied: {}".format(applied))
    check_vms(vms)

    LOG.tc_step("Remove test patch {}".format(applied))
    patching_helper.remove_patches(patch_ids=applied)
    partial_remove_ids = get_test_patches(state=PatchState.PARTIAL_REMOVE)
    assert all(patch in partial_remove_ids for patch in applied), \
        "Expected patch {} not in partial-remove state".format(applied)

    LOG.tc_step("Remove patch through orchestration: {}".format(applied))
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, instance_action=instance_action,
                                     alarm_restrictions='relaxed')
    LOG.info("Remove patch through orchestration completed for patch {}".format(applied))

    LOG.tc_step("Check vms after patch removed: {}".format(applied))
    check_vms(vms)


@mark.parametrize('ignored_alarm_texts', [
    'HOST_LOCK-VM_STOP'
])
def test_patch_orch_with_ignored_alarms(patch_orchestration_setup, patch_function_check, ignored_alarm_texts):
    """
    This test verifies the patch orchestration operation with presence of alarms that are normally ignored by the
    orchestration. These alarms are '200.001', '700.004,', '900.001', '900.005', '900.101'. This test generates the
    alarms host lock (200.001) and VM stopped ( 700.004) before executing the patch orchestration.
    Args:
        patch_orchestration_setup:
        patch_function_check
        ignored_alarm_texts:

    Returns:

    """
    vms = patch_function_check
    patches, controllers, computes, storages = patch_orchestration_setup
    hosts = controllers + computes + storages
    patch_id = patching_helper.parse_test_patches(patch_ids=patches, search_str='INSVC_ALLNODES')[0]

    if 'HOST_LOCK' in ignored_alarm_texts and len(hosts) < 2:
        skip("Not enough hosts present in the system")

    if 'HOST_LOCK' in ignored_alarm_texts:
        host = hosts[-1]
        HostsToRecover.add(host)
        LOG.info("Lock host {} to generate 200.001 alarm".format(host))
        host_helper.lock_host(host)
        system_helper.wait_for_alarm(alarm_id='200.001', fail_ok=False)
        LOG.info("Host {} is locked and 200.001 alarm is generated".format(host))

    vm_id_to_stop = None
    if 'VM_STOP' in ignored_alarm_texts:
        vm_id_to_stop = vms[0]
        LOG.info("Stop VM {} to generate 700.004 alarm".format(vm_id_to_stop))
        vm_helper.stop_vms(vm_id_to_stop)
        system_helper.wait_for_alarm(alarm_id='700.004')

    patch_file = patches[patch_id]

    LOG.tc_step("Upload patch file {}".format(patch_file))
    uploaded_id = patching_helper.upload_patches(patch_files=patch_file)[1][0]
    assert patch_id == uploaded_id, "Expected patch {} and uploaded patch {} mismatch".format(patch_id, uploaded_id)
    LOG.info("Patch {} uploaded".format(uploaded_id))

    LOG.tc_step("Apply patch {}".format(uploaded_id))
    applied = patching_helper.apply_patches(patch_ids=[uploaded_id])[1]
    LOG.info("Patch {} applied".format(applied))

    LOG.tc_step("Install patch {} through orchestration".format(uploaded_id))
    patching_helper.wait_for_affecting_alarms_gone()
    run_patch_orchestration_strategy()
    LOG.info("Install patch through orchestration completed for patch {}".format(applied))
    host_helper.wait_for_hosts_ready(hosts=hosts)

    LOG.tc_step("Check vms after patch is installed.")
    if vm_id_to_stop:
        vm_helper.start_vms(vm_id_to_stop)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id_to_stop)
    check_vms(vms)

    LOG.tc_step("Remove test patch {}".format(applied))
    if vm_id_to_stop:
        vm_helper.stop_vms(vm_id_to_stop)

    patching_helper.remove_patches(patch_ids=applied)

    LOG.tc_step("Remove patch through orchestration: {}".format(applied))
    run_patch_orchestration_strategy(alarm_restrictions='relaxed')
    LOG.info("Apply/Remove through patch orchestration completed for patch {}".format(applied))

    LOG.tc_step("Check vms after patch removed: {}.".format(applied))
    if vm_id_to_stop:
        vm_helper.start_vms(vm_id_to_stop)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id_to_stop)
    check_vms(vms)


def test_patch_orch_reject_with_alarms(patch_orchestration_setup, patch_function_check):
    """
    This test verifies the patch orchestration operation can not proceed with presence of alarms that are not normally
    ignored by the orchestration. The test generates the alarm ( 700.002 - VM paused) before executing the patch
    orchestration.
    Args:
        patch_orchestration_setup:
        patch_function_check

    Returns:

    """
    vms = patch_function_check
    patches, controllers, computes, storages = patch_orchestration_setup

    LOG.tc_step("Generate VM paused ( 700.002) critical alarm")
    paused_vm, unpaused_vm = vms
    vm_helper.pause_vm(paused_vm)
    system_helper.wait_for_alarm(alarm_id='700.002')

    patch = patching_helper.parse_test_patches(patch_ids=patches, search_str='RR_ALLNODES')[0]
    patch_file = patches[patch]
    LOG.tc_step("Upload patch file {}".format(patch_file))
    uploaded_id = patching_helper.upload_patches(patch_files=patch_file)[1][0]
    assert patch == uploaded_id, "Expected patch {} and uploaded patch {} mismatch"\
        .format(patch, uploaded_id)
    LOG.info("Patch {} uploaded".format(uploaded_id))

    LOG.tc_step("Apply patch {}".format(uploaded_id))
    applied = patching_helper.apply_patches(patch_ids=[uploaded_id])[1]
    LOG.info("Patch {} applied".format(applied))

    LOG.tc_step("Attempt to create patch orchestration strategy; expected to fail")
    rc, msg = orchestration_helper.create_strategy('patch', fail_ok=True)
    assert rc != 0, "Patch orchestration strategy created with presence of critical alarm; expected to fail: {}"\
        .format(msg)

    LOG.info("Delete the failed patch orchestration strategy")
    orchestration_helper.delete_strategy("patch")

    LOG.tc_step("Remove test patch {}".format(applied))
    patching_helper.remove_patches(patch_ids=applied)
    assert 0 == patching_helper.wait_for_patch_states(applied, expected_states=PatchState.AVAILABLE)[0]

    LOG.tc_step("Un-pause vm after test patch removal, and check vms are in good state.")
    vm_helper.unpause_vm(paused_vm)
    vm_helper.wait_for_vm_pingable_from_natbox(paused_vm)
    check_vms(vms)


@fixture(scope='function')
def failed_patch_setup(request, patch_function_check):
    LOG.fixture_step("Delete available test patches before start.")
    avail_patches = get_test_patches(state=PatchState.AVAILABLE)
    patching_helper.delete_patches(avail_patches)

    def remove_failed():
        remove_test_patches(failure_patch=True)
    request.addfinalizer(remove_failed)

    return patch_function_check


@mark.parametrize('patch_type', [
    '_RESTART_FAILURE',
    '_PREINSTALL_FAILURE',
    '_POSTINSTALL_FAILURE'
])
def test_patch_orch_failure(patch_orchestration_setup, failed_patch_setup, patch_type):
    """
    This test verifies the patch orchestration operation with invalid or failure test patches. The patches are
    expected to fail on applying the patch orchestration.

    Args:
        patch_orchestration_setup:
        del_test_patch_before_start
        patch_function_check
        patch_type:

    Returns:

    """
    vms = failed_patch_setup
    downloaded_patches, controllers, computes, storages = patch_orchestration_setup

    patch_id = patching_helper.parse_test_patches(downloaded_patches, search_str=patch_type, failure_patch=True)[0]
    patch_file = downloaded_patches[patch_id]

    LOG.tc_step("Upload patch file {}".format(patch_file))
    uploaded_id = patching_helper.upload_patches(patch_file)[1][0]
    LOG.info("Patch {} uploaded".format(uploaded_id))

    LOG.tc_step("Apply patch {}".format(uploaded_id))
    applied = patching_helper.apply_patches(patch_ids=uploaded_id, apply_all=True)[1]
    LOG.info("Patch {} applied.".format(applied))

    LOG.tc_step("Attempt to install the invalid patch {} through orchestration".format(applied))
    patching_helper.wait_for_affecting_alarms_gone()

    LOG.tc_step("Create patch orchestration strategy")
    rc, msg = orchestration_helper.create_strategy('patch', fail_ok=True)
    assert rc == 0, "Patch orchestration strategy create failed : {}".format(msg)

    LOG.tc_step("Apply patch orchestration strategy with failure patch: {}".format(applied))
    rc, msg = orchestration_helper.apply_strategy('patch', fail_ok=True)
    assert rc != 0, "Patch orchestration strategy apply succeeded which expected to fail : {}".format(msg)

    LOG.tc_step("Check vms are still in good state after apply patch failed.")
    check_vms(vms)
