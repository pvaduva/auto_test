import time
import pytest
import os
import re
from utils.tis_log import LOG
from consts.auth import SvcCgcsAuto, HostLinuxCreds
from keywords import system_helper, host_helper, install_helper, patching_helper, \
    orchestration_helper, nova_helper, vm_helper
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from consts.build_server import Server, get_build_server_info
from consts.proj_vars import ProjVar, PatchingVars, InstallVars
from consts.cgcs import Prompt, HostAvailState
from utils.clients.ssh import ControllerClient, SSHClient


@pytest.fixture(scope='session')
def pre_check_patch():

    # ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    LOG.tc_func_start("PATCH_ORCHESTRATION_TEST")

    # Check system health for patch orchestration;
    check_health()


def check_health(check_patch_ignored_alarms=True):

    rc, health = system_helper.get_system_health_query()
    if rc == 0:
        LOG.info("System health OK for patching ......")
    else:
        if len(health) > 1:
            assert False, "System health query failed: {}".format(health)
        else:
            if "No alarms" in health.keys() and check_patch_ignored_alarms:
                rtn = ('Alarm ID',)
                current_alarms_ids = system_helper.get_alarms(rtn_vals=rtn, mgmt_affecting=True)
                affecting_alarms = [id_ for id_ in current_alarms_ids if id_ not in
                                    orchestration_helper.IGNORED_ALARM_IDS]
                if len(affecting_alarms) > 1:
                    assert False, "Management affecting alarm(s) present: {}".format(affecting_alarms)
            else:
                assert False, "System health query failed: {}".format(health)

    return rc, health


@pytest.fixture(scope='session')
def patch_orchestration_setup():

    lab = InstallVars.get_install_var('LAB')
    pre_check_patch()
    current_release = system_helper.get_system_software_version()
    build_id = system_helper.get_system_build_id()

    bld_server = get_build_server_info(PatchingVars.get_patching_var('PATCH_BUILD_SERVER'))
    output_dir = ProjVar.get_var('LOG_DIR')
    patch_dir = PatchingVars.get_patching_var('PATCH_DIR')

    LOG.info("Using  patch directory path: {}".format(patch_dir))
    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    bld_server_attr['prompt'] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', bld_server['name'])
    bld_server_conn = SSHClient(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])
    bld_server_conn.connect()
    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)

    if not patch_dir:
        patch_base_dir = PatchingVars.get_patching_var('PATCH_BASE_DIR')
        if build_id:
            patch_dir = patch_base_dir + '/' + build_id
            rc = bld_server_obj.ssh_conn.exec_cmd("test -d " + patch_dir)[0]
            if rc != 0 or bld_server_obj.ssh_conn.exec_cmd("ls -1 --color=none {}/*.patch".format(patch_dir))[0] != 0:
                patch_dir = patch_base_dir + '/latest_build'
        else:
            patch_dir = patch_base_dir + '/latest_build'

    # Download patch files from specified patch dir
    LOG.info("Downloading patch files from patch dir {}".format(patch_dir))

    rc = bld_server_obj.ssh_conn.exec_cmd("test -d " + patch_dir)[0]
    if rc != 0:
        if 'latest_build' in os.path.basename(patch_dir):
            assert False, "Patch directory path {} not found".format(patch_dir)
        else:
            patch_dir_latest = os.path.join(os.path.split(patch_dir)[0], 'latest_build')
            LOG.info("Test Patch directory {} not found. Trying the latest_build subdir:{}".
                     format(patch_dir, patch_dir_latest))
            rc = bld_server_obj.ssh_conn.exec_cmd("test -d " + patch_dir_latest)[0]
            assert rc == 0, "Test Patch directory {} not found".format(patch_dir_latest)
            patch_dir = patch_dir_latest

    clear_patch_dest_dir()
    patches = download_patches(lab, bld_server_obj, patch_dir)
    if len(patches) == 0:
        pytest.skip("No patch files found in {}:{}.".format(bld_server_obj.name, patch_dir))

    enable_dev_certificate = BuildServerPath.PATCH_ENABLE_DEV_CERTIFICATES[current_release]

    get_patch_dev_enabler_certificate(bld_server_obj, enable_dev_certificate, lab)

    _patching_setup = {'lab': lab, 'output_dir': output_dir, 'build_server': bld_server_obj,
                       'patch_dir': patch_dir, 'enable_dev_certificate': enable_dev_certificate,
                       'patches': patches}

    LOG.info("Patch Orchestration ready to start: {} ".format(_patching_setup))
    return _patching_setup


