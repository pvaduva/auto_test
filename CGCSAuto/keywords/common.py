#
# Copyright (c) 2016 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#


#############################################################
# DO NOT import anything from helper modules to this module #
#############################################################

import os
import re
import time
import ipaddress
from contextlib import contextmanager
from datetime import datetime

import pexpect

from consts.auth import Tenant, TestFileServer, HostLinuxUser
from consts.proj_vars import ProjVar
from consts.build_server import YOW_TUXLAB2
from consts.stx import OAM_IP_v6, Prompt
from utils import exceptions
from utils.clients.ssh import ControllerClient, NATBoxClient, SSHClient, SSHFromSSH, \
    get_cli_client
from utils.tis_log import LOG


def scp_from_test_server_to_user_file_dir(source_path, dest_dir, dest_name=None,
                                          timeout=900, con_ssh=None,
                                          central_region=False):
    if con_ssh is None:
        con_ssh = get_cli_client(central_region=central_region)
    if dest_name is None:
        dest_name = source_path.split(sep='/')[-1]

    if ProjVar.get_var('USER_FILE_DIR') == ProjVar.get_var('TEMP_DIR'):
        LOG.info("Copy file from test server to localhost")
        source_server = TestFileServer.get_server()
        source_user = TestFileServer.get_user()
        source_password = TestFileServer.get_password()
        dest_path = dest_dir if not dest_name else os.path.join(dest_dir,
                                                                dest_name)
        LOG.info('Check if file already exists on TiS')
        if con_ssh.file_exists(file_path=dest_path):
            LOG.info('dest path {} already exists. Return existing path'.format(
                dest_path))
            return dest_path

        os.makedirs(dest_dir, exist_ok=True)
        con_ssh.scp_on_dest(source_user=source_user, source_ip=source_server,
                            source_path=source_path,
                            dest_path=dest_path, source_pswd=source_password,
                            timeout=timeout)
        return dest_path
    else:
        LOG.info("Copy file from test server to active controller")
        return scp_from_test_server_to_active_controller(
            source_path=source_path, dest_dir=dest_dir,
            dest_name=dest_name, timeout=timeout, con_ssh=con_ssh)


