from utils import cli
from utils import table_parser


def get_tenant_id(tenant_name, ssh_client=None):
    """

    Args:
        tenant_name: user name. e.g., 'admin', 'tenant1'
        ssh_client: object of SSHClient. If not set, active controller client will be used,
            assuming set_active_controller was called.

    Returns:

    """
    table_ = table_parser.table(cli.openstack('project list', ssh_client=ssh_client))
    return table_parser.get_values(table_, 'ID', Name=tenant_name)