def clear_patch_dest_dir():

    patch_dest_path = WRSROOT_HOME + "patches/"
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.exec_cmd("rm {}/*".format(patch_dest_path))


def delete_patch_strategy():

    orchestration_helper.delete_strategy("patch")


def get_patch_dev_enabler_certificate(server, cert_path, lab):

    current_release = system_helper.get_system_software_version()
    enable_dev_certificate = BuildServerPath.PATCH_ENABLE_DEV_CERTIFICATES[current_release]
    rc = server.ssh_conn.exec_cmd("test -f " + enable_dev_certificate)[0]
    assert rc == 0, "Designer patch enabler certificate {} not found.".format(enable_dev_certificate)
    active_controller = system_helper.get_active_controller_name()
    patch_dest_dir = WRSROOT_HOME + "patches/"
    dest_server = lab[active_controller + ' ip']

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    server.ssh_conn.rsync(cert_path, dest_server, patch_dest_dir, ssh_port=None, pre_opts=pre_opts)


@pytest.fixture(scope='session', autouse=True)
def patch_tear_down(request):

    def remove_on_teardown():
        delete_patch_strategy()
        applied_patches = patching_helper.get_patches_in_state(expected_states='Applied')
        applied_patches = [p for p in applied_patches if "RR_" or "INSVC" in p]
        partial_applied_patches = [p for p in patching_helper.get_partial_applied() if "RR_" or "INSVC" in p]
        if len(applied_patches + partial_applied_patches) > 0:
            patches_for_removal = ' '.join(applied_patches + partial_applied_patches)
            LOG.info("Patches to be removed: {}".format(patches_for_removal))

            removed = patching_helper.remove_patches(patches_for_removal)
            if len(removed) > 0:
                LOG.info("Patches removed: {}".format(removed))

        partial_removed_patches = patching_helper.get_partial_removed()

        if len(partial_removed_patches) > 0:
            patches_for_removal = ' '.join(partial_removed_patches)
            LOG.info("Patches to be removed: {}".format(patches_for_removal))
            run_patch_orchestration_strategy(alarm_restrictions='relaxed')

        available_patches = patching_helper.get_available_patches()
        if len(available_patches) > 0:
            patching_helper.delete_patches(available_patches)

    request.addfinalizer(remove_on_teardown)


def get_downloaded_patch_files(patch_dest_dir=None, conn_ssh=None):

    if conn_ssh is None:
        conn_ssh = ControllerClient.get_active_controller()
    if not patch_dest_dir:
        patch_dest_dir = WRSROOT_HOME + "patches/"
    patch_names = []
    rc, output = conn_ssh.exec_cmd("ls -1 --color=none {}/*.patch".format(patch_dest_dir))
    assert rc == 0, "Failed to list downloaded patch files in directory path {}.".format(patch_dest_dir)
    if output is not None:
        for item in output.splitlines():
            # Remove ".patch" extension
            patch_file_name = os.path.basename(item)
            LOG.info("Found patch named: " + patch_file_name)
            patch_names.append(os.path.basename(patch_file_name))

    return patch_names


def download_patches(lab, server, patch_dir, conn_ssh=None):
    """

    Args:
        lab:
        server:
        patch_dir:
        conn_ssh:

    Returns:

    """

    patches = {}

    rc, output = server.ssh_conn.exec_cmd("ls -1 --color=none {}/*.patch".format(patch_dir))
    assert rc == 0, "Failed to list patch files in directory path {}.".format(patch_dir)

    if output is not None:
        patch_dest_dir = WRSROOT_HOME + "patches/"
        active_controller = system_helper.get_active_controller_name()
        dest_server = lab[active_controller + ' ip']
        ssh_port = None
        pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

        server.ssh_conn.rsync(patch_dir + "/*.patch", dest_server, patch_dest_dir, ssh_port=ssh_port,
                              pre_opts=pre_opts)

        if conn_ssh is None:
            conn_ssh = ControllerClient.get_active_controller()

        rc, output = conn_ssh.exec_cmd("ls -1  {}/*.patch".format(patch_dest_dir))
        assert rc == 0, "Failed to list downloaded patch files in directory path {}.".format(patch_dest_dir)

        if output is not None:
            for item in output.splitlines():
                patches[os.path.splitext(os.path.basename(item))[0]] = item

            patch_ids = " ".join(patches.keys())
            LOG.info("List of patches:\n {}".format(patch_ids))

    return patches


