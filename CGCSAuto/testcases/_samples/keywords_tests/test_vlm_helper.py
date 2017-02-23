from keywords import vlm_helper

from testfixtures.vlm_fixtures import unreserve_hosts_session, unreserve_hosts_module, HostsReserved


def test_vlm_reserve_unreserve():
    vlm_helper.reserve_hosts('controller-0')
    HostsReserved.add(hosts='controller-0', scope='session')
