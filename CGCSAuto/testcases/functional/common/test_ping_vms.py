from pytest import fixture, mark

from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import vm_helper


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
