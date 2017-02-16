
import time
from pytest import mark, fixture
from utils import cli, table_parser
from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import NATBoxClient
from utils.multi_thread import MThread
from consts.cgcs import FlavorSpec, VMStatus
from keywords import network_helper, vm_helper, nova_helper, cinder_helper, system_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def hosts_pci_device_list():
    """
    """
    # get lab host list
    hosts_device_info = {}
    compute_hosts = system_helper.get_computes()
    for host in compute_hosts:
        device_info = host_helper.get_host_co_processor_pci_list(host)
        if len(device_info) > 0:
            hosts_device_info[host] = device_info
    LOG.info("Hosts device info: {}".format(hosts_device_info))
    return hosts_device_info


@fixture(scope='function')
def enable_device_and_unlock_compute(request, hosts_pci_device_list):
    """
    """
    def teardown():

        compute_hosts = system_helper.get_computes()
        if not any(hosts_pci_device_list):
            return

        for host in compute_hosts:
            if host_helper.is_host_locked(host):
                status = system_helper.get_host_device_pci_status(host, hosts_pci_device_list[host][0]['pci_address'])
                if status == 'False':
                    system_helper.modify_host_device_status(host, hosts_pci_device_list[host][0]['pci_address'], 'True')
                host_helper.unlock_host(host)
            else:
                status = system_helper.get_host_device_pci_status(host, hosts_pci_device_list[host][0]['pci_address'])
                if status == 'False':
                    host_helper.lock_host(host)
                    system_helper.modify_host_device_status(host, hosts_pci_device_list[host][0]['pci_address'], 'True')
                    host_helper.unlock_host(host)

    request.addfinalizer(teardown)
    return None


@fixture(scope='module')
def _flavors(request, hosts_pci_device_list):
    """
    Creates all flavors required for this test module
    Args:
        request:
        hosts_pci_device_list:

    Returns:

    """

    flavor_parms = {'flavor_qat_vf_1': [2, 1024, 2, 1],
                    'flavor_resize_qat_vf_1': [4, 2048, 2, 1],
                    'flavor_qat_vf_4': [2, 1024, 2, 4],
                    'flavor_resize_qat_vf_4': [2, 2048, 2, 4],
                    'flavor_qat_vf_32': [2, 1024, 2, 32],
                    'flavor_qat_vf_33': [2, 1024, 2, 33],
                    'flavor_none': [1, 1024, 2, 0],
                    'flavor_resize_none': [2, 2048, 2, 0],
                    'flavor_resize_qat_vf_32': [4, 2048, 2, 32],
                   }

    flavors = {}
    for k, v in flavor_parms.items():
        vf = v[3]
        LOG.fixture_step("Create a flavor with {} Coletro Creek crypto VF....".format(vf))
        flavor_id = nova_helper.create_flavor(name=k, vcpus=v[0], ram=v[1], root_disk=v[2])[1]
        ResourceCleanup.add('flavor', flavor_id, scope='module')
        if vf > 0:
            extra_spec = {FlavorSpec.PCI_PASSTHROUGH_ALIAS: 'qat-vf:{}'.format(vf),
                           FlavorSpec.NUMA_NODES: '2',
                           FlavorSpec.CPU_POLICY: 'dedicated'}

            nova_helper.set_flavor_extra_specs(flavor_id, **extra_spec)
        flavors[k] = flavor_id

    return flavors


@mark.skipif( not any(hosts_pci_device_list()),
                    reason="requires labs with Colecto Creek device")
