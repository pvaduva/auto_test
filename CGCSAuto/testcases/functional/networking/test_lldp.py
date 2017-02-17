from utils import table_parser, cli
from utils.tis_log import LOG


def test_lldp_neighbor_remote_port():
    """
    Tests if LLDP Neighbor remote_port exists on all hosts

    Test Steps:
        - Checks LLDP Neighbor remote_port to ensure it exists
    """

    remote_port_missing = "false"

    LOG.tc_step("Parsing host-list for hostnames")
    hosts_tab = table_parser.table(cli.system('host-list'))
    all_hosts = table_parser.get_column(hosts_tab, 'hostname')

    for host_name in all_hosts:

        LOG.tc_step("Parsing host-lldp-neighbor-list for remote_ports on the " + host_name + " host")
        host = table_parser.table(cli.system('host-lldp-neighbor-list ' + host_name))
        host_remote_ports = table_parser.get_column(host, 'remote_port')

        for remote_port in host_remote_ports:

            LOG.tc_step("Checking LLDP remote_port to ensure it exists")
            if remote_port is None:
                LOG.tc_step("Port missing")
                remote_port_missing = "true"
            elif remote_port is "":
                LOG.tc_step("Port missing")
                remote_port_missing = "true"

    assert remote_port_missing is "false"