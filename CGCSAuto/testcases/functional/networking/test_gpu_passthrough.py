import re
import time
from pytest import fixture
from utils.tis_log import LOG

from consts.cgcs import VMStatus, FlavorSpec, GuestImages, DevClassID
from keywords import network_helper, nova_helper, vm_helper, glance_helper, system_helper, host_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module', autouse=True)
def setup_alias(request):
    LOG.fixture_step("Create nova device list for gpu device")
    nova_gpu_alias = _get_nova_alias(class_id=DevClassID.GPU, dev_type='gpu')
    LOG.fixture_step("Create nova device list for usb device")
    nova_usb_alias = _get_nova_alias(class_id=DevClassID.USB, dev_type='user')

    def revert_alias_setup():

        service = 'nova'
        gpu_uuid = system_helper.get_service_parameter_values \
                                                (rtn_value='uuid', service=service, section='pci_alias', name='gpu')[0]
        user_uuid = system_helper.get_service_parameter_values \
                                                (rtn_value='uuid', service=service, section='pci_alias', name='user')[0]
        LOG.fixture_step("Delete service parameter uuid {} ".format(gpu_uuid))
        system_helper.delete_service_parameter(uuid=gpu_uuid)
        LOG.fixture_step("Delete service parameter uuid {} ".format(user_uuid))
        system_helper.delete_service_parameter(uuid=user_uuid)

        system_helper.apply_service_parameters(service, wait_for_config=True)

        # CGTS-9637  cpu usage high
        time.sleep(120)

    request.addfinalizer(revert_alias_setup)

    return nova_gpu_alias, nova_usb_alias


def test_gpu_passthrough(setup_alias):

    """
        Test case for GPU passthrough

    Test Steps:
        - Create pci alias for dev type 'gpu' and 'user'
        - Calculate the initial pf used in 'nova device-list'
        - Create flavor with extra spec with PCI_PASSTHROUGH_ALIAS device gpu & usb
        - Boot a vm with created flavor & gpu passthrough specfic centos image
        - Verify the pf used increased after vm launch


    Teardown:
        - Delete created vm, flavor, pci_alias

    """

    nova_gpu_alias, nova_usb_alias = setup_alias

    #initialize parameter for basic operation
    name = 'gpu_passthrough'
    guest_os = 'centos_gpu'
    pf = 1

    LOG.tc_step("Create a flavor for GPU Passthrough")
    flavor_id = nova_helper.create_flavor(name=name, root_disk=16)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')
    extra_spec = {FlavorSpec.PCI_PASSTHROUGH_ALIAS: '{}:{},{}:{}'.format(nova_gpu_alias, pf, nova_usb_alias, pf),
                  FlavorSpec.CPU_POLICY: 'dedicated'}

    nova_helper.set_flavor_extra_specs(flavor_id, **extra_spec)

    initial_gpu_pfs_used = _calculate_pf_used(nova_gpu_alias)
    initial_usb_pfs_used = _calculate_pf_used(nova_usb_alias)

    LOG.tc_step("Get/Create {} glance image".format(guest_os))
    image_id = glance_helper.get_guest_image(guest_os=guest_os)
    if not re.search(GuestImages.TIS_GUEST_PATTERN, guest_os):
        ResourceCleanup.add('image', image_id, scope='module')

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()

    mgmt_nic = {'net-id': mgmt_net_id, 'vif-model': 'virtio'}
    tenant_nic = {'net-id': tenant_net_id, 'vif-model': 'virtio'}
    nics = [mgmt_nic, tenant_nic]

    LOG.tc_step("Boot a vm  {} with pci-alias and flavor ".format(nova_gpu_alias, flavor_id))
    vm_id = vm_helper.boot_vm(name, flavor=flavor_id, source='image', source_id=image_id, nics=nics, cleanup='function')[1]

    actual_gpu_pfs_used = _calculate_pf_used(nova_gpu_alias)
    expected_gpu_pfs_used = initial_gpu_pfs_used + pf
    assert actual_gpu_pfs_used == expected_gpu_pfs_used, "actual gpu pci pfs is not equal to expected pci pfs"

    actual_usb_pfs_used = _calculate_pf_used(nova_usb_alias)
    expected_usb_pfs_used = initial_usb_pfs_used + pf
    assert actual_usb_pfs_used == expected_usb_pfs_used, "actual usb pci pfs is not equal to expected pci pfs"

    LOG.tc_step("Delete vm  {} ".format(vm_id))
    vm_helper.delete_vms(vms=vm_id, stop_first=False)

    actual_gpu_pfs_used = _calculate_pf_used(nova_gpu_alias)
    assert actual_gpu_pfs_used == initial_gpu_pfs_used, "actual gpu pci pfs is not equal to expected pci pfs after vm delete"

    actual_usb_pfs_used = _calculate_pf_used(nova_usb_alias)
    assert actual_usb_pfs_used == initial_usb_pfs_used, "actual usb pci pfs is not equal to expected pci pfs after vm delete"

    LOG.tc_step("Deleting nova service parameter service parameters for gpu & usb")


def _get_nova_alias(class_id, dev_type):
    hosts = host_helper.get_up_hypervisors()
    devices = host_helper.get_host_device_list_values(host=hosts[0], field='address', list_all=True,
                                                      **{'class id': class_id})
    dev_len = min(len(devices), 2)
    devices = devices[:dev_len]

    nova_devices = network_helper.create_pci_alias_for_devices(dev_type=dev_type, devices=devices)
    nova_alias = nova_devices[0]['pci alias']
    LOG.info("nova alias name {}".format(nova_alias))
    return nova_alias


def _calculate_pf_used(nova_pci_alias):
    pf_used = network_helper.get_pci_device_list_values(field='pci_pfs_used', **{'PCI Alias': nova_pci_alias})[0]
    LOG.info("Initial {} pci_pfs_used: {}".format(nova_pci_alias, pf_used))
    return pf_used



