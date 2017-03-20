# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
from pytest import skip
import time
from pytest import fixture
from utils.tis_log import LOG
from consts.cgcs import EventLogID
from keywords import host_helper, system_helper


@fixture(scope='module')
def get_hosts_infra_info():
    hosts = system_helper.get_hostnames()

    field_names = ['ifname', 'networktype', 'iftype', 'vlan_id']
    hosts_infra_info = system_helper.get_hosts_interfaces_info(hosts, field_names, **{'network type': 'infra'})
    LOG.info("Hosts infra network info: {}".format(hosts_infra_info))
    hosts_infra_dict = {}

    for host in hosts:
        infra_values_dict = hosts_infra_info[host]
        if len(infra_values_dict) > 0:
            infra_ports = system_helper.get_host_ports_for_net_type(host, net_type='infra')
            LOG.info("Host {} ports: {}".format(host, infra_ports))
            infra_interface_name = next(iter(infra_values_dict))
            infra_values = infra_values_dict[infra_interface_name]
            ifconfig_name = ''
            dev_names = host_helper.get_host_network_interface_dev_names(host)
            if infra_values[2] == 'vlan':
                if infra_interface_name in dev_names:
                    ifconfig_name += infra_interface_name
                else:
                    dev_name = next(dev for dev in dev_names if infra_values[3] in dev)
                    ifconfig_name += dev_name if dev_name else "{}.{}".format(infra_ports[0].infra_values[3])
            elif infra_values[2] == 'ae':
                ifconfig_name += infra_interface_name
            else:
                ifconfig_name += infra_interface_name if infra_ports[0] in infra_interface_name else infra_ports[0]

            infra_values.append(infra_ports)
            infra_values.append(ifconfig_name)
            hosts_infra_dict[host] = infra_values

    LOG.info("Hosts infra network info: {}".format(hosts_infra_dict))
    return hosts_infra_dict


def test_infrastructure_network_heartbeat_recovery(get_hosts_infra_info):
    """
    US48577: Mtce: Infrastructure Network Heartbeat
        TC3839 - Bring down the infra network on hosts( expect  active controller) and verify that the host recovers.
        TC3840 – Verify the infra network with Lag and heart beat mechanism is working as expected

    Args:
        get_hosts_infra_info:

    Setup:
        CPE -  controller-1
        Regular - computes
        Storage - computes and storages

    Test Steps:
    1) ssh to host and identify infra interface device name
    2) sudo ifconfig <interface> down
    3) verify critical alarms raised
        - set 200.004 <host> experienced a service-affecting failure. Auto-recovery in progress.  host=storage-1
        - set  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
         host=<host>.network=Infrastructure
    4) Verify host recovered and critical alarms are cleared
        - clear 200.004 <host> experienced a service-affecting failure. Auto-recovery in progress.  host=storage-1
        - clear  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
         host=<host>.network=Infrastructure
        - log  200.022  <host> is now 'enabled'  host=<host>.state=enabled

    Teardown:
        - None
    Skip:
        - System with no infrastructure network

    Potential flaws:
        1.  We're not checking if unexpected alarms are raised (TODO).


    """
    hosts_infra_info = get_hosts_infra_info
    active_controller, standby_controller = system_helper.get_active_standby_controllers()
    if active_controller in hosts_infra_info:
        del hosts_infra_info[active_controller]

    if len(hosts_infra_info) == 0:
        skip(msg="No infrastructure network in the system")
    hosts = []
    if system_helper.is_small_footprint():
        hosts.append(standby_controller)
    else:
        for host in hosts_infra_info:
            if 'controller' not in host:
                hosts.append(host)

    for host in hosts:
        infra_info = hosts_infra_info[host]
        infra_interface_dev_name = infra_info[5]
        with host_helper.ssh_to_host(host) as host_ssh:
            cmd = "ifconfig {} down".format(infra_interface_dev_name)
            LOG.tc_step('Disabling host {} infra network {} '.format(host, infra_interface_dev_name))
            rc, output = host_ssh.exec_sudo_cmd(cmd)
            assert rc == 0, "Fail to execute cmd {} on host {}: {}. ".format(cmd, host, output)

        LOG.tc_step('Verifying host {} in failed state after infra put down '.format(host))
        expected = {'operational': 'disabled', 'availability': 'failed'}
        assert host_helper.wait_for_host_states(host, timeout=30, **expected)

        LOG.tc_step('Verifying expected events  for infra network failure')
        entity_instance = 'host={}.network=Infrastructure'.format(host)

        system_helper.wait_for_events(5, num=5, strict=False,
                                      **{'Entity Instance ID': entity_instance,
                                         'Event Log ID': EventLogID.INFRASTRUCTURE_NETWORK_FAILURE,
                                         'State': 'set'})
        entity_instance = 'host={}'.format(host)
        system_helper.wait_for_events(5, num=5, strict=False,
                                      **{'Entity Instance ID': entity_instance,
                                         'Event Log ID': EventLogID.MTC_MONITORED_PROCESS_FAILURE,
                                         'State': 'set'})

        LOG.tc_step('Verifying host in recovery mode after infra network failure')
        expected = {'operational': 'enabled', 'availability': 'available'}
        host_helper.wait_for_host_states(host, **expected)

        assert system_helper.wait_for_alarm_gone(EventLogID.INFRASTRUCTURE_NETWORK_FAILURE), "Alarm {} not cleared"\
            .format(EventLogID.INFRASTRUCTURE_NETWORK_FAILURE)
        assert system_helper.wait_for_alarm_gone(EventLogID.MTC_MONITORED_PROCESS_FAILURE), "Alarm {} not cleared"\
            .format(EventLogID.MTC_MONITORED_PROCESS_FAILURE)

        LOG.info('Host {} recovered from  infra network failure'.format(host))


