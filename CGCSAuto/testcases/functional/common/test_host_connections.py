from pytest import mark

from utils.tis_log import LOG
from utils.ssh import ControllerClient

from keywords import system_helper, network_helper


@mark.sanity
def test_ping_hosts():
    con_ssh = ControllerClient.get_active_controller()

    ping_failed_list = []
    for hostname in system_helper.get_hostnames():
        LOG.tc_step("Send 100 pings to {} from Active Controller".format(hostname))
        ploss_rate, untran_p = network_helper._ping_server(hostname, con_ssh, num_pings=100, timeout=300, fail_ok=True)
        if ploss_rate > 0:
            if ploss_rate == 100:
                ping_failed_list.append("{}: Packet loss rate: {}/100\n".format(hostname, ploss_rate))
            else:
                ping_failed_list.append("{}: All packets dropped.\n".format(hostname))
        if untran_p > 0:
            ping_failed_list.append("{}: {}/100 pings are untransmitted within 300 seconds".format(hostname, untran_p))

    LOG.tc_step("Ensure all packets are received.")
    assert not ping_failed_list, "Dropped/Un-transmitted packets detected when ping hosts. " \
                                 "Details:\n{}".format(ping_failed_list)