def check_alarms_():

    current_alarms_ids = system_helper.get_alarms(mgmt_affecting=True, combine_entries=False)
    affecting_alarms = [id_ for id_ in current_alarms_ids if id_[0] not in orchestration_helper.IGNORED_ALARM_IDS]
    if len(affecting_alarms) > 0:
        assert system_helper.wait_for_alarms_gone(alarms=affecting_alarms, timeout=240, fail_ok=True)[0],\
            "Alarms present: {}".format(affecting_alarms)


def run_patch_orchestration_strategy(controller_apply_type='serial', storage_apply_type='serial',
                                     compute_apply_type='serial', max_parallel_computes=2,
                                     instance_action='stop-start', alarm_restrictions='strict'):

    patches_ids = patching_helper.get_patches_in_state(expected_states=['Partial-Apply', 'Partial-Remove'])

    # current_alarms_ids = system_helper.get_alarms(mgmt_affecting=True, combine_entries=False)
    # affecting_alarms = [id_ for id_ in current_alarms_ids if id_[0] not in orchestration_helper.IGNORED_ALARM_IDS]
    # if len(affecting_alarms) > 0:
    #     assert system_helper.wait_for_alarms_gone(alarms=affecting_alarms, timeout=240, fail_ok=True)[0],\
    #         "Alarms present: {}".format(affecting_alarms)

    LOG.tc_step("Running patch orchestration with parameters: {}.....".format(locals()))

    patching_helper.orchestration_patch_hosts(
            controller_apply_type=controller_apply_type,
            storage_apply_type=storage_apply_type,
            compute_apply_type=compute_apply_type,
            max_parallel_computes=max_parallel_computes,
            instance_action=instance_action,
            alarm_restrictions=alarm_restrictions)

    LOG.info(" Applying Patch orchestration strategy completed for {} ....".format(patches_ids))


@pytest.mark.parametrize('test_patch_type', ['_RR_', '_INSVC_', '_LARGE', '_[A-C]'])
def test_rr_insvc_patch_orchestration(patch_orchestration_setup, test_patch_type):
    """
    Verifies apply/remove rr and in-service test patches through patch orchestration
    Args:
        patch_orchestration_setup:
        test_patch_type:

    Returns:

    """
    lab = patch_orchestration_setup['lab']
    downloaded_patches = patch_orchestration_setup['patches']
    reg_str = '^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}'
    reg_str = reg_str + test_patch_type + ')'
    reg = re.compile(reg_str)

    patchs = [k for k in downloaded_patches.keys() if "FAILURE" not in k and reg.match(k)]
    if len(patchs) == 0:
        pytest.skip("No patches with pattern {} availabe in patch-dir {}"
                    .format(test_patch_type, patch_orchestration_setup['patch-dir']))

    patch_files = [downloaded_patches[patch] for patch in patchs]
    patches_to_upload = ' '.join(patch_files)

    LOG.tc_step("Uploading patch file {} .....".format(patches_to_upload))
    uploaded_ids = patching_helper.upload_patch_files(files=patch_files)[0]

    LOG.info(" Patch {} uploaded .....".format(uploaded_ids))

    LOG.tc_step("Applying patch {} .....".format(uploaded_ids))
    applied = patching_helper.apply_patches(patch_ids=uploaded_ids, apply_all=True)
    LOG.info(" Patch {} applied .....".format(applied))

    computes = len(lab['compute_nodes']) if 'compute_nodes' in lab.keys() else 0
    storages = len(lab['storage_nodes']) if 'storage_nodes' in lab.keys() else 0

    compute_apply_type = 'parallel' if computes > 2 else 'serial'
    max_parallel_computes = 4 if computes > 5 else 2
    storage_apply_type = 'parallel' if storages / 2 >= 2 else 'serial'

    LOG.tc_step("Installing patches through orchestration .....")
    check_alarms_()
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, alarm_restrictions='relaxed')

    LOG.info(" Install patch through orchestration completed for patches {} ....".format(applied))

    LOG.tc_step("Removing test patch {} .....".format(applied))

    patching_helper.remove_patches(patch_ids=' '.join(applied))

    LOG.tc_step("Completing the removal of patches {} through orchestration.....".format(applied))
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, alarm_restrictions='relaxed')

    LOG.info(" Remove patch through orchestration completed for patches {} ....".format(applied))

    LOG.tc_step("Deleting test patches {} from repo .....".format(applied))
    patching_helper.delete_patches(patch_ids=applied)

    all_patches = patching_helper.get_all_patch_ids()
    assert all(applied) not in all_patches, "Unable to delete patches {} from repo".format(applied)

    LOG.info(" Testing apply/remove through patch orchestration completed for patches {}.....".format(applied))


