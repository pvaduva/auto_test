import re
from pytest import fixture, mark
from utils.tis_log import LOG

from consts.cgcs import VMStatus, GuestImages
from keywords import network_helper, nova_helper, vm_helper, glance_helper, cinder_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def base_vm():
    internal_net = 'internal0-net1'
    internal_net_id = network_helper.get_net_id_from_name(internal_net)
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()

    mgmt_nic = {'net-id': mgmt_net_id, 'vif-model': 'virtio'}
    tenant_nic = {'net-id': tenant_net_id, 'vif-model': 'virtio'}
    nics = [mgmt_nic,
            {'net-id': internal_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'}]

    vm_id = vm_helper.boot_vm(name='base_vm', nics=nics)[1]
    ResourceCleanup.add('vm', vm_id, scope='module')

    return vm_id, mgmt_nic, tenant_nic, internal_net_id, tenant_net_id


@mark.parametrize(('guest_os', 'if_attach_arg', 'vif_model'), [
    ('tis-centos-guest', 'net_id', 'e1000'),
    ('tis-centos-guest', 'net_id', 'avp'),
    ('tis-centos-guest', 'net_id', 'virtio'),
    ('tis-centos-guest', 'port_id', 'rtl8139')
])
def _test_interface_attach_detach(base_vm, guest_os, if_attach_arg, vif_model):
    """
    Sample test case for interface attach/detach
    Args:
        base_vm (tuple): (base_vm_id, mgmt_nic, internal_net_id)
        if_attach_arg (str): whether to attach via port_id or net_id
        vif_model (str): vif_model to pass to interface-attach cli, or None

    Setups:
        - Boot a base vm with mgmt net and internal0-net1   (module)

    Test Steps:
        - Create a new port on internal0-net1 if attaching port via port_id
        - Boot a vm with mgmt & tenant nic
        - Attach an interface to vm with given if_attach_arg and vif_model
        - Bring up the interface from vm
        - ping between base_vm and vm_under_test over internal0-net1
        - detach the internal interface
        - Verify vm_under_test can no longer ping base_vm over internal0-net1
        - detach the tenant interface
        - Attach the tenant interface back to the vm with net_id and vif_model
        - ping between base_vm and vm_under_test over mgmt & tenant network
        - Perform VM action - Cold migrate, live migrate, pause resume, suspend resume
        - Repeat attach/detach after performing each vm action

    Teardown:
        - Delete created vm, volume, port (if any)  (func)
        - Delete base vm, volume    (module)

    """
    base_vm_id, mgmt_nic, tenant_nic, internal_net_id, tenant_net_id = base_vm

    internal_port_id = None
    if if_attach_arg == 'port_id':
        LOG.tc_step("Create a new port")
        internal_port_id = network_helper.create_port(internal_net_id, 'if_attach_port')[1]
        ResourceCleanup.add('port', internal_port_id)
        internal_net_id = None

    LOG.tc_step("Get/Create {} glance image".format(guest_os))
    image_id = glance_helper.get_guest_image(guest_os=guest_os)
    if not re.search(GuestImages.TIS_GUEST_PATTERN, guest_os):
        ResourceCleanup.add('image', image_id, scope='module')

    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(vcpus=2, guest_os=guest_os)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Create a volume from {} image".format(guest_os))
    code, vol_id = cinder_helper.create_volume(name='vol-' + guest_os, image_id=image_id, guest_image=guest_os,
                                               fail_ok=True)
    ResourceCleanup.add('volume', vol_id)
    assert 0 == code, "Issue occurred when creating volume"
    source_id = vol_id

    LOG.tc_step("Boot a vm with mgmt nic only")
    vm_under_test = vm_helper.boot_vm(name='if_attach_tenant', nics=[mgmt_nic, tenant_nic], source_id=source_id,
                                      guest_os=guest_os)[1]
    ResourceCleanup.add('vm', vm_under_test)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)
    tenant_port_id = nova_helper.get_vm_interfaces_info(vm_id=vm_under_test, net_id=tenant_net_id)[0]['port_id']

    for vm_actions in [['live_migrate'], ['cold_migrate'], ['pause', 'unpause'], ['suspend', 'resume']]:
        LOG.tc_step("Attach internal interface to vm via {} with vif_model: {}".format(if_attach_arg, vif_model))
        internal_port = vm_helper.attach_interface(vm_under_test, net_id=internal_net_id, vif_model=vif_model,
                                                   port_id=internal_port_id)[1]
        if internal_port_id:
            assert internal_port_id == internal_port, "Specified port_id is different than attached port"

        LOG.tc_step("Bring up attached {} internal interface from vm".format(vif_model))
        _bring_up_attached_interface(vm_under_test, guest_os=guest_os)

        LOG.tc_step("Verify VM {} internet0-net1 interface is up".format(vif_model))
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, retry=5, net_types='internal')

        LOG.tc_step("Detach {} internal port {} from VM".format(vif_model, internal_port))
        vm_helper.detach_interface(vm_id=vm_under_test, port_id=internal_port)

        res = vm_helper.ping_vms_from_vm(to_vms=base_vm_id, from_vm=vm_under_test, fail_ok=True, retry=0,
                                         net_types=['internal'])[0]
        assert not res, "Ping from base_vm to vm via detached interface still works"

        LOG.tc_step("Detach tenant interface {} from VM".format(tenant_port_id))
        vm_helper.detach_interface(vm_id=vm_under_test, port_id=tenant_port_id)

        LOG.tc_step("Attach tenant interface back to vm with vif_model: {}".format(vif_model))
        tenant_port_id = vm_helper.attach_interface(vm_under_test, vif_model=vif_model, net_id=tenant_net_id)[1]

        LOG.tc_step("Bring up attached tenant interface from vm")
        _bring_up_attached_interface(vm_under_test, guest_os=guest_os)

        LOG.tc_step("Verify VM tenant interface is up")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, retry=5, net_types=['mgmt','data'])

        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
                        "base vm over management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)
                if action == 'cold_migrate':
                    LOG.tc_step("Bring up all the attached tenant interface from vm after {}".format(vm_actions))
                    _bring_up_attached_interface(vm_under_test, guest_os=guest_os)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management networks still works "
                    "after {}".format(vm_actions))
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt', 'data'])



