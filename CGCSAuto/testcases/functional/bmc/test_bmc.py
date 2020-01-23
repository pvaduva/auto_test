from consts.filepaths import BMCPath
from consts import stx
from consts.timeout import HostTimeout
from consts.stx import HostAvailState, HostAdminState
from enum import Enum
from keywords import host_helper, system_helper, common
from pytest import mark, skip, fixture
from utils import cli, table_parser
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
import ipaddress
import json
import pytest
from testfixtures.recover_hosts import HostsToRecover

REFRESH_TIME = 130  # seconds to wait for mtce refresh bm settings
initial_host_state = []


class BMProtocols:
    IPMI = 'ipmi'
    REDFISH = 'redfish'
    DYNAMIC = 'dynamic'


class HostState:
    def __init__(self):
        self.admin_state = ''
        self.node = ''


@fixture(autouse=True)
def check_alarms():
    pass


def _check_redfish_support(bm_ip, con_ssh):
    redfish_supported = False
    ip = ipaddress.ip_address(bm_ip)
    if ip.version == 6:
        cmd = 'redfishtool -S Always -T 30 -r [%s] versions' % bm_ip
    else:
        cmd = 'redfishtool -S Always -T 30 %s versions' % bm_ip

    ret, cmd_out = con_ssh.exec_cmd(cmd, fail_ok=True)
    if ret == 0:
        redfish_ver = json.loads(cmd_out)
        if redfish_ver is not None:
            redfish_supported = True

    return redfish_supported