@pytest.mark.parametrize('storage_apply_type, compute_apply_type, max_parallel_computes, instance_action, test_patch',
                         [('serial', 'serial', 2, 'migrate', 'INSVC_COMPUTE'),
                          ('serial', 'serial', 2, 'migrate', 'INSVC_ALLNODES'),
                          ('serial', 'parallel', 2, 'stop-start', 'RR_COMPUTE'),
                          ('serial', 'parallel', 2, 'stop-start', 'INSVC_NOVA'),
                          ('parallel', 'parallel', 2, 'migrate', 'INSVC_ALLNODES'),
                          ('serial', 'parallel', 4, 'stop-start', 'RR_NOVA'),
                          ('serial', 'parallel', 4, 'stop-start', 'INSVC_COMPUTE')])
def test_patch_orchestration_apply_type(patch_orchestration_setup, storage_apply_type, compute_apply_type,
                                        max_parallel_computes, instance_action, test_patch):
    """
    This test verifies the patch orchestration strategy apply type  and instance action options

    Args:
        patch_orchestration_setup:
        storage_apply_type:
        compute_apply_type:
        max_parallel_computes:
        instance_action:
        test_patch:

    Returns:

    """
    personality = test_patch[6:].lower() if 'INSVC' in test_patch else test_patch[3:].lower()

    if 'allnodes' not in personality and 'nova' not in personality \
            and len(system_helper.get_hostnames(personality=personality)) == 0:
            pytest.skip("No {} hosts in system".format(personality))

    check_health()

    controllers = system_helper.get_hostnames(personality='controller')
    computes = system_helper.get_hostnames(personality='compute')
    storages = system_helper.get_hostnames(personality='storage')
    hosts = controllers + computes + storages
    if "parallel" in storage_apply_type and len(storages) < 4:
        pytest.skip("At least two pairs tier storages required for this test: {}".format(storages))
    if "parallel" in compute_apply_type and len(computes) < (max_parallel_computes + 1):
        pytest.skip("At least {} computes are required for this test: {}".format(1 + max_parallel_computes, hosts))

    LOG.info("Launching a VM ... ")

    vm_id = vm_helper.boot_vm(cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    patches = patch_orchestration_setup['patches']
    patch = [k for k in patches.keys() if test_patch in k][0]
    patch_file = patches[patch]
    LOG.tc_step("Uploading patch file {} .....".format(patch_file))
    uploaded_id = patching_helper.upload_patch_file(patch_file=patch_file)
    assert patch.strip() == uploaded_id.strip(), " Expected patch {} and uploaded patch {} mismatch"\
        .format(patch, uploaded_id)
    LOG.info(" Patch {} uploaded .....".format(uploaded_id))

    LOG.tc_step("Applying patch {} .....".format(uploaded_id))
    applied = patching_helper.apply_patches(patch_ids=[uploaded_id])
    LOG.info(" Patch {} applied .....".format(applied))

    LOG.tc_step("Installing patches through orchestration for patch {} .....".format(applied))
    check_alarms_()
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, instance_action=instance_action,
                                     alarm_restrictions='relaxed')

    LOG.info(" Install patch through orchestration completed for patch {} ....".format(applied))
    time.sleep(20)
    LOG.tc_step("Verifying VM connectivity after patch {} .....".format(applied))
    assert vm_helper.ping_vms_from_natbox(vm_ids=vm_id, fail_ok=True)[0], "VM connectivity lost after patch {}"\
        .format(applied)
    LOG.info(" VM {}  is active after patch {} .....".format(vm_id, applied))

    LOG.tc_step("Removing test patch {} .....".format(applied))

    patching_helper.remove_patches(patch_ids=' '.join(applied))
    partial_remove_ids = patching_helper.get_partial_removed()
    assert all(patch in partial_remove_ids for patch in applied), \
        "Expected patch {} not in partial-remove state".format(applied)

    LOG.tc_step("Completing the removing of patch {} through orchestration.....".format(applied))
    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, instance_action=instance_action,
                                     alarm_restrictions='relaxed')

    LOG.info(" Remove patch through orchestration completed for patch {} ....".format(applied))

    LOG.tc_step("Deleting test patch {} from repo .....".format(applied))
    patching_helper.delete_patches(patch_ids=applied)

    all_patches = patching_helper.get_all_patch_ids()
    assert applied not in all_patches, "Unable to delete patch {} from repo".format(applied)

    LOG.info(" Testing apply/remove through patch orchestration completed for patch {}.....".format(applied))


