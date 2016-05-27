from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import VMStatus
from keywords import vm_helper, nova_helper, host_helper, network_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.wait_for_hosts_recover import HostsToWait


@fixture(scope='module', autouse=True)
def set_snat(request):
    gateway_info = network_helper.get_router_ext_gateway_info()
    run_teardown = False if gateway_info['enable_snat'] else True

    network_helper.set_router_gateway(enable_snat=True)     # Check snat is handled by the keyword

    def disable_snat():
        if run_teardown:
            network_helper.set_router_gateway(enable_snat=False)
            # network_helper.update_router_ext_gateway_snat(enable_snat=False)
    request.addfinalizer(disable_snat)


@fixture(scope='module')
def vm_():
    vm_id = vm_helper.boot_vm()[1]
    # ResourceCleanup.add('vm', vm_id, scope='module')

    # Ensure vm can be reached from outside before proceeding with the test cases
    vm_helper.ping_vms_from_natbox(vm_id)

    return vm_id


def test_ext_access_vm_actions(vm_):
    """
    Test VM external access over VM launch, live-migration, cold-migration, pause/unpause, etc

    Args:
        vm_ (str): vm created by module level test fixture

    Test Setups:
        - boot a vm from volume and ping vm from NatBox     (module)

    Test Steps:
        - Ping from VM to 8.8.8.8
        - Live-migrate the VM and verify ping from VM
        - Cold-migrate the VM and verify ping from VM
        - Pause and un-pause the VM and verify ping from VM
        - Suspend and resume the VM and verify ping from VM
        - Stop and start the VM and verify ping from VM
        - Reboot the VM and verify ping from VM

    Test Teardown:
        - Delete the created vm     (module)

    """
    LOG.tc_step("Ping from VM {} to 8.8.8.8".format(vm_))
    vm_helper.ping_ext_from_vm(vm_)

    LOG.tc_step("Live-migrate the VM and verify ping from VM")
    vm_helper.live_migrate_vm(vm_)
    vm_helper.ping_ext_from_vm(vm_)

    LOG.tc_step("Cold-migrate the VM and verify ping from VM")
    vm_helper.cold_migrate_vm(vm_)
    vm_helper.ping_ext_from_vm(vm_)

    LOG.tc_step("Pause and un-pause the VM and verify ping from VM")
    vm_helper.pause_vm(vm_)
    vm_helper.unpause_vm(vm_)
    vm_helper.ping_ext_from_vm(vm_)

    LOG.tc_step("Suspend and resume the VM and verify ping from VM")
    vm_helper.suspend_vm(vm_)
    vm_helper.resume_vm(vm_)
    vm_helper.ping_ext_from_vm(vm_)

    LOG.tc_step("Stop and start the VM and verify ping from VM")
    vm_helper.stop_vms(vm_)
    vm_helper.start_vms(vm_)
    vm_helper.ping_ext_from_vm(vm_)

    LOG.tc_step("Reboot the VM and verify ping from VM")
    vm_helper.reboot_vm(vm_)
    vm_helper.ping_ext_from_vm(vm_)


@mark.skipif(True, reason="Evacuation JIRA")
@mark.slow
@mark.usefixtures('hosts_recover_func')
def test_ext_access_host_reboot(vm_):
    """
    Test VM external access after evacuation.

    Args:
        vm_ (str): vm created by module level test fixture

    Test Setups:
        - boot a vm from volume and ping vm from NatBox     (module)

    Test Steps:
        - Ping VM from NatBox
        - Reboot vm host
        - Verify vm is evacuated to other host
        - Verify vm can still ping outside

    Test Teardown:
        - Delete the created vm     (module)
    """
    LOG.tc_step("Ping VM from NatBox".format(vm_))
    vm_helper.ping_vms_from_natbox(vm_)

    LOG.tc_step("Reboot vm host")
    host = nova_helper.get_vm_host(vm_)
    host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
    HostsToWait.add(host, scope='function')

    LOG.tc_step("Verify vm is evacuated and can still ping outside")
    vm_helper._wait_for_vm_status(vm_, status=VMStatus.ACTIVE, timeout=120)
    post_evac_host = nova_helper.get_vm_host(vm_)
    assert post_evac_host != host, "VM is on the same host after original host rebooted."
    vm_helper.ping_ext_from_vm(vm_)


def test_reset_router_ext_gateway(vm_):
    """
    Test VM external access after evacuation.

    Args:
        vm_ (str): vm created by module level test fixture

    Test Setups:
        - boot a vm from volume and ping vm from NatBox     (module)

    Test Steps:
        - Ping outside from VM
        - Clear router gateway
        - Verify vm cannot be ping'd from NatBox
        - Set router gateway
        - Verify vm can be ping'd from NatBox
        - Verify vm can ping outside

    Test Teardown:
        - Delete the created vm     (module)
    """
    LOG.tc_step("Ping outside from VM".format(vm_))
    vm_helper.ping_ext_from_vm(vm_)

    LOG.tc_step("Clear router gateway and verify vm cannot be ping'd from NatBox")
    network_helper.clear_router_gateway(check_first=False)
    ping_res = vm_helper.ping_vms_from_natbox(vm_, fail_ok=True)[0]
    assert ping_res is False, "VM can still be ping'd from outside after clearing router gateway."

    LOG.tc_step("Set router gateway and verify vm can ping to and be ping'd from outside")
    network_helper.set_router_gateway(clear_first=False)
    vm_helper.ping_vms_from_natbox(vm_)
    vm_helper.ping_ext_from_vm(vm_)


@mark.skipif(True, reason="Not implemented")
def test_vm_nat_protocol(vm_):
    # scp to vm from natbox
    # wget to vm
    raise NotImplementedError("Test not implemented yet.")