class BMTestCase:
    class SensorFileState(Enum):
        FileNotFound = 2
        FileIsEmpty = 1
        FileOK = 0

    def __init__(self, node, con_ssh):
        self.node = node
        self.con_ssh = con_ssh
        fields = ['bm_type', 'bm_ip', 'bm_username']
        bm_type, bm_ip, bm_username = system_helper.get_host_values(node, fields=fields)
        LOG.info('%s %s' % (node, [bm_type, bm_ip, bm_username]))
        self.bm_type = bm_type
        self.bm_ip = bm_ip
        self.bm_username = bm_username
        self.bm_password = None
        self.init_bm_type = bm_type
        self.init_bm_ip = bm_ip
        self.init_bm_username = bm_username
        self.redfish_supported = False

        if bm_type is None or bm_ip is None or bm_username is None:
            self.bm_provisioned = False
        else:
            self.bm_provisioned = True
            self.redfish_supported = _check_redfish_support(self.bm_ip, self.con_ssh)

    def reconfig_bm(self, bm_type=None, bm_ip=None):
        if bm_type is None and bm_ip is None:
            LOG.info('Nothing changed')
            return

        if bm_type is None:
            bm_type = self.bm_type

        if bm_ip is None:
            bm_ip = self.bm_ip

        cli.system("host-update",
                   positional_args="%s bm_type=%s bm_ip=%s" % (self.node, bm_type, bm_ip))

        fields = ['bm_type', 'bm_ip', 'bm_username']
        values = system_helper.get_host_values(self.node, fields=fields)

        assert len(values) == 3
        assert bm_type == values[0]
        assert bm_ip == values[1]
        assert self.bm_username == values[2]
        LOG.info('Applied new bm_type %s to %s' % (values, self.node))
        self.bm_type = bm_type
        self.bm_ip = bm_ip

    def reconfig_bm_credential(self, bm_username, bm_password):
        cli.system("host-update",
                   positional_args="%s bm_username=%s bm_password=%s" % (self.node, bm_username, bm_password))

        fields = ['bm_type', 'bm_ip', 'bm_username']
        values = system_helper.get_host_values(self.node, fields=fields)

        assert len(values) == 3
        assert self.bm_type == values[0]
        assert self.bm_ip == values[1]
        assert bm_username == values[2]
        LOG.info('Applied new bm_settings %s to %s' % (values, self.node))

    def check_sensors(self):
        # verify sensors, return sensor array
        cmd_output = cli.system("host-sensor-list", positional_args=self.node)[1]

        t = table_parser.table(cmd_output)
        t = table_parser.filter_table(t, state='enabled', status='ok')
        return t['values']

    def get_sensor_data_filenames(self):
        if self.bm_type == BMProtocols.IPMI or \
                (not self.redfish_supported and self.bm_type == BMProtocols.DYNAMIC):
            sensor_data_files = BMCPath.get_ipmi_sensor_data_files(self.node)
        else:
            sensor_data_files = BMCPath.get_redfish_sensor_data_files(self.node)
        return sensor_data_files

    def check_sensor_data_file(self):
        sensor_data_files = self.get_sensor_data_filenames()

        # verify sensor data file(s) exists and not empty
        for sensor_data_file in sensor_data_files:
            c = 'ls -s %s' % sensor_data_file
            ret_val, out_text = self.con_ssh.exec_cmd(c)
            if ret_val != 0:
                return BMTestCase.SensorFileState.FileNotFound

        if int(out_text.split(' ')[0]) == 0:
            return BMTestCase.SensorFileState.FileIsEmpty

        return BMTestCase.SensorFileState.FileOK

    def check_bm_alarms(self, alarm_ids):
        alarm_tab = system_helper.get_alarms_table()
        t = table_parser.filter_table(
            alarm_tab, alarm_id=alarm_ids, entity_id='.*%s.*' % self.node, regex=True)
        alarms = t['values']
        return alarms

    def power_off(self):
        LOG.info('power off %s' % self.node)
        cli.system('host-power-off %s' % self.node, ssh_client=self.con_ssh)

        wait_time = HostTimeout.POWER_OFF_OFFLINE
        LOG.info('wait for %s power off (up to %s seconds)' % (self.node, wait_time))
        # here an easy verification is taken, instead of waiting many minutes
        # to ensure node is powered off instead of a reboot
        ret = system_helper.wait_for_host_values(self.node, wait_time,
                                                 availability=[HostAvailState.POWER_OFF])
        assert ret, "%s is not offline %s seconds after power-off executed" % (self.node, wait_time)

    def power_on(self):
        LOG.info('power on %s' % self.node)
        cli.system('host-power-on %s' % self.node, ssh_client=self.con_ssh)

        wait_time = 120 # wait for power on task complete
        LOG.info('wait for %s power on action completed (up to %s seconds)' % (self.node, wait_time))
        ret = system_helper.wait_for_host_values(self.node, wait_time,
                                                 task=['Powering On'])
        if not ret:
            LOG.info('Powering on task has not shown up in %s seconds' % wait_time)

        wait_time = HostTimeout.HOST_LOOKED_REBOOT
        LOG.tc_step('wait for %s online (up to %s seconds)' % (self.node, wait_time))
        ret = system_helper.wait_for_host_values(self.node, wait_time,
                                                 availability=[HostAvailState.ONLINE,
                                                               HostAvailState.DEGRADED,
                                                               HostAvailState.AVAILABLE])
        assert ret, 'wait for %s online %s seconds after power-on timeout' % (self.node, wait_time)

    def reset(self):
        LOG.info('reset %s' % self.node)
        cli.system('host-reset %s' % self.node, ssh_client=self.con_ssh)

        wait_time = HostTimeout.POWER_OFF_OFFLINE
        LOG.info('wait for %s offline (up to %s seconds)' % (self.node, wait_time))
        ret = system_helper.wait_for_host_values(self.node, wait_time, availability=[HostAvailState.OFFLINE])
        assert ret, "%s is not offline %s seconds after system host-reset executed" % (self.node, wait_time)

        wait_time = HostTimeout.HOST_LOOKED_REBOOT
        LOG.info('wait for %s online (up to %s seconds)' % (self.node, wait_time))
        ret = system_helper.wait_for_host_values(self.node, wait_time,
                                                 availability=[HostAvailState.ONLINE,
                                                               HostAvailState.DEGRADED,
                                                               HostAvailState.AVAILABLE])
        assert ret, 'wait for %s online %s seconds after power-on timeout' % (self.node, wait_time)

    def verify_bm_config(self):
        def _check_sensors():
            sensors = self.check_sensors()
            if len(sensors) == 0:
                LOG.info('.')
                return 1

            ssh = ControllerClient.get_active_controller()
            sql = "select mtce_info from i_host where hostname='%s'" % self.node
            cmd = "sudo su - postgres -c \"psql -d sysinv -t -c \\\"" + sql + "\\\"\""
            ret, txt = ssh.exec_sudo_cmd(cmd, fail_ok=False)
            actual_protocol = self.bm_type
            if self.bm_type == BMProtocols.DYNAMIC:
                if self.redfish_supported:
                    actual_protocol = BMProtocols.REDFISH
                else:
                    actual_protocol = BMProtocols.IPMI
            expected = 'bmc_protocol:%s' % actual_protocol
            if expected not in txt:
                LOG.info(expected)
                return 2

            rc = self.check_sensor_data_file()
            if rc == BMTestCase.SensorFileState.FileNotFound:
                return 3
            elif rc == BMTestCase.SensorFileState.FileNotFound.FileIsEmpty:
                return 4

            return 0

        wait_timeout = REFRESH_TIME
        LOG.info('wait for sensor data refresh (up to %s seconds)' % wait_timeout)
        ret, val = common.wait_for_val_from_func([0], wait_timeout, 5, _check_sensors)

        assert ret, 'Timeout (%s seconds) waiting for sensors to be recreated' % wait_timeout
        if val == 1:
            assert 0, 'No sensor is enabled/ok'
        elif val == 2:
            assert 0, 'bm type incorrect'
        elif val == 3:
            assert 0, 'sensor data file(s) not exists'
        elif val == 4:
            assert 0, 'sensor data file(s) empty'

        LOG.info('verify there is no bmc alarms')
        alarms = self.check_bm_alarms(stx.EventLogID.BM_ALARM)

        assert len(alarms) == 0, 'Found alarms %s' % alarms


