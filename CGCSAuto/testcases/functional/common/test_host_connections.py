from pytest import mark

from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient

from consts.cgcs import HostAvailabilityState
from keywords import system_helper, network_helper, host_helper


@mark.p3
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


@mark.sanity
@mark.cpe_sanity
@mark.sx_sanity
def test_ssh_to_hosts():
    hosts_to_ssh = host_helper.get_hosts(availability=[HostAvailabilityState.AVAILABLE, HostAvailabilityState.ONLINE])
    failed_list = []
    for hostname in hosts_to_ssh:
        LOG.tc_step("Attempt SSH to {}".format(hostname))
        try:
            with host_helper.ssh_to_host(hostname):
                pass
        except Exception as e:
            failed_list.append("\n{}: {}".format(hostname, e.__str__()))

    assert not failed_list, "SSH to host(s) failed: {}".format(failed_list)