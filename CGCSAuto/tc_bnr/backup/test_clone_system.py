

from pytest import fixture, skip
from utils.tis_log import LOG
from keywords import install_helper, system_helper
from consts.proj_vars import InstallVars



@fixture(scope='function')
def pre_system_clone():

    LOG.tc_func_start("CLONE_TEST")
    lab = InstallVars.get_install_var('LAB')

    LOG.info("Preparing lab for system clone....")

    if 'compute_nodes' in lab.keys() or 'storage_nodes' in lab.keys():
        skip("The system {} is not All-in-one; clone is supported only for AIO systems".format(lab))

    assert system_helper.get_active_controller_name() == 'controller-0', "controller-0 is not the active controller"
    LOG.tc_step("Checking if  a USB flash drive is plugged in controller-0 node... ")
    usb_device = install_helper.get_usb_device_name()
    assert usb_device, "No USB found in controller-0"

    usb_size = install_helper.get_usb_disk_size(usb_device)
    LOG.info("Size of {} = {}".format(usb_device, usb_size))
    if not ( usb_size >= 5):
        skip("Insufficient size in {} which is {}; at least 8G is required.".format(usb_device, usb_size))



def test_create_cloned_image(pre_system_clone):
    """
    Test creating cloned image on stable All-in-one (AIO) system.
    Creating a bootable  USB of cloned image

    Args:


    Setup:
        - create system cloned image using config_controller --clone-iso <cloned image name>

    Test Steps:
        - check system is All-in-one and stable for clone
        - check creating cloned image is successfull
        - check the cloned image is copied to bootable USB flash successfully

    Teardown:
        - Delete cloned image iso file in system

    """

    usb_device = install_helper.get_usb_device_name()
    lab = InstallVars.get_install_var('LAB')
    LOG.tc_step("Creating  cloned image for: lab={}")
    install_helper.create_cloned_image(usb_device=usb_device)

