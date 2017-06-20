import time
from pytest import fixture, mark, skip

from consts.auth import Tenant
from consts.proj_vars import ProjVar
from utils.tis_log import LOG
from utils.ssh import NATBoxClient
from consts.cgcs import VMStatus
from keywords import vm_helper, nova_helper, host_helper, network_helper, system_helper, common
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True, params=['distributed', 'centralized'])
def snat_setups(request):
    find_dvr = 'True' if request.param == 'distributed' else 'False'

    primary_tenant = Tenant.get_primary()
    primary_tenant_name = common.get_tenant_name(primary_tenant)
    other_tenant = Tenant.TENANT2 if primary_tenant_name == 'tenant1' else Tenant.TENANT1

    for auth_info in [primary_tenant, other_tenant]:
        tenant_router = network_helper.get_tenant_router(auth_info=auth_info)
        is_dvr_router = network_helper.get_router_info(router_id=tenant_router, field='distributed')
        if find_dvr == is_dvr_router:
            LOG.fixture_step("Setting primary tenant to {}".format(common.get_tenant_name(auth_info)))
            Tenant.set_primary(auth_info)
            break
    else:
        skip("No {} router found on system.".format(request.param))

    LOG.fixture_step("Update router to enable SNAT")
    network_helper.update_router_ext_gateway_snat(enable_snat=True)     # Check snat is handled by the keyword

    def disable_snat():
        LOG.fixture_step("Disable SNAT on tenant router")
        try:
            network_helper.update_router_ext_gateway_snat(enable_snat=False)
        except:
            raise
        finally:
            LOG.fixture_step("Revert primary tenant to {}".format(primary_tenant_name))
            Tenant.set_primary(primary_tenant)
    request.addfinalizer(disable_snat)

    LOG.fixture_step("Boot a VM from volume")
    vm_id = vm_helper.boot_vm(name='snat', reuse_vol=False, cleanup='module')[1]

    LOG.fixture_step("Attempt to ping from NatBox and ensure if fails")
    ping_res = vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60, fail_ok=True, use_fip=False)
    assert ping_res is False, "VM can still be ping'd from outside after SNAT enabled without floating ip."

    LOG.fixture_step("Create a floating ip and associate it to VM")
    floatingip = network_helper.create_floating_ip()[1]
    ResourceCleanup.add('floating_ip', floatingip, scope='module')
    network_helper.associate_floating_ip(floatingip, vm_id, fip_val='ip')

    LOG.fixture_step("Ping vm's private and floating ip from NatBox")
    vm_helper.ping_vms_from_natbox(vm_id, use_fip=False)

    return vm_id, floatingip


@fixture()
def enable_snat_as_teardown(request):
    def enable_snat_teardown():
        network_helper.update_router_ext_gateway_snat(enable_snat=True)
    request.addfinalizer(enable_snat_teardown)


@mark.usefixtures('enable_snat_as_teardown')
@mark.parametrize('snat', [
    mark.p3('snat_disabled'),
    mark.domain_sanity('snat_enabled'),
])
def test_snat_vm_actions(snat_setups, snat):
    """
    Test VM external access over VM launch, live-migration, cold-migration, pause/unpause, etc

    Args:
        snat_setups (tuple): returns vm id and fip. Enable snat, create vm and attach floating ip.

    Test Setups (module):
        - Find a tenant router that is dvr or non-dvr based on the parameter
        - Enable SNAT on tenant router
        - boot a vm and attach a floating ip
        - Ping vm from NatBox

    Test Steps:
        - Enable/Disable SNAT based on snat param
        - Ping from VM to 8.8.8.8
        - wget <lab_fip> to VM
        - scp from NatBox to VM
        - Live-migrate the VM and verify ping from VM
        - Cold-migrate the VM and verify ping from VM
        - Pause and un-pause the VM and verify ping from VM
        - Suspend and resume the VM and verify ping from VM
        - Stop and start the VM and verify ping from VM
        - Reboot the VM and verify ping from VM

    Test Teardown:
        - Enable snat for next test in the same module     (function)
        - Delete the created vm     (module)
        - Disable snat  (module)

    """
    vm_ = snat_setups[0]
    snat = True if snat == 'snat_enabled' else False
    LOG.tc_step("Update tenant router external gateway to set SNAT to {}".format(snat))
    network_helper.update_router_ext_gateway_snat(enable_snat=snat)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)

    LOG.tc_step("Ping from VM {} to 8.8.8.8".format(vm_))
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("wget to VM {}".format(vm_))
    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_, use_fip=True) as vm_ssh:
        vm_ssh.exec_cmd('wget google.ca', fail_ok=False)

    LOG.tc_step("scp from NatBox to VM {}".format(vm_))
    vm_fip = network_helper.get_mgmt_ips_for_vms(vms=vm_, use_fip=True)[0]
    natbox_ssh = NATBoxClient.get_natbox_client()
    natbox_ssh.scp_files(source_file='test', dest_file='/tmp/', dest_server=vm_fip,
                         dest_password='root', dest_user='root', timeout=30, fail_ok=False)

    LOG.tc_step("Live-migrate the VM and verify ping from VM")
    vm_helper.live_migrate_vm(vm_)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("Cold-migrate the VM and verify ping from VM")
    vm_helper.cold_migrate_vm(vm_)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("Pause and un-pause the VM and verify ping from VM")
    vm_helper.pause_vm(vm_)
    vm_helper.unpause_vm(vm_)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("Suspend and resume the VM and verify ping from VM")
    vm_helper.suspend_vm(vm_)
    vm_helper.resume_vm(vm_)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("Stop and start the VM and verify ping from VM")
    vm_helper.stop_vms(vm_)
    vm_helper.start_vms(vm_)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("Reboot the VM and verify ping from VM")
    vm_helper.reboot_vm(vm_)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)


