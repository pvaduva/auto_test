from utils.tis_log import LOG
from keywords import glance_helper, vm_helper, nova_helper


def test_boot_ge_edge_uefi():
    guest = 'ge_edge'
    LOG.tc_step("Get ge_edge guest image from test server and create glance image with uefi property")
    glance_helper.get_guest_image(guest_os=guest, rm_image=True)

    LOG.tc_step("Create a flavor for ge_edge vm")
    flavor = nova_helper.create_flavor(guest_os=guest)[1]

    LOG.tc_step("Launch a GE_EDGE vm with UEFI boot")
    vm_helper.boot_vm(name='ge_edge_uefi', flavor=flavor, guest_os=guest)
