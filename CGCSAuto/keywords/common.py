####################################################################################
# DO NOT import anything from helper modules to this module, such as nova_helper   #
####################################################################################

import os
import pexpect
import time
from datetime import datetime, timedelta

from consts.cgcs import Prompt
from consts.auth import Tenant, SvcCgcsAuto, HostLinuxCreds
from consts.proj_vars import ProjVar
from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.filepaths import WRSROOT_HOME


def scp_from_test_server_to_active_controller(source_path, dest_dir, dest_name=None, timeout=120,
                                              is_dir=False, con_ssh=None):
    """
    SCP file or files under a directory from test server to TiS server

    Args:
        source_path (str): test server file path or directory path
        dest_dir (str): destination directory. should end with '/'
        dest_name (str): destination file name if not dir
        timeout (int):
        is_dir (bool):
        con_ssh:

    Returns (str|None): destination file/dir path if scp successful else None

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    dir_option = '-r ' if is_dir else ''
    source_server = SvcCgcsAuto.SERVER
    source_user = SvcCgcsAuto.USER
    source_password = SvcCgcsAuto.PASSWORD

    if not is_dir and dest_name is None:
        dest_name = source_path.split(sep='/')[-1]

    dest_path = dest_dir if not dest_name else dest_dir + dest_name

    scp_cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {}{}@{}:{} {}'.format(
            dir_option, source_user, source_server, source_path, dest_path)

    if con_ssh.file_exists(file_path=dest_path):
        LOG.info('dest path {} already exists. Return existing path'.format(dest_path))
        return dest_path

    LOG.debug('Create destination directory on tis server if not already exists')
    cmd = 'mkdir -p {}'.format(dest_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    LOG.info("scp file(s) from test server to tis server")
    con_ssh.send(scp_cmd)
    index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=timeout)
    if index == 2:
        con_ssh.send('yes')
        index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT], timeout=timeout)
    if index == 1:
        con_ssh.send(source_password)
        index = con_ssh.expect()
    if index != 0:
        LOG.error("Failed to scp files")

    if not con_ssh.file_exists(file_path=dest_path):
        LOG.error("File path {} does not exist after scp".format(dest_path))
        return None
    else:
        return dest_path


def scp_from_active_controller_to_test_server(source_path, dest_dir, dest_name=None, timeout=180, is_dir=False,
                                              multi_files=False, con_ssh=None):

    """
    SCP file or files under a directory from test server to TiS server

    Args:
        source_path (str): test server file path or directory path
        dest_dir (str): destination directory. should end with '/'
        dest_name (str): destination file name if not dir
        timeout (int):
        is_dir (bool):
        con_ssh:

    Returns (str|None): destination file/dir path if scp successful else None

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    dir_option = '-r ' if is_dir else ''
    dest_server = SvcCgcsAuto.SERVER
    dest_user = SvcCgcsAuto.USER
    dest_password = SvcCgcsAuto.PASSWORD

    dest_path = dest_dir if not dest_name else dest_dir + dest_name

    scp_cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {}{} {}@{}:{}'.format(
        dir_option, source_path, dest_user, dest_server, dest_path)

    LOG.info("scp file(s) from tis server to test server")
    con_ssh.send(scp_cmd)
    index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=timeout)
    if index == 2:
        con_ssh.send('yes')
        index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT], timeout=timeout)
    if index == 1:
        con_ssh.send(dest_password)
        index = con_ssh.expect(timeout=timeout)

    assert index == 0, "Failed to scp files"

    exit_code = con_ssh.get_exit_code()
    assert 0 == exit_code, "scp not fully succeeded"

    return dest_path


def scp_to_active_controller(source_path, dest_path='',
                             dest_user=HostLinuxCreds.get_user(), dest_password=HostLinuxCreds.get_password(),
                             timeout=60, is_dir=False):

    active_cont_ip = ControllerClient.get_active_controller().host

    return scp_from_local(source_path, active_cont_ip, dest_path=dest_path,
                          dest_user=dest_user, dest_password=dest_password,
                          timeout=timeout, is_dir=is_dir)


def scp_from_active_controller(source_path, dest_path='',
                               src_user=HostLinuxCreds.get_user(), src_password=HostLinuxCreds.get_password(),
                               timeout=60, is_dir=False):

    active_cont_ip = ControllerClient.get_active_controller().host

    return scp_to_local(source_path, active_cont_ip, dest_path=dest_path,
                        source_user=src_user, source_password=src_password,
                        timeout=timeout, is_dir=is_dir)


