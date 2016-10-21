from pytest import mark
from utils.ssh import ControllerClient

from keywords import system_helper, network_helper


@mark.sanity
def test_ping_hosts():
    con_ssh = ControllerClient.get_active_controller()

    ping_failed_list = []
    for hostname in system_helper.get_hostnames():
        ploss_rate = network_helper._ping_server(hostname, con_ssh, num_pings=100, timeout=5, fail_ok=True)
        if ploss_rate > 0:
            if ploss_rate == 100:
                ping_failed_list.append("Packet loss rate for 100 pings to {}: {}\n".format(hostname, ploss_rate))
            else:
                ping_failed_list.append("All packets lost when pinging {}\n".format(hostname))

    assert not ping_failed_list, "Packet drop detected when ping hosts. Details:\n{}".format(ping_failed_list)