def _scp_from_remote_to_active_controller(source_server, source_path,
                                          dest_dir, dest_name=None,
                                          source_user=None,
                                          source_password=None,
                                          timeout=900, con_ssh=None,
                                          is_dir=False, ipv6=None):
    """
    SCP file or files under a directory from remote server to TiS server

    Args:
        source_path (str): remote server file path or directory path
        dest_dir (str): destination directory. should end with '/'
        dest_name (str): destination file name if not dir
        timeout (int):
        con_ssh:
        is_dir

    Returns (str|None): destination file/dir path if scp successful else None

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if not source_user:
        source_user = TestFileServer.get_user()
    if not source_password:
        source_password = TestFileServer.get_password()

    if dest_name is None and not is_dir:
        dest_name = source_path.split(sep='/')[-1]

    dest_path = dest_dir if not dest_name else os.path.join(dest_dir, dest_name)

    LOG.info('Check if file already exists on TiS')
    if not is_dir and con_ssh.file_exists(file_path=dest_path):
        LOG.info('dest path {} already exists. Return existing path'.format(
            dest_path))
        return dest_path

    LOG.info('Create destination directory on tis server if not already exists')
    cmd = 'mkdir -p {}'.format(dest_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    nat_name = ProjVar.get_var('NATBOX')
    if nat_name:
        nat_name = nat_name.get('name')
    if nat_name and (
            nat_name == 'localhost' or nat_name.startswith('128.224.')):
        LOG.info('VBox detected, performing intermediate scp')

        nat_dest_path = '/tmp/{}'.format(dest_name)
        nat_ssh = NATBoxClient.get_natbox_client()

        if not nat_ssh.file_exists(nat_dest_path):
            LOG.info("scp file from {} to NatBox: {}".format(nat_name,
                                                             source_server))
            nat_ssh.scp_on_dest(source_user=source_user,
                                source_ip=source_server,
                                source_path=source_path,
                                dest_path=nat_dest_path,
                                source_pswd=source_password, timeout=timeout,
                                is_dir=is_dir)

        LOG.info(
            'scp file from natbox {} to active controller'.format(nat_name))
        dest_user = HostLinuxUser.get_user()
        dest_pswd = HostLinuxUser.get_password()
        dest_ip = ProjVar.get_var('LAB').get('floating ip')
        nat_ssh.scp_on_source(source_path=nat_dest_path, dest_user=dest_user,
                              dest_ip=dest_ip, dest_path=dest_path,
                              dest_password=dest_pswd, timeout=timeout,
                              is_dir=is_dir)

    else:  # if not a VBox lab, scp from remote server directly to TiS server
        LOG.info("scp file(s) from {} to tis".format(source_server))
        con_ssh.scp_on_dest(source_user=source_user, source_ip=source_server,
                            source_path=source_path,
                            dest_path=dest_path, source_pswd=source_password,
                            timeout=timeout, is_dir=is_dir, ipv6=ipv6)

    return dest_path

def _scp_from_remote_to_active_controllers(source_server, source_path,
                                          dest_dir, dest_name=None,
                                          source_user=None,
                                          source_password=None,
                                          timeout=900, cons_ssh=None,
                                          is_dir=False, ipv6=None):
    """
    SCP file or files under a directory from remote server to TiS server

    Args:
        source_path (str): remote server file path or directory path
        dest_dir (str): destination directory. should end with '/'
        dest_name (str): destination file name if not dir
        timeout (int):
        con_ssh:
        is_dir

    Returns (str|None): destination file/dir path if scp successful else None

    """
    if cons_ssh is None:
        cons_ssh = ControllerClient.get_active_controllers()
    if not source_user:
        source_user = TestFileServer.get_user()
    if not source_password:
        source_password = TestFileServer.get_password()

    if dest_name is None and not is_dir:
        dest_name = source_path.split(sep='/')[-1]

    dest_path = dest_dir if not dest_name else os.path.join(dest_dir, dest_name)

    LOG.info('Create destination directory on tis server if not already exists')
    cmd = 'mkdir -p {}'.format(dest_dir)
    for con_ssh in cons_ssh:
        con_ssh.exec_cmd(cmd, fail_ok=False)
    
        nat_name = ProjVar.get_var('NATBOX')
        if nat_name:
            nat_name = nat_name.get('name')
        if nat_name and (
                nat_name == 'localhost' or nat_name.startswith('128.224.')):
            LOG.info('VBox detected, performing intermediate scp')
    
            nat_dest_path = '/tmp/{}'.format(dest_name)
            nat_ssh = NATBoxClient.get_natbox_client()
    
            if not nat_ssh.file_exists(nat_dest_path):
                LOG.info("scp file from {} to NatBox: {}".format(nat_name,
                                                                 source_server))
                nat_ssh.scp_on_dest(source_user=source_user,
                                    source_ip=source_server,
                                    source_path=source_path,
                                    dest_path=nat_dest_path,
                                    source_pswd=source_password, timeout=timeout,
                                    is_dir=is_dir)
    
            LOG.info(
                'scp file from natbox {} to active controller'.format(nat_name))
            dest_user = HostLinuxUser.get_user()
            dest_pswd = HostLinuxUser.get_password()
            dest_ip = ProjVar.get_var('LAB').get('floating ip')
            nat_ssh.scp_on_source(source_path=nat_dest_path, dest_user=dest_user,
                                  dest_ip=dest_ip, dest_path=dest_path,
                                  dest_password=dest_pswd, timeout=timeout,
                                  is_dir=is_dir)
    
        else:  # if not a VBox lab, scp from remote server directly to TiS server
            LOG.info("scp file(s) from {} to tis".format(source_server))
            con_ssh.scp_on_dest(source_user=source_user, source_ip=source_server,
                                source_path=source_path,
                                dest_path=dest_path, source_pswd=source_password,
                                timeout=timeout, is_dir=is_dir, ipv6=ipv6)
    
    return dest_path

def scp_from_test_server_to_active_controller(source_path, dest_dir,
                                              dest_name=None, timeout=900,
                                              con_ssh=None,
                                              is_dir=False,
                                              force_ipv4=False):
    """
    SCP file or files under a directory from test server to TiS server

    Args:
        source_path (str): test server file path or directory path
        dest_dir (str): destination directory. should end with '/'
        dest_name (str): destination file name if not dir
        timeout (int):
        con_ssh:
        is_dir (bool)

    Returns (str|None): destination file/dir path if scp successful else None

    """
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    if not force_ipv4:
        ipv6 = ProjVar.get_var('IPV6_OAM')
    else:
        ipv6 = None

    source_server = TestFileServer.get_server(ipv6=ipv6)
    source_user = TestFileServer.get_user()
    source_password = TestFileServer.get_password()

    return _scp_from_remote_to_active_controller(
        source_server=source_server,
        source_path=source_path,
        dest_dir=dest_dir,
        dest_name=dest_name,
        source_user=source_user,
        source_password=source_password,
        timeout=timeout,
        con_ssh=con_ssh,
        is_dir=is_dir,
        ipv6=ipv6)

def scp_from_test_server_to_active_controllers(source_path, dest_dir,
                                              dest_name=None, timeout=900,
                                              cons_ssh=None,
                                              is_dir=False,
                                              force_ipv4=False):
    """
    SCP file or files under a directory from test server to TiS server

    Args:
        source_path (str): test server file path or directory path
        dest_dir (str): destination directory. should end with '/'
        dest_name (str): destination file name if not dir
        timeout (int):
        con_ssh:
        is_dir (bool)

    Returns (str|None): destination file/dir path if scp successful else None

    """
    if not cons_ssh:
        cons_ssh = ControllerClient.get_active_controllers()

    if not force_ipv4:
        ipv6 = ProjVar.get_var('IPV6_OAM')
    else:
        ipv6 = None

    source_server = TestFileServer.get_server(ipv6=ipv6)
    source_user = TestFileServer.get_user()
    source_password = TestFileServer.get_password()
    return _scp_from_remote_to_active_controllers(
        source_server=source_server,
        source_path=source_path,
        dest_dir=dest_dir,
        dest_name=dest_name,
        source_user=source_user,
        source_password=source_password,
        timeout=timeout,
        cons_ssh=cons_ssh,
        is_dir=is_dir,
        ipv6=ipv6)



def scp_from_active_controller_to_test_server(source_path, dest_dir,
                                              dest_name=None, timeout=900,
                                              is_dir=False,
                                              con_ssh=None):
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

    ipv6 = ProjVar.get_var('IPV6_OAM')
    dest_server = TestFileServer.get_server(ipv6=ipv6)
    dest_user = TestFileServer.get_user()
    dest_password = TestFileServer.get_password()

    dest_path = dest_dir if not dest_name else os.path.join(dest_dir, dest_name)

    LOG.info("scp file(s) from tis server to test server")
    con_ssh.scp_on_source(source_path=source_path, dest_user=dest_user,
                          dest_password=dest_password, dest_path=dest_path,
                          timeout=timeout, is_dir=is_dir, dest_ip=dest_server, ipv6=ipv6)

    return dest_path


def scp_from_localhost_to_active_controller(source_path, dest_path,
                                            dest_user=None,
                                            dest_password=None,
                                            timeout=900, is_dir=False):
    active_cont_ip = ControllerClient.get_active_controller().host

    return scp_from_local(source_path, active_cont_ip, dest_path=dest_path,
                          dest_user=dest_user, dest_password=dest_password,
                          timeout=timeout, is_dir=is_dir)


def scp_from_active_controller_to_localhost(source_path, dest_path,
                                            src_user=None,
                                            src_password=None,
                                            timeout=900, is_dir=False):
    active_cont_ip = ControllerClient.get_active_controller().host

    if not src_user:
        src_user = HostLinuxUser.get_user()
    if not src_password:
        src_password = HostLinuxUser.get_password()

    return scp_to_local(source_path=source_path, source_server=active_cont_ip,
                        dest_path=dest_path,
                        source_user=src_user, source_password=src_password,
                        timeout=timeout, is_dir=is_dir)


def scp_from_local(source_path, dest_ip, dest_path=None,
                   dest_user=None, dest_password=None,
                   timeout=900, is_dir=False):
    """
    Scp file(s) from localhost (i.e., from where the automated tests are
    executed).

    Args:
        source_path (str): source file/directory path
        dest_ip (str): ip of the destination host
        dest_user (str): username of destination host.
        dest_password (str): password of destination host
        dest_path (str): destination directory path to copy the file(s) to
        timeout (int): max time to wait for scp finish in seconds
        is_dir (bool): whether to copy a single file or a directory

    """
    if not dest_path:
        dest_path = HostLinuxUser.get_home()
    if not dest_user:
        dest_user = HostLinuxUser.get_user()
    if not dest_password:
        dest_password = HostLinuxUser.get_password()

    dir_option = '-r ' if is_dir else ''

    cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ' \
          '{}{} {}@{}:{}'.\
        format(dir_option, source_path, dest_user, dest_ip, dest_path)

    _scp_on_local(cmd, remote_password=dest_password, timeout=timeout)


def scp_to_local(dest_path, source_path, source_server=None,
                 source_user=None,
                 source_password=None,
                 timeout=900, is_dir=False, ipv6=None):
    """
    Scp file(s) to localhost (i.e., to where the automated tests are executed).

    Args:
        source_path (str): source file/directory path
        source_server (str): ip of the source host.
        source_user (str): username of source host.
        source_password (str): password of source host
        dest_path (str): destination directory path to copy the file(s) to
        timeout (int): max time to wait for scp finish in seconds
        is_dir (bool): whether to copy a single file or a directory
        ipv6

    """
    if not source_user:
        source_user = HostLinuxUser.get_user()
    if not source_password:
        source_password = HostLinuxUser.get_password()

    dir_option = '-r ' if is_dir else ''
    ipv6_arg = ''
    if get_ip_version(source_server) == 6:
        ipv6_arg = '-6 '
        source_server = '[{}]'.format(source_server)
    elif ipv6:
        ipv6_arg = '-6 '
    cmd = 'scp {}-oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ' \
          '{}{}@{}:{} {}'.\
        format(ipv6_arg, dir_option, source_user, source_server, source_path, dest_path)

    _scp_on_local(cmd, remote_password=source_password, timeout=timeout)


def _scp_on_local(cmd, remote_password, logdir=None, timeout=900):
    LOG.debug('scp cmd: {}'.format(cmd))

    logdir = logdir or ProjVar.get_var('LOG_DIR')
    logfile = os.path.join(logdir, 'scp_files.log')

    with open(logfile, mode='a') as f:
        local_child = pexpect.spawn(command=cmd, encoding='utf-8', logfile=f)
        index = local_child.expect([pexpect.EOF, 'assword:', 'yes/no'],
                                   timeout=timeout)

        if index == 2:
            local_child.sendline('yes')
            index = local_child.expect([pexpect.EOF, 'assword:'],
                                       timeout=timeout)

        if index == 1:
            local_child.sendline(remote_password)
            local_child.expect(pexpect.EOF, timeout=timeout)


def get_tenant_name(auth_info=None):
    """
    Get name of given tenant. If None is given, primary tenant name will be
    returned.

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
        raise ValueError(
            "Invalid resource_type provided. Valid types: {}".format(
                valid_types))

    if existing_names:
        if resource_type in ['image', 'volume', 'flavor']:
            unique_name = name_str
        else:
            unique_name = "{}-{}".format(name_str, NameCount.get_number(
                resource_type=resource_type))

        for i in range(50):
            if unique_name not in existing_names:
                return unique_name

            unique_name = "{}-{}".format(name_str, NameCount.get_number(
                resource_type=resource_type))
        else:
            raise LookupError("Cannot find unique name.")
    else:
        unique_name = "{}-{}".format(name_str, NameCount.get_number(
            resource_type=resource_type))

    return unique_name


