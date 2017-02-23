from keywords import vlm_helper

from testfixtures.vlm_fixtures import unreserve_hosts_session, unreserve_hosts_module, HostsReserved


def test_vlm_reserve():
    HostsReserved.add(hosts='controller-0', scope='session')
    vlm_helper.reserve_hosts('controller-0')


def test_vlm_reboot():
    HostsReserved.add(hosts='controller-0', scope='session')
    vlm_helper.reboot_hosts('controller-0')


def test_vlm_power_off_and_on():
    HostsReserved.add(hosts='controller-0', scope='session')
    vlm_helper.power_off_hosts('controller-0')
    vlm_helper.power_on_hosts('controller-0', reserve=False)