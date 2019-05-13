import random

from pytest import mark, fixture, skip
from utils import cli, table_parser
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, DevClassID
from keywords import network_helper, vm_helper, nova_helper, host_helper, check_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(autouse=True)
def list_nova_device():
    # run nova device-list for debugging purpose.
    network_helper.get_pci_device_list_values()


def get_vif_type():
    return 'avp' if system_helper.is_avs() else None


@fixture(scope='module', autouse=True)
def hosts_pci_device_info():
    # get lab host list
    hosts_device_info = {}
    compute_hosts = host_helper.get_up_hypervisors()
    for host in compute_hosts:
        device_info = host_helper.get_host_co_processor_pci_list(host)
        if len(device_info) > 0:
            hosts_device_info[host] = device_info
    LOG.info("Hosts device info: {}".format(hosts_device_info))

    if not hosts_device_info:
        skip("co-processor PCI device not found")

    vm_helper.ensure_vms_quotas(vms_num=20)
    return hosts_device_info


@fixture(scope='function')
def enable_device_and_unlock_compute(request, hosts_pci_device_info):

    def teardown():
        compute_hosts = host_helper.get_up_hypervisors()
        if not any(hosts_pci_device_info):
            return

        for host in compute_hosts:
            host_helper.modify_host_device(host, hosts_pci_device_info[host][0]['pci_address'], new_state=True,
                                           check_first=True, lock_unlock=True)
    request.addfinalizer(teardown)
    return None


@fixture(scope='module')
def _flavors(hosts_pci_device_info):
    """
    Creates all flavors required for this test module
    """
    device_id = list(hosts_pci_device_info.values())[0][0]['vf_device_id']
    pci_alias = network_helper.get_pci_device_list_values(field='PCI Alias', **{'Device Id': device_id})[0]
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
            extra_spec = {FlavorSpec.PCI_PASSTHROUGH_ALIAS: '{}:{}'.format(pci_alias, vf),
                          # FlavorSpec.NUMA_NODES: '2',     # feature deprecated. May need to update test case as well.
                          FlavorSpec.CPU_POLICY: 'dedicated'}

            nova_helper.set_flavor(flavor_id, **extra_spec)
        flavors[k] = flavor_id

    return flavors


def test_ea_host_device_sysinv_commands(hosts_pci_device_info, enable_device_and_unlock_compute):
    """
    Verify the system host device cli commands
    Args:
        hosts_pci_device_info:
        enable_device_and_unlock_compute:

    Returns:

    """
    hosts = list(hosts_pci_device_info.keys())

    for host_ in hosts:
        LOG.tc_step("Verify the system host-device-list include all pci devices for host{}.".format(host_))
        table_ = table_parser.table(cli.system('host-device-list --nowrap', host_))
        check_device_list_against_pci_list(hosts_pci_device_info[host_], table_)
        LOG.info("All devices are listed for host {}.".format(host_))

    host = random.choice(hosts)
    HostsToRecover.add(host)
    if not host_helper.is_host_locked(host):
        LOG.tc_step("Verifying  system host-device-modify fail for unlocked host.")
        assert host_helper.modify_host_device(host, hosts_pci_device_info[host][0]['pci_name'],
                                              new_name='new_pci_name', fail_ok=True)[0] == 1, \
            "It is possible to modify host device name without host is being locked "

        host_helper.lock_host(host)

    LOG.tc_step("Verify system host-device-modify can modify device name and state.")
    device_address = hosts_pci_device_info[host][0]['pci_address']
    origin_name, origin_state = host_helper.get_host_device_values(host, device_address, fields=('name', 'enabled'))
    new_name = "{}_new".format(origin_name)
    new_state = False if origin_state else True

    try:
        host_helper.modify_host_device(host, device_address, new_name=new_name, new_state=new_state)
    finally:
        LOG.tc_step("Revert {} device name and status to original values".format(host))
        host_helper.modify_host_device(host, device_address, new_name=origin_name, new_state=origin_state)

    LOG.info(" Unlock host {} after modify.".format(host))
    host_helper.unlock_host(host)


