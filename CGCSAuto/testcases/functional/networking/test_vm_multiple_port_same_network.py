import random

from pytest import fixture, mark, skip

from utils import table_parser
from utils.tis_log import LOG

# from consts.auth import Tenant
# from consts.cgcs import VMStatus, FlavorSpec
from keywords import system_helper, vm_helper, nova_helper, host_helper, network_helper, cinder_helper
from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus, EventLogID

from testfixtures.resource_mgmt import ResourceCleanup
# from testfixtures.wait_for_hosts_recover import HostsToWait


@fixture(scope='module')
def net_setups_(request):

    # create flavor
    flavor_id = nova_helper.create_flavor(name='dedicated')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {'hw:cpu_policy': 'dedicated'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    # get net IDs
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'virtio'}
    ]
    base_vm = vm_helper.boot_vm(flavor=flavor_id, nics=nics)[1]
    #ResourceCleanup.add('vm', base_vm, scope='module')

    return flavor_id, mgmt_net_id, tenant_net_id, internal_net_id, base_vm

# {
@mark.parametrize("vifs", [
        ['avp', 'avp'],      # TC1 same_network_could_be_used_with_same_vif-model
        ['virtio', 'virtio'],# TC2 same_network_could_be_used_with_same_vif-model
        ['e1000', 'virtio'], # TC3 same_network_could_be_used_with_different_vif-models
        ['avp', 'virtio']    # TC4 The same network could be used for 2 virtual devices (e.g., virtio, avp)
])
def test_vm_ports_network_1(vifs, net_setups_):

    flavor, mgmt_net_id, tenant_net_id, internal_net_id, base_vm = net_setups_

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'avp'}]
    for vif in vifs:
        nics.append({'net-id': tenant_net_id, 'vif-model': vif})

    LOG.tc_step("linyu::{}".format(nics))

    vm = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
    #ResourceCleanup.add('vm', vm)
    vm_helper.wait_for_vm_pingable_from_natbox(vm, fail_ok=False)

    LOG.tc_step("Ping from base_vm to verify the data connection ")
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=base_vm, net_types=['mgmt', 'data'])

    # vm_helper.live_migrate_vm(vm)
    # LOG.tc_step("Live migrate the VM and verify ping from natbox")
    # vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Cold migrate the VM and verify ping from natbox")
    vm_helper.cold_migrate_vm(vm)
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Pause and un-pause the VM and verify ping from natbox")
    vm_helper.pause_vm(vm)
    vm_helper.unpause_vm(vm)

    LOG.tc_step("Suspend and resume the VM and verify ping")
    vm_helper.suspend_vm(vm)
    vm_helper.resume_vm(vm)
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Verify vm auto recovery is True by setting vm to error state.")
    vm_helper.set_vm_state(vm_id=vm, error_state=True, fail_ok=False)
    vm_helper.wait_for_vm_values(vm_id=vm, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=base_vm, net_types=['mgmt', 'data'])
#}


# {
@mark.parametrize("vifs", [
    # TC5 same network could be used for 2 SRIOV/PCI-passthrough devices
    ['pci-sriov', 'pci-passthrough'],
    # TC6 same network could be used for 2, 3, 4, … N network attachments
    ['avp', 'virtio', 'e1000', 'pci-passthrough', 'pci-sriov']
])
def test_vm_ports_network_pci_1(vifs, net_setups_):
    flavor, mgmt_net_id, tenant_net_id, internal_net_id, base_vm = net_setups_     # network_helper.get_mgmt_net_id()

    # check to see if the lab support the pci interface
    providernet = network_helper.get_provider_net_for_interface(interface='sriov', rtn_val='name')

    if not providernet:
        skip("*******The lab is not support the pci interface*******")

    netids = network_helper.get_networks_on_providernet(providernet)

    # only need one
    tenant_net_id = random.choice(netids)

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'avp'}]
    for vif in vifs:
        nics.append({'net-id': tenant_net_id, 'vif-model': vif})

    LOG.tc_step("8888888888888888 nics={}".format(nics))

    LOG.tc_step("Boot a vm with interfaces under same data network with following vif models: {} ".format(vifs))
    vm = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
    #ResourceCleanup.add('vm', vm)
    vm_helper.wait_for_vm_pingable_from_natbox(vm, fail_ok=False)

    LOG.tc_step("Boot second vm with interfaces under same data network with following vif models: {} ".format(vifs))
    vm2 = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
    #ResourceCleanup.add('vm', vm2)
    vm_helper.wait_for_vm_pingable_from_natbox(vm2, fail_ok=False)



    LOG.tc_step("Ping from base_vm to verify the data connection ")
    #vm_helper.ping_vms_from_vm(vm, base_vm, net_types=['mgmt','data'])
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=vm2, net_types=['mgmt', 'data'])

    vm_helper.cold_migrate_vm(vm)
    LOG.tc_step("Cold migrate the VM and ping from another vm over data and management network")
    # vm_helper.ping_vms_from_natbox(vm)
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=vm2, net_types=['mgmt', 'data'])

    LOG.tc_step("Pause and un-pause the VM and verify ping from natbox")
    vm_helper.pause_vm(vm)
    vm_helper.unpause_vm(vm)
    vm_helper.ping_vms_from_natbox(vm)

    LOG.tc_step("Suspend and resume the VM and verify ping")
    vm_helper.suspend_vm(vm)
    vm_helper.resume_vm(vm)
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=vm2, net_types=['mgmt', 'data'])

    LOG.tc_step("Verify vm auto recovery is True by setting vm to error state.")
    vm_helper.set_vm_state(vm_id=vm, error_state=True, fail_ok=False)
    vm_helper.wait_for_vm_values(vm_id=vm, status=VMStatus.ACTIVE, fail_ok=False, timeout=600)
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=vm2, net_types=['mgmt', 'data'])
# }