@pytest.mark.parametrize('ignored_alarm_texts', ['HOST_LOCK-VM_STOPPED'])
def test_patch_orchestration_with_ignored_alarms(patch_orchestration_setup, ignored_alarm_texts):
    """
    This test verifies the patch orchestration operation with presence of alarms that are normally ignored by the
    orchestration. These alarms are '200.001', '700.004,', '900.001', '900.005', '900.101'.  This test generates the
    alarms host lock (200.001) and VM stopped ( 700.004) before executing the patch orchestration.
    Args:
        patch_orchestration_setup:
        ignored_alarm_texts:

    Returns:

    """
    check_health()

    controllers = system_helper.get_hostnames(personality='controller')
    computes = system_helper.get_hostnames(personality='compute')
    storages = system_helper.get_hostnames(personality='storage')
    hosts = controllers + computes + storages
    host = None
    host_locked = False
    vm_stopped = False

    if 'HOST_LOCK' in ignored_alarm_texts and (len(computes) <= 1 or len(controllers) == 1):
        pytest.skip("Not enough hosts present in the system")

    if 'HOST_LOCK' in ignored_alarm_texts:
        if len(computes) > 0:
            host = computes[0]
        else:
            host = system_helper.get_standby_controller_name()

        LOG.info("Locking host {}  to generate 200.001 alarm".format(host))
        host_helper.lock_host(host)
        assert system_helper.wait_for_alarm(alarm_id='200.001')[0], \
            "Timeout waiting for  host {} lock alarm to be generated".format(host)
        host_locked = True
        LOG.info("Host {}  locked and an  200.001 alarm is generated".format(host))

    if 'VM_STOPPED' in ignored_alarm_texts:

        vms = nova_helper.get_all_vms()
        # vm_id_to_stop = None
        if len(vms) > 0:
            vm_id_to_stop = vms[0]
        else:
            LOG.info("No vms running in system; creating one ... ")
            vm_id_to_stop = vm_helper.boot_vm(cleanup='function')[1]
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id_to_stop)

        assert vm_id_to_stop, "Fail to launch VM"
        LOG.info("Stop VM {} to generate 700.004 alarm....".format(vm_id_to_stop))
        vm_helper.stop_vms(vm_id_to_stop)
        assert system_helper.wait_for_alarm(alarm_id='700.004')[0], \
            "Timeout waiting for  VM stopped alarm to be generated"

        vm_stopped = True

    if vm_stopped or host_locked:
        patches = patch_orchestration_setup['patches']
        patch = [k for k in patches.keys() if 'INSVC_ALLNODES' in k][0]
        patch_file = patches[patch]
        LOG.tc_step("Uploading patch file {} .....".format(patch_file))
        uploaded_id = patching_helper.upload_patch_file(patch_file=patch_file)
        assert patch.strip() == uploaded_id.strip(), " Expected patch {} and uploaded patch {} mismatch"\
            .format(patch, uploaded_id)
        LOG.info(" Patch {} uploaded .....".format(uploaded_id))

        LOG.tc_step("Applying patch {} .....".format(uploaded_id))
        applied = patching_helper.apply_patches(patch_ids=[uploaded_id])
        LOG.info(" Patch {} applied .....".format(applied))
        LOG.tc_step("Installing patch {} through orchestration .....".format(uploaded_id))
        check_alarms_()
        run_patch_orchestration_strategy()
        LOG.info(" Install patch through orchestration completed for patch {} ....".format(applied))
        if host_locked and host:
            host_helper.wait_for_host_states(host, check_interval=20, availability=HostAvailState.ONLINE)
            unlocked_hosts = [h for h in hosts if h not in host]
            host_helper.wait_for_hosts_states(unlocked_hosts, check_interval=20, availability=HostAvailState.AVAILABLE)

        LOG.tc_step("Removing test patch {} .....".format(applied))

        patching_helper.remove_patches(patch_ids=' '.join(applied))
        partial_remove_ids = patching_helper.get_partial_removed()
        assert all(patch in partial_remove_ids for patch in applied), \
            "Expected patch {} not in partial-remove state".format(applied)

        LOG.tc_step("Completing  removal of patch {} through orchestration.....".format(applied))
        run_patch_orchestration_strategy(alarm_restrictions='relaxed')

        LOG.tc_step("Deleting test patch {} from repo .....".format(applied))
        patching_helper.delete_patches(patch_ids=applied)

        all_patches = patching_helper.get_all_patch_ids()
        assert applied not in all_patches, "Unable to delete patch {} from repo".format(applied)

        LOG.info(" Testing apply/remove through patch orchestration completed for patch {}.....".format(applied))

        if host_locked and host:
            host_helper.unlock_host(host)
            host_helper.wait_for_host_states(host, check_interval=20, availability=HostAvailState.AVAILABLE)