def test_ea_host_device_sysinv_commands(hosts_pci_device_list, enable_device_and_unlock_compute):
    """
    Verify the system host device cli commands
    Args:
        hosts_pci_device_list:
        enable_device_and_unlock_compute:

    Returns:

    """

    hosts = list(hosts_pci_device_list.keys())
    for host in hosts:
        LOG.tc_step("Verifying the system host-device-list include all pci devices for host{}.".format(host))
        table_ = table_parser.table(cli.system('host-device-list', host))
        check_device_list_against_pci_list(hosts_pci_device_list[host], table_)
        LOG.info("All devices are listed for host {}.".format(host))

        if not host_helper.is_host_locked(host):
            LOG.tc_step("Verifying  system host-device-modify fail for unlocked host.")
            assert system_helper.modify_host_device_pci_name(host, hosts_pci_device_list[host][0]['pci_name'],
                                                         'new_pci_name', fail_ok=True)[0] == 1,\
                "It is possible to modify host device name without host is being locked "

        LOG.tc_step("Verifying  system host-device-modify can  modify device name.")
        if not host_helper.is_host_locked(host):
            assert host_helper.lock_host(host)[0] == 0,  "Host {} fail to lock; Cannot modify device name".format(host)
        device_address = hosts_pci_device_list[host][0]['pci_address']
        device_name = system_helper.get_host_device_pci_name(host, device_address)
        new_device_name = "{}_new".format(device_name)
        rc, msg = system_helper.modify_host_device_pci_name(host, device_name, new_device_name, fail_ok=True)
        assert rc == 0, "The command system host-device-modify failed to modify device name to {}: {}"\
            .format(new_device_name, msg)
        assert new_device_name == system_helper.get_host_device_pci_name(host, device_address), \
            "The command system host-device-modify failed to modify device name to {}: {}"\
            .format(new_device_name, msg)
        LOG.info(" Host {} device {} successfully renamed to {}.".format(host, device_name, new_device_name ))

        LOG.tc_step("Verifying  system host-device-modify can  modify availability status.")
        if not host_helper.is_host_locked(host):
            assert host_helper.lock_host(host)[0] == 0,  "Host {} fail to lock; Cannot modify device name".format(host)
        current_enabled = system_helper.get_host_device_pci_status(host, device_address)
        new_enabled = 'False' if current_enabled == 'True' else 'True'
        rc, msg = system_helper.modify_host_device_status(host, device_address, new_enabled, fail_ok=True)
        assert rc == 0, "The command system host-device-modify failed to modify device status to {}: {}"\
            .format(new_enabled, msg)
        assert new_enabled == system_helper.get_host_device_pci_status(host, device_address),\
            "The command system host-device-modify failed to modify device status to {}: {}"\
            .format(new_enabled, msg)

        LOG.info(" Host {} device {} successfully modified availability status to {}."
                 .format(host, device_name, new_device_name))

        LOG.info(" Reverting {} device status {} to original value {}.".format(host, new_enabled, current_enabled))
        rc, msg = system_helper.modify_host_device_status(host, device_address, current_enabled)
        assert rc == 0, \
            "The command system host-device-modify failed to modify device status to {} on host {}: {}"\
            .format(current_enabled, host, msg)

        LOG.info(" Reverting {} device name {} to original name {}.".format(host, new_device_name, device_name))
        rc, msg = system_helper.modify_host_device_pci_name(host, device_address, device_name, fail_ok=True)
        assert rc == 0, \
            "The command system host-device-modify failed to revert the device name to original name {} on {}: {}"\
            .format(device_name, host, msg)

        LOG.info(" Unlocking  Host {} after modify.".format(host))
        assert host_helper.unlock_host(host)[0] == 0,  "Host {} fail to unlock after enable/disable device name"\
            .format(host, device_name)


@mark.skipif(not any(hosts_pci_device_list()),
                    reason="requires labs with Colecto Creek device")
def test_ea_vm_with_crypto_vfs(_flavors, hosts_pci_device_list, enable_device_and_unlock_compute):
    """
    Verify guest can be launched with  one crypto VF, AVP, VIRTIO, and SRIOV interfaces.
    Verify device cannot be disabled while on use. ( mainly for labs with two computes)
    Args:
        _flavors:
        hosts_pci_device_list:
        enable_device_and_unlock_compute:

    Returns:

    """

    LOG.tc_step("Verifying  launching a VM with single crypto VF.....")

    vm_name = 'vm_with_pci_device'
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'avp'},
            {'net-id': internal_net_id, 'vif-model': 'pci-sriov'}]

    flavor_id = _flavors['flavor_qat_vf_1']
    LOG.info("Boot a vm  {} with pci-sriov nics and flavor flavor_qat_vf_1".format(vm_name))
    vm_id = vm_helper.boot_vm(vm_name, flavor=flavor_id, source='image', nics=nics, fail_ok=True)[1]
    ResourceCleanup.add('vm', vm_id)

    LOG.info("VM {} booted successfully and become active with crypto VF".format(vm_name))

    LOG.tc_step("Verifying device which is in use by VM cannot be disabled  .....")

    vm_host = nova_helper.get_vm_host(vm_id)
    device_address = hosts_pci_device_list[vm_host][0]['pci_address']

    LOG.info("VM {} host is {}; force lock to attempt disable device".format(vm_name, vm_host))
    rc, msg = host_helper.lock_host(vm_host,force=True)
    assert rc == 0, "Fail to lock VM host {}".format(vm_host)

    LOG.info("Host {} locked. Attempting to disable device on VM host {}".format(vm_host, vm_host))
    rc, msg = system_helper.modify_host_device_status(vm_host, device_address, 'False', fail_ok=True)
    assert rc == 0, "Unable to disable device {}  on {}".format(device_address, vm_host)
    LOG.info("Host {} unlocking...".format(vm_host))
    rc, msg = host_helper.unlock_host(vm_host)
    assert rc in [0, 4], "Fail to unlock VM host {}".format(vm_host)
    vm_name = 'vm_with_pci_device_2'
    flavor_id = _flavors['flavor_qat_vf_1']
    LOG.info("Boot a vm  {} with pci-sriov nics and flavor flavor_qat_vf_1".format(vm_name))
    vm_id = vm_helper.boot_vm(vm_name, flavor=flavor_id, source='image', nics=nics)[1]
    ResourceCleanup.add('vm', vm_id)
    vm_host_2 = nova_helper.get_vm_host(vm_id)
    assert vm_host_2 != vm_host, "Possible to launch VM {} on host {} with device disabled".format(vm_name, vm_host)


