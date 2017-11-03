import time
from pytest import mark, fixture, skip
from utils.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG
from keywords import install_helper, host_helper, system_helper, cinder_helper, \
    storage_helper,  local_storage_helper, glance_helper, vm_helper, nova_helper, common
from consts.cgcs import EventLogID, GuestImages,Networks
from consts.build_server import Server, get_build_server_info
from consts.auth import SvcCgcsAuto, Tenant
from consts.cgcs import Prompt
from consts.filepaths import WRSROOT_HOME, TestServerPath
from consts.proj_vars import ProjVar, InstallVars
from testfixtures.resource_mgmt import ResourceCleanup


def test_launch_vms_using_scripts_pre_upgrade():
    """
    This test uses the launch instance scripts created by lab_setup to launch the VMs if not created by lab
    automated installer before doing upgrade to the next release.

    Args:


    Returns:

    """
    LOG.tc_step("Launching VMs  pre upgrade ...")
    #
    vms = install_helper.launch_vms_post_install()
    assert len(vms) > 0, "Failed to launch VMs: {}".format(vms)


