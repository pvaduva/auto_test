import os

import pytest

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient, SSHClient
from consts.cgcs import Prompt, PatchState
from consts.auth import SvcCgcsAuto, HostLinuxCreds
from consts.filepaths import WRSROOT_HOME
from consts.build_server import Server, get_build_server_info
from consts.proj_vars import ProjVar, PatchingVars, InstallVars
from keywords import system_helper, install_helper, patching_helper, orchestration_helper


@pytest.fixture(scope='session')
def patch_orchestration_setup():
    ProjVar.set_var(SOURCE_OPENRC=True)
    patching_helper.check_system_health()

    lab = InstallVars.get_install_var('LAB')
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

    _patching_setup = {'lab': lab, 'output_dir': output_dir, 'build_server': bld_server_obj,
                       'patch_dir': patch_dir,
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


def test_system_patch_orchestration(patch_orchestration_setup):
    """
    This test verifies the patch orchestration operation procedures for release patches. The patch orchestration
    automatically patches all hosts on a system in the following order: controllers, storages, and computes.
    The test creates a patch  orchestration strategy or plan for automated patching operation with the following
    options to customize the test:

    --controller-apply-type : specifies how controllers are patched serially or in parallel.  By default controllers are
    patched always in serial regardless of the selection.
    --storage-apply-type : specifies how the storages are patched. Possible values are: serial, parallel or ignore. The
    default value is serial.
   --compute-apply-type : specifies how the computes are patched. Possible values are: serial, parallel or ignore. The
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
    patching_helper.check_system_health(check_patch_ignored_alarms=False)

    LOG.info("Starting patch orchestration for lab {} .....".format(lab))

    patches = patch_orchestration_setup['patches']
    patch_ids = ' '.join(patches.keys())

    LOG.tc_step("Uploading  patches {} ... ".format(patch_ids))

    patch_dest_dir = WRSROOT_HOME + '/patches'
    rc = patching_helper.run_patch_cmd('upload-dir', args=patch_dest_dir)[0]
    assert rc in [0, 1], "Fail to upload patches in dir {}".format(patch_dest_dir)

    uploaded = patching_helper.get_available_patches()
    if rc == 0:
        LOG.info("Patches uploaded: {}".format(uploaded))
    else:
        LOG.info("Patches are already in repo")

    if len(uploaded) > 0:
        LOG.tc_step("Applying patches ...")
        uploaded_patch_ids = ' '.join(uploaded)
        applied = patching_helper.apply_patches(patch_ids=uploaded_patch_ids)[1]

        LOG.info("Patches applied: {}".format(applied))
    else:
        LOG.info("No Patches are applied; Patches may be already applied: {}")

    partial_patches_ids = patching_helper.get_patches_in_state((PatchState.PARTIAL_APPLY, PatchState.PARTIAL_REMOVE))
    if len(partial_patches_ids) > 0:

        current_alarms_ids = system_helper.get_alarms(mgmt_affecting=True, combine_entries=False)
        affecting_alarms = [id_ for id_ in current_alarms_ids if id_[0] not in orchestration_helper.IGNORED_ALARM_IDS]
        if len(affecting_alarms) > 0:
            assert system_helper.wait_for_alarms_gone(alarms=affecting_alarms, timeout=240, fail_ok=True)[0],\
                "Alarms present: {}".format(affecting_alarms)

        LOG.tc_step("Installing patches through orchestration  .....")
        patching_helper.orchestration_patch_hosts(
                controller_apply_type=patch_orchestration_setup['controller_apply_strategy'],
                storage_apply_type=patch_orchestration_setup['storage_apply_strategy'],
                compute_apply_type=patch_orchestration_setup['compute_apply_strategy'],
                max_parallel_computes=patch_orchestration_setup['max_parallel_computes'],
                instance_action=patch_orchestration_setup['instance_action'],
                alarm_restrictions=patch_orchestration_setup['alarm_restrictions'])

        LOG.info(" Applying Patch orchestration strategy completed for {} ....".format(partial_patches_ids))

        LOG.tc_step("Deleting  patches  orchestration strategy .....")
        delete_patch_strategy()
        LOG.info("Deleted  patch orchestration strategy .....")
    else:
        pytest.skip("All patches in  patch-dir are already in system.")