@mark.skipif(not any(hosts_pci_device_list()),
                    reason="requires labs with Colecto Creek device")
@mark.parametrize('vfs', [32, 33])
def test_ea_vm_with_multiple_crypto_vfs(vfs, _flavors, hosts_pci_device_list):
    """
    Verify guest can be launched with multiple crypto VFs, AVP, VIRTIO, and SRIOV interfaces.
    Verify max number of crypto VFs, verify beyond the limit (max is 32) and VM Maintenance
    activity.
    Args:
        vfs:
        _flavors:
        hosts_pci_device_list:

    Returns:

    """

    LOG.info("Launching a VM with flavor flavor_qat_vf_{}".format(vfs))
    vm_name = 'vm_with_{}_vf_pci_device'.format(vfs)
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'avp'},
            {'net-id': internal_net_id, 'vif-model': 'avp'}]

    if vfs == 33:
        LOG.tc_step("Verifying  VM with over limit crypto VFs={} can not be launched .....".format(vfs))
    else:
        LOG.tc_step("Verifying  VM with maximum crypto VFs={} .....".format(vfs))

    LOG.info("Boot a vm {} with pci-sriov nics, and flavor=flavor_qat_vf_{}".format(vm_name, vfs))
    flavor_id = _flavors['flavor_qat_vf_{}'.format(vfs)]
    rc, vm_id, msg, vol = vm_helper.boot_vm(vm_name, flavor=flavor_id, source='image', nics=nics, fail_ok=True)
    if vm_id:
        ResourceCleanup.add('vm', vm_id)
    if vfs == 33:
        assert rc != 0, " Unexpected VM was launched with over limit crypto vfs: {}".format(msg)
    else:

        LOG.tc_step("Checking VM status; VM Instance id is: {}......".format(vm_id))
        vm_state = nova_helper.get_vm_status(vm_id)

        assert vm_state == VMStatus.ACTIVE, 'VM {} state is {}; Not in ACTIVATE state as expected'.format(vm_id, vm_state)
        LOG.info("VM {} booted successfully and become active with 32 crypto VF".format(vm_name))

        LOG.tc_step("Verify  VM can be pinged from NAT box...")
        assert vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False),"VM is not pingable."

        LOG.tc_step("Attempting cold migrate VM {} ....".format(vm_name))
        rc = vm_helper.cold_migrate_vm(vm_id=vm_id)[0]
        LOG.info("Verifying cold migration succeeded...")
        assert rc == 0, "VM {} failed to cold migrate".format(vm_name)

        LOG.tc_step("Attempting to suspend VM {} ....".format(vm_name))
        rc = vm_helper.suspend_vm(vm_id)[0]
        LOG.info("Verifying vm suspended...")
        assert rc == 0, "VM {} failed to suspend".format(vm_name)

        LOG.tc_step("Attempting to resume VM {} ....".format(vm_name))
        rc = vm_helper.resume_vm(vm_id)[0]
        LOG.info("Verifying vm resumed...")
        assert rc == 0, "VM {} failed to resume".format(vm_name)

        LOG.tc_step("Attempting to resize cpu and memory of VM {} ....".format(vm_name))
        resize_flavor_id = _flavors['flavor_resize_qat_vf_{}'.format(vfs)]
        LOG.info("Resizing VM to new flavor {} ...".format(resize_flavor_id))
        rc = vm_helper.resize_vm(vm_id, resize_flavor_id)[0]
        LOG.info("Verifying vm resized to flavor {} ...".format(resize_flavor_id))
        assert rc == 0, "VM {} failed to resize to: {}".format(vm_name, resize_flavor_id)


@mark.skipif(not any(hosts_pci_device_list()),
                    reason="requires labs with Colecto Creek device")
