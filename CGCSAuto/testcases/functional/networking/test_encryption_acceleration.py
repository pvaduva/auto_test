
import time
from pytest import mark, fixture
from utils import cli, table_parser
from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import NATBoxClient
from utils.multi_thread import MThread
from consts.cgcs import FlavorSpec, Prompt
from keywords import network_helper, vm_helper, nova_helper, cinder_helper, system_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup



@fixture(scope='function')
def hosts_pci_device_list():
    """
    """
    # get lab host list
    hosts_device_info = {}
    hostnames = system_helper.get_hostnames()
    for host in hostnames:
        device_info = host_helper.get_host_co_processor_pci_list(host)
        if len(device_info) > 0:
            hosts_device_info[host] = device_info

    return hosts_device_info

# @fixture(scope='function')
# @mark.usefixtures('ubuntu14_image')
# def _vms(ubuntu14_image):
#     """
#
#     Args:
#         ubuntu14_image:
#
#     Returns:
#
#     """
#
#     image_id = ubuntu14_image
#     guest_os = 'ubuntu_14'
#     size = 9
#
#     LOG.fixture_step("Create a favor with {}G root disk and dedicated cpu policy".format(size))
#     flavor_id = nova_helper.create_flavor(name='dedicated-{}g'.format(size), root_disk=size)[1]
#     ResourceCleanup.add('flavor', flavor_id, scope='module')
#
#     nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated'})
#
#     mgmt_net_id = network_helper.get_mgmt_net_id()
#     tenant_net_ids = network_helper.get_tenant_net_ids()
#     internal_net_id = network_helper.get_internal_net_id()
#     vm_names = ['virtio1_vm', 'avp1_vm', 'avp2_vm', 'vswitch1_vm']
#     vm_vif_models = {'virtio1_vm': 'virtio',
#                      'avp1_vm': 'avp',
#                      'avp2_vm': 'avp',
#                      'vswitch1_vm': 'avp'}
#
#     vms = []
#
#     for (vm, i) in zip(vm_names, range(0, 4)):
#         nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
#                 {'net-id': tenant_net_ids[i], 'vif-model': vm_vif_models[vm]},
#                 {'net-id': internal_net_id, 'vif-model': vm_vif_models[vm]}]
#
#         LOG.fixture_step("Create a {}G volume from {} image".format(size, image_id))
#         vol_id = cinder_helper.create_volume(name='vol-{}'.format(vm), image_id=image_id, size=size)[1]
#         ResourceCleanup.add('volume', vol_id)
#
#         LOG.fixture_step("Boot a ubuntu14 vm with {} nics from above flavor and volume".format(vm_vif_models[vm]))
#         vm_id = vm_helper.boot_vm('{}'.format(vm), flavor=flavor_id, source='volume',
#                                   source_id=vol_id, nics=nics, guest_os=guest_os)[1]
#         ResourceCleanup.add('vm', vm_id, del_vm_vols=True)
#         vms.append(vm_id)
#
#     return vms


def test_host_device_sysinv_commands(hosts_pci_device_list):


    hosts = system_helper.get_hostnames()

    for host in hosts:
        LOG.tc_step("Verifying the system host-device-list include all pci devices for host{}.".format(host))
        table_ = table_parser.table(cli.system('host-device-list', host))
        check_device_list_against_pci_list(hosts_pci_device_list[host], table_)
        LOG.tc_step("All devices are listed for host {}.".format(host))

        LOG.tc_step("Verifying  system host-device-modify fail for in unlocked host.")
        table_ = table_parser.table(cli.system('host-device-show', host))

        expt_sub_headers.extend(['sriov_totalvfs', 'sriov_numvfs', 'sriov_vfs_pci_address',
                                                  'extra_info', 'created_at', 'updated_at'])

        LOG.tc_step("Check 'system host-device-show' contains expected fields")
        actual_fields = table_parser.get_column(table_, 'Property')
        assert set(expt_sub_headers) <= set(actual_fields), "Some expected fields are not included in system show table."



def check_device_list_against_pci_list(pci_list_info, device_table_list):

    #Check all pci are listed as devices:
    LOG.info("Checking all devices are included in the list")
    assert len(pci_list_info) == len(device_table_list['values'][0]), "host devices list:{} and pci list:{} mismatch".\
        format(len(device_table_list['values'][0]),device_table_list)
    # check if pci attribute values are the identical
    for pci in pci_list_info:
        assert pci['pci_name'] in device_table_list['values'][0], "PCI name {} not listed in  host device list {}"\
            .format(pci['pci_name'], device_table_list['values'][0])
        assert pci['pci_address'] in device_table_list['values'][1], "PCI address {} not listed in host device list {}"\
            .format(pci['pci_address'], device_table_list['values'][1])
        assert pci['vendor_name'] in device_table_list['values'][6], "Vendor name {} not listed in host device list {}"\
            .format(pci['vendor_name'], device_table_list['values'][6])
        assert pci['vendor_id'] in device_table_list['values'][3], "Vendor id {} not listed in host device list {}"\
            .format(pci['vendor_id'], device_table_list['values'][3])
        assert pci['device_id'] in device_table_list['values'][4], "Device id {} not listed in host device list {}"\
            .format(pci['device_id'], device_table_list['values'][4])

    LOG.info("All host devices are listed")