@pytest.fixture(scope='module',
                params=[BMProtocols.IPMI,
                        BMProtocols.REDFISH,
                        BMProtocols.DYNAMIC])
def bm_test_instances(pytestconfig, request):
    bm_type = request.param
    bmc_password = pytestconfig.getoption("bmc_password")
    target_nodes = pytestconfig.getoption("bmc_target")
    online_nodes = system_helper.get_hosts(availability=[HostAvailState.AVAILABLE,
                                                         HostAvailState.DEGRADED,
                                                         HostAvailState.ONLINE])
    if len(target_nodes) == 0:
        nodes = online_nodes
    else:
        nodes = []
        for node in target_nodes:
            if node in online_nodes:
                nodes.append(node)
            else:
                LOG.info('%s is offline, skip it' % node)

    instances = []
    con_ssh = ControllerClient.get_active_controller()
    for node in nodes:
        test_instance = BMTestCase(node, con_ssh)
        if not test_instance.bm_provisioned:
            LOG.info('Skip %s, bm is not provisioned' % node)
            continue
        if bm_type == BMProtocols.REDFISH and not test_instance.redfish_supported:
            LOG.info('Skip %s for redfish, unsupported protocol' % node)
            continue
        test_instance.bm_password = bmc_password
        alarms = test_instance.check_bm_alarms([stx.EventLogID.BM_ALARM,
                                                stx.EventLogID.BM_SENSOR_ALARM,
                                                stx.EventLogID.BM_SENSOR_CFG_ALARM,
                                                stx.EventLogID.BM_SERSORGRP_CFG_ALARM])
        if len(alarms) > 0:
            LOG.info('Skip %s, bm alarm(s) exists' % node)
            continue

        LOG.info("%s %s" % (node, bm_type))
        test_instance.reconfig_bm(bm_type=bm_type)
        instances.append(test_instance)

    if len(instances) == 0:
        skip("no suitable node in the lab to test")

    yield instances


@mark.bmctests
def test_bmc_verify_bm_type(bm_test_instances):
    """
    TC1: Verify mixed BM types
    Description:
    ============
    This test is to verify dynamic, redfish and ipmi bm_type applied to different hosts and verify
    sensor data collection on all the hosts.

    Pre-requisites:
    ==============
    LAB is capable of collecting sensor data using redfish and ipmitool. Lab is installed with latest
    load. Lab have at least 3 hosts to have all three parameters redfish,ipmi and dynamic in all the hosts.
    Eg: Wolfpass labs.

    STEPS
    ======
    1. Update host bm_type = redfish, bm_type = ipmitool bm_type = dynamic .
    System host-update <hostname> bm_type=ipmi bm_password=<bmc pw> bm_username=<bm un> bm_ip=bm_ip.

    2. Verify sensor data file in each host in below path as per provision.
        System debug host-show controller-0 and verify provisioned protocol
    3. Verify sensor data are collected for all the hosts using below command
         System host-sensor-list <hostname>
    4. Verify no vm alarm 200.010 is raised.
    *********************************************************************
    """
    for instance in bm_test_instances:
        instance.verify_bm_config()


