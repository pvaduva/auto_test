from utils.tis_log import LOG
from keywords import host_helper, system_helper


def test_ntp_alarm_in_sync_with_ntpq_stats():
    for host in system_helper.get_controllers():
        LOG.tc_step("Check ntp alarm and 'ntpq -pn'")
        host_helper.wait_for_ntp_sync(host=host, fail_ok=False)