# @mark.skipif(True, reason="Evacuation JIRA CGTS-4917")
@mark.slow
@mark.usefixtures('enable_snat_as_teardown')
@mark.parametrize('snat', [
    mark.p3('snat_disabled'),
    mark.domain_sanity('snat_enabled'),
])
def test_snat_evacuate_vm(snat_setups, snat):
    """
    Test VM external access after evacuation.

    Args:
        snat_setups (tuple): returns vm id and fip. Enable snat, create vm and attach floating ip.
        snat (bool): whether or not to enable SNAT on router

    Test Setups (module):
        - Find a tenant router that is dvr or non-dvr based on the parameter
        - Enable SNAT on tenant router
        - boot a vm and attach a floating ip
        - Ping vm from NatBox

    Test Steps:
        - Ping VM from NatBox
        - Reboot vm host
        - Verify vm is evacuated to other host
        - Verify vm can still ping outside

    Test Teardown:
        - Delete the created vm     (module)
        - Disable snat  (module)

    """
    vm_ = snat_setups[0]

    snat = True if snat == 'snat_enabled' else False
    LOG.tc_step("Update tenant router external gateway to set SNAT to {}".format(snat))
    network_helper.update_router_ext_gateway_snat(enable_snat=snat)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)

    host = nova_helper.get_vm_host(vm_)

    LOG.tc_step("Ping VM from NatBox".format(vm_))
    vm_helper.ping_vms_from_natbox(vm_, use_fip=False)
    # vm_helper.ping_vms_from_natbox(vm_, use_fip=True)

    LOG.tc_step("Reboot vm host")
    HostsToRecover.add(host, scope='function')
    host_helper.reboot_hosts(host, wait_for_reboot_finish=False)

    LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
    vm_helper._wait_for_vms_values(vm_, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120)

    LOG.tc_step("Verify vm is evacuated to other host")
    vm_helper._wait_for_vm_status(vm_, status=VMStatus.ACTIVE, timeout=300, fail_ok=False)
    post_evac_host = nova_helper.get_vm_host(vm_)
    assert post_evac_host != host, "VM is on the same host after original host rebooted."

    LOG.tc_step("Verify vm can still ping outside")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)


