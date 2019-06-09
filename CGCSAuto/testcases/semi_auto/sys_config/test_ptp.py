from pytest import fixture, mark
from keywords import system_helper
from utils.tis_log import LOG


@fixture(scope='module')
def default_config(request):
    """
    Args:
        request:
    Test steps:
            1. Capture the default setting for ptp
            2. Restore NTP and PTP values at the end of the run
    Returns:

    """

    ptp_default = system_helper.get_ptp_values(fields=['enabled', 'mode', 'transport', 'mechanism'])
    LOG.info('Ptp values= {} {}'.format(ptp_default[0], ptp_default[1]))

    def restore_default_confg():
        LOG.info('Restoring Ptp values= {} {} {} {}'.format(ptp_default[0], ptp_default[1], ptp_default[2],
                                                            ptp_default[3]))
        if ptp_default[0] == 'False':
            system_helper.modify_ptp(enabled=False, mode=ptp_default[1], transport=ptp_default[2],
                                     mechanism=ptp_default[3], clear_alarm=True)
            system_helper.modify_ntp(enabled=True, clear_alarm=True)
        else:
            system_helper.modify_ntp(enabled=False, clear_alarm=True)
            system_helper.modify_ptp(enabled=False, mode=ptp_default[1], transport=ptp_default[2],
                                     mechanism=ptp_default[3], clear_alarm=True)
    request.addfinalizer(restore_default_confg)
    return ptp_default


def test_system_ptp_enable_negative():
    """
       This test is to veirfy the Negative senario by trying to enable both PTP and NTP together
       Test steps:  1. Change PTP enabled
                    2. Verify string for PTP failure
                    3. PTP is neabled success change NTP enabled
                    4. Verify sting for NTP enabled
    """

    ret_value, output = system_helper.modify_ptp(enabled=True, clear_alarm=True, wait_with_best_effort=True,
                                                 fail_ok=True)

    if ret_value != 0:
        find_string = output.find('PTP cannot be configured alongside with NTP')
        assert find_string == 0, 'Test Failed: Error message \"PTP cannot be configured alongside with NTP\"' \
                                 ' not found'
    if ret_value == 0:
        ret_value, output = system_helper.modify_ntp(enabled=True, clear_alarm=True, wait_with_best_effort=True,
                                                     fail_ok=True)
        if ret_value > 0:
            find_string = output.find('NTP cannot be configured alongside with PTP')
            assert find_string == 0, 'Test Failed: Error message \"NTP cannot be configured alongside ' \
                                     'with PTP\" not found'


@mark.parametrize(('mode', 'transport', 'mechanism'), [
    ('software', 'l2', 'p2p'),
    ('software', 'udp', 'p2p'),
   # ('hardware', 'l2', 'p2p'),
    #('hardware', 'l2', 'e2e'),
    #('hardware', 'l2', 'e2e'),
])
def test_ptp_parameter_modify(mode, transport, mechanism, default_config):
    """
         This test is to verify  PTP parameters.
         Note: There are some hardware dependency to support all the parameters.
    Args:
        mode:
        transport:
        mechanism:
        default_config:


         Test steps: 1. Check PTP enabled
                     2. Change parameter and clear alarm

    """

    LOG.tc_step("PTP Enabled check")
    ptp_enabled = system_helper.get_ptp_values(fields='enabled')
    if ptp_enabled[0] != 'True':
        system_helper.modify_ntp(enabled=False, clear_alarm=False)
        system_helper.modify_ptp(enabled=True, clear_alarm=False)
    LOG.tc_step("PTP Modify parameters")
    ret_value, output = system_helper.modify_ptp(mode=mode, transport=transport, mechanism=mechanism)
    LOG.info(format(output))


def test_ptp_and_ntp_disable():
    """
        This test is to verify disabling both NTP and PTP


        Test steps: 1. Disable NTP enabled
                    2.  Disable PTP and clear alarm.

    """
    system_helper.modify_ntp(enabled=False, clear_alarm=False)
    system_helper.modify_ptp(enabled=False, clear_alarm=True)
    

