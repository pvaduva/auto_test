import re
from pytest import fixture, mark, skip
from utils.tis_log import LOG

from consts.cgcs import VMStatus, GuestImages, Prompt
from keywords import network_helper, nova_helper, vm_helper, glance_helper, cinder_helper, system_helper


def id_gen(val):
    if not isinstance(val, str):
        new_val = []
        for val_1 in val:
            if isinstance(val_1, (tuple, list)):
                val_1 = '_'.join([str(val_2).lower() for val_2 in val_1])
            new_val.append(val_1)
    else:
        new_val = [val]

    return '_'.join(new_val)


@fixture(scope='module')
def base_vm():
    internal_net_id = network_helper.get_internal_net_id()
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()

    mgmt_nic = {'net-id': mgmt_net_id}
    tenant_nic = {'net-id': tenant_net_id}
    nics = [mgmt_nic,
            {'net-id': internal_net_id},
            {'net-id': tenant_net_id}]

    vm_id = vm_helper.boot_vm(name='base_vm', nics=nics, cleanup='module')[1]

    return vm_id, mgmt_nic, tenant_nic, internal_net_id, tenant_net_id, mgmt_net_id


@mark.nics
@mark.parametrize(('guest_os', 'if_attach_arg', 'vifs'), [
    ('tis-centos-guest', 'net_id', [('virtio', 2)]),
    ('tis-centos-guest', 'port_id', [('avp', 8), ('rtl8139', 7)]),
    ('vxworks', 'net_id', [('e1000', 0)])
], ids=id_gen)
def test_interface_attach_detach_max_vnics(guest_os, if_attach_arg, vifs, skip_for_ovs, base_vm):
    """
    Sample test case for interface attach/detach to maximum vnics

    Setups:
        - Boot a base vm with mgmt net and internal0-net1   (module)

    Test Steps:
        - Boot a vm with only mgmt interface
        - Attach an vifs to vm with given if_attach_arg and vif_model
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
    if guest_os == 'vxworks' and not system_helper.is_avs():
        skip('e1000 vif unsupported by OVS')

    base_vm_id, mgmt_nic, tenant_nic, internal_net_id, tenant_net_id, mgmt_net_id = base_vm

    glance_vif = None
    if not (if_attach_arg == 'port_id' and system_helper.is_avs()):
        for vif in vifs:
            if vif[0] in ('e1000', 'rtl8139'):
                glance_vif = vif[0]
                break

    LOG.tc_step("Get/Create {} glance image".format(guest_os))
    cleanup = None if (not glance_vif and re.search(GuestImages.TIS_GUEST_PATTERN, guest_os)) else 'function'
    image_id = glance_helper.get_guest_image(guest_os=guest_os, cleanup=cleanup,
                                             use_existing=False if cleanup else True)

    if glance_vif:
        glance_helper.set_image(image_id, hw_vif_model=glance_vif, new_name='{}_{}'.format(guest_os, glance_vif))

    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(vcpus=1, guest_os=guest_os, cleanup='function')[1]

    LOG.tc_step("Create a volume from {} image".format(guest_os))
    code, vol_id = cinder_helper.create_volume(name='vol-' + guest_os, source_id=image_id, fail_ok=True,
                                               guest_image=guest_os, cleanup='function')
    assert 0 == code, "Issue occurred when creating volume"
    source_id = vol_id

    LOG.tc_step("Boot a vm with mgmt nic only")
    vm_under_test = vm_helper.boot_vm(name='if_attach_tenant', nics=[mgmt_nic], source_id=source_id, flavor=flavor_id,
                                      guest_os=guest_os, cleanup='function')[1]
    prev_port_count = 1
    for vm_actions in [['live_migrate'], ['cold_migrate'], ['pause', 'unpause'], ['suspend', 'resume'],
                       ['stop', 'start']]:
        tenant_port_ids = []
        if 'vxworks' not in guest_os:
            LOG.tc_step("Attach specified vnics to the VM before {} and bring up interfaces".format(vm_actions))
            expt_vnics = 1
            for vif in vifs:
                vif_model, vif_count = vif
                expt_vnics += vif_count
                LOG.info("iter {}".format(vif_count))
                for i in range(vif_count):
                    if if_attach_arg == 'port_id':
                        vif_model = vif_model if system_helper.is_avs() else None
                        port = network_helper.create_port(net_id=tenant_net_id, wrs_vif=vif_model, cleanup='function',
                                                          name='attach_{}_{}'.format(vif_model, i))[1]
                        kwargs = {'port_id': port}
                    else:
                        kwargs = {'net_id': tenant_net_id}
                    tenant_port_id = vm_helper.attach_interface(vm_under_test, **kwargs)[1]
                    tenant_port_ids.append(tenant_port_id)
                LOG.info("Attached new vnics to the VM {}".format(tenant_port_ids))

            vm_ports_count = len(network_helper.get_ports(server=vm_under_test))
            LOG.info("vnics attached to VM: {}" .format(vm_ports_count))
            assert vm_ports_count == expt_vnics, "vnics attached is not equal to max number."

            LOG.info("Bring up all the attached new vifs {} on tenant net from vm".format(vifs))
            _bring_up_attached_interface(vm_under_test, ports=tenant_port_ids, guest_os=guest_os, base_vm=base_vm_id)

            if expt_vnics == 16:
                LOG.tc_step("Verify no more vnic can be attached after reaching upper limit 16")
                res = vm_helper.attach_interface(vm_under_test, net_id=tenant_net_id,
                                                 fail_ok=True)[0]
                assert res == 1, "vnics attach exceed maximum limit"

        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
                        "base vm over management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
            # if 'vxworks' not in guest_os:
            #     _bring_up_attached_interface(vm_under_test, guest_os=guest_os, num=new_vnics)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)
                if action == 'cold_migrate' or action == 'start':
                    LOG.tc_step("Bring up all the attached tenant interface from vm after {}".format(vm_actions))
                    # if 'vxworks' not in guest_os:
                    #     _bring_up_attached_interface(vm_under_test, guest_os=guest_os, num=new_vnics)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        if 'vxworks' not in guest_os:
            LOG.tc_step("Verify ping from base_vm to vm_under_test over management networks still works "
                        "after {}".format(vm_actions))
            vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt', 'data'], retry=10)

            LOG.tc_step("Detach all attached interface {} after {}".format(tenant_port_ids, vm_actions))
            for tenant_port_id in tenant_port_ids:
                vm_helper.detach_interface(vm_id=vm_under_test, port_id=tenant_port_id, cleanup_route=True)

            vm_ports_count = len(network_helper.get_ports(server=vm_under_test))
            assert prev_port_count == vm_ports_count, "VM ports still listed after interface-detach"
            res = vm_helper.ping_vms_from_vm(to_vms=base_vm_id, from_vm=vm_under_test, fail_ok=True, retry=0,
                                             net_types=['data'])[0]
            assert not res, "Detached interface still works"


@mark.parametrize(('guest_os', 'boot_source', 'vifs'), [
    ('tis-centos-guest', 'image', [('avp', 14)]),
    ('tis-centos-guest', 'volume', [('avp', 1), ('virtio', 1)])
], ids=id_gen)
def test_interface_attach_detach_on_paused_vm(guest_os, boot_source, vifs, skip_for_ovs, base_vm):
    """
    Sample test case for interface attach/detach on stopped vm

    Setups:
        - Boot a base vm with mgmt net and tenant_port_id (module)

    Test Steps:
        - Boot a vm with mgmt and avp port interface
        - Pause the vm
        - Attach an vifs to vm with given if_attach_arg and vif_model
        - perform live migration on paused vm
        - unpause the vm
        - Bring up the interface from vm
        - ping between base_vm and vm_under_test over mgmt & tenant network
        - detach all the tenant interface
        - Verify ping to tenant interfaces fail

    Teardown:
        - Delete created vm, volume, port (if any)  (func)
        - Delete base vm, volume    (module)

    """

    base_vm_id, mgmt_nic, tenant_nic, internal_net_id, tenant_net_id, mgmt_net_id = base_vm
    LOG.tc_step("Create a avp port")
    init_port_id = network_helper.create_port(tenant_net_id, 'tenant_avp_port', wrs_vif='avp', cleanup='function')[1]
    tenant_net_nic = {'port-id': init_port_id, 'vif-model': 'avp'}

    LOG.tc_step("Get/Create {} glance image".format(guest_os))
    cleanup = None if re.search(GuestImages.TIS_GUEST_PATTERN, guest_os) else 'module'
    image_id = glance_helper.get_guest_image(guest_os=guest_os, cleanup=cleanup)

    LOG.tc_step("Boot a {} vm and flavor from {} with a mgmt and a data interface".format(guest_os, boot_source))
    vm_under_test = vm_helper.boot_vm('if_attach-{}-{}'.format(guest_os, boot_source),
                                      nics=[mgmt_nic, tenant_net_nic], source=boot_source, image_id=image_id,
                                      guest_os=guest_os, cleanup='function')[1]

    _ping_vm_data(vm_under_test=vm_under_test, base_vm_id=base_vm_id, action='boot')

    LOG.tc_step("Pause vm {} before attaching interfaces".format(vm_under_test))
    vm_helper.perform_action_on_vm(vm_under_test, action='pause')

    LOG.tc_step("Create and attach vnics to the VM: {}".format(vifs))
    tenant_port_ids = network_helper.get_ports(server=vm_under_test, network=tenant_net_id)
    expt_vnics = 2
    new_vnics = 0
    for vif in vifs:
        vif_model, vif_count = vif
        expt_vnics += vif_count
        LOG.info("iter {}".format(vif_count))
        LOG.info("Create and attach {} {} vnics to vm {}".format(vif_count, vif_model, vm_under_test))
        for i in range(vif_count):
            name = 'attached_port-{}_{}'.format(vif_model, i)
            port_id = network_helper.create_port(net_id=tenant_net_id, name=name, wrs_vif=vif_model,
                                                 cleanup='function')[1]
            vm_helper.attach_interface(vm_under_test, port_id=port_id)
            new_vnics += 1
            tenant_port_ids.append(port_id)

    vm_ports_count = len(network_helper.get_ports(server=vm_under_test))
    LOG.info("vnics attached to VM: {}".format(vm_ports_count))
    assert vm_ports_count == expt_vnics, "vnics attached is not equal to max number."

    if expt_vnics == 16:
        res = vm_helper.attach_interface(vm_under_test, net_id=tenant_net_id, fail_ok=True)[0]
        assert res == 1, "vnics attach exceed maximum limit"

    LOG.tc_step("Live migrate paused vm")
    vm_helper.perform_action_on_vm(vm_under_test, action='live_migrate')

    LOG.tc_step("Unpause live-migrated vm, bring up attached interfaces and ping the VM")
    vm_helper.perform_action_on_vm(vm_under_test, action='unpause')
    _bring_up_attached_interface(vm_under_test, guest_os=guest_os, ports=tenant_port_ids, base_vm=base_vm_id,
                                 action='pause, attach interfaces, live migrate and unpause')

    LOG.tc_step("Live migrate again after unpausing the vm")
    vm_helper.perform_action_on_vm(vm_under_test, action='live_migrate')
    _ping_vm_data(vm_under_test, base_vm_id, action='live migrate')

    LOG.tc_step("Detach ports: {}".format(tenant_port_ids))
    for tenant_port_id in tenant_port_ids:
        vm_helper.detach_interface(vm_id=vm_under_test, port_id=tenant_port_id)
        new_vnics -= 1

    res = vm_helper.ping_vms_from_vm(to_vms=base_vm_id, from_vm=vm_under_test, fail_ok=True, retry=0,
                                     net_types=['data'])[0]
    assert not res, "Ping from base_vm to vm via detached interface still works"

    LOG.tc_step("Attach single interface with tenant id {}".format(tenant_net_id))
    port_id = vm_helper.attach_interface(vm_under_test, net_id=tenant_net_id)[1]
    new_vnics += 1

    LOG.tc_step("Live migrate vm after detach/attach, bring up interfaces and ensure ping works")
    vm_helper.perform_action_on_vm(vm_under_test, action='live_migrate')
    _bring_up_attached_interface(vm_under_test, guest_os=guest_os, ports=[port_id], base_vm=base_vm_id,
                                 action='attach interface and live migrate')


@mark.parametrize(('guest_os', 'nic_arg', 'boot_source'), [
    ('tis-centos-guest', 'port_id', 'image')
], ids=id_gen)
def test_vm_with_max_vnics_attached_during_boot(base_vm, guest_os, nic_arg, boot_source):
    """
    Setups:
        - Boot a base vm with mgmt net and tenant_port_id (module)

    Test Steps:
        - Boot a vm with 1 mgmt and 15 avp/virtio Interfaces
        - Perform nova action (live migrate --force, live migrate, rebuild, reboot hard/soft, resize revert, resize)
        - ping between base_vm and vm_under_test over mgmt & tenant network

    Teardown:
        - Delete created vm, volume, port (if any)  (func)
        - Delete base vm, volume    (module)

    """

    base_vm_id, mgmt_nic, tenant_nic, internal_net_id, tenant_net_id, mgmt_net_id = base_vm
    vif_type = 'avp' if system_helper.is_avs() else None

    LOG.tc_step("Get/Create {} glance image".format(guest_os))
    cleanup = None if re.search(GuestImages.TIS_GUEST_PATTERN, guest_os) else 'function'
    image_id = glance_helper.get_guest_image(guest_os=guest_os, cleanup=cleanup)

    # TODO Update vif model config. Right now vif model avp still under implementation
    nics = [mgmt_nic]
    for i in range(15):
        if nic_arg == 'port_id':
            port_id = network_helper.create_port(tenant_net_id, 'tenant_port-{}'.format(i), wrs_vif=vif_type,
                                                 cleanup='function')[1]
            nics.append({'port-id': port_id})
        else:
            nics.append({'net-id': tenant_net_id, 'vif-model': vif_type})

    LOG.tc_step("Boot a {} vm and flavor from {} with 1 mgmt and 15 data interfaces".format(guest_os, boot_source))
    vm_under_test = vm_helper.boot_vm('max_vifs-{}-{}'.format(guest_os, boot_source), nics=nics, source=boot_source,
                                      image_id=image_id, guest_os=guest_os, cleanup='function')[1]

    vm_ports_count = len(network_helper.get_ports(server=vm_under_test))
    expt_vnics = 16
    LOG.info("vnics attached to VM: {}".format(vm_ports_count))
    assert vm_ports_count == expt_vnics, "vnics attached is not equal to max number."

    _ping_vm_data(vm_under_test, vm_under_test, action='boot')
    vm_helper.configure_vm_vifs_on_same_net(vm_id=vm_under_test)
    _ping_vm_data(vm_under_test, base_vm_id, action='configure routes')

    destination_host = vm_helper.get_dest_host_for_live_migrate(vm_id=vm_under_test)
    if destination_host:
        # LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, 'live-migrate --force'))
        # vm_helper.live_migrate_vm(vm_id=vm_under_test, destination_host=destination_host, force=True)
        # _ping_vm_data(vm_under_test, base_vm_id, action='live migrate --force')

        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, 'live-migrate'))
        vm_helper.live_migrate_vm(vm_id=vm_under_test)
        _ping_vm_data(vm_under_test, base_vm_id, action='live-migrate')

    LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, 'hard reboot'))
    vm_helper.reboot_vm(vm_id=vm_under_test, hard=True)
    _ping_vm_data(vm_under_test, base_vm_id, action='hard reboot')

    LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, 'soft reboot'))
    vm_helper.reboot_vm(vm_id=vm_under_test)
    _ping_vm_data(vm_under_test, base_vm_id, action='soft rebuild')

    LOG.tc_step('Create destination flavor')
    dest_flavor_id = nova_helper.create_flavor(name='dest_flavor', vcpus=2, guest_os=guest_os)[1]

    LOG.tc_step('Resize vm to dest flavor and revert')
    vm_helper.resize_vm(vm_under_test, dest_flavor_id, revert=True, fail_ok=False)
    _ping_vm_data(vm_under_test, base_vm_id, action='resize revert')

    LOG.tc_step('Resize vm to dest flavor and revert False')
    vm_helper.resize_vm(vm_under_test, dest_flavor_id, fail_ok=False)
    _ping_vm_data(vm_under_test, base_vm_id, action='resize')

    LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, 'rebuild'))
    vm_helper.rebuild_vm(vm_id=vm_under_test)
    _ping_vm_data(vm_under_test, vm_under_test, action='rebuild')
    vm_helper.configure_vm_vifs_on_same_net(vm_id=vm_under_test)
    _ping_vm_data(vm_under_test, base_vm_id, action='rebuild')


def _ping_vm_data(vm_under_test, base_vm_id, action):
    LOG.tc_step("Verify ping vm_under_test {} from vm {} over mgmt & data networks works after {}".
                format(vm_under_test, base_vm_id, action))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['data'], retry=10)


# def _remove_dhclient_cache(vm_id):
#     dhclient_leases_cache = '/var/lib/dhclient/dhclient.leases'
#     with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
#         if vm_ssh.file_exists(dhclient_leases_cache):
#             vm_ssh.exec_sudo_cmd('rm {}'.format(dhclient_leases_cache))


def _bring_up_attached_interface(vm_id, ports, guest_os, base_vm, action='attach interfaces'):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    vm_macs = network_helper.get_ports(rtn_val='MAC Address', server=vm_id, port_id=ports)
    prompt = Prompt.VXWORKS_PROMPT if guest_os == 'vxworks' else None
    vm_helper.add_ifcfg_scripts(vm_id=vm_id, vm_prompt=prompt, mac_addrs=vm_macs, reboot=False)
    vm_helper.configure_vm_vifs_on_same_net(vm_id=vm_id, ports=ports, vm_prompt=prompt, reboot=True)
    _ping_vm_data(vm_under_test=vm_id, base_vm_id=base_vm, action=action)


def _force_live_migrate(vm_id):

    destination_host = vm_helper.get_dest_host_for_live_migrate(vm_id=vm_id)
    args_dict = {
        'force': True,
        'destination_host': destination_host,
    }
    kwargs = {}
    for key, value in args_dict.items():
        if value:
            kwargs[key] = value

    LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_id, 'live-migrate --force'))
    vm_helper.perform_action_on_vm(vm_id, action='live_migrate', **kwargs)
    return 0