# {
@mark.parametrize("vifss", [
    [['virtio', 'avp', 'avp'], ['virtio', 'avp']]     # TC7 same_network_could_be_used_with_same_vif-model
])
def test_vm_ports_network_2(vifss, net_setups_):

    mgmt_net_id = net_setups_[1]      # network_helper.get_mgmt_net_id()
    tenant_net_id = net_setups_[2]    # network_helper.get_tenant_net_id()

    nics = []
    nic = dict()
    nic['net-id'] = mgmt_net_id

    for vif in vifss[0]:
        nic['vif-model'] = vif
        nics.append(nic.copy())
        nic.clear()
        nic['net-id'] = tenant_net_id

    LOG.tc_step("linyu:1111111:{}".format(nics))

    #   get flavor flavor-show

    flavor = net_setups_[0]

    vm = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
    ResourceCleanup.add('vm', vm)

    vm_helper.wait_for_vm_pingable_from_natbox(vm, fail_ok=False)
    LOG.tc_step("Ping VM {} from natbox".format(vm))
    vm_helper.ping_vms_from_natbox(vm)

    # build for VM2, data from vifss[1]
    nics.clear()
    nic.clear()
    nic['net-id'] = mgmt_net_id
    for vif in vifss[1]:
        nic['vif-model'] = vif
        nics.append(nic.copy())
        nic.clear()
        nic['net-id'] = tenant_net_id

    LOG.tc_step("linyu:vm2:{}".format(nics))
    vm2 = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
    ResourceCleanup.add('vm', vm2)


    vm_helper.wait_for_vm_pingable_from_natbox(vm2, fail_ok=False)
    LOG.tc_step("Ping VM {} from natbox".format(vm2))
    vm_helper.ping_vms_from_natbox(vm2)

    LOG.tc_step("Ping VM {} from VM {}".format(vm, vm2))
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=vm2, fail_ok=False)

# }

# {
@mark.parametrize("vifss", [
    # TC8 The VM is pingable from both interfaces from the perspective of another VM)
    [['virtio', 'avp', 'pci-sriov', 'pci-passthrough', 'pci-sriov', 'pci-sriov'],
    ['virtio', 'virtio', 'pci-sriov', 'avp']]

])
def test_vm_ports_network_pci_2(vifss, net_setups_):

    mgmt_net_id = net_setups_[1]           # network_helper.get_mgmt_net_id()

    system_hosts = system_helper.get_hostnames()

    # check if the compute node is available
    computes = ['compute-0', 'compute-1']
    hosts = [host for host in computes if host in system_hosts]
    if not len(hosts):
        skip("*******No compute node available, check for lab set up*******")

    hostname = hosts[0]

    table_ = system_helper.get_interfaces(hostname, con_ssh=None)

    if len(table_) == 0:
        skip("*******No interface, check for lab set up*******")

    # check to see if the lab support  the pci interface
    providernet = network_helper.get_provider_net_for_interface(interface='sriov', rtn_val='name')
    if not len(providernet):
        skip("*******The lab is not support the pci interface*******")

    exit_code, netids = network_helper.get_net_list_on_providernet(providernet=providernet)
    if exit_code:
        skip("*******The lab issue: can not get provider networks*******")

    # only need last one
    tenant_net_id = netids[-1]

    # build for VM1, data from vifss[0]
    nics = []
    nic = dict()
    nic['net-id'] = mgmt_net_id

    for vif in vifss[0]:
        nic['vif-model'] = vif
        nics.append(nic.copy())
        nic.clear()
        nic['net-id'] = tenant_net_id

    #   get flavor flavor-show
    flavor = net_setups_[0]

    vm = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
    ResourceCleanup.add('vm', vm)

    vm_helper.wait_for_vm_pingable_from_natbox(vm, fail_ok=False)
    LOG.tc_step("Ping VM {} from natbox".format(vm))
    vm_helper.ping_vms_from_natbox(vm)

    # build for VM2, data from vifss[1]
    nics.clear()
    nic.clear()
    nic['net-id'] = mgmt_net_id
    for vif in vifss[1]:
        nic['vif-model'] = vif
        nics.append(nic.copy())
        nic.clear()
        nic['net-id'] = tenant_net_id

    LOG.tc_step("linyu:vm2:{}".format(nics))
    vm2 = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
    ResourceCleanup.add('vm', vm2)

    vm_helper.wait_for_vm_pingable_from_natbox(vm2, fail_ok=False)
    LOG.tc_step("Ping VM {} from natbox".format(vm2))
    vm_helper.ping_vms_from_natbox(vm2)

    LOG.tc_step("Ping VM {} from VM {}".format(vm, vm2))
    vm_helper.ping_vms_from_vm(to_vms=vm, from_vm=vm2, fail_ok=False)

#   }