def test_infrastructure_network_heartbeat_with_swact(get_hosts_infra_info):
    """
    US48577: Mtce: Infrastructure Network Heartbeat
    TC3842 – Do a Swact while the infra network loss is detected. Verify the failure is detected by newly
        active controller and proper recovery is started

    Args:
        get_hosts_infra_info:

    Setup:
        - Requires non cpe lab

    Test Steps:
    1) ssh to a compute or storage node and identify infra interface device name
    2) sudo ifconfig <interface> down
    3) Do swact
    4) verify network loss are detected by newly active controller and critical alarms raised
        - set 200.004 <host> experienced a service-affecting failure. Auto-recovery in progress.  host=storage-1
        - set  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
         host=<host>.network=Infrastructure
    5) Verify host recovered and critical alarms are cleared
        - clear 200.004 <host> experienced a service-affecting failure. Auto-recovery in progress.  host=storage-1
        - clear  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
         host=<host>.network=Infrastructure
        - log  200.022  <host> is now 'enabled'  host=<host>.state=enabled

    Teardown:
        - None
    Skip:
        - System with no infrastructure network
        - CPE system - Cannot swact to degraded controller.

    Potential flaws:
        1.  We're not checking if unexpected alarms are raised (TODO).


    """
    hosts_infra_info = get_hosts_infra_info
    if 'controller-0' in hosts_infra_info:
        del hosts_infra_info['controller-0']

    if len(hosts_infra_info) == 0:
        skip(msg="No infrastructure network in the system")
    if system_helper.is_small_footprint():
        skip(msg="System is CPE lab.")

    host = 'storage-0' if 'storage-0' in hosts_infra_info else \
        next(h for h in hosts_infra_info if 'controller' not in h)
    infra_info = hosts_infra_info[host]
    infra_interface_dev_name = infra_info[5]

    with host_helper.ssh_to_host(host) as host_ssh:
        cmd = "ifconfig {} down".format(infra_interface_dev_name)
        LOG.tc_step('Disabling host {} infra network {} '.format(host, infra_interface_dev_name))
        rc, output = host_ssh.exec_sudo_cmd(cmd)
        assert rc == 0, "Fail to execute cmd {} on host {}: {}. ".format(cmd, host, output)

    LOG.tc_step('Swacting while infra on host {} is down '.format(host))
    rc, msg = host_helper.swact_host()
    assert rc == 0, "Fail to swact"

    LOG.tc_step('Verifying host {} in failed state after infra put down '.format(host))
    expected = {'operational': 'disabled', 'availability': 'failed'}
    assert host_helper.wait_for_host_states(host, timeout=30, **expected)

    LOG.tc_step('Verifying expected events  for infra network failure')
    entity_instance = 'host={}.network=Infrastructure'.format(host)

    system_helper.wait_for_events(5, num=5, strict=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID': EventLogID.INFRASTRUCTURE_NETWORK_FAILURE,
                                     'State': 'set'})
    entity_instance = 'host={}'.format(host)
    system_helper.wait_for_events(5, num=5, strict=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID': EventLogID.MTC_MONITORED_PROCESS_FAILURE,
                                     'State': 'set'})

    LOG.tc_step('Verifying host in recovery mode after infra network failure')
    expected = {'operational': 'enabled', 'availability': 'available'}
    host_helper.wait_for_host_states(host, **expected)

    assert system_helper.wait_for_alarm_gone(EventLogID.INFRASTRUCTURE_NETWORK_FAILURE), "Alarm {} not cleared"\
        .format(EventLogID.INFRASTRUCTURE_NETWORK_FAILURE)
    assert system_helper.wait_for_alarm_gone(EventLogID.MTC_MONITORED_PROCESS_FAILURE), "Alarm {} not cleared"\
        .format(EventLogID.MTC_MONITORED_PROCESS_FAILURE)

    LOG.info('Host {} recovered from  infra network failure'.format(host))