@mark.bmctests
def test_bmc_incorrect_provision(bm_test_instances):
    """
    *********************************************************************
    TC3: Incorrect provision (username password and/or ip address) for BMC to verify
    provision failure alarm.

    Description:
    ============
    This test is to verify alarms on incorrect provision data(username password and/or
     ip address) and reject error message.

    Pre-requisites:
    ==============
    Either ipmi or redfish tool supported lab. Lab that supports both tools will be ideal
    lab for this test.
    Eg: Wolfpass labs.

    STEPS
    ======
    1. Update host bm_type = dynamic and check which tool is used to collect BMC sensor
       data.
     It should be in /var/run/bmc/ ipmitool /hwmond_<hostname>_sensor_data  or
       /var/run/bmc/ipmitool/hwmond_<hostname>_sensor_data.
       System host-update <hostname> bm_type=ipmi bm_password=<bmc pw> bm_username=<bm un> bm_ip=bm_ip.
    2. Verify there is no BMC connection failure alarm for any of the hosts and sensor data collected.
       System host-sensor-list <hostname>
    3. Update bm_ip=incorrect bm_ip address
    4. Verify Incorrect IP alarm BMC access failure alarm.
    5. Update bm_ip=correct bm_ip address verify alarm cleared and sensor data is collected.
    6. Update bmc_password=<incorrect bmc pw>   and verify incorrect BMC access BMC failure alarm.
    7. Update bmc_password=<correct bmc pw>   and verify sensor data is collected
    8. Verify sensor data in file hwmond_<hostname>_sensor_data  is collected as before.
         Hosts provision as IPMI is collected in /var/run/bmc/ipmitool/
        Hosts provision in redfish is collected in /var/run/bmc/redfish/


    ***********************************************************************
    Start: Group of test cases to test BMC operations under certain bm_type
    ***********************************************************************

    Common setups for all tests in this section:
    - Configure specified bm_type for all hosts (redfish or ipml)

    """
    for instance in bm_test_instances:
        instance.verify_bm_config()

    for instance in bm_test_instances:
        dummy_ip = '127.0.0.1'
        LOG.tc_step('reconfigure %s bm_ip %s' % (instance.node, dummy_ip))
        instance.reconfig_bm(bm_ip=dummy_ip)

        def _check_alarm():
            alarms = instance.check_bm_alarms([stx.EventLogID.BM_ALARM])
            return len(alarms)

        try:
            wait_timeout = REFRESH_TIME
            LOG.tc_step('wait for bm config alarm to show up (up to %s seconds)' % wait_timeout)
            ret, num_of_alarms = common.wait_for_val_from_func([1], wait_timeout, 5, _check_alarm)
            assert num_of_alarms == 1, 'Expected alarms %s not found' % stx.EventLogID.BM_ALARM
        finally:
            LOG.tc_step('restore %s bm settings' % instance.node)
            instance.reconfig_bm(bm_ip=instance.init_bm_ip)
            wait_timeout = REFRESH_TIME
            LOG.tc_step('wait for bm config alarm to clear (up to %s seconds)' % wait_timeout)
            ret, num_of_alarms = common.wait_for_val_from_func([0], wait_timeout, 5, _check_alarm)
            assert num_of_alarms == 0, 'Alarm is not cleared after %s seconds' % wait_timeout

    total_tests = 0
    for instance in bm_test_instances:
        if instance.bm_password is None:
            continue

        total_tests = total_tests + 1
        dumy_username = '%s1' % instance.bm_username
        LOG.tc_step('reconfigure %s bm_username %s' % (instance.node, dumy_username))
        instance.reconfig_bm_credential(dumy_username, instance.bm_password)

        def _check_alarm():
            alarms = instance.check_bm_alarms([stx.EventLogID.BM_ALARM])
            return len(alarms)

        try:
            wait_timeout = REFRESH_TIME
            LOG.tc_step('wait for bm config alarm to show up (up to %s seconds)' % wait_timeout)
            ret, num_of_alarms = common.wait_for_val_from_func([1], wait_timeout, 5, _check_alarm)
            assert num_of_alarms == 1, 'Expected alarms %s not found' % stx.EventLogID.BM_ALARM
        finally:
            LOG.tc_step('restore %s bm settings' % instance.node)
            instance.reconfig_bm_credential(instance.bm_username, instance.bm_password)
            wait_timeout = REFRESH_TIME
            LOG.tc_step('wait for bm config alarm to clear (up to %s seconds)' % wait_timeout)
            ret, num_of_alarms = common.wait_for_val_from_func([0], wait_timeout, 5, _check_alarm)
            assert num_of_alarms == 0, 'Alarm is not cleared after %s seconds' % wait_timeout

    if total_tests > 0:
        LOG.info('Invalid credential verified %s passeed' % total_tests)


