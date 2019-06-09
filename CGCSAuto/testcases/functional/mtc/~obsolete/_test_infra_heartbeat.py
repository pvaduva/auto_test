# # Copyright (c) 2016 Wind River Systems, Inc.
# #
# # The right to copy, distribute, modify, or otherwise make use
# # of this software may be licensed only pursuant to the terms
# # of an applicable Wind River license agreement.
#
# import re
# from pytest import skip, fixture, mark
#
# from utils.tis_log import LOG
# from consts.cgcs import EventLogID, HostAvailState, HostOperState
# from keywords import host_helper, system_helper
# from testfixtures.recover_hosts import HostsToRecover
#
# # NOTE: This is removed due to CGTS-7651 - ifconfig down or ifdown is not valid procedure for infra failure test
# # Will be reworked via US102236
#
# IF_DOWN_HOSTS = []
# HOST_TYPE_PATTERN = re.compile('compute|storage|standby_controller|active_controller')
#
#
# @fixture(scope='module', autouse=True)
# def skip_module():
#     LOG.fixture_step("(module) Check if system has infra configured")
#     active_con = system_helper.get_active_controller_name()
#     infra_ifs = host_helper.get_host_interfaces_for_net_type(host=active_con, net_type='infra')
#     if not infra_ifs:
#         skip("No infra network configured on system.")
#
#     if system_helper.is_aio_simplex():
#         skip("Simplex lab - expected behavior unknown. Skip for now.")
#
#
# @fixture(scope='function', autouse=True)
# def bring_up_hosts(request):
#     def recover():
#         for host_and_if in IF_DOWN_HOSTS:
#             host, infra_if = host_and_if
#             try:
#                 LOG.fixture_step("Attempt to run ifup on {} infra interface {}".format(host, infra_if))
#                 with host_helper.ssh_to_host(host) as host_ssh:
#                     host_ssh.exec_sudo_cmd('ifup {}'.format(infra_if), fail_ok=True, get_exit_code=False)
#             except:
#                 pass
#
#     request.addfinalizer(recover)
#
#
# def _select_and_get_host_infra_info(host_type):
#     """
#     Select one host of given host_type and get the infra eth names.
#     Args:
#         host_type (str): Valid values: 'compute', 'storage', 'active_controller', 'standby_controller'
#
#     Returns (tuple): (host, infra_interfaces)
#
#     """
#     LOG.fixture_step("Getting host with {} function and the infra eth names for selected host".format(host_type))
#     if host_type == 'compute':
#         if system_helper.is_aio_duplex():
#             host = system_helper.get_standby_controller_name()
#             assert host
#         else:
#             host = host_helper.get_up_hypervisors()[0]
#
#     elif host_type == 'storage':
#         storage_hosts = system_helper.get_hosts('storage', 'unlocked', 'enabled', 'available')
#         if not storage_hosts:
#             skip("No up storage host on system")
#         host = storage_hosts[0]
#
#     elif host_type == 'active_controller':
#         host = system_helper.get_active_controller_name()
#
#     elif host_type == 'standby_controller':
#         if system_helper.is_aio_system():
#             skip("Not applicable to CPE system")
#         host = system_helper.get_standby_controller_name()
#
#     else:
#         raise ValueError("Unknown host_type: {}".format(host_type))
#
#     infra_ifs = host_helper.get_host_interfaces_for_net_type(host=host, net_type='infra')
#     infra_aes = []
#     for i in infra_ifs['ae']:
#         infra_aes += i[1]
#
#     infra_ifs = infra_ifs['ethernet'] + infra_ifs['vlan'] + infra_aes
#
#     LOG.info("{} is selected. Infra ifs: {}".format(host, infra_ifs))
#     return host, infra_ifs
#
#
# def bring_up_or_down_infra_on_host(host, infra_if, infra_up=False):
#     global IF_DOWN_HOSTS
#     with host_helper.ssh_to_host(host) as host_ssh:
#         host_and_if = (host, infra_if)
#         if not infra_up:
#             IF_DOWN_HOSTS.append(host_and_if)
#
#         if_state = 'up' if infra_up else 'down'
#         cmd = "ifconfig {} {}".format(infra_if, if_state)
#         LOG.tc_step('Run ifconfig {} on {} infra interface {}'.format(if_state, host, infra_if))
#         host_ssh.exec_sudo_cmd(cmd, fail_ok=False)
#         if infra_up and host_and_if in IF_DOWN_HOSTS:
#             IF_DOWN_HOSTS.remove(host_and_if)
#
#
# def wait_for_infra_net_fail_events(host, is_standby=False, swacted=False):
#     LOG.tc_step('Verify expected events for infra network failure')
#     entity_inst_infra_fail = 'host={}.network=Infrastructure'.format(host)
#     if not swacted:
#         # Note: If condition added due to CGTS-6749, which is closed as 'won't fix'
#         # For infra AE, it might take up to 60 seconds to start rebooting host, for single infra, it took about 15
#         # seconds
#         system_helper.wait_for_alarm(alarm_id=EventLogID.INFRA_NET_FAIL, entity_id=entity_inst_infra_fail,
#                                      severity='critical', timeout=60, fail_ok=False)
#
#     entity_inst_recovery = 'host={}'.format(host)
#     res = system_helper.wait_for_alarm(alarm_id=EventLogID.HOST_RECOVERY_IN_PROGRESS, entity_id=entity_inst_recovery,
#                                        severity='critical', timeout=60, fail_ok=True)[0]
#
#     if is_standby:
#         assert not res, "Host recovery event is logged for standby controller"
#     else:
#         assert res, "Host recovery event did not appear"
#
#
# @mark.usefixtures('check_alarms')
# @mark.parametrize('host_function', [
#     'storage',
#     'compute',
#     'compute_and_swact',
#     'standby_controller',
# ])
# def test_infra_network_failure_recovery(host_function):
#     """
#     US48577: Mtce: Infrastructure Network Heartbeat
#         TC3839 - Bring down the infra network on hosts (expect active_controller) and verify that the host recovers.
#         TC3840 – Verify the infra network with Lag and heart beat mechanism is working as expected
#         TC3842 – Do a Swact while the infra network loss is detected. Verify the failure is detected by newly
#                  active controller and proper recovery is started
#
#     Args:
#         host_function: scenario under test
#
#     Skip Conditions:
#         - Simplex lab (behavior unknown)
#         - No infra network configured on system
#
#     Test Steps:
#         - ssh to host and identify infra interface device name
#         - sudo ifconfig <interface> down
#         - verify critical alarms raised
#             - For compute and storage only: set 200.004 <host> experienced a service-affecting failure. Auto-recovery
#                 in progress.  host=storage-1
#             - set  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
#                 host=<host>.network=Infrastructure
#         - For standby controller:
#             - verify host in degraded state
#             - verify swact is not allowed
#             - sudo ifconfig <interface> up to manually recover the system
#         - For compute or storage host:
#             - (swact when specified in host_function)
#             - Wait for host to be rebooted automatically for recovery
#         - Verify host recovered and critical alarms are cleared
#             - verify host is in good states
#             - For compute and storage only: clear 200.004 <host> experienced a service-affecting failure. Auto-recovery
#                 in progress.  host=storage-1
#             - clear  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
#                 host=<host>.network=Infrastructure
#             - log  200.022  <host> is now 'enabled'  host=<host>.state=enabled
#         - For standby controller:
#             - verify swact can be done after recovery
#
#     Teardown:
#         - ifup when necessary
#         - Wait for host to recover
#
#     """
#     global IF_DOWN_HOSTS
#     host_type = HOST_TYPE_PATTERN.findall(host_function)[0]
#     do_swact = True if 'swact' in host_function else False
#     is_standby = True if host_type == 'standby_controller' else False
#
#     if do_swact and system_helper.is_aio_system():
#         skip("Skip for CPE where swact is disallowed when infra failed on standby")
#
#     host, infra_ifs = _select_and_get_host_infra_info(host_type=host_type)
#     assert infra_ifs, "Infra interfaces not found on {} even though infra is configured on system".format(host)
#
#     infra_interface_dev_name = infra_ifs[0]
#
#     HostsToRecover.add(host)
#     bring_up_or_down_infra_on_host(host, infra_interface_dev_name)
#
#     if do_swact:
#         LOG.tc_step("Swact controllers to check infra heartbeat status persists with new active controller")
#         host_helper.swact_host()
#
#     wait_for_infra_net_fail_events(host=host, is_standby=is_standby, swacted=do_swact)
#
#     if is_standby:
#         LOG.tc_step("Wait for standby controller to stay in degraded state for at least 60 seconds")
#         expt_states = {'operational': HostOperState.ENABLED, 'availability': HostAvailState.DEGRADED}
#         system_helper.wait_for_hosts_states(hosts=host, timeout=300, duration=60, check_interval=10, fail_ok=False,
#                                             **expt_states)
#
#         LOG.tc_step("Check swact is not allowed when standby controller has infra fail")
#         res, out = host_helper.swact_host(fail_ok=True)
#         assert 1 == res, "SWACT is not rejected even though infra failed on standby. Details: {}".format(out)
#
#         bring_up_or_down_infra_on_host(host, infra_if=infra_interface_dev_name, infra_up=True)
#
#     else:
#         LOG.tc_step('Verify host {} in failed state after infra put down '.format(host))
#         expt_states = {'operational': HostOperState.DISABLED,
#                        'availability': [HostAvailState.FAILED, HostAvailState.OFFLINE]}
#         system_helper.wait_for_host_values(host, timeout=60, fail_ok=False, **expt_states)
#         IF_DOWN_HOSTS.remove((host, infra_interface_dev_name))
#
#     LOG.tc_step('Wait for host to be recovered')
#     expt_recov_states = {'operational': HostOperState.ENABLED,
#                          'availability': HostAvailState.AVAILABLE}
#     system_helper.wait_for_hosts_states(host, duration=10, fail_ok=False, **expt_recov_states)
#     host_helper.wait_for_hosts_ready(hosts=host)
#
#     LOG.tc_step("Check relative alarms are cleared after recovery")
#     system_helper.wait_for_alarm_gone(EventLogID.INFRA_NET_FAIL, entity_id=host, fail_ok=False, timeout=60)
#     if not is_standby:
#         system_helper.wait_for_alarm_gone(EventLogID.HOST_RECOVERY_IN_PROGRESS, entity_id=host, fail_ok=False,
#                                           timeout=30)
#
#     if is_standby:
#         LOG.tc_step("Check swact controllers are working after infra recovery on standby controller")
#         host_helper.swact_host()
#         host_helper.swact_host()
#
#     LOG.info('System successfully recovered from {} infra network failure'.format(host_type))