def test_infrastructure_network_heartbeat_standby_controller(get_hosts_infra_info):
    """
    Bring down the infra network on standby controller on non cpe lab. Verify the  standby controller changes
    to degraded state and  becomes available when the infra network is up.
    Args:
        get_hosts_infra_info:

    Setup:
        - Non cpe lab

    Test Steps:
        1) ssh to a standby controller and identify infra interface device name
        2) Disable infra network: sudo ifconfig <interface> down
        3) verify standby controller goes to degraded state and critical alarms raised
            - set 200.004 <host> experienced a service-affecting failure. Auto-recovery in progress.  host=storage-1
            - set  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
                host=<host>.network=Infrastructure
        4) Very node remains in degraded state,  no recovery is initiated
        5) Enable the infra interface: sudo ifconfig <interface> up
        6) Verify host recovered and critical alarms are cleared
            - clear 200.004 <host> experienced a service-affecting failure. Auto-recovery in progress.  host=storage-1
            - clear  200.009 <host> experienced a persistent critical 'Infrastructure Network' communication failure.
                host=<host>.network=Infrastructure
            - log  200.022  <host> is now 'enabled'  host=<host>.state=enabled

    Teardown:
        - None
    Skip:
        - System with no infrastructure network
        - CPE system.

    Potential flaws:
        1.  We're not checking if unexpected alarms are raised (TODO).


    """
    hosts_infra_info = get_hosts_infra_info
    active_controller, standby_controller = system_helper.get_active_standby_controllers()
    if active_controller in hosts_infra_info:
        del hosts_infra_info[active_controller]

    if len(hosts_infra_info) == 0:
        skip(msg="No infrastructure network in the system")
    if system_helper.is_small_footprint():
        skip(msg="System is CPE lab.")

    host = standby_controller
    infra_info = hosts_infra_info[host]
    infra_interface_dev_name = infra_info[5]

    with host_helper.ssh_to_host(host) as host_ssh:
        cmd = "ifconfig {} down".format(infra_interface_dev_name)
        LOG.tc_step('Disabling host {} infra network {} '.format(host, infra_interface_dev_name))
        rc, output = host_ssh.exec_sudo_cmd(cmd)
        assert rc == 0, "Fail to execute cmd {} on host {}: {}. ".format(cmd, host, output)

    LOG.tc_step('Verifying host {} in degraded state after infra put down and remains on this state'.format(host))
    expected = {'operational': 'enabled', 'availability': 'degraded'}
    for count in range(1, 4):
        LOG.info("Checking standby controller remains in degraded state; iteration {}".format(count))
        assert host_helper.wait_for_host_states(host, timeout=30, **expected)
        time.sleep(60)

    LOG.info('Host {} remained in degraded state with no recovery.'.format(host))

    LOG.tc_step('Verifying expected events  for infra network failure on standby controller')
    entity_instance = 'host={}.network=Infrastructure'.format(host)

    system_helper.wait_for_events(5, num=5, strict=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID': EventLogID.INFRASTRUCTURE_NETWORK_FAILURE,
                                     'State': 'set'})

    entity_instance = 'host={}'.format(host)
    system_helper.wait_for_events(5, num=5, strict=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID': EventLogID.MTC_MONITORED_PROCESS_FAILURE,
                                     'State': 'set'})

    LOG.tc_step('Verifying  swact is rejected  while infra on host {} is down '.format(host))
    rc, msg = host_helper.swact_host(fail_ok=True)
    assert rc == 1, "Swact was possible while standby is in degraded state"

    LOG.tc_step('Verifying  host {} recovers when infra network is enabled again...'.format(host))
    with host_helper.ssh_to_host(host) as host_ssh:
        cmd = "ifconfig {} up".format(infra_interface_dev_name)
        LOG.tc_step('Enabling host {} infra network {} '.format(host, infra_interface_dev_name))
        rc, output = host_ssh.exec_sudo_cmd(cmd)
        assert rc == 0, "Fail to execute cmd {} on host {}: {}. ".format(cmd, host, output)

    LOG.tc_step('Verifying host {} is recovered  after infra network is enabled'.format(host))
    expected = {'operational': 'enabled', 'availability': 'available'}
    host_helper.wait_for_host_states(host, **expected)
    LOG.tc_step('Verifying alarms are cleared after host {} is recovered '.format(host))
    assert system_helper.wait_for_alarm_gone(EventLogID.INFRASTRUCTURE_NETWORK_FAILURE), "Alarm {} not cleared"\
        .format(EventLogID.INFRASTRUCTURE_NETWORK_FAILURE)
    assert system_helper.wait_for_alarm_gone(EventLogID.MTC_MONITORED_PROCESS_FAILURE), "Alarm {} not cleared"\
        .format(EventLogID.MTC_MONITORED_PROCESS_FAILURE)

    LOG.tc_step('Verifying  swact is possible  after host {} recovery '.format(host))
    rc, msg = host_helper.swact_host()
    assert rc == 0, "Fail to swact after standby recovered from infra failure"
    LOG.info('Swact to host {} was successful'.format(host))

    LOG.tc_step('Swacting back again ......')
    rc, msg = host_helper.swact_host()
    assert rc == 0, "Fail to swact back  standby after  infra is enabled"
    LOG.info('Swact to host {} was successful'.format(host))

