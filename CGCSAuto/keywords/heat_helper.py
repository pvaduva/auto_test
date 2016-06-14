import random
import re

from keywords import common, nova_helper,ceilometer_helper
from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import HOME
from consts.cgcs import HEAT_PATH
from utils.ssh import NATBoxClient, VMSSHClient, ControllerClient, SSHFromSSH
import os
import yaml
from consts.heat import Heat


def _get_stack_user_id(con_ssh=None, auth_info=None):
    """ Function for getting stack user ID"""
    if auth_info is None:
        auth_info = Primary.get_primary()

    tenant = auth_info['tenant']
    table_ = table_parser.table(cli.openstack('user list',ssh_client=con_ssh, auth_info=auth_info))
    user_id = table_parser.get_column(table_, 'ID', Name=tenant)
    return user_id

def _get_tenant_id(con_ssh=None, auth_info=None):
    """ Function for getting stack user ID"""
    if auth_info is None:
        auth_info = Primary.get_primary()

    tenant = auth_info['tenant']
    table_ = table_parser.table(cli.openstack('project list',ssh_client=con_ssh, auth_info=auth_info))
    tenant_id = table_parser.get_column(table_, 'ID', Name=tenant)
    return tenant_id

def get_stack_list(con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.heat('stack-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_column(table_, 'stack_name')

def get_stack_status(stack_name=None, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.heat('stack-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_,'stack_status', stack_name=stack_name)

def delete_stack(stack_name, con_ssh=None, auth_info=None):
    LOG.info("Deleting Heat Stack %s", stack_name)
    exitcode, output = cli.heat('stack-delete', stack_name, ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=True, rtn_list=True)
    if exitcode == 1:
        LOG.warning("Delete heat stack request rejected.")
        return [1, output]

    return 0