def test_patch_orchestration_with_alarms_negative(patch_orchestration_setup):
    """
    This test verifies the patch orchestration operation can not proceed with presence of alarms that are not normally
    ignored by the orchestration.  The test generates the alarm ( 700.002 - VM paused) before executing the patch
    orchestration.
    Args:
        patch_orchestration_setup:

    Returns:

    """
    check_health()

    # generate VM paused ( 700.002) critical alarm
    LOG.tc_step("Generating VM paused ( 700.002) critical alarm .....")

    vms = nova_helper.get_all_vms()
    # vm_id_to_pause = None
    if len(vms) > 0:
        vm_id_to_pause = vms[0]
    else:
        LOG.info("No vms running in system; creating one ... ")
        vm_id_to_pause = vm_helper.boot_vm(cleanup='function')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id_to_pause)

    assert vm_id_to_pause, "Fail to launch VM"
    LOG.info("Pause VM {} to generate 700.002 critical alarm....".format(vm_id_to_pause))
    vm_helper.pause_vm(vm_id_to_pause)
    assert system_helper.wait_for_alarm(alarm_id='700.002')[0], \
        "Timeout waiting for  VM paused alarm to be generated"

    patches = patch_orchestration_setup['patches']
    patch = [k for k in patches.keys() if 'RR_ALLNODES' in k][0]
    patch_file = patches[patch]
    LOG.tc_step("Uploading patch file {} .....".format(patch_file))
    uploaded_id = patching_helper.upload_patch_file(patch_file=patch_file)
    assert patch.strip() == uploaded_id.strip(), " Expected patch {} and uploaded patch {} mismatch"\
        .format(patch, uploaded_id)
    LOG.info(" Patch {} uploaded .....".format(uploaded_id))

    LOG.tc_step("Applying patch {} .....".format(uploaded_id))
    applied = patching_helper.apply_patches(patch_ids=[uploaded_id])
    LOG.info(" Patch {} applied .....".format(applied))

    LOG.tc_step("Attempting to create patch orchestration strategy; expected to fail.....")
    rc, msg = orchestration_helper.create_strategy('patch', fail_ok=True)
    assert rc != 0,  "Patch orchestration strategy created with presence of critical alarm; expected to fail: {}"\
        .format(msg)

    LOG.info("Deleting the failed patch orchestration strategy .....")
    orchestration_helper.delete_strategy("patch")

    LOG.tc_step("Removing test patch {} .....".format(applied))

    patching_helper.remove_patches(patch_ids=' '.join(applied))
    partial_remove_ids = patching_helper.get_partial_removed()
    assert all(patch in partial_remove_ids for patch in applied), \
        "Expected patch {} not in partial-remove state".format(applied)

    LOG.tc_step("Completing  removal of patch {} through orchestration.....".format(applied))
    run_patch_orchestration_strategy(alarm_restrictions='relaxed')

    LOG.tc_step("Deleting test patch {} from repo .....".format(applied))
    patching_helper.delete_patches(patch_ids=applied)

    all_patches = patching_helper.get_all_patch_ids()
    assert applied not in all_patches, "Unable to delete patch {} from repo".format(applied)

    LOG.info(" Testing apply/remove through patch orchestration with  alarm is completed......")