def test_ea_vm_co_existence_with_and_without_crypto_vfs(_flavors, hosts_pci_device_list):
    """
    Verify guest with cypto VFs can co-exists with guest without crypto VFs.
    Args:
        _flavors:
        hosts_pci_device_list:

    Returns:

    """
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_ids = network_helper.get_tenant_net_ids()
    internal_net_id = network_helper.get_internal_net_id()

    vm_params = {'vm_no_crypto_1': [_flavors['flavor_none'], [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                                                      {'net-id': tenant_net_ids[0], 'vif-model': 'avp'},
                                                      {'net-id': internal_net_id, 'vif-model': 'avp'}]],
                 'vm_no_crypto_2': [_flavors['flavor_none'], [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                                                       {'net-id': tenant_net_ids[1], 'vif-model': 'avp'},
                                                       {'net-id': internal_net_id, 'vif-model': 'avp'}]],
                 'vm_sriov_crypto': [_flavors['flavor_qat_vf_1'], [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                                                         {'net-id': tenant_net_ids[2], 'vif-model': 'avp'},
                                                         {'net-id': internal_net_id, 'vif-model': 'pci-sriov'}]],
                 'vm_crypto_1': [_flavors['flavor_qat_vf_1'], [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                                                              {'net-id': tenant_net_ids[3], 'vif-model': 'avp'},
                                                              {'net-id': internal_net_id, 'vif-model': 'avp'}]],
                 'vm_crypto_2': [_flavors['flavor_qat_vf_1'], [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                                                              {'net-id': tenant_net_ids[4], 'vif-model': 'avp'},
                                                              {'net-id': internal_net_id, 'vif-model': 'avp'}]],
                }

    vms = {}

    for vm, param in vm_params.items():

        LOG.tc_step("Boot vm {} with {} flavor".format(vm, param[0]))
        vm_id = vm_helper.boot_vm('{}'.format(vm), flavor=param[0], source='image', nics=param[1], fail_ok=True)[1]
        if vm_id:
            ResourceCleanup.add('vm', vm_id)
        LOG.info("Verify  VM can be pinged from NAT box...")
        assert vm_helper.wait_for_vm_pingable_from_natbox(vm_id), "VM is not pingable."
        vms[vm] = vm_id

    for k, v in vms.items():

        LOG.tc_step("Attempting cold migrate VM {} ....".format(k))
        rc = vm_helper.cold_migrate_vm(vm_id=v)[0]
        LOG.info("Verifying cold migration succeeded...")
        assert rc == 0, "VM {} failed to cold migrate".format(k)

        LOG.tc_step("Attempting to suspend VM {} ....".format(k))
        rc = vm_helper.suspend_vm(v)[0]
        LOG.info("Verifying vm suspended...")
        assert rc == 0, "VM {} failed to suspend.".format(k)

        LOG.tc_step("Attempting to resume VM {} ....".format(k))
        rc = vm_helper.resume_vm(v)[0]
        LOG.info("Verifying vm resumed...")
        assert rc == 0, "VM {} failed to resume".format(k)

        LOG.tc_step("Attempting to resize cpu and memory of VM {} ....".format(k))
        resize_flavor = _flavors["flavor_resize_qat_vf_1"] if "no_crypto" not in k else _flavors["flavor_resize_none"]
        LOG.info("Resizing VM to new flavor {} ...".format(resize_flavor))
        rc = vm_helper.resize_vm(v, resize_flavor)[0]
        LOG.info("Verifying vm resized to flavor {} ...".format(resize_flavor))
        assert rc == 0, "VM {} failed to resize to: {}".format(k, resize_flavor)


@mark.skipif(not any(hosts_pci_device_list()),
                    reason="requires labs with Colecto Creek device")
