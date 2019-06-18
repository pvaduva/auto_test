from utils.tis_log import LOG
from keywords import glance_helper, vm_helper, nova_helper
from consts.stx import FlavorSpec


def test_boot_windows_guest():
    """
    Boot a windows guest to assist for manual testing on windows guest
    """
    # Change the following parameters to change the vm type.
    guest = 'win_2012'          # such as tis-centos-guest
    storage = 'local_image'          # local_lvm, local_image, or remote
    boot_source = 'image'      # volume or image

    LOG.tc_step("Get/Create {} glance image".format(guest))
    glance_helper.get_guest_image(guest_os=guest)

    LOG.tc_step("Create flavor with {} storage backing".format(storage))
    flv_id = nova_helper.create_flavor(name='{}-{}'.format(storage, guest), vcpus=4, ram=8192,
                                       storage_backing=storage, guest_os=guest)[1]
    nova_helper.set_flavor(flv_id, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    LOG.tc_step("Boot {} vm".format(guest))
    vm_id = vm_helper.boot_vm(name='{}-{}'.format(guest, storage), flavor=flv_id, guest_os=guest, source=boot_source)[1]

    LOG.tc_step("Ping vm and ssh to it")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        code, output = vm_ssh.exec_cmd('pwd', fail_ok=False)
        LOG.info(output)

    LOG.info("{} is successfully booted from {} with {} storage backing".format(guest, boot_source, storage))
