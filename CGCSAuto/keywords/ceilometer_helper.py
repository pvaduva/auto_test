import random
import time

from consts.auth import Tenant
from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from consts.timeout import VolumeTimeout
from keywords import glance_helper, keystone_helper




def get_alarms(name=None, strict=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Return a list of volume ids based on the given criteria

    Args:
        vols (list or str):
        name (str):
        name_strict (bool):
        vol_type (str):
        size (str):
        status:(str)
        attached_vm (str):
        bootable (str|bool): true or false
        auth_info (dict): could be Tenant.ADMIN,Tenant.TENANT_1,Tenant.TENANT_2
        con_ssh (str):

    Returns (list): a list of volume ids based on the given criteria
    """

    table_ = table_parser.table(cli.ceilometer('alarm-list', auth_info=auth_info, ssh_client=con_ssh))
    if name is None:
        return table_

    return table_parser.get_values(table_, 'Alarm ID', Name='STACK1', strict=strict)