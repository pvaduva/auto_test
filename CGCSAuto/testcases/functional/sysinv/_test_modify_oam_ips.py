###
# Change OAM interface using CLI
###


import time

from pytest import fixture, mark

from consts.cgcs import EventLogID, HostAvailState, HostOperState, SpareIP
from keywords import host_helper, system_helper, keystone_helper
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG

original_ip0 = "0.0.0.0"
original_ip1 = "0.0.0.0"
original_ip2 = "0.0.0.0"

host_ip_changed = False


@mark.parametrize('oam_ips', [
    'oam_c0',
    'oam_c1',
    'oam_floating',
    'oam_c0_c1',
    'oam_c0_floating',
    'oam_c1_floating',
    'oam_c0_c1_floating'
    ])
def _test_modify_oam_ips(oam_ips):
    """
    Change OAM IPs using CLI

    Verify that oam IPs on both standby and active controller can be modified by cli

    Args:
        - it has to be at least one arg
        - max 3 args: oam_c0, oam_c1, oam_floating

    Setup:
        - Nothing

    Test Steps:
        - verify there is no 250.001 alarm
        - get original oam IPs
        - modify oam IPs
        - verify oam IPs have been changed
        - verify Alarms 250.001 Configuration out-of-date raised for controllers
        - lock/unlock standby controllers
        - verify there is standby controller 250.001 alarm in clear
        - swact controller
        - lock/unlock another controllers
        - verify there is no 250.001 alarms
        - verify all controllers are in good status

    Teardown:
        - verify there is no 250.001 alarm
        - get current oam IPs
        - modify oam IPs to original IPs
        - verify oam IPs have been changed
        - verify Alarms 250.001 Configuration out-of-date raised for controllers
        - lock/unlock standby controllers
        - verify there is standby controller 250.001 alarm in clear
        - swact controller
        - lock/unlock another controllers
        - verify there is no 250.001 alarms
        - verify all controllers are in good status

    """

    global original_ip0
    global original_ip1
    global original_ip2
    global host_ip_changed

    # make sure there is no 250.001 alarm in alarm-list
    if not system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, fail_ok=False):
        err_msg = "250.001 Alarms did not clear at the beginning of the test. "
        return 1, err_msg

    LOG.info("There is no 250.001 alarm in alarm list at the beginning of the test.")

    LOG.tc_step("Get original OAM IPs")
    original_oam_ips = system_helper.get_oam_ips()
    original_ip0 = original_oam_ips['oam_c0_ip']
    original_ip1 = original_oam_ips['oam_c1_ip']
    original_ip2 = original_oam_ips['oam_floating_ip']
    LOG.info("Original OAM IPs: {}".format(original_oam_ips))
    LOG.info("Original oam_c0_ip: {}".format(original_ip0))
    LOG.info("Original oam_c1_ip {}".format(original_ip1))
    LOG.info("Original oam_floating_ip: {}".format(original_ip2))

    LOG.tc_step("Modify OAM IPs to new IPs")
    new_oam_ip0 = SpareIP.NEW_OAM_IP0
    new_oam_ip1 = SpareIP.NEW_OAM_IP1
    new_oam_ip2 = SpareIP.NEW_OAM_IP2
    arg_str = ""
    LOG.info("args passed in:{}".format(oam_ips))
    if not oam_ips:
        assert "There is no argument passed in this test. It should be something like, oam_c0_c1_floating."
    if oam_ips == 'oam_c0':
        arg_str = " oam_c0_ip=" + new_oam_ip0
        LOG.info("oam_c0_ip will be changed to {}".format(new_oam_ip0))
    elif oam_ips == 'oam_c1':
        arg_str = " oam_c1_ip=" + new_oam_ip1
        LOG.info("oam_c1_ip will be changed to {}".format(new_oam_ip1))
    elif oam_ips == 'oam_floating':
        arg_str = " oam_floating_ip=" + new_oam_ip2
        LOG.info("oam_floating_ip will be changed to {}".format(new_oam_ip2))
        host_ip_changed = True
    elif oam_ips == 'oam_c0_c1':
        arg_str = " oam_c0_ip=" + new_oam_ip0 + " oam_c1_ip=" + new_oam_ip1
        LOG.info("oam_c0_ip will be changed to {}".format(new_oam_ip0))
        LOG.info("oam_c1_ip will be changed to {}".format(new_oam_ip1))
    elif oam_ips == 'oam_c0_floating':
        arg_str = " oam_c0_ip=" + new_oam_ip0 + " oam_floating_ip=" + new_oam_ip2
        LOG.info("oam_c0_ip will be changed to {}".format(new_oam_ip0))
        LOG.info("oam_floating_ip will be changed to {}".format(new_oam_ip2))
        host_ip_changed = True
    elif oam_ips == 'oam_c1_floating':
        arg_str = " oam_c1_ip=" + new_oam_ip1 + " oam_floating_ip=" + new_oam_ip2
        LOG.info("oam_c1_ip will be changed to {}".format(new_oam_ip1))
        LOG.info("oam_floating_ip will be changed to {}".format(new_oam_ip2))
        host_ip_changed = True
    elif oam_ips == 'oam_c0_c1_floating':
        arg_str = " oam_c0_ip=" + new_oam_ip0 + " oam_c1_ip=" + new_oam_ip1 + " oam_floating_ip=" + new_oam_ip2
        LOG.info("oam_c0_ip will be changed to {}".format(new_oam_ip0))
        LOG.info("oam_c1_ip will be changed to {}".format(new_oam_ip1))
        LOG.info("oam_floating_ip will be changed to {}".format(new_oam_ip2))
        host_ip_changed = True
    else:
        LOG.info("The argument: {} is not expected for this function".format(oam_ips))

    LOG.info("arg string:{}".format(arg_str))
    LOG.info("host_ip_change: {}".format(host_ip_changed))

    if not arg_str:
        assert "The argument: {} is not expected for this function".format(oam_ips)

    code, output = system_helper.modify_oam_ips(arg_str, fail_ok=True)
    if code != 0:
        assert False, output

    LOG.tc_step("verify oam IPs have been changed")
    new_oam_ips = system_helper.get_oam_ips()
    LOG.info("Original OAM IPs: {}".format(original_oam_ips))
    LOG.info('New OAM IPs: {}'.format(new_oam_ips))

    if "c0" in oam_ips and original_oam_ips["oam_c0_ip"] == new_oam_ips["oam_c0_ip"]:
        assert False, "oam_c0_ip was not changed."
    if "c1" in oam_ips and original_oam_ips["oam_c1_ip"] == new_oam_ips["oam_c1_ip"]:
        assert False, "oam_c1_ip was not changed."
    if "floating" in oam_ips and original_oam_ips["oam_floating_ip"] == new_oam_ips["oam_floating_ip"]:
        assert False, "oam_floating_ip was not changed."

    LOG.info('The selected oam IPs have been changed.')

    LOG.tc_step("verify Alarms 250.001 Configuration out-of-date raised for controllers")
    active, standby = system_helper.get_active_standby_controllers()
    if not system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(standby),
                                        timeout=10, fail_ok=False):
        assert "250.001 alarms NOT raised "

    if not system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(active),
                                        timeout=10, fail_ok=False):
        assert "250.001 alarms NOT raised "

    LOG.tc_step("lock standby controller: {}".format(standby))
    host_helper.lock_host(standby)
    time.sleep(10)
    LOG.tc_step("unlock the standby controller: {}".format(standby))
    host_helper.unlock_host(standby)

    LOG.tc_step("check 250.001 about {} is cleared".format(standby))
    if not system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                             entity_id="host={}".format(standby)):
        assert "{} 250.001 alarms is NOT clear.".format(standby)

    if host_ip_changed:
        LOG.tc_step("Change host IPs Before swact")
        LOG.info('get original host IP...')
        con_ssh = ControllerClient.get_active_controller()
        ori_host_ip = con_ssh.get_host()
        LOG.info('Original SSH host IP: {}'.format(ori_host_ip))
        LOG.info('update SSH host IP')
        con_ssh.update_host(new_oam_ip2)
        current_host_ip = con_ssh.get_host()
        LOG.info('New SSH host IP: {}'.format(current_host_ip))

    # Before swacting ensure the controller is in available state
    if not host_helper.wait_for_host_values(standby, timeout=360, fail_ok=True,
                                            operational=HostOperState.ENABLED,
                                            availability=HostAvailState.AVAILABLE):
        err_msg = " Swacting to standby controller is not possible because controller is not in available state " \
                  "within  360 sec"
        assert False, err_msg

    LOG.tc_step("Swact controllers")
    exit_code, output = host_helper.swact_host(active, fail_ok=True, swact_complete_timeout=1800)
    assert 0 == exit_code, 'Failed to swact host: from {}'.format(active)

    if not host_helper.wait_for_host_values(standby, timeout=360, fail_ok=True,
                                            operational=HostOperState.ENABLED,
                                            availability=HostAvailState.AVAILABLE):
        err_msg = " After Swacting, {} is not in available state within  360 sec".format(standby)
        assert False, err_msg

    if not host_helper.wait_for_host_values(active, timeout=360, fail_ok=True,
                                            operational=HostOperState.ENABLED,
                                            availability=HostAvailState.AVAILABLE):
        err_msg = " After Swacting, {} is not in available state within  360 sec".format(active)
        assert False, err_msg

    LOG.tc_step("lock the controller")
    host_helper.lock_host(active)
    time.sleep(10)
    LOG.tc_step("unlock the controller")
    host_helper.unlock_host(active)

    LOG.tc_step("verify 250.001 alarms cleared")
    # make sure there is no 250.001
    if not system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, fail_ok=True):
        err_msg = "250.001 Alarms did not clear at the end of the test. "
        assert False, err_msg

    LOG.info('There is no 250.001 alarm in alarm list.')

    LOG.tc_step("Make sure controllers are in good status at the end of testing")
    if not host_helper.wait_for_host_values(standby, timeout=360, fail_ok=True,
                                            operational=HostOperState.ENABLED,
                                            availability=HostAvailState.AVAILABLE):
        err_msg = "{} is not in available state within  360 sec".format(standby)
        assert False, err_msg

    if not host_helper.wait_for_host_values(active, timeout=360, fail_ok=True,
                                            operational=HostOperState.ENABLED,
                                            availability=HostAvailState.AVAILABLE):
        err_msg = "{} is not in available state within  360 sec".format(active)
        assert False, err_msg

    LOG.info('Test is done here.')

    return 0