def parse_cpus_list(cpus):
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

    Returns ()

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


def wait_for_val_from_func(expt_val, timeout, check_interval, func, *args,
                           **kwargs):
    end_time = time.time() + timeout
    current_val = None
    while time.time() < end_time:
        current_val = func(*args, **kwargs)
        if not isinstance(expt_val, list) or isinstance(expt_val, tuple):
            expt_val = [expt_val]

        for val in expt_val:
            if val == current_val:
                return True, val

        time.sleep(check_interval)

    return False, current_val


def wait_for_process(ssh_client, process, sudo=False, disappear=False,
                     timeout=60, time_to_stay=1, check_interval=1,
                     fail_ok=True):
    """
    Wait for given process to appear or disappear

    Args:
        ssh_client (SSH_Client):
        process (str): unique identification of process, such as pid, or
            unique proc name
        sudo (bool)
        disappear (bool): whether to wait for proc appear or disappear
        timeout (int): max wait time
        time_to_stay (int): seconds to persists
        check_interval (int): how often to check
        fail_ok (bool):

    Returns (bool): whether or not process appear/disappear within timeout

    """
    cmd = 'ps aux | grep --color=never {} | grep -v grep'.format(process)
    # msg_str = 'disappear' if disappear else 'appear'

    res = ssh_client.wait_for_cmd_output_persists(
        cmd, process, timeout=timeout, time_to_stay=time_to_stay,
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
    return ssh_client.exec_cmd("date +'{}'".format(date_format),
                               fail_ok=False)[1]


def write_to_file(file_path, content, mode='a'):
    """
    Write content to specified local file
    Args:
        file_path (str): file path on localhost
        content (str): content to write to file
        mode (str): file operation mode. Default is 'a' (append to end of file).

    Returns: None

    """
    time_stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    with open(file_path, mode=mode) as f:
        f.write(
            '\n-----------------[{}]-----------------\n{}\n'.format(time_stamp,
                                                                    content))


def collect_software_logs(con_ssh=None, lab_ip=None):
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    LOG.info("Collecting all hosts logs...")
    con_ssh.exec_cmd('source /etc/platform/openrc', get_exit_code=False)
    con_ssh.send('collect all')

    expect_list = ['.*password for .*:', 'collecting data.',
                   con_ssh.prompt]
    index_1 = con_ssh.expect(expect_list, timeout=20)
    if index_1 == 2:
        LOG.error(
            "Something is wrong with collect all. Check ssh console log for "
            "detail.")
        return
    elif index_1 == 0:
        con_ssh.send(con_ssh.password)
        con_ssh.expect('collecting data')

    index_2 = con_ssh.expect(['/scratch/ALL_NODES.*', con_ssh.prompt],
                             timeout=1200)
    if index_2 == 0:
        output = con_ssh.cmd_output
        con_ssh.expect()
        logpath = re.findall('.*(/scratch/ALL_NODES_.*.tar).*', output)[0]
        LOG.info(
            "\n################### TiS server log path: {}".format(logpath))
    else:
        LOG.error("Collecting logs failed. No ALL_NODES logs found.")
        return

    if lab_ip is None:
        lab_ip = ProjVar.get_var('LAB')['floating ip']
    dest_path = ProjVar.get_var('LOG_DIR')
    try:
        LOG.info("Copying log file from lab {} to local {}".format(lab_ip,
                                                                   dest_path))
        scp_to_local(source_path=logpath, source_server=lab_ip,
                     dest_path=dest_path,
                     timeout=300)
        LOG.info("{} is successfully copied to local directory: {}".format(
            logpath, dest_path))
    except Exception as e:
        LOG.warning("Failed to copy log file to localhost.")
        LOG.error(e, exc_info=True)


def parse_args(args_dict, repeat_arg=False, vals_sep=' '):
    """
    parse args dictionary and convert it to string
    Args:
        args_dict (dict): key/value pairs
        repeat_arg: if value is tuple, list, dict, should the arg be repeated.
            e.g., True for --nic in nova boot. False for -m in gnocchi
            measures aggregation
        vals_sep (str): separator to join multiple vals. Only applicable when
        repeat_arg=False.

    Returns (str):

    """
    def convert_val_dict(key__, vals_dict, repeat_key):
        vals_ = []
        for k, v in vals_dict.items():
            if isinstance(v, str) and ' ' in v:
                v = '"{}"'.format(v)
            vals_.append('{}={}'.format(k, v))
        if repeat_key:
            args_str = ' ' + ' '.join(
                ['{} {}'.format(key__, v_) for v_ in vals_])
        else:
            args_str = ' {} {}'.format(key__, vals_sep.join(vals_))
        return args_str

    args = ''
    for key, val in args_dict.items():
        if val is None:
            continue

        key = key if key.startswith('-') else '--{}'.format(key)
        if isinstance(val, str):
            if ' ' in val:
                val = '"{}"'.format(val)
            args += ' {}={}'.format(key, val)
        elif isinstance(val, bool):
            if val:
                args += ' {}'.format(key)
        elif isinstance(val, (int, float)):
            args += ' {}={}'.format(key, val)
        elif isinstance(val, dict):
            args += convert_val_dict(key__=key, vals_dict=val,
                                     repeat_key=repeat_arg)
        elif isinstance(val, (list, tuple)):
            if repeat_arg:
                for val_ in val:
                    if isinstance(val_, dict):
                        args += convert_val_dict(key__=key, vals_dict=val_,
                                                 repeat_key=False)
                    else:
                        args += ' {}={}'.format(key, val_)
            else:
                args += ' {}={}'.format(key, vals_sep.join(val))
        else:
            raise ValueError(
                "Unrecognized value type. Key: {}; value: {}".format(key, val))

    return args.strip()


def get_symlink(ssh_client, file_path):
    code, output = ssh_client.exec_cmd(
        'ls -l {} | grep --color=never ""'.format(file_path))
    if code != 0:
        LOG.warning('{} not found!'.format(file_path))
        return None

    res = re.findall('> (.*)', output)
    if not res:
        LOG.warning('No symlink found for {}'.format(file_path))
        return None

    link = res[0].strip()
    return link


def is_file(filename, ssh_client):
    code = ssh_client.exec_cmd('test -f {}'.format(filename), fail_ok=True)[0]
    return 0 == code


def is_directory(dirname, ssh_client):
    code = ssh_client.exec_cmd('test -d {}'.format(dirname), fail_ok=True)[0]
    return 0 == code


def lab_time_now(con_ssh=None, date_format='%Y-%m-%dT%H:%M:%S'):
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    date_cmd_format = date_format + '.%N'
    timestamp = get_date_in_format(ssh_client=con_ssh,
                                   date_format=date_cmd_format)
    with_milliseconds = timestamp.split('.')[0] + '.{}'.format(
        int(int(timestamp.split('.')[1]) / 1000))
    format1 = date_format + '.%f'
    parsed = datetime.strptime(with_milliseconds, format1)

    return with_milliseconds.split('.')[0], parsed


def search_log(file_path, ssh_client, pattern, extended_regex=False,
               get_all=True, top_down=False, sudo=False,
               start_time=None):

    prefix_space = False
    if 'bash' in file_path:
        ssh_client.exec_cmd('HISTCONTROL=ignorespace')
        prefix_space = True
        sudo = True

    # Reformat the timestamp to add or remove T based on the actual format
    # in specified log
    if start_time:
        tmp_cmd = """zgrep -m 1 "" {} | awk '{{print $1}}'""".format(file_path)
        if sudo:
            tmp_time = ssh_client.exec_sudo_cmd(tmp_cmd, fail_ok=False,
                                                prefix_space=prefix_space)[1]
        else:
            tmp_time = ssh_client.exec_cmd(tmp_cmd, fail_ok=False,
                                           prefix_space=prefix_space)[1]

        if re.search(r'\dT\d', tmp_time):
            start_time = start_time.strip().replace(' ', 'T')
        else:
            start_time = start_time.strip().replace('T', ' ')

    # Compose the zgrep cmd to search the log
    init_filter = """| awk '$0 > "{}"'""".format(start_time) if start_time \
        else ''
    count = '' if get_all else '|grep --color=never -m 1 ""'
    extended_regex = '-E ' if extended_regex else ''
    base_cmd = '' if top_down else '|tac'
    cmd = 'zgrep --color=never {}"{}" {}|grep -v grep{}{}{}'.\
        format(extended_regex, pattern, file_path, init_filter, base_cmd, count)
    if sudo:
        out = ssh_client.exec_sudo_cmd(cmd, fail_ok=True,
                                       prefix_space=prefix_space)[1]
    else:
        out = ssh_client.exec_cmd(cmd, fail_ok=True,
                                  prefix_space=prefix_space)[1]

    return out


@contextmanager
def ssh_to_remote_node(host, username=None, password=None, prompt=None,
                       ssh_client=None, use_telnet=False,
                       telnet_session=None):
    """
    ssh to a external node from sshclient.

    Args:
        host (str|None): hostname or ip address of remote node to ssh to.
        username (str):
        password (str):
        prompt (str):
        ssh_client (SSHClient): client to ssh from
        use_telnet:
        telnet_session:

    Returns (SSHClient): ssh client of the host

    Examples: with ssh_to_remote_node('128.224.150.92) as remote_ssh:
                  remote_ssh.exec_cmd(cmd)
\    """

    if not host:
        raise exceptions.SSHException(
            "Remote node hostname or ip address must be provided")

    if use_telnet and not telnet_session:
        raise exceptions.SSHException(
            "Telnet session cannot be none if using telnet.")

    if not ssh_client and not use_telnet:
        ssh_client = ControllerClient.get_active_controller()

    if not use_telnet:
        from keywords.security_helper import LinuxUser
        default_user, default_password = LinuxUser.get_current_user_password()
    else:
        default_user = HostLinuxUser.get_user()
        default_password = HostLinuxUser.get_password()

    user = username if username else default_user
    password = password if password else default_password
    if use_telnet:
        original_host = telnet_session.exec_cmd('hostname')[1]
    else:
        original_host = ssh_client.host

    if not prompt:
        prompt = '.*' + host + r'\:~\$'

    remote_ssh = SSHClient(host, user=user, password=password,
                           initial_prompt=prompt)
    remote_ssh.connect()
    current_host = remote_ssh.host
    if not current_host == host:
        raise exceptions.SSHException(
            "Current host is {} instead of {}".format(current_host, host))
    try:
        yield remote_ssh
    finally:
        if current_host != original_host:
            remote_ssh.close()


def get_ip_version(ip_addr):
    try:
        ip_version = ipaddress.ip_address(ip_addr).version
    except ValueError:
        ip_version = None

    return ip_version


def convert_ipv4_to_ipv6(ipv4_ip):
    ip = ipv4_ip
    if get_ip_version(ipv4_ip) == 4:
        second_last, suffix = str(ipv4_ip).rsplit('.')[-2:]
        if second_last == '151':
            suffix = '1{}'.format(suffix.rjust(3, '0'))
        ip = OAM_IP_v6.format(suffix)
    return ip


def convert_to_ipv6(lab):
    for ip_type in ('floating ip', 'controller-0 ip', 'controller-1 ip'):
        if ip_type in lab:
            ipv4_ip = lab[ip_type]
            if get_ip_version(ipv4_ip) == 4:
                lab[ip_type] = convert_ipv4_to_ipv6(ipv4_ip)
    LOG.info('{} IPv6 OAM ip: {}'.format(lab['short_name'], lab['floating ip']))
    return lab


def ssh_to_stx(lab=None, set_client=False):
    if not lab:
        lab = ProjVar.get_var('LAB')

    user = HostLinuxUser.get_user()
    password = HostLinuxUser.get_password()
    if ProjVar.get_var('IPV6_OAM'):
        lab = convert_to_ipv6(lab)
        LOG.info("SSH to IPv6 system {} via tuxlab2".format(lab['short_name']))
        tuxlab2_ip = YOW_TUXLAB2['ip']
        tux_user = TestFileServer.get_user()
        tuxlab_prompt = r'{}@{}\:(.*)\$ '.format(tux_user, YOW_TUXLAB2['name'])
        tuxlab2_ssh = SSHClient(host=tuxlab2_ip, user=tux_user,
                                password=TestFileServer.get_password(), initial_prompt=tuxlab_prompt)
        tuxlab2_ssh.connect(retry_timeout=300, retry_interval=30, timeout=60)
        con_ssh = SSHFromSSH(ssh_client=tuxlab2_ssh, host=lab['floating ip'],
                             user=user, password=password,
                             initial_prompt=Prompt.CONTROLLER_PROMPT)
    else:
        con_ssh = SSHClient(lab['floating ip'], user=HostLinuxUser.get_user(),
                            password=HostLinuxUser.get_password(),
                            initial_prompt=Prompt.CONTROLLER_PROMPT)

    con_ssh.connect(retry=True, retry_timeout=30, use_current=False)
    if set_client:
        ControllerClient.set_active_controller(con_ssh)

    return con_ssh
