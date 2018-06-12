import time
import pytest
import os
from utils.tis_log import LOG
from consts.auth import SvcCgcsAuto, HostLinuxCreds, Tenant
from keywords import system_helper, host_helper, install_helper, upgrade_helper, patching_helper, orchestration_helper, nova_helper, vm_helper
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from consts.build_server import Server, get_build_server_info
from consts.proj_vars import ProjVar, PatchingVars, InstallVars
from consts.cgcs import Prompt, HostAvailState, HostOperState
from utils.clients.ssh import ControllerClient, SSHClient
from testfixtures.fixture_resources import ResourceCleanup


IGNORED_ALARM_IDS = ['200.001', '700.004,', '900.001', '900.005', '900.101' ]


@pytest.fixture(scope='session')
def pre_check_patch():

    #ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
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
                affecting_alarms = [id for id in current_alarms_ids if id not in IGNORED_ALARM_IDS ]
                if len(affecting_alarms) > 0:
                    assert False, "Managment affecting alarm(s) present: {}".format(affecting_alarms)
            else:
                assert False, "System health query failed: {}".format(health)

    return rc, health

@pytest.fixture(scope='session')
def patch_orchestration_setup(pre_check_patch):

    lab = InstallVars.get_install_var('LAB')

    # establish ssh connection with active controller
    controller_conn = ControllerClient.get_active_controller()
    #cpe = system_helper.is_small_footprint(controller_conn)
    #is_simplex = system_helper.is_simplex()
    current_release = system_helper.get_system_software_version()
    build_id = system_helper.get_system_build_id()

    bld_server = get_build_server_info(PatchingVars.get_patching_var('PATCH_BUILD_SERVER'))
    output_dir = ProjVar.get_var('LOG_DIR')
    patch_dir = PatchingVars.get_patching_var('PATCH_DIR')
    if not patch_dir:
        patch_base_dir = PatchingVars.get_patching_var('PATCH_BASE_DIR')
        if build_id:
            patch_dir = patch_base_dir + '/' + build_id
        else:
            patch_dir = patch_base_dir + '/latest_build'

    LOG.info("Using  patch directory path: {}".format(patch_dir))
    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    # bld_server_attr['prompt'] = r'.*yow-cgts[1234]-lx.*$ '
    bld_server_attr['prompt'] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', bld_server['name'])
    # '.*yow\-cgts[34]\-lx ?~\]?\$ '
    bld_server_conn = SSHClient(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])
    bld_server_conn.connect()
    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)


    # Download patch files from specified patch dir
    LOG.info("Downloading patch files from patch dir {}".format(patch_dir))
    rc = bld_server_obj.ssh_conn.exec_cmd("test -d " + patch_dir)[0]
    assert rc == 0, "Patch directory path {} not found".format(patch_dir)
    clear_patch_dest_dir()
    patches = download_patches(lab, bld_server_obj, patch_dir)
    if len(patches) == 0:
        pytest.skip("No patch files found in {}:{}.".format(bld_server_obj.name, patch_dir))

    controller_apply_strategy = PatchingVars.get_patching_var('CONTROLLER_APPLY_TYPE')
    storage_apply_strategy = PatchingVars.get_patching_var('STORAGE_APPLY_TYPE')
    compute_apply_strategy = PatchingVars.get_patching_var('COMPUTE_APPLY_TYPE')
    max_parallel_computes = PatchingVars.get_patching_var('MAX_PARALLEL_COMPUTES')
    instance_action = PatchingVars.get_patching_var('INSTANCE_ACTION')
    alarm_restrictions = PatchingVars.get_patching_var('ALARM_RESTRICTIONS')

    if controller_apply_strategy:
        LOG.info("Controller apply type: {}".format(controller_apply_strategy))
    if storage_apply_strategy:
        LOG.info("Storage apply type: {}".format(storage_apply_strategy))
    if compute_apply_strategy:
        LOG.info("Compute apply type: {}".format(compute_apply_strategy))
    if max_parallel_computes:
        LOG.info("Maximum parallel computes: {}".format(max_parallel_computes))
    if instance_action:
        LOG.info("Instance action: {}".format(instance_action))
    if alarm_restrictions:
        LOG.info("Alarm restriction option: {}".format(alarm_restrictions))


    enable_dev_certificate = BuildServerPath.PATCH_ENABLE_DEV_CERTIFICATES[current_release]

    get_patch_dev_enabler_certificate(bld_server_obj, enable_dev_certificate, lab)

    _patching_setup = {'lab': lab, 'output_dir': output_dir, 'build_server': bld_server_obj,
                       'patch_dir': patch_dir, 'enable_dev_certificate': enable_dev_certificate,
                       'patches': patches,
                       'controller_apply_strategy': controller_apply_strategy,
                       'storage_apply_strategy': storage_apply_strategy,
                       'compute_apply_strategy': compute_apply_strategy,
                       'max_parallel_computes': max_parallel_computes,
                       'instance_action': instance_action, 'alarm_restrictions': alarm_restrictions,
                      }

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

    server.ssh_conn.rsync(cert_path, dest_server, patch_dest_dir, ssh_port=None,
                                  pre_opts=pre_opts)