@fixture(scope='module', autouse=True)
def restore_oam_original_ip(request):
    """
    Fixture to restore lab oam IPs to original IPs after test

    Args:
        request: request passed in by py.test system

    """

    def restore_oam_ip_settings():

        LOG.fixture_step("Get lab https info")
        if keystone_helper.is_https_lab():
            LOG.info('This is a https lab')
        else:
            LOG.info('This is NOT a https lab')

        LOG.fixture_step("Get current OAM IPs")
        new_oam_ips = system_helper.get_oam_ips()
        LOG.info('current OAM IPs: {}'.format(new_oam_ips))
        con_ssh = ControllerClient.get_active_controller()
        current_host_ip = con_ssh.get_host()
        LOG.info('Current SSH host IP: {}'.format(current_host_ip))

        LOG.info('Original oam_c0_ip: {}'.format(original_ip0))
        LOG.info('Original oam_c1_ip {} '.format(original_ip1))
        LOG.info('Original oam_floating_ip: {}'.format(original_ip2))

        LOG.fixture_step("Modify OAM IPs to original IPs")
        arg_str = " oam_c0_ip={} oam_c1_ip={} oam_floating_ip={}".format(original_ip0, original_ip1, original_ip2)
        code, output = system_helper.modify_oam_ips(arg_str, fail_ok=True)
        if code != 0:
            assert False, output

        LOG.fixture_step("verify Alarms 250.001 Configuration out-of-date raised for controllers")
        active, standby = system_helper.get_active_standby_controllers()
        if not system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(standby),
                                            timeout=10, fail_ok=False):
            assert "250.001 alarms NOT raised "

        if not system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(active),
                                            timeout=10, fail_ok=False):
            assert "250.001 alarms NOT raised "

        LOG.fixture_step("lock standby controller: {}".format(standby))
        host_helper.lock_host(standby)
        time.sleep(10)
        LOG.fixture_step("unlock the standby controller: {}".format(standby))
        host_helper.unlock_host(standby)

        LOG.fixture_step("check 250.001 for {} is cleared".format(standby))
        if not system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                                 entity_id="host={}".format(standby)):
            assert "{} 250.001 alarms is NOT cleared.".format(standby)

        if host_ip_changed:
            LOG.fixture_step("Change host IP to original before swact")
            LOG.info('get current host IP...')
            con_ssh = ControllerClient.get_active_controller()
            current_host_ip = con_ssh.get_host()
            LOG.info('Current SSH host IP: {}'.format(current_host_ip))
            LOG.info('update SSH to current host IP')
            con_ssh.update_host(original_ip2)
            current_host_ip = con_ssh.get_host()
            LOG.info('New SSH host IP: {}'.format(current_host_ip))

        # Before swacting ensure the controller is in available state
        if not host_helper.wait_for_host_values(standby, timeout=360, fail_ok=True,
                                                operational=HostOperState.ENABLED,
                                                availability=HostAvailState.AVAILABLE):
            err_msg = " Swacting to standby controller is not possible because controller is not in available state " \
                      "within  360 sec"
            assert False, err_msg

        LOG.fixture_step("Swact controllers")
        exit_code, output = host_helper.swact_host(active, fail_ok=True, swact_complete_timeout=1800)
        assert 0 == exit_code, 'Failed to swact host: from {}'.format(active)

        LOG.fixture_step("lock the controller")
        host_helper.lock_host(active)
        time.sleep(10)
        LOG.fixture_step("unlock the controller")
        host_helper.unlock_host(active)

        LOG.fixture_step("verify 250.001 alarms cleared")
        # make sure there is no 250.001
        if not system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, fail_ok=True):
            err_msg = "250.001 Alarms did not clear at the end of the test. "
            assert False, err_msg
        LOG.info('There is no 250.001 alarm in alarm list.')

        LOG.fixture_step("Make sure controllers are in good status before test finish")
        if not host_helper.wait_for_host_values(standby, timeout=360, fail_ok=True,
                                                operational=HostOperState.ENABLED,
                                                availability=HostAvailState.AVAILABLE):
            err_msg = "{} is not in available state within  360 sec".format(standby)
            assert False, err_msg

        if not host_helper.wait_for_host_values(active, timeout=360, fail_ok=True,
                                                operational=HostOperState.ENABLED,
                                                availability=HostAvailState.AVAILABLE):
            err_msg = "{} is not in available state within  360 sec".format(active)
            assert False, err_msg

    request.addfinalizer(restore_oam_ip_settings)
