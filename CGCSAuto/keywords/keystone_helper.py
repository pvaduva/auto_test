from utils import cli
from utils import table_parser
from consts.auth import Primary


def get_tenant_ids(tenant_name=None, con_ssh=None):
    """
    Return a list of tenant id(s) with given tenant name.

    Args:
        tenant_name (str): openstack tenant name. e.g., 'admin', 'tenant1'. If None, the primary tenant will be used.
        con_ssh (SSHClient): If None, active controller client will be used, assuming set_active_controller was called.

    Returns (list): list of tenant id(s)

    """
    if tenant_name is None:
        tenant_name = Primary.get_primary()['tenant']
    table_ = table_parser.table(cli.openstack('project list', ssh_client=con_ssh))
    return table_parser.get_values(table_, 'ID', Name=tenant_name)


def get_user_ids(user_name=None, con_ssh=None):
    """
    Return a list of user id(s) with given user name.

    Args:
        user_name (str): openstack user name. If None, the current user for primary tenant will be used
        con_ssh (SSHClient):

    Returns (list): list of user id(s)

    """
    if user_name is None:
        user_name = Primary.get_primary()['user']
    table_ = table_parser.table(cli.openstack('user list', ssh_client=con_ssh))
    return table_parser.get_values(table_, 'ID', Name=user_name)