@pytest.mark.parametrize('failure_patch_type', ['_RESTART_FAILURE', '_PREINSTALL_FAILURE', '_POSTINSTALL_FAILURE'])
def test_failure_patches_patch_orchestration(patch_orchestration_setup, failure_patch_type):
    """
    This test verifies the patch orchestration operation with invalid or failure test patches. The patches are
    expected to fail on applying the patch orchestration.

    Args:
        patch_orchestration_setup:
        failure_patch_type:

    Returns:

    """
    lab = patch_orchestration_setup['lab']
    downloaded_patches = patch_orchestration_setup['patches']
    reg_str = '^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}'
    reg_str = reg_str + "_INSVC" + failure_patch_type + ')'
    reg = re.compile(reg_str)

    patchs = [k for k in downloaded_patches.keys() if reg.match(k)]
    if len(patchs) == 0:
        pytest.skip("No patches with pattern {} availabe in patch-dir {}"
                    .format(failure_patch_type, patch_orchestration_setup['patch-dir']))

    patch_files = [downloaded_patches[patch] for patch in patchs]
    patches_to_upload = ' '.join(patch_files)

    LOG.tc_step("Uploading patch file {} .....".format(patches_to_upload))
    uploaded_ids = patching_helper.upload_patch_files(files=patch_files)[0]

    LOG.info(" Patch {} uploaded .....".format(uploaded_ids))

    LOG.tc_step("Applying patch {} .....".format(uploaded_ids))
    applied = patching_helper.apply_patches(patch_ids=uploaded_ids, apply_all=True)
    LOG.info(" Patch {} applied .....".format(applied))

    LOG.tc_step("Attempting to install the invalid patch {} through orchestration .....".format(applied))
    check_alarms_()

    LOG.tc_step("Creating patch orchestration strategy .....")
    rc, msg = orchestration_helper.create_strategy('patch', fail_ok=True)
    assert rc == 0,  "Patch orchestration strategy create failed : {}".format(msg)

    LOG.tc_step("Apply patch orchestration strategy with failure patches; expected to fail on applying.....")
    rc, msg = orchestration_helper.apply_strategy('patch', fail_ok=True)
    assert rc != 0,  "Patch orchestration strategy apply succeeded which expected to fail : {}".format(msg)

    LOG.info("Deleting the failed patch orchestration strategy .....")
    orchestration_helper.delete_strategy("patch")

    LOG.tc_step("Removing test patch {} .....".format(applied))

    patching_helper.remove_patches(patch_ids=' '.join(applied))
    partial_remove_ids = patching_helper.get_partial_removed()

    LOG.info('Install impacted hosts after removing patch IDs:{}'.format(partial_remove_ids))
    states = patching_helper.get_system_patching_states()
    impacts_hosts = states['host_states']
    active = system_helper.get_active_controller_name()
    standby = system_helper.get_standby_controller_name()

    hosts_install = []
    if standby in impacts_hosts.keys():
        hosts_install.append(standby)
    if active in impacts_hosts.keys():
        hosts_install.append(active)
    hosts_install.extend([h for h in impacts_hosts.keys() if h != active and h != standby])

    for host in hosts_install:
        host_patch_state = impacts_hosts[host]
        if not host_patch_state['patch-current']:
            if host_patch_state['rr']:
                # lock host
                LOG.info('Patch install failed; lock-unlock host {}'.format(host))
                swact = True if host == active else False
                host_helper.lock_host(host, force=True, swact=swact)
            LOG.info('Install patch for  host {}'.format(host))
            rc = patching_helper.run_patch_cmd("host-install", args=host, fail_ok=True)[0]
            if rc != 0:
                if not host_helper.is_host_locked(host):
                    host_helper.lock_host(host)
            if host_helper.is_host_locked(host):
                host_helper.unlock_host(host)

    new_states = patching_helper.get_system_patching_states()
    new_host_states = new_states['host_states']
    for host in impacts_hosts.keys():

        host_patch_state = new_host_states[host]
        LOG.info('Host patch install states = {}'.format( host_patch_state))
        assert host_patch_state['patch-current'], "Unable to remove patches {}".format(applied)

    LOG.tc_step("Deleting test patch {} from repo .....".format(applied))
    patching_helper.delete_patches(patch_ids=applied)

    all_patches = patching_helper.get_all_patch_ids()
    assert applied not in all_patches, "Unable to delete patch {} from repo".format(applied)

    LOG.info(" Testing apply/remove  invalid patches through patch orchestration is completed......")

