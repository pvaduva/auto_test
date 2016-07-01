import random

from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, VMStatus
from keywords import system_helper, vm_helper, nova_helper, network_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def base_setup():

    flavor_id = nova_helper.create_flavor(name='dedicated')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'virtio'}
    ]
    base_vm = vm_helper.boot_vm(flavor=flavor_id, nics=nics)[1]
    ResourceCleanup.add('vm', base_vm, scope='module')

    return base_vm, flavor_id, mgmt_net_id, tenant_net_id, internal_net_id


def id_params(val):
    return '_'.join(val)


class TestMutiPortsBasic:

    vifs_to_test = [('avp', 'avp'),
                    ('virtio', 'virtio'),
                    ('e1000', 'virtio'),
                    ('avp', 'virtio'),]

    @fixture(scope='class', params=vifs_to_test, ids=id_params)
    def vms_to_test(self, request, base_setup):
        """
        Create a vm under test with specified vifs for tenant network
        Args:
            request: pytest param
            base_vm_ (tuple): base vm, flavor, management net, tenant net, interal net to use

        Returns (str): id of vm under test

        """
        vifs = request.param
        base_vm, flavor, mgmt_net_id, tenant_net_id, internal_net_id = base_setup

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}]
        for vif in vifs:
            nics.append({'net-id': tenant_net_id, 'vif-model': vif})

        # add interface for internal net
        nics.append({'net-id': internal_net_id, 'vif-model': 'avp'})

        LOG.info("Boot a vm with following nics: {}".format(nics))
        vm_under_test = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
        ResourceCleanup.add('vm', vm_under_test, scope='class')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

        LOG.info("Ping vm's own data network ips")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types='data')

        LOG.info("Ping vm_under_test from base_vm to verify management and data networks connection")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

        return base_vm, vm_under_test

    @mark.parametrize("vm_actions", [
        (['live_migrate']),
        (['cold_migrate']),
        (['pause', 'unpause']),
        (['suspend', 'resume']),
        (['auto_recover']),
    ], ids=id_params)
    def test_multiports_on_same_network_vm_actions(self, vms_to_test, vm_actions):
        """
        Test vm actions on vm with multiple ports with given vif models on the same tenant network

        Args:
            vifs (tuple): vif models to test. Used when booting vm with tenant network nics info
            net_setups_ (tuple): flavor, networks to use and base vm info

        Setups:
            - create a flavor with dedicated cpu policy (module)
            - choose one tenant network and one internal network to be used by test (module)
            - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox (module)
            - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with base vm,
            and ping it from NatBox      (class)
            - Ping vm2's own data network ips        (class)
            - Ping vm2 from vm1 to verify management and data networks connection    (class)

        Test Steps:
            - Perform given actions on vm2 (migrate, start/stop, etc)
            - Verify ping from vm1 to vm2 over management and data networks still works

        Teardown:
            - Delete created vms and flavor
        """

        base_vm, vm_under_test = vms_to_test

        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from base vm over "
                        "management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works after {}".
                    format(vm_actions))
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    @mark.skipif(True, reason='Evacuation JIRA CGTS-4264')
    def test_multiports_on_same_network_evacuate_vm(self, vms_to_test):
        """
        Test evacuate vm with multiple ports on same network

        Args:
            vifs (tuple): vif models to test. Used when booting vm with tenant network nics info
            net_setups_ (tuple): flavor, networks to use and base vm info

        Setups:
            - create a flavor with dedicated cpu policy (module)
            - choose one tenant network and one internal network to be used by test (module)
            - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox (module)
            - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with base vm,
            and ping it from NatBox     (class)
            - Ping vm2's own data network ips       (class)
            - Ping vm2 from vm1 to verify management and data networks connection   (class)

        Test Steps:
            - Reboot vm2 host
            - Wait for vm2 to be evacuated to other host
            - Wait for vm2 pingable from NatBox
            - Verify ping from vm1 to vm2 over management and data networks still works

        Teardown:
            - Delete created vms and flavor
        """
        base_vm, vm_under_test = vms_to_test
        host = nova_helper.get_vm_host(vm_under_test)

        LOG.tc_step("Reboot vm host {}".format(host))
        host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
        HostsToRecover.add(host, scope='function')

        LOG.tc_step("Verify vm is evacuated to other host")
        vm_helper._wait_for_vm_status(vm_under_test, status=VMStatus.ACTIVE, timeout=120, fail_ok=False)
        post_evac_host = nova_helper.get_vm_host(vm_under_test)
        assert post_evac_host != host, "VM is on the same host after original host rebooted."

        LOG.tc_step("Wait for vm pingable from NatBox after evacuation.")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works after "
                    "evacuation.")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])


######################################################################################################################
@mark.parametrize("vifs", [
    # TC5 same network could be used for 2 SRIOV/PCI-passthrough devices
    ['pci-sriov', 'pci-passthrough'],
    # TC6 same network could be used for 2, 3, 4, … N network attachments
    ['avp', 'virtio', 'e1000', 'pci-passthrough', 'pci-sriov']
])
def a_test_vm_ports_network_pci_1(vifs, net_setups_):
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


@mark.parametrize("vifs", [
    [['virtio', 'avp', 'avp'], ['virtio', 'avp']]     # TC7 same_network_could_be_used_with_same_vif-model
])
def a_test_vm_ports_network_2(vifs, net_setups_):

    mgmt_net_id = net_setups_[1]      # network_helper.get_mgmt_net_id()
    tenant_net_id = net_setups_[2]    # network_helper.get_tenant_net_id()

    nics = []
    nic = dict()
    nic['net-id'] = mgmt_net_id

    for vif in vifs[0]:
        nic['vif-model'] = vif
        nics.append(nic.copy())
        nic.clear()
        nic['net-id'] = tenant_net_id

    LOG.tc_step("linyu:1111111:{}".format(nics))

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
    for vif in vifs[1]:
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


@mark.parametrize("vifs", [
    # TC8 The VM is pingable from both interfaces from the perspective of another VM)
    [['virtio', 'avp', 'pci-sriov', 'pci-passthrough', 'pci-sriov', 'pci-sriov'],
    ['virtio', 'virtio', 'pci-sriov', 'avp']]

])
def a_test_vm_ports_network_pci_2(vifs, net_setups_):

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

    for vif in vifs[0]:
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
    for vif in vifs[1]:
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
