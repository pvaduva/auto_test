"""
This module provides helper functions for storage based testing, with a focus
on CEPH-related helper functions.
"""

import time
import re

from utils import table_parser, cli
from utils.tis_log import LOG
from utils.ssh import ControllerClient, SSHFromSSH
from keywords import system_helper, host_helper
from consts.cgcs import Prompt
from consts.auth import Host

def is_ceph_healthy(con_ssh=None):
    """
    Query 'ceph -s' and return True if ceph health is okay
    and False otherwise.

    Args:
        con_ssh (SSHClient):

    Returns:
        - (bool) True if health okay, False otherwise
        - (string) message
    """

    health_ok = 'HEALTH_OK'
    health_warn = 'HEALTH_WARN'
    cmd = 'ceph -s'

    rtn_code, out = con_ssh.exec_cmd(cmd)

    if health_ok in out:
        msg = 'CEPH cluster is healthy'
        return True, msg
    elif health_warn in out:
        msg = 'CEPH cluster is in health warn state'
        return False, msg

    LOG.info('Cannot determine CEPH health state')
    return False, msg

def get_num_osds(con_ssh=None):
    """
    Return the number of OSDs on a CEPH system"
    Args:
        con_ssh(SSHClient):

    Returns (numeric): Return the number of OSDs on the system,
    """

    cmd = 'ceph -s'

    rtn_code, out = con_ssh.exec_cmd(cmd)
    osds = re.search('(\d+) osds', out)
    if osds.group(1):
        LOG.info('There are {} OSDs on the system'.format(osds.group(1)))
        return int(osds.group(1))

    LOG.info('There are no OSDs on the system')
    return 0

def get_osd_host(osd_id, con_ssh=None):
    """
    Return the host associated with the provided OSD ID
    Args:
        con_ssh(SSHClient):
        osd_id - an OSD number, e.g. 0, 1, 2, 3...

    Returns:
        - Return hostname or -1 if not found
        - Return message
    """

    cli.source_admin(con_ssh)

    storage_hosts = system_helper.get_storage_nodes()
    for host in storage_hosts:
        cmd = 'system host-stor-list {}'.format(host)
        rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
        table_ = table_parser.table(cli.system('host-stor-list', host))
        osd_list = table_parser.get_values(table_, 'osdid')
        if osd_id in osd_list:
            msg = 'OSD ID {} is on host {}'.format(osd_id, host)
            return host, msg

    msg = 'Could not find host for OSD ID {}'.format(osd_id)
    return -1, msg

def kill_process(host, pid):
    """
    Given the id of an OSD, kill the process and ensure it restarts.
    Args:
        host (string) - the host to ssh into, e.g. 'controller-1'
        pid (string) - pid to kill, e.g. '12345'

    Returns:
        - (bool) True if process was killed, False otherwise
        - (string) message
    """


    cmd = 'kill -9 {}'.format(pid)

    # SSH could be redundant if we are on controller-0 (oh well!)
    LOG.info('Kill process {} on {}'.format(pid, host))
    with host_helper.ssh_to_host(host) as host_ssh:
        with host_ssh.login_as_root() as root_ssh:
            rtn_code, out = root_ssh.exec_cmd(cmd, expect_timeout=60)
            LOG.info(cmd)

        LOG.info('Ensure the PID is no longer listed')
        pid_exists, msg = check_pid_exists(pid, root_ssh)
        if pid_exists:
            return False, msg

    return True, msg

# TODO: get_osd_pid and get_mon_pid are good candidates for combining
def get_osd_pid(osd_host, osd_id):
    """
    Given the id of an OSD, return the pid.
    Args:
        osd_host (string) - the host to ssh into, e.g. 'storage-0'
        osd_id (string) - osd_id to get the pid of, e.g. '0'
    Returns:
        - (integer) pid if found, or -1 if pid not found
        - (string) message
    """

    cmd = 'cat /var/run/ceph/osd.{}.pid'.format(osd_id)

    with host_helper.ssh_to_host(osd_host) as storage_ssh:
        LOG.info(cmd)
        rtn_code, out = storage_ssh.exec_cmd(cmd, expect_timeout=60)
        osd_match = r'(\d+)'
        pid = re.match(osd_match, out)
        if pid:
            msg = 'Corresponding pid for OSD ID {} is {}'.format(osd_id, pid.group(1))
            return pid.group(1), msg

    msg = 'Corresponding pid for OSD ID {} was not found'.format(osd_id)
    return -1, msg

