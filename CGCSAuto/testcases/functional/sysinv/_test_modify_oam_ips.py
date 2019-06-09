###
# Change OAM interface using CLI
###

from pytest import fixture, mark, skip

from consts.cgcs import EventLogID, SpareIP
from keywords import system_helper
from utils.tis_log import LOG


@mark.parametrize('oam_ips', [
    'oam_c0',
    'oam_c1',
    'oam_floating',
    'oam_c0_c1',
    'oam_c0_floating',
    'oam_c1_floating',
    'oam_c0_c1_floating'
    ])
def _test_modify_oam_ips(restore_oam, oam_ips):
    """
    Change OAM IPs using CLI

    Verify that oam IPs on both standby and active controller can be modified by cli

    Test Steps:
        - verify there is no 250.001 alarm
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
        - Revert oam ips if modified

    """

    # make sure there is no 250.001 alarm in alarm-list
    if not system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, fail_ok=False):
        skip("250.001 Alarms did not clear at the beginning of the test")

    LOG.tc_step("Modify OAM IPs to new IPs")
    new_oam_ip0 = SpareIP.NEW_OAM_IP0
    new_oam_ip1 = SpareIP.NEW_OAM_IP1
    new_oam_ip2 = SpareIP.NEW_OAM_IP2

    kwargs = {}
    if 'c0' in oam_ips:
        kwargs['oam_c0_ip'] = new_oam_ip0
    if 'c1' in oam_ips:
        kwargs['oam_c1_ip'] = new_oam_ip1
    if 'floating' in oam_ips:
        kwargs['oam_floating_ip'] = new_oam_ip2

    system_helper.modify_oam_ips(**kwargs)


@fixture(scope='module')
def restore_oam(request):
    """
    Fixture to restore lab oam IPs to original IPs after test
    """
    if system_helper.is_aio_simplex():
        fields = 'oam_ip'
    else:
        fields = ('oam_c0_ip', 'oam_c1_ip', 'oam_floating_ip')
    original_oam_info = system_helper.get_oam_values(fields=fields)

    def restore_oam_ip_settings():
        post_oam_info = system_helper.get_oam_values(fields=fields)
        kwargs = {k: v for k, v in original_oam_info.items() if post_oam_info[k] != v}
        if kwargs:
            LOG.fixture_step("Revert oam ip(s) to: {}".format(kwargs))
            system_helper.modify_oam_ips(**kwargs)
    request.addfinalizer(restore_oam_ip_settings)