@mark.bmctests
def test_bmc_host_power_off(bm_test_instances):
    """
    TC5: Verify hosts power off and power on using BMC.
    Description:
    ============
        Verify sensor data is collected as per provision (dynamic,IPMI,Redfish) after the hosts was locked and unlocked.

    Pre-requisites:
    ==============
    Lab is installed with latest load. LAB is connected to BMC and provisioned with redfish or ipmitool or dynamic
    depends on lab capabilities.

    STEPS
    ======
    1. Power off using BMC cmd - system host-power-off
    2. Verify host is offline in a few seconds
    3. Power on using BMC cmd - system host-power-on
    4. Wait for host to come online (timeout should be boot time)
    5. Verify Sensor data is still collected >> Does this make sense when host is locked but online??

    *********************************************************************
    """
    if system_helper.is_aio_simplex():
        skip('BMC power on/off tests do not apply to AIO-SX labs')

    active_controller = system_helper.get_active_controller_name(con_ssh=bm_test_instances[0].con_ssh)
    test_nodes = 0
    for instance in bm_test_instances:
        node = instance.node
        if active_controller == node:
            continue

        admin_state = system_helper.get_host_values(node, 'administrative')
        if HostAdminState.UNLOCKED in admin_state:
            LOG.tc_step('lock %s' % node)
            ret, val = host_helper.lock_host(node, fail_ok=True)
            if ret != 0:
                continue  # cannot lock host, we don't care
            HostsToRecover.add(node, 'module')
        try:
            LOG.tc_step('power off %s' % node)
            instance.power_off()
        finally:
            avail_status = system_helper.get_host_values(node, 'availability')
            if avail_status not in [HostAvailState.ONLINE, HostAvailState.DEGRADED, HostAvailState.AVAILABLE]:
                LOG.tc_step('power on %s (%s)' % (node, avail_status))
                instance.power_on()

        instance.verify_bm_config()
        test_nodes = test_nodes + 1
    if test_nodes == 0:
        skip('No node is suitable for this test')


@mark.bmctests
def test_bmc_host_reset(bm_test_instances):
    """
    TC6: Verify hosts power off and power on using BMC.
    Steps are same as TC5 except change the BMC operation from power-off/on to reset
    *********************************************************************
    """
    if system_helper.is_aio_simplex():
        skip('BMC reset test does not apply to AIO-SX labs')

    test_nodes = 0
    active_controller = system_helper.get_active_controller_name(con_ssh=bm_test_instances[0].con_ssh)
    for instance in bm_test_instances:
        node = instance.node
        if active_controller == node:
            continue

        admin_state = system_helper.get_host_values(node, 'administrative')
        if HostAdminState.UNLOCKED in admin_state:
            LOG.tc_step('lock %s' % node)

            ret, val = host_helper.lock_host(node, fail_ok=True)
            if ret != 0:
                continue  # cannot lock host, we don't care
            HostsToRecover.add(node, 'module')

        LOG.tc_step('reset %s' % node)
        instance.reset()
        instance.verify_bm_config()
        test_nodes = test_nodes + 1
    if test_nodes == 0:
        skip('No node is suitable for this test')
