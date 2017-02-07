from pytest import mark, skip, fixture

from consts.cli_errs import PciAddrErr  # Don't remove - used in eval()
from testfixtures.resource_mgmt import ResourceCleanup
from keywords import vm_helper, network_helper


@mark.parametrize(('unsupported_pci_addr', 'vif_model', 'expt_err'), [
    ('0001:00:10.0', 'virtio', "PciAddrErr.NONE_ZERO_DOMAIN"),
    ('0000:00:00.0', 'e1000', "PciAddrErr.RESERVED_SLOTS_BUS0"),
    ('0000:00:01.0', 'avp', "PciAddrErr.RESERVED_SLOTS_BUS0"),
    ('0000:02:04.0', 'avp', "PciAddrErr.WRONG_BUS_VAL"),
    ('0000:01:00.0', 'virtio', "PciAddrErr.RESERVED_SLOT_ANY_BUS"),
    ('0000:08:02.1', 'virtio', "PciAddrErr.NONE_ZERO_FUNCTION"),
    ('0000:09:1e.0', 'virtio', "PciAddrErr.LARGER_THAN_MAX_BUS"),
    ('0000:08:20.0', 'virtio', "PciAddrErr.LARGER_THAN_MAX_SLOT"),
    ('00:04:1e.0', 'virtio',"PciAddrErr.BAD_FORMAT"),
    ('04:1e', 'virtio', "PciAddrErr.BAD_FORMAT"),
    ('0000:04:1e', 'virtio', "PciAddrErr.BAD_FORMAT"),
    ('0000_04:1e.0', 'virtio', "PciAddrErr.BAD_FORMAT"),
])
def test_boot_vm_with_configurable_pci_addr_negative(unsupported_pci_addr, vif_model, expt_err):
    """
    Verify boot vm with invalid pci_address is rejected.

    Args:
        unsupported_pci_addr (str): invalid pci address
        vif_model (str):
        expt_err (str): expected error returned from nova boot cli

    Test Steps:
        - Attempt to boot a vm with a nic with give vif_model and vif_pci_address
        - Verify nova boot cli is rejected with expected error message

    """
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': vif_model, 'vif-pci-address': unsupported_pci_addr},
            ]
    code, vm_id, output, vol_id = vm_helper.boot_vm(name='pci_negative', source='image', nics=nics, fail_ok=True)
    if vm_id:
        ResourceCleanup.add('vm', vm_id)

    assert code in [1, 4], "Boot VM is not rejected"
    assert eval(expt_err) in output, "Expected error message is not found"


