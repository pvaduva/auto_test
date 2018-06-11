from keywords import network_helper
from utils import table_parser
from utils import cli


def test_merge_lines():
    port_table = table_parser.table(cli.neutron('port-list'))
    # subnet_table = table_parser.table(cli.neutron('subnet-list'))

    fixed_ips = table_parser.get_values(port_table, 'fixed_ips', merge_lines=True)
    print(str(fixed_ips))
    for i in fixed_ips:
        assert isinstance(i, str)