def test_ea_vm_with_crypto_vfs(_flavors, hosts_pci_device_info, enable_device_and_unlock_compute):
    """
    Verify guest can be launched with  one crypto VF, AVP, VIRTIO, and SRIOV interfaces.
    Verify device cannot be disabled while on use. ( mainly for labs with two computes)
    Args:
        _flavors:
        hosts_pci_device_info:
        enable_device_and_unlock_compute:

    Returns:

    """
    hosts = list(hosts_pci_device_info.keys())
    vm_name = 'vm_with_pci_device'
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()
    vif_type = get_vif_type()

    nics = [{'net-id': mgmt_net_id},
            {'net-id': tenant_net_id, 'vif-model': vif_type},
            {'net-id': internal_net_id, 'vif-model': 'pci-sriov'}]

    flavor_id = _flavors['flavor_qat_vf_1']
    LOG.tc_step("Boot a vm  {} with pci-sriov nics and flavor flavor_qat_vf_1".format(vm_name))
    vm_id = vm_helper.boot_vm(vm_name, flavor=flavor_id, nics=nics, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    LOG.info("VM {} booted successfully and become active with crypto VF".format(vm_name))

    vm_host = nova_helper.get_vm_host(vm_id)
    device_address = hosts_pci_device_info[vm_host][0]['pci_address']

    host_dev_name = host_helper.get_host_device_list_values(vm_host, field='device name',
                                                            **{'class id': DevClassID.QAT_VF})[0]
    expt_qat_devs = {host_dev_name: 1}
    check_helper.check_qat_service(vm_id=vm_id, qat_devs=expt_qat_devs)

    LOG.tc_step("Lock vm host {}, disable qat device on host, and unlock".format(vm_host))
    HostsToRecover.add(vm_host)

    extra_str = ''
    expt_code = 0
    force = False
    if len(hosts) < 2:
        force = True
        expt_code = 1
        extra_str = 'not'

    LOG.info("VM {} host is {}; force lock to attempt disable device".format(vm_name, vm_host))
    host_helper.lock_host(vm_host, force=force)

    LOG.tc_step("Check qat device can{} be disabled".format(extra_str))
    code, output = host_helper.modify_host_device(vm_host, device_address, new_state=False, fail_ok=True)
    assert expt_code == code, output

    if len(hosts) > 1:
        host_helper.unlock_host(vm_host)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_helper.check_qat_service(vm_id=vm_id, qat_devs=expt_qat_devs)

        LOG.tc_step("Check new vm with qat-vf will not be scheduled on host with disabled qat device")
        vm_name = 'vm_with_pci_device_2'
        flavor_id = _flavors['flavor_qat_vf_1']
        LOG.info("Boot a vm  {} with pci-sriov nics and flavor flavor_qat_vf_1".format(vm_name))
        vm_id = vm_helper.boot_vm(vm_name, flavor=flavor_id, nics=nics, cleanup='function')[1]

        vm2_host = nova_helper.get_vm_host(vm_id)
        assert vm2_host != vm_host, "Possible to launch VM {} on host {} with device disabled".format(vm_name, vm_host)


def _perform_nova_actions(vms_dict, flavors, vfs=None):
    for vm_name, vm_id in vms_dict.items():
        LOG.tc_step("Cold migrate VM {} ....".format(vm_name))
        vm_helper.cold_migrate_vm(vm_id=vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        LOG.tc_step("Live migrate VM {} ....".format(vm_name))
        expt_codes = [0] if 'vm_no_crypto' in vm_name else [1, 6]
        code, msg = vm_helper.live_migrate_vm(vm_id=vm_id, fail_ok=True)
        assert code in expt_codes, "Expect live migrate to fail for vm with pci device attached. Actual: {}".format(msg)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        LOG.tc_step("Suspend/Resume VM {} ....".format(vm_name))
        vm_helper.suspend_vm(vm_id)
        vm_helper.resume_vm(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        if vfs is None:
            resize_flavor_id = flavors["flavor_resize_qat_vf_1"] if "no_crypto" not in vm_name else \
                flavors["flavor_resize_none"]
        else:
            resize_flavor_id = flavors['flavor_resize_qat_vf_{}'.format(vfs)]

        LOG.info("Resizing VM {} to new flavor {} ...".format(vm_name, resize_flavor_id))
        vm_helper.resize_vm(vm_id, resize_flavor_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)


@mark.parametrize('vfs', [32, 33])
def test_ea_vm_with_multiple_crypto_vfs(vfs, _flavors, hosts_pci_device_info):
    """
    Verify guest can be launched with multiple crypto VFs, AVP, VIRTIO, and SRIOV interfaces.
    Verify max number of crypto VFs, verify beyond the limit (max is 32) and VM Maintenance
    activity.
    Args:
        vfs:
        _flavors:
        hosts_pci_device_info:

    Returns:

    """

    LOG.info("Launching a VM with flavor flavor_qat_vf_{}".format(vfs))
    vm_name = 'vm_with_{}_vf_pci_device'.format(vfs)
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()
    vif_type = get_vif_type()

    nics = [{'net-id': mgmt_net_id},
            {'net-id': tenant_net_id, 'vif-model': vif_type},
            {'net-id': internal_net_id, 'vif-model': vif_type}]

    if vfs == 33:
        LOG.tc_step("Verifying  VM with over limit crypto VFs={} can not be launched .....".format(vfs))
    else:
        LOG.tc_step("Verifying  VM with maximum crypto VFs={} .....".format(vfs))

    LOG.info("Boot a vm {} with pci-sriov nics, and flavor=flavor_qat_vf_{}".format(vm_name, vfs))
    flavor_id = _flavors['flavor_qat_vf_{}'.format(vfs)]
    rc, vm_id, msg, vol = vm_helper.boot_vm(vm_name, flavor=flavor_id, nics=nics, cleanup='function', fail_ok=True)

    if vfs == 33:
        assert rc != 0, " Unexpected VM was launched with over limit crypto vfs: {}".format(msg)
    else:
        assert rc == 0, "VM is not successfully launched. Details: {}".format(msg)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        vm_host = nova_helper.get_vm_host(vm_id)
        host_dev_name = host_helper.get_host_device_list_values(vm_host, field='device name',
                                                                **{'class id': DevClassID.QAT_VF})[0]
        expt_qat_devs = {host_dev_name: vfs}
        # 32 qat-vfs takes more than 1.5 hours to run tests
        check_helper.check_qat_service(vm_id=vm_id, qat_devs=expt_qat_devs, run_cpa=False)

        _perform_nova_actions(vms_dict={vm_name: vm_id}, flavors=_flavors, vfs=vfs)
        check_helper.check_qat_service(vm_id=vm_id, qat_devs=expt_qat_devs, timeout=14400)


def test_ea_vm_co_existence_with_and_without_crypto_vfs(_flavors):
    """
    Verify guest with cypto VFs can co-exists with guest without crypto VFs.
    Args:
        _flavors:

    Returns:

    """
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_ids = network_helper.get_tenant_net_ids()
    internal_net_id = network_helper.get_internal_net_id()
    vif_type = get_vif_type()

    vm_params = {'vm_no_crypto_1': [_flavors['flavor_none'], [{'net-id': mgmt_net_id},
                                                              {'net-id': tenant_net_ids[0], 'vif-model': vif_type},
                                                              {'net-id': internal_net_id, 'vif-model': vif_type}]],
                 'vm_no_crypto_2': [_flavors['flavor_none'], [{'net-id': mgmt_net_id},
                                                              {'net-id': tenant_net_ids[1], 'vif-model': vif_type},
                                                              {'net-id': internal_net_id, 'vif-model': vif_type}]],
                 'vm_sriov_crypto': [_flavors['flavor_qat_vf_1'],
                                     [{'net-id': mgmt_net_id},
                                      {'net-id': tenant_net_ids[2], 'vif-model': vif_type},
                                      {'net-id': internal_net_id, 'vif-model': 'pci-sriov'}]],
                 'vm_crypto_1': [_flavors['flavor_qat_vf_1'], [{'net-id': mgmt_net_id},
                                                               {'net-id': tenant_net_ids[3], 'vif-model': vif_type},
                                                               {'net-id': internal_net_id, 'vif-model': vif_type}]],
                 'vm_crypto_2': [_flavors['flavor_qat_vf_1'], [{'net-id': mgmt_net_id},
                                                               {'net-id': tenant_net_ids[4], 'vif-model': vif_type},
                                                               {'net-id': internal_net_id, 'vif-model': vif_type}]],
                 }

    vms = {}
    vms_qat_devs = {}

    for vm_name, param in vm_params.items():

        LOG.tc_step("Boot vm {} with {} flavor".format(vm_name, param[0]))
        vm_id = vm_helper.boot_vm('{}'.format(vm_name), flavor=param[0], nics=param[1], cleanup='function')[1]

        LOG.info("Verify  VM can be pinged from NAT box...")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id), "VM is not pingable."
        vms[vm_name] = vm_id
        vm_host = nova_helper.get_vm_host(vm_id)
        host_dev_name = host_helper.get_host_device_list_values(vm_host, field='device name',
                                                                **{'class id': DevClassID.QAT_VF})[0]
        expt_qat_devs = {} if '_no_crypto' in vm_name else {host_dev_name: 1}
        vms_qat_devs[vm_id] = expt_qat_devs
        check_helper.check_qat_service(vm_id=vm_id, qat_devs=expt_qat_devs)

    _perform_nova_actions(vms, flavors=_flavors, vfs=None)

    for vm_id_, expt_qat_devs_ in vms_qat_devs.items():
        check_helper.check_qat_service(vm_id_, qat_devs=expt_qat_devs_)


def test_ea_max_vms_with_crypto_vfs(_flavors, hosts_pci_device_info):
    """
    Verify maximum number of guests with Crypto VFs can be launched and
    stabilized

    Args:
        _flavors:
        hosts_pci_device_info:

    Returns:

    """

    LOG.info("Pci device  {}".format(hosts_pci_device_info))

    flavor_id = _flavors['flavor_qat_vf_4']
    # Assume we only have 1 coleto creek pci device on system
    crypto_hosts = list(hosts_pci_device_info.keys())
    vf_device_id = hosts_pci_device_info[crypto_hosts[0]][0]['vf_device_id']
    LOG.info("Vf_device_id {}".format(vf_device_id))
    configured_vfs = network_helper.get_pci_device_configured_vfs_value(vf_device_id)
    used_vfs = network_helper.get_pci_device_used_vfs_value(vf_device_id)

    LOG.info("Checking configured number of vfs = {}; used number of vfs = {}".format(configured_vfs, used_vfs))

    # number of vms to launch to max out the total configured device VFs. Each VM is launched with 4 Vfs. 4 Vfs in each
    # compute are reserved for resize nova action.

    number_of_vms = int(((int(configured_vfs) - int(used_vfs)) - 4 * len(crypto_hosts)) / 4)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    vif_type = get_vif_type()

    nics = [{'net-id': mgmt_net_id},
            {'net-id': tenant_net_id, 'vif-model': vif_type}]

    vm_helper.ensure_vms_quotas(number_of_vms + 10)

    vms = {}
    LOG.tc_step("Launch {} vms using flavor flavor_qat_vf_4 and nics {}".format(number_of_vms, nics))
    for i in range(1, number_of_vms + 1):
        vm_name = 'vm_crypto_{}'.format(i)
        vm_id = vm_helper.boot_vm(cleanup='function', name='vm_crypto_{}'.format(i), nics=nics, flavor=flavor_id)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        vms[vm_name] = vm_id

    for vm_name_, vm_id_ in vms.items():
        vm_host = nova_helper.get_vm_host(vm_id_)
        host_dev_name = host_helper.get_host_device_list_values(vm_host, field='device name',
                                                                **{'class id': DevClassID.QAT_VF})[0]
        expt_qat_devs = {host_dev_name: 4}
        check_helper.check_qat_service(vm_id=vm_id_, qat_devs=expt_qat_devs)

        LOG.info("Checking if other host has room for cold migrate vm {}".format(vm_name_))
        for host_ in crypto_hosts:
            if host_ != vm_host:
                total_vfs, used_vfs = network_helper.get_pci_device_vfs_counts_for_host(
                        host_, device_id=vf_device_id, fields=('pci_vfs_configured', 'pci_vfs_used'))

                if int(total_vfs) - int(used_vfs) >= 4:
                    LOG.info("Migrate to other host is possible")
                    expt_res = 0
                    break
        else:
            LOG.info("Migrate to other host is not possible")
            expt_res = 2

        LOG.tc_step("Attempt to cold migrate {} and ensure it {}".format(vm_name_,
                                                                         'succeeds' if expt_res == '0' else 'fails'))
        rc, msg = vm_helper.cold_migrate_vm(vm_id=vm_id_,  fail_ok=True)
        assert expt_res == rc, "Expected: {}. Actual: {}".format(expt_res, msg)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id_)

        LOG.tc_step("Suspend/resume VM {} ....".format(vm_name_))
        vm_helper.suspend_vm(vm_id_)
        vm_helper.resume_vm(vm_id_)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id_)

        # vm_host = nova_helper.get_vm_host(vm_id_)
        # total, used = network_helper.get_pci_device_vfs_counts_for_host(vm_host, vf_device_id)[0]
        # if (total - int(used)) >= 4:
        #     expt_res = 0

        flavor_resize_id = _flavors['flavor_resize_qat_vf_4']
        LOG.tc_step("Resize VM {} to new flavor {} with increased memory...".format(vm_name_, flavor_resize_id))
        vm_helper.resize_vm(vm_id_, flavor_resize_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id_)

        # else:
        #     expt_res = 1
        #     LOG.info("Resizing of vm {} skipped; host {} max out vfs; used vfs = {}".format(vm_name_, vm_host, used))

        LOG.tc_step("Attempt to live migrate {} and ensure it's rejected".format(vm_name_))
        rc, msg = vm_helper.live_migrate_vm(vm_id=vm_id_, fail_ok=True)
        assert 6 == rc, "Expect live migration to fail on vm with pci alias device. Actual: {}".format(msg)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id_)

        check_helper.check_qat_service(vm_id=vm_id_, qat_devs=expt_qat_devs)


