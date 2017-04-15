from utils.tis_log import LOG
from keywords import glance_helper, vm_helper


def test_boot_windows_guest():
    """
    Boot a windows guest from volume to assist for manual testing on windows guest
    """
    guest = 'win_2012'

    guest = 'tis-centos-guest'
    LOG.tc_step("Get/Create {} glance image".format(guest))
    glance_helper.get_guest_image(guest_os=guest)

    LOG.tc_step("Boot {} vm".format(guest))
    vm_helper.boot_vm(name='{}'.format(guest), guest_os=guest)

    LOG.info("VM is booted")