def test_ea_max_vms_with_crypto_vfs(_flavors, hosts_pci_device_list):
    """
    Verify maximum number of guests with Crypto VFs can be launched and
    stabilized

    Args:
        _flavors:
        hosts_pci_device_list:

    Returns:

    """

    LOG.info("Pci device  {}".format(hosts_pci_device_list))

    flavor_id = _flavors['flavor_qat_vf_4']
    computes = list(system_helper.get_computes().keys())
    vf_device_id = hosts_pci_device_list[computes[0]][0]['vf_device_id']
    LOG.info("Vf_device_id {}".format(vf_device_id))
    configured_vfs = network_helper.get_pci_device_configured_vfs_value(vf_device_id)
    used_vfs = network_helper.get_pci_device_used_vfs_value(vf_device_id)

    LOG.info("Checking configured number of vfs = {}; used number of vfs = {}".format(configured_vfs, used_vfs ))

    # number of vms to launch to max out the total configured device VFs. Each VM is launched with 4 Vfs. 4 Vfs in each
    # compute are reserved for resize nova action.

    number_of_vms = int(((int(configured_vfs) - int(used_vfs)) - 4 * len(computes)) / 4)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'avp'}
           ]
    quota_instance = number_of_vms if number_of_vms > 20 else 20
    quota_cores = quota_instance * 4
    nova_helper.update_quotas(instances=quota_instance, cores=quota_cores)

    vms = {}
    for i in range(1, number_of_vms + 1):
        vm_name = 'vm_crypto_{}'.format(i)
        LOG.tc_step("( Booting  a vm {} using flavor flavor_qat_vf_4 and nics {}".format(vm_name, nics))
        vm_id = vm_helper.boot_vm(name='vm_crypto_{}'.format(i), nics=nics, flavor=flavor_id, source='image')[1]
        ResourceCleanup.add('vm', vm_id)
        assert vm_helper.wait_for_vm_pingable_from_natbox(vm_id),"VM is not pingable."
        vms[vm_name] = vm_id

    for k, v in vms.items():
        # LOG.tc_step("Attempting cold migrate {}; Expected to fail ....".format(k))
        # rc, msg = vm_helper.cold_migrate_vm(vm_id=v,  fail_ok=True)
        # LOG.info("Verifying cold migration failed...")
        # assert rc == 0, "VM {} succeed to cold migrate: {}".format(k,  msg)
        #
        LOG.tc_step("Attempting to suspend VM {} ....".format(k))
        rc = vm_helper.suspend_vm(v)[0]
        LOG.info("Verifying vm suspended...")
        assert rc == 0, "VM {} failed to suspend: {}".format(k)

        LOG.tc_step("Attempting to resume VM {} ....".format(k))
        rc = vm_helper.resume_vm(v)[0]
        LOG.info("Verifying vm resumed...")
        assert rc == 0, "VM {} failed to resume.".format(k)
        #assert VMStatus.ACTIVE == nova_helper.get_vm_status(v),

        vm_host = nova_helper.get_vm_host(v)
        used = network_helper.get_pci_device_used_vfs_value_per_compute(vm_host, vf_device_id)
        if ( 32 - int(used)) >= 4:
            LOG.tc_step("Attempting to resize cpu and memory of VM {} ....".format(k))
            flavor_resize_id = _flavors['flavor_resize_qat_vf_4']
            LOG.info("Resizing VM to new flavor {} ...".format(flavor_resize_id))
            vm_helper.resize_vm(v, flavor_resize_id)
            LOG.info("Verifying vm resized to flavor {} ...".format(flavor_resize_id))
            assert VMStatus.ACTIVE == nova_helper.get_vm_status(v), \
                "VM {} failed to resize to {}".format(k, flavor_resize_id)
        else:
            LOG.info("Resizing of vm {} skipped; host {} max out vfs; used vfs = {}".format(k, vm_host, used))

    LOG.tc_step("Verify all vms status is ACTIVE....")
    for k, v in vms.items():
        LOG.info("Verifying VM {} status ....".format(k))
        assert VMStatus.ACTIVE == nova_helper.get_vm_status(v), "VM {} is not in ACTIVE status".format(k)
        LOG.info("VM {} status is ACTIVE".format(k))


def check_device_list_against_pci_list(pci_list_info, device_table_list):
    """
    Checks the host pci info against the output of cli system host-device-list
    Args:
        pci_list_info: host's pci co-processor list from lspci command
        device_table_list: pci list from cli system host-device-list

    Returns:

    """

    LOG.info("Checking all devices are included in the list")
    assert len(pci_list_info) == len(device_table_list['values']), "host devices list:{} and pci list:{} mismatch".\
        format(device_table_list['values'], pci_list_info)
    # check if pci attribute values are the identical
    for pci in pci_list_info:
        values_index = [index for (index, item) in enumerate(device_table_list['values']) if pci['pci_address'] in item]
        assert len(values_index) > 0, "PCI address {} not listed in  host device list {}"\
            .format(pci['pci_address'], device_table_list['values'])
        l = values_index.pop()
        assert pci['vendor_name'] in device_table_list['values'][l], \
            "Vendor name {} not listed in host device list {}"\
            .format(pci['vendor_name'], device_table_list['values'][l])
        assert pci['vendor_id'] in device_table_list['values'][l], "Vendor id {} not listed in host device list {}"\
            .format(pci['vendor_id'], device_table_list['values'][l])
        assert pci['device_id'] in device_table_list['values'][l], "Device id {} not listed in host device list {}"\
            .format(pci['device_id'], device_table_list['values'][l])

    LOG.info("All host devices are listed")