@pytest.fixture(scope='function')
def patch_tear_down(request):

    def remove_on_teardown():
        delete_patch_strategy()
        applied_patches = patching_helper.get_patches_in_state(expected_states='Applied')
        applied_patches = [p for p in applied_patches if "RR_" or "INSVC" in p]
        partial_applied_patches = [p for p in patching_helper.get_partial_applied() if "RR_" or "INSVC" in p]
        if len(applied_patches + partial_applied_patches ) > 0:
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
        if "Test_Patch_Build" in patch_dir:
            server.ssh_conn.rsync(patch_dir + "/*_RR_*.patch", dest_server, patch_dest_dir, ssh_port=ssh_port,
                                  pre_opts=pre_opts)
            server.ssh_conn.rsync(patch_dir + "/*_INSVC_*.patch", dest_server, patch_dest_dir, ssh_port=ssh_port,
                                  pre_opts=pre_opts)
        else:
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


def run_patch_orchestration_strategy(controller_apply_type='serial', storage_apply_type='serial', compute_apply_type='serial',
                              max_parallel_computes=2, instance_action='stop-start', alarm_restrictions='strict'):

    patches_ids = patching_helper.get_patches_in_state(expected_states=['Partial-Apply', 'Partial-Remove'])

    current_alarms_ids = system_helper.get_alarms(mgmt_affecting=True, combine_entries=False)
    affecting_alarms = [id for id in current_alarms_ids if id[0] not in IGNORED_ALARM_IDS]
    if len(affecting_alarms) > 0:
        assert system_helper.wait_for_alarms_gone(alarms=affecting_alarms, timeout=240, fail_ok=True)[0],\
            "Alarms present: {}".format(affecting_alarms)

    LOG.tc_step("Running patch orchestration with parameters: {}.....".format(locals()))

    patching_helper.orchestration_patch_hosts(
            controller_apply_type=controller_apply_type,
            storage_apply_type=storage_apply_type,
            compute_apply_type=compute_apply_type,
            max_parallel_computes=max_parallel_computes,
            instance_action=instance_action,
            alarm_restrictions=alarm_restrictions)

    LOG.info(" Applying Patch orchestration strategy completed for {} ....".format(patches_ids))


