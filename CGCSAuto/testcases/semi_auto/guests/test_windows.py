from utils.tis_log import LOG
from keywords import glance_helper, vm_helper, nova_helper


def test_boot_windows_guest():
    """
    Boot a windows guest to assist for manual testing on windows guest
    """
    # Change the following parameters to change the vm type.
    guest = 'win_2012'          # such as tis-centos-guest
    storage = 'local_lvm'          # local_lvm, local_image, or remote
    boot_source = 'volume'      # volume or image

    LOG.tc_step("Get/Create {} glance image".format(guest))
    glance_helper.get_guest_image(guest_os=guest)

    LOG.tc_step("Create flavor with {} storage backing".format(storage))
    flv_id = nova_helper.create_flavor(name='{}-{}'.format(storage, guest), storage_backing=storage, guest_os=guest)[1]

    LOG.tc_step("Boot {} vm".format(guest))
    vm_helper.boot_vm(name='{}-{}'.format(guest, storage), flavor=flv_id, guest_os=guest, source=boot_source)

    LOG.info("VM is booted")