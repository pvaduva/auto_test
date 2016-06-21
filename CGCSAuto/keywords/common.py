import os
import pexpect
from consts.auth import Tenant
from consts.proj_vars import ProjVar
from utils.tis_log import LOG
from utils.ssh import ControllerClient


def scp_to_active_controller(source_path, dest_path='',
                   dest_user='wrsroot', dest_password='li69nux',
                   timeout=60, is_dir=False):

    active_cont_ip = ControllerClient.get_active_controller().host

    return scp_from_local(source_path, active_cont_ip, dest_path=dest_path,
                          dest_user=dest_user, dest_password=dest_password,
                          timeout=timeout, is_dir=is_dir)


def scp_from_active_controller(source_path, dest_path='',
                               src_user='wrsroot', src_password='li69nux',
                               timeout=60, is_dir=False):

    active_cont_ip = ControllerClient.get_active_controller().host

    return scp_to_local(source_path, active_cont_ip, dest_path=dest_path,
                        src_user=src_user, src_password=src_password,
                        timeout=timeout, is_dir=is_dir)


def scp_from_local(source_path, dest_ip, dest_path='/home/wrsroot',
                   dest_user='wrsroot', dest_password='li69nux',
                   timeout=60, is_dir=False):
    """
    Scp file(s) from localhost (i.e., from where the automated tests are executed).

    Args:
        source_path (str): source file/directory path
        dest_ip (str): ip of the destination host
        dest_user (str): username of destination host.
        dest_password (str): password of destination host
        dest_path (str): destination directory path to copy the file(s) to
        timeout (int): max time to wait for scp finish in seconds
        is_dir (bool): whether to copy a single file or a directory

    """
    dir_option = '-r ' if is_dir else ''

    cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {}{} {}@{}:{}'.format(
            dir_option, source_path, dest_user, dest_ip, dest_path)

    __scp_base(cmd, remote_password=dest_password, timeout=timeout)


def scp_to_local(source_path, source_ip, dest_path='/home/wrsroot',
                 source_user='wrsroot', source_password='li69nux',
                 timeout=60, is_dir=False):
    """
    Scp file(s) to localhost (i.e., to where the automated tests are executed).

    Args:
        source_path (str): source file/directory path
        source_ip (str): ip of the source host.
        source_user (str): username of source host.
        source_password (str): password of source host
        dest_path (str): destination directory path to copy the file(s) to
        timeout (int): max time to wait for scp finish in seconds
        is_dir (bool): whether to copy a single file or a directory

    """
    dir_option = '-r ' if is_dir else ''
    cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {}{}@{}:{} {}'.format(
            dir_option, source_user, source_ip, source_path, dest_path)

    __scp_base(cmd, remote_password=source_password, timeout=timeout)


def __scp_base(cmd, remote_password, logdir=None, timeout=60):
    LOG.debug('scp cmd: {}'.format(cmd))

    logdir = logdir or ProjVar.get_var('LOG_DIR')
    logfile = os.path.join(logdir, 'scp_files.log')


    with open(logfile, mode='a') as f:
        local_child = pexpect.spawn(command=cmd, encoding='utf-8', logfile=f)
        index = local_child.expect([pexpect.EOF, 'assword:', 'yes/no'], timeout=timeout)

        if index == 2:
            local_child.sendline('yes')
            index = local_child.expect(pexpect.EOF, 'assword:')

        if index == 1:
            local_child.sendline(remote_password)
            local_child.expect(pexpect.EOF)


def get_tenant_name(auth_info=None):
    """
    Get name of given tenant. If None is given, primary tenant name will be returned.

    Args:
        auth_info (dict|None): Tenant dict

    Returns:
        str: name of the tenant

    """
    if auth_info is None:
        auth_info = Tenant.get_primary()
    return auth_info['tenant']


class Count:
    __vm_count = 0
    __flavor_count = 0
    __volume_count = 0
    __image_count = 0
    __server_group = 0
    __router = 0
    __subnet = 0
    __other = 0

    @classmethod
    def get_vm_count(cls):
        cls.__vm_count += 1
        return cls.__vm_count

    @classmethod
    def get_flavor_count(cls):
        cls.__flavor_count += 1
        return cls.__flavor_count

    @classmethod
    def get_image_count(cls):
        cls.__image_count += 1
        return cls.__image_count

    @classmethod
    def get_sever_group_count(cls):
        cls.__server_group += 1
        return cls.__server_group

    @classmethod
    def get_router_count(cls):
        cls.__router += 1
        return cls.__router

    @classmethod
    def get_subnet_count(cls):
        cls.__subnet += 1
        return cls.__subnet

    @classmethod
    def get_other_count(cls):
        cls.__other += 1
        return cls.__other


class NameCount:
    __names_count = {
        'vm': 0,
        'flavor': 0,
        'volume': 0,
        'image': 0,
        'server_group': 0,
        'subnet': 0,
        'heat_stack': 0,
        'other': 0,
    }

    @classmethod
    def get_number(cls, resource_type='other'):
        cls.__names_count[resource_type] += 1
        return cls.__names_count[resource_type]

    @classmethod
    def get_valid_types(cls):
        return list(cls.__names_count.keys())


def get_unique_name(name_str, existing_names=None, resource_type='other'):
    """
    Get a unique name string by appending a number to given name_str

    Args:
        name_str (str): partial name string
        existing_names (list): names to avoid
        resource_type (str): type of resource. valid values: 'vm'

    Returns:

    """
    valid_types = NameCount.get_valid_types()
    if resource_type not in valid_types:
        raise ValueError("Invalid resource_type provided. Valid types: {}".format(valid_types))

    unique_name = "{}-{}".format(name_str, NameCount.get_number(resource_type=resource_type))

    if existing_names:
        for i in range(50):
            if unique_name not in existing_names:
                break
            unique_name = "{}-{}".format(name_str, NameCount.get_number(resource_type=resource_type))
        else:
            raise LookupError("Cannot find unique name.")

    return unique_name
