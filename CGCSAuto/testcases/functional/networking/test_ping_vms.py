import time
from pytest import mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec

from keywords import vm_helper, glance_helper, nova_helper, network_helper, cinder_helper, check_helper

from testfixtures.resource_mgmt import ResourceCleanup


def id_gen(val):
    if not isinstance(val, str):
        new_val = []
        for val_1 in val:
            if not isinstance(val_1, str):
                val_1 = '_'.join([str(val_2).lower() for val_2 in val_1])
            new_val.append(val_1)
        new_val = '_'.join(new_val)
    else:
        new_val = val

    return new_val


def _append_nics(vifs, net_ids, nics):
    for i in range(len(vifs)):
        vif = vifs[i]
        net_id = net_ids[i]
        vif_model, pci_addr = vif
        nic = {'net-id': net_id, 'vif-model': vif_model}
        if pci_addr is not None:
            pci_prefix, pci_append = pci_addr.split(':')
            pci_append_incre = format(int(pci_append, 16) + i, '02x')
            nic['vif-pci-address'] = ':'.join(['0000', pci_prefix, pci_append_incre]) + '.0'
        nics.append(nic)

    return nics


@mark.parametrize(('guest_os', 'vifs'), [
    mark.priorities('cpe_sanity', 'sanity')(('cgcs-guest', (('avp', None), ('virtio', '01:04')))),
    mark.priorities('cpe_sanity', 'sanity')(('ubuntu_14', (('e1000', '00:1f'), ('virtio', None)))),
    ('ubuntu_14', (('avp', '08:1f'), ('virtio', '00:02')))
], ids=id_gen)
def test_ping_between_two_vms(guest_os, vifs, ubuntu14_image):
    """
    Ping between two cgcs-guest/ubuntu vms with virtio and avp vif models

    Test Steps:
        - Create a favor with dedicated cpu policy and proper root disk size
        - Create a volume from guest image under test with proper size
        - Boot a vm with vif model avp for data and internal networks from above volume with above flavor
        - Ping VM from NatBox
        - Repeat previous 3 steps with vif model virtio
        - Ping betweem two vms via management, data and internal networks

    Test Teardown:
        - Delete vms, volumes, flavor created

    """
    # determine the disk size and image id based on the guest os under test

    if guest_os == 'ubuntu_14':
        image_id = ubuntu14_image
        size = 9
    else:
        image_id = glance_helper.get_image_id_from_name('cgcs-guest')
        size = 1

    LOG.tc_step("Create a favor with {}G root disk and dedicated cpu policy".format(size))
    flavor_id = nova_helper.create_flavor(name='dedicated-{}g'.format(size), root_disk=size)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    # vif_models = ['avp', 'virtio'] if guest_os == 'cgcs-guest' else ['virtio', 'virtio']
    vms = []
    vms_nics = []
    for i in range(2):
        # compose vm nics
        nics = _append_nics(vifs, [tenant_net_id, internal_net_id], [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}])

        LOG.tc_step("Create a {}G volume from {} image".format(size, guest_os))
        vol_id = cinder_helper.create_volume(name='vol-{}'.format(guest_os), image_id=image_id, size=size)[1]
        ResourceCleanup.add('volume', vol_id)

        LOG.tc_step("Boot a {} vm with {} vifs from above flavor and volume".format(guest_os, vifs))
        vm_id = vm_helper.boot_vm('{}_vifs'.format(guest_os), flavor=flavor_id,
                                  source='volume', source_id=vol_id, nics=nics, guest_os=guest_os)[1]
        ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

        LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_id))
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

        # vm_helper.ping_vms_from_vm(vm_id, vm_id, net_types=['data', 'internal'])
        vms.append(vm_id)
        vms_nics.append(nics)

    LOG.tc_step("Check vif pci address for both vms")
    check_helper.check_vm_pci_addr(vms[0], vms_nics[0])
    check_helper.check_vm_pci_addr(vms[1], vms_nics[1])

    LOG.tc_step("Ping between two vms over management, data, and internal networks")
    vm_helper.ping_vms_from_vm(to_vms=vms[0], from_vm=vms[1], net_types=['mgmt', 'data', 'internal'])
    vm_helper.ping_vms_from_vm(to_vms=vms[1], from_vm=vms[0], net_types=['mgmt', 'data', 'internal'])


# Remove following test from regression due to ping is tested in other guest os test cases.
@mark.p3
@mark.features('guest_os')
@mark.usefixtures('centos7_image',
                  'centos6_image',
                  'ubuntu14_image',
                  'opensuse12_image',
                  'opensuse11_image',
                  'rhel7_image')
@mark.parametrize('guest_os', [
    'centos_7',
    'centos_6',
    'ubuntu_14',
    'opensuse_12',
    'opensuse_11',
    'rhel_7',
])
def _test_ping_vm_basic(guest_os):
    """
    Args:
    guest_os (str): guest os to test

    Setups:
        - scp various guest images from test server to /home/wrsroot/images     (session)
        - create glance image from it    (session)

    Test Steps:
        - create a flavor with dedicated cpu policy
        - Boot two vms from volume/image with above flavor and specified guest os
        - Ping vm from NatBox
        - Ping vm from the other vm

     Teardown:
        - Delete created vm, volume, flavor

    """
    vm_id = vm_helper.boot_vm(name=guest_os, guest_os=guest_os)[1]
    ResourceCleanup.add('vm', vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    vm_helper.ping_vms_from_vm(vm_id, vm_id, net_types=['mgmt'])
