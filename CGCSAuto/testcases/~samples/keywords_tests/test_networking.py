
from utils.tis_log import LOG

from testfixtures.fixture_resources import ResourceCleanup
from keywords import vm_helper, network_helper


def test_fip():
    vm_id = vm_helper.boot_vm(name='snat', reuse_vol=False)[1]
    ResourceCleanup.add('vm', vm_id, scope='module')

    LOG.tc_step("Ping from NatBox")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False, use_fip=False)

    LOG.tc_step("Create a floating ip and associate it to VM")
    floatingip = network_helper.create_floating_ip()[1]
    ResourceCleanup.add('floating_ip', floatingip, scope='module')
    network_helper.associate_floating_ip(floatingip, vm_id, fip_val='ip')

    # vm_helper.ping_vms_from_natbox(vm_id, use_fip=False)      TODO: used to work before Mitaka, but should not work?
    LOG.tc_step("Ping vm's floating ip from NatBox and ensure it's pingable")
    vm_helper.ping_vms_from_natbox(vm_id, use_fip=True)

    LOG.tc_step("Attempt to ping vm's private ip from NatBox")
    vm_helper.ping_vms_from_natbox(vm_id, use_fip=False)

