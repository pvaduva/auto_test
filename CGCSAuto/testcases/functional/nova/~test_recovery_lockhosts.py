#
# from pytest import fixture, mark, skip
#
# from utils.tis_log import LOG
# from consts.timeout import VMTimeout
# from consts.cgcs import FlavorSpec, VMStatus, EventLogID
# from keywords import nova_helper, vm_helper, host_helper, system_helper
# from testfixtures.fixture_resources import ResourceCleanup
# from testfixtures.recover_hosts import HostsToRecover
#
#
# @fixture(autouse=True)
# def check_alarms():
#     # Override check alarms fixture
#     pass
#
#
# @fixture(scope='function')
# def target_host():
#     nova_hosts = host_helper.get_up_hypervisors()
#     if len(nova_hosts) > 4:
#         skip("More than 4 nova hosts detected.")
#
#     if system_helper.is_aio_system():
#         target_host = system_helper.get_active_controller_name()
#     else:
#         target_host = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=True)
#
#     assert target_host, "No nova host found on the system."
#
#     nova_hosts = host_helper.get_up_hypervisors()
#     hosts_to_lock = list(set(nova_hosts) - {target_host})
#     HostsToRecover.add(hosts_to_lock, scope='function')
#
#     for host in hosts_to_lock:
#         host_helper.lock_host(host, swact=False)
#
#     return target_host
#
#
# # Deprecated - guest heartbeat. reboot with only host is covered by other test.
# @mark.p1
# def _test_vm_autorecovery_reboot_host(target_host):
#     """
#     Test vm auto recovery by rebooting the host while the rest of the nova hosts are locked.
#
#     Args:
#         target_host
#
#     Setups:
#         - Lock nova hosts except the one with most vms on it  (module)
#
#     Test Steps:
#         - Create a default flavor (auto recovery should be enabled by default)
#         - Set guest-heartbeat extra spec to specified value
#         - Boot a vm with above flavor
#         - Reboot vm host (the only unlocked nova host in the system)
#         - Verify auto recovery is triggered to reboot vm
#         - Verify vm reaches Active state
#
#     Teardown:
#         - Delete created vm and flavor
#         - Unlock hosts that were locked in setup (module)
#
#     """
#     vms = []
#     for heartbeat in [True, False]:
#         LOG.tc_step("Create a flavor and set guest heartbeat to {}".format(heartbeat))
#         flavor_id = nova_helper.create_flavor(name='ar_default_hb_{}'.format(heartbeat))[1]
#         ResourceCleanup.add('flavor', flavor_id)
#
#         extra_specs = {FlavorSpec.GUEST_HEARTBEAT: str(heartbeat)}
#         nova_helper.set_flavor(flavor=flavor_id, **extra_specs)
#
#         LOG.tc_step("Boot a vm with above flavor")
#         vm_id = vm_helper.boot_vm(flavor=flavor_id, cleanup='function')[1]
#         vms.append(vm_id)
#
#     LOG.tc_step("Reboot the only nova host")
#     HostsToRecover.add(target_host, scope='function')
#     host_helper.reboot_hosts(target_host)
#     host_helper.wait_for_hypervisors_up(target_host)
#
#     for vm_id_ in vms:
#         LOG.tc_step("Verify vm failure event is logged for vm {}".format(vm_id_))
#         system_helper.wait_for_events(30, num=50, strict=False, fail_ok=False,
#                                       **{'Entity Instance ID': vm_id_, 'Event Log ID': EventLogID.VM_FAILED})
#
#         LOG.tc_step("Verify auto recovery for vm {}: ensure vm reboot complete event is logged and vm in Active state.".
#                     format(vm_id_))
#         system_helper.wait_for_events(VMTimeout.AUTO_RECOVERY, num=50, strict=False, fail_ok=False,
#                                       **{'Entity Instance ID': vm_id_, 'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})
#
#         vm_helper.wait_for_vm_values(vm_id_, timeout=30, status=VMStatus.ACTIVE)