@pytest.mark.release_patch
def test_system_patch_orchestration(patch_orchestration_setup):
    """
    This test verifies the patch orchestration operation procedures for release patches. The patch orchestration
    automatically patches all hosts on a system in the following order: controllers, storages, and computes.
    The test creates a patch  orchestration strategy or plan for automated patching operation with the following
    options to customize the test:

    --controller-apply-type : specifies how controllers are patched serially or in parallel.  By default controllers are
    patched always in serial regardless of the selection.
    --storage-apply-type : speciefies how the storages are patched. Possible values are: serial, parallel or ignore. The
    default value is serial.
   --compute-apply-type : speciefies how the computes are patched. Possible values are: serial, parallel or ignore. The
    default value is serial.
    --max-parallel-compute-hosts: specifies the maximum number of computes to patch in parallel. Possible values
    [2 - 100]The default is 2.
    --instance-action - For reboot-required patches,  specifies how the VM instances are moved from compute hosts being
    patched. Possible choices are:
        start-stop - VMs are stopped before compute host is patched.
        migrate - VMs are either live migrated or cold migrated off the compute before applying the patches.


    Args:
        patch_orchestration_setup:

    Returns:

    """

    lab = patch_orchestration_setup['lab']
    check_health(check_patch_ignored_alarms=False)

    LOG.info("Starting patch orchestration for lab {} .....".format(lab))

    patches = patch_orchestration_setup['patches']
    patch_ids = ' '.join(patches.keys())

    LOG.tc_step("Uploading  patches {} ... ".format(patch_ids))
    patch_dest_dir = WRSROOT_HOME + '/patches'
    assert patching_helper.run_patch_cmd("upload-dir", args=patch_dest_dir)[0] in [0, 1],\
        "Failed to upload  patches : {}".format(patch_ids)

    LOG.tc_step("Querying patches ... ")
    assert patching_helper.run_patch_cmd("query")[0] == 0, "Failed to query patches"

    LOG.tc_step("Applying patches ... ")
    rc = patching_helper.run_patch_cmd("apply", args='--all')[0]
    assert rc in [0, 1, 2], "Failed to apply patches"

    LOG.tc_step("Installing patches through orchestration for lab {} .....".format(lab))
    patching_helper.orchestration_patch_hosts(
            controller_apply_type=patch_orchestration_setup['controller_apply_strategy'],
            storage_apply_type=patch_orchestration_setup['storage_apply_strategy'],
            compute_apply_type=patch_orchestration_setup['compute_apply_strategy'],
            max_parallel_computes=patch_orchestration_setup['max_parallel_computes'],
            instance_action=patch_orchestration_setup['instance_action'],
            alarm_restrictions=patch_orchestration_setup['alarm_restrictions'])


@pytest.mark.test_patch
@pytest.mark.parametrize('test_patch_type', ['RR_', 'INSVC_'])
def test_rr_insvc_patch_orchestration(patch_orchestration_setup, test_patch_type, patch_tear_down):
    """
    Verifies apply/remove rr and in-service test patches through patch orchestration
    Args:
        patch_orchestration_setup:
        test_patch_type:
        patch_tear_down:

    Returns:

    """

    downloaded_patches = patch_orchestration_setup['patches']
    patchs = [k for k in downloaded_patches.keys() if "FAILURE" not in k and test_patch_type in k]

    patch_files = [downloaded_patches[patch] for patch in patchs]
    patches_to_upload = ' '.join(patch_files)

    LOG.tc_step("Uploading patch file {} .....".format(patches_to_upload))
    uploaded_ids = patching_helper.upload_patch_files(files=patch_files)[0]

    LOG.info(" Patch {} uploaded .....".format(uploaded_ids))

    LOG.tc_step("Applying patch {} .....".format(uploaded_ids))
    applied = patching_helper.apply_patches(patch_ids=uploaded_ids, apply_all=True)
    LOG.info(" Patch {} applied .....".format(applied))

    LOG.tc_step("Installing patches through orchestration .....")
    run_patch_orchestration_strategy(alarm_restrictions='relaxed')

    LOG.info(" Install patch through orchestration completed for patches {} ....".format(applied))

    LOG.tc_step("Removing test patch {} .....".format(applied))

    patching_helper.remove_patches(patch_ids=' '.join(applied))

    LOG.tc_step("Completing the removal of patches {} through orchestration.....".format(applied))
    run_patch_orchestration_strategy(alarm_restrictions='relaxed')

    LOG.info(" Remove patch through orchestration completed for patches {} ....".format(applied))

    LOG.tc_step("Deleting test patches {} from repo .....".format(applied))
    patching_helper.delete_patches(patch_ids=applied)

    all_patches = patching_helper.get_all_patch_ids()
    assert all(applied) not in all_patches, "Unable to delete patches {} from repo".format(applied)

    LOG.info(" Testing apply/remove through patch orchestration completed for patches {}.....".format(applied))