# TODO: get_osd_pid and get_mon_pid are good candidates for combining
def get_mon_pid(mon_host):
    """
    Given the host name of a monitor, return the pid of the ceph-mon process
    Args:
        mon_host (string) - the host to get the pid of, e.g. 'storage-1'
    Returns:
        - (integer) pid if found, or -1 if pid not found
        - (string) message
    """

    cmd = 'cat /var/run/ceph/mon.{}.pid'.format(mon_host)

    with host_helper.ssh_to_host(mon_host) as mon_ssh:
        LOG.info(cmd)
        rtn_code, out = mon_ssh.exec_cmd(cmd, expect_timeout=60)
        mon_match = r'(\d+)'
        pid = re.match(mon_match, out)
        if pid:
            msg = 'Corresponding ceph-mon pid for {} is {}'.format(mon_host, pid.group(1))
            return pid.group(1), msg

    msg = 'Corresponding ceph-mon pid for {} was not found'.format(mon_host)


def get_osds(host=None, con_ssh=None):
    """
    Given a hostname, get all OSDs on that host

    Args:
        con_ssh(SSHClient)
        host - the host to ssh into
    Returns:
        (list) List of OSDs on the host.  Empty list if none.
    """

    def _get_osds_per_host(host, osd_list, con_ssh=None):
        """
        Return the OSDs on a system.

        Args:
            host - the host to query

        Returns:
            Nothing.  Update osd_list by side-effect.
        """

        cli.source_admin(con_ssh)

        cmd = 'system host-stor-list {}'.format(host)
        rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
        table_ = table_parser.table(cli.system('host-stor-list', host))
        osd_list = osd_list + table_parser.get_values(table_, 'osdid')

        return osd_list

    osd_list = []

    if host:
        osd_list = _get_osds_per_host(host, osd_list, con_ssh)
    else:
        storage_hosts = system_helper.get_storage_hosts()
        for host in storage_hosts:
            osd_list = _get_osds_per_host(host, osd_list, con_ssh)

    return osd_list

def is_osd_up(osd_id, con_ssh=None):
    """
    Determine if a particular OSD is up.

    Args:
        osd_id (int) - ID of OSD we want to query

    Returns:
        (bool) True if OSD is up, False if OSD is down
    """

    cmd = 'ceph osd tree | grep osd.{}'.format(osd_id)
    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
    if re.search('up', out):
        return True
    else:
        return False

def check_pid_exists(pid, con_ssh=None):
    """
    Check if a PID exists on a particular host.
    Args:
        con_ssh(SSHClient)
        pid - the process ID
    Returns (bool):
        True if pid exists and False otherwise
    """

    cmd = 'kill -0 {}'.format(pid)

    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
    if rtn_code != 1:
        msg = 'Process {} exists'.format(pid)
        return True, msg

    msg = 'Process {} does not exist'.format(pid)
    return False, msg

def get_storage_group(host):
    """
    Determine the storage replication group name associated with the storage
    host.

    Args:
        host (string) - storage host, e.g. 'storage-0'
    Returns:
        storage_group (string) - group name, e.g. 'group-0'
        msg (string) - log message
    """

    host_table = table_parser.table(cli.system('host-show', host))
    peers = table_parser.get_values(host_table, 'Value', Property='peers')
    storage_group = re.search('(group-\d+)', peers[0])
    msg = 'Unable to determine replication group for {}'.format(host)
    assert storage_group, msg
    storage_group = storage_group.group(0)
    msg = 'The replication group for {} is {}'.format(host, storage_group)
    return storage_group, msg

def download_images(dload_type='all', img_dest='~/images/', con_ssh=None):
    """
    Retrieve images for testing purposes.  Note, this will add *a lot* of time
    to the test execution.

    Args:
        - type: 'all' to get all images (default),
                'ubuntu' to get ubuntu images,
                'centos' to get centos images
        - con_ssh
        - image destination - where on fileystem images are stored

    Returns:
        - List containing the names of the imported images
    """

    def _wget(urls):
        """
        This function does a wget on the provided urls.
        """
        for url in urls:
            cmd = 'wget {} --no-check-certificate -P {}'.format(url, img_dest)
            rtn_code, out = con_ssh.exec_cmd(cmd)
            assert not rtn_code, out

    centos_image_location = \
    ['http://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud.qcow2', \
     'http://cloud.centos.org/centos/6/images/CentOS-6-x86_64-GenericCloud.qcow2']

    ubuntu_image_location = \
    ['https://cloud-images.ubuntu.com/precise/current/precise-server-cloudimg-amd64-disk1.img']

    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    LOG.info('Create directory for image storage')
    cmd = 'mkdir -p {}'.format(img_dest)
    rtn_code, out = con_ssh.exec_cmd(cmd)
    assert not rtn_code, out

    LOG.info('wget images')
    if dload_type == 'ubuntu' or dload_type == 'all':
        _wget(ubuntu_image_location)
    elif dload_type == 'centos' or dload_type == 'all':
        _wget(centos_image_location)

    #return image_names