@mark.slow
@mark.trylast
@mark.p3
# @mark.skipif(True, reason="Evacuation JIRA CGTS-4917")
def test_snat_computes_lock_reboot(snat_setups):
    """
    test vm external access after host compute reboot with all rest of computes locked

    Args:
        snat_setups (tuple): returns vm id and fip. Enable snat, create vm and attach floating ip.

    Test Setups (module):
        - Find a tenant router that is dvr or non-dvr based on the parameter
        - Enable SNAT on tenant router
        - boot a vm and attach a floating ip
        - Ping vm from NatBox

    Steps:
        - Ping VM {} from NatBox
        - Lock all nova hosts except the vm host
        - Ping external from vm
        - Reboot VM host
        - Wait for vm host to complete reboot
        - Verify vm is recovered after host reboot complete and can still ping outside

    Test Teardown:
        - Unlock all hosts
        - Delete the created vm     (module)
        - Disable SNAT on router    (module)

    """
    hypervisors = host_helper.get_hypervisors(state='up', status='enabled')
    if len(hypervisors) > 3:
        skip("More than 3 hypervisors on system. Skip to reduce run time.")
    if system_helper.is_small_footprint():
        skip("Skip for CPE system.")

    vm_ = snat_setups[0]
    LOG.tc_step("Ping VM {} from NatBox".format(vm_))
    vm_helper.ping_vms_from_natbox(vm_, use_fip=True)

    vm_host = nova_helper.get_vm_host(vm_)
    LOG.info("VM host is {}".format(vm_host))
    assert vm_host in hypervisors, "vm host is not in nova hypervisor-list"

    hosts_should_lock = set(hypervisors) - {vm_host}
    hosts_already_locked = set(host_helper.get_hosts(administrative='locked'))
    hosts_to_lock = list(hosts_should_lock - hosts_already_locked)
    LOG.tc_step("Lock all compute hosts {} except vm host {}".format(hosts_to_lock, vm_host))
    for host_ in hosts_to_lock:
        host_helper.lock_host(host_, swact=True)
        HostsToRecover.add(host_, scope='module')

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_, timeout=60)
    LOG.tc_step("Ping external from vm {}".format(vm_))
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("Reboot vm host")
    host_helper.reboot_hosts(vm_host)
    host_helper.wait_for_hypervisors_up(vm_host)

    LOG.tc_step("Check vm host did not change after host reboot")
    post_reboot_host = nova_helper.get_vm_host(vm_)
    assert vm_host == post_reboot_host, "VM has moved to {} even though it's locked".format(post_reboot_host)

    LOG.tc_step("Verify vm is recovered after host reboot complete and can still ping outside")
    vm_helper._wait_for_vm_status(vm_, status=VMStatus.ACTIVE, timeout=300, fail_ok=False)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_, timeout=120, use_fip=True)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_, timeout=60)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)


@mark.domain_sanity
def test_snat_reset_router_ext_gateway(snat_setups):
    """
    Test VM external access after evacuation.

    Args:
        snat_setups (tuple): returns vm id and fip. Enable snat, create vm and attach floating ip.

    Test Setups:
        - Find a tenant router that is dvr or non-dvr based on the parameter
        - Enable SNAT on tenant router
        - boot a vm and attach a floating ip
        - Ping vm from NatBox

    Test Steps:
        - Ping outside from VM
        - Clear router gateway
        - Verify vm cannot be ping'd from NatBox
        - Set router gateway
        - Verify vm can be ping'd from NatBox
        - Verify vm can ping outside

    Test Teardown:
        - Delete the created vm     (module)
        - Disable SNAT on router    (module)
    """
    vm_, fip = snat_setups
    LOG.tc_step("Ping vm management net ip from NatBox")
    vm_helper.ping_vms_from_natbox(vm_, use_fip=False)
    # vm_helper.ping_vms_from_natbox(vm_, use_fip=True)

    LOG.tc_step("Ping outside from VM".format(vm_))
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)

    LOG.tc_step("Disassociate floatingip from vm and verify it's successful.")
    network_helper.disassociate_floating_ip(floating_ip=fip)
    # assert not network_helper.get_floating_ip_info(fip=fip, field='fixed_ip_address'), \
    #     "Floating ip {} still attached to fixed ip".format(fip)

    LOG.tc_step("Clear router gateway and verify vm cannot be ping'd from NatBox")
    fixed_ip = network_helper.get_router_ext_gateway_info()['external_fixed_ips'][0]['ip_address']
    network_helper.clear_router_gateway(check_first=False)
    ping_res = vm_helper.ping_vms_from_natbox(vm_, fail_ok=True, use_fip=False)[0]
    assert ping_res is False, "VM can still be ping'd from outside after clearing router gateway."

    LOG.tc_step("Set router gateway with the same fixed ip")
    network_helper.set_router_gateway(clear_first=False, fixed_ip=fixed_ip, enable_snat=True)

    LOG.tc_step("Verify SNAT is enabled by default after setting router gateway.")
    assert network_helper.get_router_ext_gateway_info()['enable_snat'], "SNAT is not enabled by default."

    LOG.tc_step("Associate floating ip to vm")
    network_helper.associate_floating_ip(floating_ip=fip, vm_id=vm_)

    LOG.tc_step("Verify vm can ping to and be ping'd from outside")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_, timeout=60, fail_ok=False)
    vm_helper.ping_ext_from_vm(vm_, use_fip=True)


def a_test_vm_nat_protocol():
    # scp to vm from natbox
    # wget to vm
    raise NotImplementedError("Test not implemented yet.")
