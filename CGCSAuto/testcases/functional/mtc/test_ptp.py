from pytest import mark, fixture
from keywords import system_helper
from utils.tis_log import LOG


@fixture(scope='module')
def disable_ntp(request):
    ntp_enabled = system_helper.get_tp(value_show='ntp')
    LOG.info('Check NTP is not  enabled and PTP is enabled')
    if ntp_enabled["enabled"] == 'True':
       ret_code, msg = system_helper.tp_enabled(enabled='False')
       LOG.info(msg)
    if system_helper.get_tp(value_show='ptp')["enabled"] == 'False':
        system_helper.tp_enabled(tp_str='ptp', enabled='True', fail_ok=False)

    def enable_ntp():
        if ntp_enabled == True:
           ret_code, msg = system_helper.tp_enabled(enabled=True)
           LOG.info(msg)

    request.addfinalizer(enable_ntp)
    return ntp_enabled


@mark.parametrize('mode,transport, mechanism', [
    ('hardware', 'udp', 'e2e')])
#, ('software', 'udp', 'e2e')
def test_ptp(disable_ntp, mode, transport, mechanism):
    """
     Test Setups:
                  If the lab configured with NTP . Disabled ntp and setup ptp

    Args:
        disable_ntp
        mode:
        transport:
        mechanism:

    Returns:
            Put back NTP parameters
    """

    LOG.tc_step('Configure Ptp with values  mode=' + mode + ' Transport=' + transport + ' Mechanism=' + mechanism)
    system_helper.ptp_modify(mode=mode, transport=transport, mechanism=mechanism)