def check_device_list_against_pci_list(lspci_list_info, sysinv_device_list_tab):
    """
    Checks the host pci info against the output of cli system host-device-list
    Args:
        lspci_list_info: host's pci co-processor list from lspci command
        sysinv_device_list_tab: pci list from cli system host-device-list

    Returns:

    """

    LOG.info("Checking all devices are included in the list")
    sysinv_device_list_tab = table_parser.filter_table(sysinv_device_list_tab, **{'class id': DevClassID.QAT_VF})

    assert len(lspci_list_info) == len(sysinv_device_list_tab['values']), \
        "host devices list:{} and pci list:{} mismatch".format(sysinv_device_list_tab['values'], lspci_list_info)

    # check if pci attribute values are the identical
    for pci in lspci_list_info:
        sysinv_tab = table_parser.filter_table(sysinv_device_list_tab, **{'name': pci['pci_name']})
        assert pci['vendor_name'] == table_parser.get_column(sysinv_tab, 'vendor name')[0]
        assert pci['vendor_id'] == table_parser.get_column(sysinv_tab, 'vendor id')[0]
        assert pci['device_id'] == table_parser.get_column(sysinv_tab, 'device id')[0]
        assert pci['class_id'] == table_parser.get_column(sysinv_tab, 'class id')[0]
        assert pci['pci_address'] == table_parser.get_column(sysinv_tab, 'address')[0]

    LOG.info("All host devices are listed")
