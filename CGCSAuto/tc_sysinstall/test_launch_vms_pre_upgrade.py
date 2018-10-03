from keywords import install_helper
from utils.tis_log import LOG


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
