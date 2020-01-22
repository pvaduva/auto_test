from consts import stx
from consts.stx import HostAvailState, HostAdminState
from keywords import host_helper, system_helper
from pytest import mark, skip, fixture
from utils import table_parser
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
import pytest
import setups
from testcases.functional.bmc.test_bmc import BMProtocols, BMTestCase


class BMSwactTestCase(BMTestCase):
    def __init__(self, target_bm_type, node, con_ssh):
        super(BMSwactTestCase, self).__init__(node, con_ssh)
        self.target_bm_type = target_bm_type


@fixture(scope='module', autouse=True)
def pre_check():
    if setups.is_vbox():
        skip('BMC tests do not apply to VBox labs')

    con_ssh = ControllerClient.get_active_controller()
    if system_helper.is_aio_simplex():
        skip('BMC swact tests do not apply to AIO-SX labs')

    alarm_tab = system_helper.get_alarms_table()
    alarm_ids = [stx.EventLogID.BM_ALARM,
                 stx.EventLogID.BM_SENSOR_ALARM,
                 stx.EventLogID.BM_SENSOR_CFG_ALARM,
                 stx.EventLogID.BM_SERSORGRP_CFG_ALARM]
    t = table_parser.filter_table(
        alarm_tab, alarm_id=alarm_ids)
    alarms = t['values']

    if len(alarms) > 0:
        skip('Skip, bm alarm(s) exists')

    con_ssh = ControllerClient.get_active_controller()
    active_controller = system_helper.get_active_controller_name(con_ssh=con_ssh)
    controllers = ['controller-0', 'controller-1']
    controllers.remove(active_controller)
    standby_controller = controllers[0]
    admin_state = system_helper.get_host_values(standby_controller, 'administrative')[0]
    LOG.info('Unlock %s if it is locked' % standby_controller)
    if admin_state == HostAdminState.LOCKED:
        ret = host_helper.unlock_host(standby_controller, fail_ok=True)
        if ret != 0:
            skip('%s is locked and failed to unlock' % standby_controller)


@pytest.fixture(scope='module',
                params=[BMProtocols.IPMI,
                        BMProtocols.REDFISH,
                        BMProtocols.DYNAMIC])
def bm_test_instances(pytestconfig, request):
    if setups.is_vbox():
        skip('BMC tests do not apply to VBox labs')

    con_ssh = ControllerClient.get_active_controller()
    if system_helper.is_aio_simplex():
        skip('BMC tests do not apply to AIO-SX labs')

    alarm_tab = system_helper.get_alarms_table()
    alarm_ids = [stx.EventLogID.BM_ALARM,
                 stx.EventLogID.BM_SENSOR_ALARM,
                 stx.EventLogID.BM_SENSOR_CFG_ALARM,
                 stx.EventLogID.BM_SERSORGRP_CFG_ALARM]
    t = table_parser.filter_table(
        alarm_tab, alarm_id=alarm_ids)
    alarms = t['values']

    if len(alarms) > 0:
        skip('Skip, bm alarm(s) exists')

    bm_type = request.param
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
                LOG.warn('%s is offline, skip it' % node)

    instances = []
    for node in nodes:
        test_instance = BMSwactTestCase(bm_type, node, con_ssh)
        if not test_instance.bm_provisioned:
            LOG.info('Skip %s, bm is not provisioned' % node)
            continue
        if bm_type == BMProtocols.REDFISH and not test_instance.redfish_supported:
            LOG.info('Skip %s for redfish, unsupported protocol' % node)
            continue

        instances.append(test_instance)

    if len(instances) == 0:
        skip("no suitable node in the lab to test")

    con_ssh = ControllerClient.get_active_controller()
    active_controller = system_helper.get_active_controller_name(con_ssh=con_ssh)
    controllers = ['controller-0', 'controller-1']
    controllers.remove(active_controller)
    standby_controller = controllers[0]

    LOG.info('swact to %s' % standby_controller)
    exitcode, msg = host_helper.swact_host(fail_ok=True)
    if 0 != exitcode:
        skip('swact to %s failed %s, test case cannot perform' % (standby_controller, msg))

    yield instances


@mark.bmctests
def test_bmc_swact(bm_test_instances):
    """
    TC7: Verify sensor data is collected as per provision after controller swact.
    Description:
    ============
        Verify sensor data is collected as per provision (dynamic,IPMI,Redfish) after the controller swact.
    Pre-requisites:
    ==============
    Lab is installed with latest load. LAB is connected to BMC and provisioned
    with redfish or ipmitool or dynamic depends on lab capabilities.

    STEPS
    =====
    1. Verify there is no BMC connection failure alarm for any of the hosts.

    2. Verify sensor data in file hwmond_<hostname>_sensor_data  is collected as per provision in below path.
    System debug host-show controller-0 and verify provisioned protocol
    3. Verify sensor data are collected using below command
       System host-sensor-list <hostname>
    4.  Swact controller and verify swact controller was successful.
    5. Verify host is in available state system host-list ??? why? this is testing swact?
    6. Follow steps 1,2 and 3 to verify.

    ***********************************************************************
    END: Group of test cases to test BMC operations under certain bm_type
    ***********************************************************************
    """
    for instance in bm_test_instances:
        instance.verify_bm_config()
        LOG.info("%s %s" % (instance.node, instance.init_bm_type))
        instance.reconfig_bm(bm_type=instance.target_bm_type)
        instance.verify_bm_config()