@mark.parametrize(('guest_os', 'if_attach_arg', 'vif_model'), [
    #('centos_7', 'net_id', 'e1000'),
    ## ('centos_7', 'net_id', 'avp'),
    ## ('centos_7', 'net_id', 'virtio'),
    ##('centos_7', 'port_id', 'rtl8139'),
    ('cgcs-guest', 'net_id', 'avp'),
    ('cgcs-guest', 'net_id', 'e1000'),
    ('cgcs-guest', 'port_id', 'virtio')
    ## ('cgcs-guest', 'net_id', 'rtl8139')

])
def _test_interface_attach_detach_max_vnics(base_vm, guest_os, if_attach_arg, vif_model):
    """
    Sample test case for interface attach/detach to maximum vnics
    Args:
        base_vm (tuple): (base_vm_id, mgmt_nic, internal_net_id)
        if_attach_arg (str): whether to attach via port_id or net_id
        vif_model (str): vif_model to pass to interface-attach cli, or None

    Setups:
        - Boot a base vm with mgmt net and internal0-net1   (module)

    Test Steps:
        - Boot a vm with only mgmt interface
        - Attach an 15 vnics to vm with given if_attach_arg and vif_model
        - Bring up the interface from vm
        - ping between base_vm and vm_under_test over mgmt & tenant network
        - Perform VM action - Cold migrate, live migrate, pause resume, suspend resume
        - Verify ping between base_vm and vm_under_test over mgmt & tenant network after vm operation
        - detach all the tenant interface
        - Repeat attach/detach after performing each vm action

    Teardown:
        - Delete created vm, volume, port (if any)  (func)
        - Delete base vm, volume    (module)

    """
    base_vm_id, mgmt_nic, tenant_nic, internal_net_id, tenant_net_id = base_vm

    nic_action = False

    internal_port_id = None
    if if_attach_arg == 'port_id':
        LOG.tc_step("Create a new port")
        internal_port_id = network_helper.create_port(internal_net_id, 'if_attach_port')[1]
        ResourceCleanup.add('port', internal_port_id)
        internal_net_id = None

    LOG.tc_step("Get/Create {} glance image".format(guest_os))
    image_id = glance_helper.get_guest_image(guest_os=guest_os)
    if not re.search(GuestImages.TIS_GUEST_PATTERN, guest_os):
        ResourceCleanup.add('image', image_id, scope='module')

    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(vcpus=2, guest_os=guest_os)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Create a volume from {} image".format(guest_os))
    code, vol_id = cinder_helper.create_volume(name='vol-' + guest_os, image_id=image_id, guest_image=guest_os,
                                               fail_ok=True)
    ResourceCleanup.add('volume', vol_id)
    assert 0 == code, "Issue occurred when creating volume"
    source_id = vol_id

    LOG.tc_step("Boot a vm with mgmt nic only")
    vm_under_test = vm_helper.boot_vm(name='if_attach_tenant', nics=[mgmt_nic], source_id=source_id,
                                      guest_os=guest_os)[1]
    ResourceCleanup.add('vm', vm_under_test)

    for vm_actions in [['cold_migrate'], ['live_migrate'], ['pause', 'unpause'], ['suspend', 'resume']]:
        tenant_port_ids = []
        LOG.tc_step("atttach maximum number of vnics to the VM")
        vnics_attached=len(nova_helper.get_vm_interfaces_info(vm_id=vm_under_test))
        LOG.info("current nic no {}".format(vnics_attached))
        max_vnics=16
        new_vnics=1
        for nic in range(vnics_attached, max_vnics):
            tenant_port_id = vm_helper.attach_interface(vm_under_test, vif_model=vif_model, net_id=tenant_net_id)[1]
            new_vnics += 1
            tenant_port_ids += [tenant_port_id]
        LOG.info("Attached new vnics to the VM {}".format(tenant_port_ids))

        vnics_attached = len(nova_helper.get_vm_interfaces_info(vm_id=vm_under_test))
        LOG.info("vnics attached to VM: {}" .format(vnics_attached))
        assert vnics_attached == max_vnics, ("vnics attached is not equal to max number.")

        LOG.tc_step("Bring up all the attached new {} {} tenant interface from vm".format(new_vnics, vif_model))
        _bring_up_attached_interface(vm_under_test, guest_os=guest_os, num=new_vnics-1)

        res = vm_helper.attach_interface(vm_under_test, vif_model=vif_model, net_id=tenant_net_id, fail_ok=True)[0]
        assert res == 1, ("vnics attach exceed maximum limit")

        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
                        "base vm over management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                #if action != 'cold_migrate' and guest_os != 'centos_7':
                vm_helper.perform_action_on_vm(vm_under_test, action=action)
                if action == 'cold_migrate':
                    LOG.tc_step("Bring up all the attached tenant interface from vm after {}".format(vm_actions))
                    _bring_up_attached_interface(vm_under_test, guest_os=guest_os, num=new_vnics-1)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management networks still works "
                    "after {}".format(vm_actions))
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt', 'data'])

        LOG.tc_step("Detach all the {} interface {}".format(vif_model, tenant_port_ids))
        for tenant_port_id in tenant_port_ids:
            vm_helper.detach_interface(vm_id=vm_under_test, port_id=tenant_port_id)

        res = vm_helper.ping_vms_from_vm(to_vms=base_vm_id, from_vm=vm_under_test, fail_ok=True, retry=0,
                                          net_types=['data'])[0]
        assert not res, "Ping from base_vm to vm via detached interface still works"


def _bring_up_attached_interface(vm_id, guest_os, num=1):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    vm_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vnics_to_check = vm_nics[-num:]
        for vnic in vnics_to_check:
            mac_addr = vnic['mac_address']
            eth_name = network_helper.get_eth_for_mac(mac_addr=mac_addr, ssh_client=vm_ssh)
            assert eth_name, "Interface with mac {} is not listed in 'ip addr' in vm {}".format(mac_addr, vm_id)
            vm_ssh.exec_sudo_cmd('ip link set dev {} up'.format(eth_name))
            if not re.search(GuestImages.TIS_GUEST_PATTERN, guest_os):
                vm_ssh.exec_sudo_cmd('dhclient {} -r'.format(eth_name))
            vm_ssh.exec_sudo_cmd('dhclient {}'.format(eth_name))

        vm_ssh.exec_sudo_cmd('ip addr')