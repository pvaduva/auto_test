from pytest import fixture, mark

from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import vm_helper,glance_helper, storage_helper
from testfixtures.resource_mgmt import ResourceCleanup
from consts.cgcs import EventLogID, IMAGE_DIR

@fixture(scope='module')
def tenants_vms(request):
    tenant1_vms, new_t1_vms = vm_helper.get_any_vms(count=2, auth_info=Tenant.TENANT_1, rtn_new=True)
    tenant2_vms, new_t2_vms = vm_helper.get_any_vms(count=2, auth_info=Tenant.TENANT_2, rtn_new=True)

    def delete():
        vm_helper.delete_vms(new_t1_vms + new_t2_vms)
    request.addfinalizer(delete)

    return tenant1_vms, tenant2_vms


def test_ping_vms_from_natbox(tenants_vms):
    """
    Test ping vms management ips from NatBox
    Args:
        tenants_vms: vms created for tenant1 and tenant2

    Test Setup:
        - Boot/Get two vms from tenant1 and two vms from tenant2
    Test Steps:
        - Send 5 pings to VMs from Nat Box
        - Verify Ping succeeded
    Test Teardown:
        - Delete newly created VMs
    """
    LOG.tc_step("Getting VMs to ping...")
    vms = tenants_vms[0] + tenants_vms[1]
    LOG.tc_step("Pinging VMs...")
    res_bool, res_dict = vm_helper.ping_vms_from_natbox(vm_ids=vms, fail_ok=True)
    assert res_bool


def test_ping_vms_from_vm(tenants_vms):
    """
    Test ping vms management ips from NatBox
    Args:
        tenants_vms: vms created for tenant1 and tenant2 as test setup

    Test Setup:
        - Boot/Get two vms from tenant1 and two vms from tenant2
    Test Steps:
        - Send 5 pings to all 4 VMs from each VM
        - Verify Ping succeeded
    Test Teardown:
        - Delete newly created VMs
    """
    LOG.tc_step("Ping vms from vm...")
    res = {}
    vms = tenants_vms[0] + tenants_vms[1]
    for vm in vms:
        res_list = vm_helper.ping_vms_from_vm(to_vms=vms, from_vm=vm, fail_ok=True)
        res[vm] = res_list

    LOG.tc_step("Check ping results...")
    for val in res.values():
        assert val[0]


@mark.parametrize('image_name', [
    mark.sanity('cgcs-guest'),
    mark.P1('ubuntu-precise-amd64')
])
def test_ping_between_two_image_vm(image_name):
    """
    Test ping between two cgcs-guest vms
    Args:

    Test Setup:
        - Boot/Get two vms from cgcs-guest image
    Test Steps:
        - Send pings from one vm to another
        -Verify that pings are successful
    Test Teardown:
        - Delete newly created VMs
    """
    if image_name == 'ubuntu-precise-amd64':
        LOG.tc_step('Downloading ubuntuimage(s)... this will take some time')
        image_names = storage_helper.download_images(dload_type='ubuntu', img_dest=IMAGE_DIR)

        LOG.tc_step('Import ubuntu images into glance')
        for image in image_names:
            source_image_loc = IMAGE_DIR + "/" + image
            img_name = 'ubuntu-precise-amd64'
            ret = glance_helper.create_image(name=image_name, public=True,
                                             source_image_file=source_image_loc,
                                             disk_format='qcow2',
                                             container_format='bare',
                                             cache_raw=True, wait=True)

    LOG.tc_step("Boot vms with two {} image".format(image_name))
    sourceid = glance_helper.get_image_id_from_name(image_name)
    vm1 = vm_helper.boot_vm(source='image', source_id=sourceid)[1]
    vm2 = vm_helper.boot_vm(source='image', source_id=sourceid)[1]

    ResourceCleanup.add('vm', vm1)
    ResourceCleanup.add('vm', vm2)
    res_list1=vm_helper.ping_vms_from_vm(to_vms=vm1, from_vm=vm2, fail_ok=True)
    res_list2=vm_helper.ping_vms_from_vm(to_vms=vm2, from_vm=vm1, fail_ok=True)

    assert res_list1[0]
    assert res_list2[0]