from pytest import fixture, mark

from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import vm_helper


@fixture(scope='module')
def tenants_vms():
    tenant1_vms = vm_helper.get_any_vm_ids(count=2, auth_info=Tenant.TENANT_1)
    tenant2_vms = vm_helper.get_any_vm_ids(count=2, auth_info=Tenant.TENANT_2)
    return [tenant1_vms, tenant2_vms]


def test_ping_vms_from_natbox(tenants_vms):
    LOG.tc_step("Getting VMs to ping...")
    vms = tenants_vms[0] + tenants_vms[1]
    LOG.tc_step("Pinging VMs...")
    res_bool, res_dict = vm_helper.ping_vms_from_natbox(vm_ids=vms, fail_ok=True)
    assert res_bool
    LOG.info("Test Result - Passed.")


def test_ping_vms_from_vm(tenants_vms):
    LOG.tc_step("Ping vms from vm...")
    res = {}
    vms = tenants_vms[0] + tenants_vms[1]
    for vm in vms:
        res_list = vm_helper.ping_vms_from_vm(to_vms=vms, from_vm=vm, fail_ok=True)
        res[vm] = res_list

    LOG.tc_step("Check ping results...")
    for val in res.values():
        assert val[0]
    LOG.info("Test Result - Passed.")