@pytest.mark.test_patch
@pytest.mark.parametrize('storage_apply_type, compute_apply_type, max_parallel_computes, instance_action, test_patch',
                         [('serial', 'serial', 2, 'migrate', 'RR_NOVA'),
                          ('serial', 'serial', 2, 'migrate', 'INSVC_ALLNODES'),
                          ('serial', 'parallel', 2, 'stop-start', 'RR_COMPUTE'),
                          ('serial', 'parallel', 2, 'stop-start', 'INSVC_NOVA'),
                          ('serial', 'parallel', 2, 'migrate', 'RR_COMPUTE'),
                          ('serial', 'parallel', 2, 'migrate', 'INSVC_NOVA'),
                          ('parallel', 'parallel', 2, 'migrate', 'INSVC_ALLNODES'),
                          ('serial', 'parallel', 4, 'stop-start', 'RR_NOVA'),
                          ('serial', 'parallel', 4, 'stop-start', 'INSVC_COMPUTE')])
def test_patch_orchestration_apply_type(patch_orchestration_setup, storage_apply_type, compute_apply_type,
                                        max_parallel_computes, instance_action, test_patch, patch_tear_down):
    """
    This test verifies the patch orchestration strategy apply type  and instance action options

    Args:
        patch_orchestration_setup:
        storage_apply_type:
        compute_apply_type:
        max_parallel_computes:
        instance_action:
        patch_tear_down:

    Returns:

    """
    personality = test_patch[6:].lower() if 'INSVC' in test_patch else test_patch[3:].lower()

    if 'allnodes' not in personality and 'nova' not in personality and \
                    len(system_helper.get_hostnames(personality=personality)) == 0:
            pytest.skip("No {} hosts in system".format(personality))

    check_health(check_patch_ignored_alarms=False)

    controllers = system_helper.get_hostnames(personality='controller')
    computes = system_helper.get_hostnames(personality='compute')
    storages = system_helper.get_hostnames(personality='storage')
    hosts = controllers + computes + storages
    if "parallel" in storage_apply_type and len(storages) < 4:
        pytest.skip("At leaset two pairs tier storages required for this test: {}".format(storages))
    if "parallel" in compute_apply_type  and len(computes) < (max_parallel_computes + 1):
        pytest.skip("At leaset {} computes are required for this test: {}".format(1 + max_parallel_computes, hosts))

    patches = patch_orchestration_setup['patches']
    patch = [k for k in patches.keys() if test_patch in k][0]
    patch_file =  patches[patch]
    LOG.tc_step("Uploading patch file {} .....".format(patch_file))
    uploaded_id = patching_helper.upload_patch_file(patch_file=patch_file)
    assert patch.strip() == uploaded_id.strip(), " Expected patch {} and uploaded patch {} mismatch"\
        .format(patch, uploaded_id)
    LOG.info(" Patch {} uploaded .....".format(uploaded_id))

    LOG.tc_step("Applying patch {} .....".format(uploaded_id))
    applied = patching_helper.apply_patches(patch_ids=[uploaded_id])
    LOG.info(" Patch {} applied .....".format(applied))

    LOG.tc_step("Installing patches through orchestration for patch {} .....".format(applied))

    run_patch_orchestration_strategy(storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                     max_parallel_computes=max_parallel_computes, instance_action=instance_action,
                                     alarm_restrictions='relaxed')

    LOG.info(" Install patch through orchestration completed for patch {} ....".format(applied))

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


