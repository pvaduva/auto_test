from utils.tis_log import LOG
from utils import cli, exceptions, table_parser
from consts.auth import Tenant


def get_subclouds(rtn_val='name', name=None, avail=None, sync=None, mgmt=None,
                  auth_info=Tenant.get('admin', 'SystemController'), con_ssh=None):
    """

    Args:
        rtn_val:
        name:
        avail:
        sync:
        auth_info:
        con_ssh:

    Returns:

    """
    # auth_info = Tenant.get('admin', 'SystemController')
    LOG.info("Auth_info: {}".format(auth_info))
    table_ = table_parser.table(cli.dcmanager('subcloud list', auth_info=auth_info, ssh_client=con_ssh))
    arg_dict = {'name': name, 'availability': avail, 'sync': sync, 'management': mgmt}
    kwargs = {key: val for key, val in arg_dict.items() if val is not None}
    subclouds = table_parser.get_values(table_, target_header=rtn_val, **kwargs)
    return subclouds