def scp_from_local(source_path, dest_ip, dest_path=WRSROOT_HOME,
                   dest_user=HostLinuxCreds.get_user(), dest_password=HostLinuxCreds.get_password(),
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

    _scp_base(cmd, remote_password=dest_password, timeout=timeout)


def scp_to_local(dest_path, source_ip, source_path,
                 source_user=HostLinuxCreds.get_user(), source_password=HostLinuxCreds.get_password(),
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

    _scp_base(cmd, remote_password=source_password, timeout=timeout)


def _scp_base(cmd, remote_password, logdir=None, timeout=60):
    LOG.debug('scp cmd: {}'.format(cmd))

    logdir = logdir or ProjVar.get_var('LOG_DIR')
    logfile = os.path.join(logdir, 'scp_files.log')

    with open(logfile, mode='a') as f:
        local_child = pexpect.spawn(command=cmd, encoding='utf-8', logfile=f)
        index = local_child.expect([pexpect.EOF, 'assword:', 'yes/no'], timeout=timeout)

        if index == 2:
            local_child.sendline('yes')
            index = local_child.expect([pexpect.EOF, 'assword:'], timeout=timeout)

        if index == 1:
            local_child.sendline(remote_password)
            local_child.expect(pexpect.EOF, timeout=timeout)


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
    def get_volume_count(cls):
        cls.__volume_count += 1
        return cls.__volume_count

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
        'qos': 0,
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

    if existing_names:
        if resource_type in ['image', 'volume', 'flavor']:
            unique_name = name_str
        else:
            unique_name = "{}-{}".format(name_str, NameCount.get_number(resource_type=resource_type))

        for i in range(50):
            if unique_name not in existing_names:
                return unique_name

            unique_name = "{}-{}".format(name_str, NameCount.get_number(resource_type=resource_type))
        else:
            raise LookupError("Cannot find unique name.")
    else:
        unique_name = "{}-{}".format(name_str, NameCount.get_number(resource_type=resource_type))

    return unique_name


def _parse_cpus_list(cpus):
    """
    Convert human friendly pcup list to list of integers.
    e.g., '5-7,41-43, 43, 45' >> [5, 6, 7, 41, 42, 43, 43, 45]

    Args:
        cpus (str):

    Returns (list): list of integers

    """
    if isinstance(cpus, str):
        if cpus.strip() == '':
            return []

        cpus = cpus.split(sep=',')

    cpus_list = list(cpus)

    for val in cpus:
        # convert '3-6' to [3, 4, 5, 6]
        if '-' in val:
            cpus_list.remove(val)
            min_, max_ = val.split(sep='-')

            # unpinned:20; pinned_cpulist:-, unpinned_cpulist:10-19,30-39
            if min_ != '':
                cpus_list += list(range(int(min_), int(max_) + 1))

    return sorted([int(val) for val in cpus_list])


def get_timedelta_for_isotimes(time1, time2):
    """

    Args:
        time1 (str): such as "2016-08-16T12:59:45.440697+00:00"
        time2 (str):

    Returns:

    """
    def _parse_time(time_):
        time_ = time_.strip().split(sep='.')[0].split(sep='+')[0]
        if 'T' in time_:
            pattern = "%Y-%m-%dT%H:%M:%S"
        elif ' ' in time_:
            pattern = "%Y-%m-%d %H:%M:%S"
        else:
            raise ValueError("Unknown format for time1: {}".format(time_))
        time_datetime = datetime.strptime(time_, pattern)
        return time_datetime

    time1_datetime = _parse_time(time_=time1)
    time2_datetime = _parse_time(time_=time2)

    return time2_datetime - time1_datetime


def _execute_with_openstack_cli():
    """
    DO NOT USE THIS IN TEST FUNCTIONS!
    """
    return ProjVar.get_var('OPENSTACK_CLI')


def wait_for_val_from_func(expt_val, timeout, check_interval, func, *args, **kwargs):
    end_time = time.time() + timeout
    while time.time() < end_time:
        current_val = func(*args, **kwargs)
        if not isinstance(expt_val, list) or isinstance(expt_val, tuple):
            expt_val = [expt_val]

        for val in expt_val:
            if val == current_val:
                return True, val

        time.sleep(check_interval)

    return False, current_val


def wait_for_process(ssh_client, process, sudo=False, disappear=False, timeout=60, time_to_stay=1, check_interval=1,
                     fail_ok=True):
    """
    Wait for given process to appear or disappear

    Args:
        ssh_client (SSH_Client):
        process (str): unique identification of process, such as pid, or unique proc name
        disappear (bool): whether to wait for proc appear or disappear
        timeout (int): max wait time
        time_to_stay (int): seconds to persists
        check_interval (int): how often to check
        fail_ok (bool):

    Returns (bool): whether or not process appear/disappear within timeout

    """
    cmd = 'ps aux | grep --color=never {} | grep -v grep'.format(process)
    # msg_str = 'disappear' if disappear else 'appear'

    res = ssh_client.wait_for_cmd_output_persists(cmd, process, timeout=timeout, time_to_stay=time_to_stay,
                                                  strict=False, regex=False, check_interval=check_interval,
                                                  exclude=disappear, non_zero_rtn_ok=True, sudo=sudo, fail_ok=fail_ok)

    return res


def get_date_in_format(ssh_client=None, date_format="%Y%m%d %T"):
    """
    Get date in given format.
    Args:
        ssh_client (SSHClient):
        date_format (str): Please see date --help for valid format strings

    Returns (str): date output in given format

    """
    if ssh_client is None:
        ssh_client = ControllerClient.get_active_controller()
    return ssh_client.exec_cmd("date +'{}'".format(date_format), fail_ok=False)[1]