@pytest.mark.test_patch
@pytest.mark.parametrize('ignored_alarm_texts',['HOST_LOCK', 'VM_STOPPED'])
def test_patch_orchestration_with_ignored_alarms(patch_orchestration_setup, ignored_alarm_texts, patch_tear_down):
    """
    This test verifies the patch orchestration operation with presence of alarms that are normally ignored by the
    orchestration. These alarms are '200.001', '700.004,', '900.001', '900.005', '900.101'.  This test generates the
    alarms host lock (200.001) and VM stopped ( 700.004) before executing the patch orchestration.
    Args:
        patch_orchestration_setup:
        ignored_alarm_texts:
        patch_tear_down:

    Returns:

    """
    check_health(check_patch_ignored_alarms=False)

    controllers = system_helper.get_hostnames(personality='controller')
    computes = system_helper.get_hostnames(personality='compute')
    storages = system_helper.get_hostnames(personality='storage')
    hosts = controllers + computes + storages
    host = None
    host_locked = False
    vm_stopped = False

    if 'HOST_LOCK' in ignored_alarm_texts and ( len(computes) <= 1 or len(controllers) == 1):
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
        vm_id_to_stop = None
        if len(vms) > 0:
            vm_id_to_stop = vms[0]
        else:
            LOG.info("No vms running in system; creating one ... ")
            vm_id_to_stop = vm_helper.launch_vms(vm_type='avp', ping_vms=True)[0]
            ResourceCleanup.add("vm", vm_id_to_stop )
        assert vm_id_to_stop, "Fail to launch VM"
        LOG.info("Stop VM {} to generate 700.004 alarm....".format(vm_id_to_stop))
        vm_helper.stop_vms(vm_id_to_stop)
        assert system_helper.wait_for_alarm(alarm_id='700.004')[0], \
            "Timeout waiting for  VM stopped alarm to be generated"

        vm_stopped = True

    if vm_stopped or host_locked:
        patches = patch_orchestration_setup['patches']
        patch = [k for k in patches.keys() if 'RR_ALLNODES' in k][0]
        patch_file =  patches[patch]
        LOG.tc_step("Uploading patch file {} .....".format(patch_file))
        uploaded_id = patching_helper.upload_patch_file(patch_file=patch_file)
        assert patch.strip() == uploaded_id.strip(), " Expected patch {} and uploaded patch {} mismatch"\
            .format(patch, uploaded_id)
        LOG.info(" Patch {} uploaded .....".format(uploaded_id))

        LOG.tc_step("Applying patch {} .....".format(uploaded_id))
        applied = patching_helper.apply_patches(patch_ids=[uploaded_id])
        LOG.info(" Patch {} applied .....".format(applied))
        LOG.tc_step("Installing patch {} through orchestration .....".format(uploaded_id))
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


@pytest.mark.test_patch
def test_patch_orchestration_with_alarms(patch_orchestration_setup,  patch_tear_down):
    """
    This test verifies the patch orchestration operation can not proceed with presence of alarms that are not normally
    ignored by the orchestration.  The test generates the alarm ( 700.002 - VM paused) before executing the patch orchestration.
    Args:
        patch_orchestration_setup:
        alarm_ids:
        patch_tear_down:

    Returns:

    """
    check_health(check_patch_ignored_alarms=False)

    # generate VM paused ( 700.002) critical alarm
    LOG.tc_step("Genenerating VM paused ( 700.002) critical alarm .....")

    vms = nova_helper.get_all_vms()
    vm_id_to_pause = None
    if len(vms) > 0:
        vm_id_to_pause = vms[0]
    else:
        LOG.info("No vms running in system; creating one ... ")
        vm_id_to_pause = vm_helper.launch_vms(vm_type='avp', ping_vms=True)[0]
        ResourceCleanup.add("vm", vm_id_to_pause)

    assert vm_id_to_pause, "Fail to launch VM"
    LOG.info("Pause VM {} to generate 700.002 critical alarm....".format(vm_id_to_pause))
    vm_helper.pause_vm(vm_id_to_pause)
    assert system_helper.wait_for_alarm(alarm_id='700.002')[0], \
        "Timeout waiting for  VM paused alarm to be generated"

    patches = patch_orchestration_setup['patches']
    patch = [k for k in patches.keys() if 'RR_ALLNODES' in k][0]
    patch_file =  patches[patch]
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
    assert rc != 0,  "Patch orchestration strategy created with presense of critical alarm; expected to fail: {}"\
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

