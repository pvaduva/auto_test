"""
This module provides helper functions for storage based testing, with a focus
on CEPH-related helper functions.
"""

import re
import time

from consts.auth import Tenant
from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from keywords import system_helper, host_helper


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

    # TODO: Get con_ssh if None
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    rtn_code, out = con_ssh.exec_cmd(cmd)

    if health_ok in out:
        msg = 'CEPH cluster is healthy'
        return True, msg
    elif health_warn in out:
        msg = 'CEPH cluster is in health warn state'
        return False, msg

    msg = 'Cannot determine CEPH health state'
    LOG.info(msg)
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
        osd_id (int): an OSD number, e.g. 0, 1, 2, 3...

    Returns:
        - Return hostname or -1 if not found
        - Return message
    """
    storage_hosts = system_helper.get_storage_nodes()
    for host in storage_hosts:
        table_ = table_parser.table(cli.system('host-stor-list', host))
        osd_list = table_parser.get_values(table_, 'osdid')
        if str(osd_id) in osd_list:
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
            root_ssh.exec_cmd(cmd, expect_timeout=60)
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
        osd_id (int|str) - osd_id to get the pid of, e.g. '0'
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
    # FIXME
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

        table_ = table_parser.table(cli.system('host-stor-list', host, ssh_client=con_ssh))
        osd_list = osd_list + table_parser.get_values(table_, 'osdid', function='osd')

        return osd_list

    osd_list = []

    if host:
        osd_list = _get_osds_per_host(host, osd_list, con_ssh)
    else:
        storage_hosts = system_helper.get_storage_nodes()
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

    cmd = "ceph osd tree | grep 'osd.{}\s'".format(osd_id)
    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
    if re.search('up', out):
        return True
    else:
        return False


def check_pid_exists(pid, host_ssh):
    """
    Check if a PID exists on a particular host.
    Args:
        host_ssh (SSHClient)
        pid (int|str): the process ID
    Returns (bool):
        True if pid exists and False otherwise
    """

    cmd = 'kill -0 {}'.format(pid)

    rtn_code, out = host_ssh.exec_cmd(cmd, expect_timeout=60)
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
    peers = table_parser.get_value_two_col_table(host_table, 'peers', merge_lines=True)
    storage_group = re.search('(group-\d+)', peers)
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
            rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=7200)
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
        LOG.info("Downloading ubuntu image")
        _wget(ubuntu_image_location)
    elif dload_type == 'centos' or dload_type == 'all':
        LOG.info("Downloading centos image")
        _wget(centos_image_location)

    #return image_names

def find_images(con_ssh, image_type='qcow2', location='~/images'):
    '''
    This function finds all images of a given type, in the given location.
    This is designed to save test time, to prevent downloading images if not
    necessary.

    Arguments:
        - image_type(string): image format, e.g. 'qcow2', 'raw', etc.
          - if the user specifies 'all', return all images
        - location(string): where to find images, e.g. '~/images'

    Test Steps:
        1.  Cycle through the files in a given location
        2.  Create a list of image names of the expected type

    Return:
        - image_names(list): list of image names of a given type, e.g.
          'cgcs-guest.img' or all images if the user specified 'all' as the
          argument to image_type.
    '''

    image_names = []

    cmd = 'ls {}'.format(location)
    rtn_code, out = con_ssh.exec_cmd(cmd)
    image_list = out.split()
    LOG.info('Found the following files: {}'.format(image_list))
    if image_type == 'all':
        return image_list

    # Return a list of image names where the image type matches what the user
    # is looking for, e.g. qcow2
    for image in image_list:
        image_path = location + "/" + image
        cmd = 'qemu-img info {}'.format(image_path)
        rtn_code, out = con_ssh.exec_cmd(cmd)
        if image_type in out:
            image_names.append(image)

    LOG.info('{} images available: {}'.format(image_type, image_names))
    return image_names


def find_image_size(con_ssh, image_name='cgcs-guest.img', location='~/images'):
    '''
    This function uses qemu-img info to determine what size of flavor to use.

    Arguments:
        - con_ssh: ssh connection
        - image_name(string): e.g. 'cgcs-guest.img'
        - location(string): where to find images, e.g. '~/images'

    Test Steps:
        1.  Parse qemu-img info for the image size

    Return:
        - image_size(int): e.g. 8
    '''


    image_path = location + "/" + image_name
    cmd = 'qemu-img info {}'.format(image_path)
    rtn_code, out = con_ssh.exec_cmd(cmd)
    virtual_size = re.search('virtual size: (\d+\.*\d*[M|G])', out)
    msg = 'Unable to determine size of image {}'.format(image_name)
    assert virtual_size.group(0), msg
    # If the size is less than 1G, round to 1
    # If the size is greater than 1G, round up
    if 'M' in virtual_size.group(1):
        image_size = 1
    else:
        image_size = round(float(virtual_size.group(1).strip('G')))

    return image_size


def modify_storage_backend(backend, cinder=None, glance=None, ephemeral=None, object_gib=None, object_gateway=False,
                           lock_unlock=True, fail_ok=False, con_ssh=None):
    """
    Modify ceph storage backend pool allocation

    Args:
        backend (str): storage backend to modify (e.g. ceph)
        cinder:
        glance:
        ephemeral:
        object_:
        fail_ok:
        con_ssh:

    Returns:
        0, dict of new allocation
        1, cli err message

    """

    args = backend

    backend_info = get_storage_backend_info(backend)

    if cinder:
        args += ' cinder_pool_gib=' + cinder
    if glance and backend == 'ceph':
        args += ' glance_pool_gib=' + glance
    if ephemeral and backend == 'ceph':
        args += ' ephemeral_pool_gib=' + ephemeral
    if object_gateway and backend == 'ceph':
        args += ' object_gateway=' + str(object_gateway)
    if object_gib and backend == 'ceph':
        args += ' object_pool_gib=' + object_gib

    code, out = cli.system('storage-backend-modify', args, con_ssh, fail_ok=fail_ok, rtn_list=True)
    # TODO return new values of storage allocation and check they are the right values
    if code == 0:
        backend_info = get_storage_backend_info(backend)
        return 0, backend_info
    else:
        msg = " Fail to modify storage backend allocations: {}".format(out)
        LOG.warning(msg)
        if fail_ok:
            return code, out
        raise exceptions.CLIRejected(msg)



def wait_for_ceph_health_ok(con_ssh=None, timeout=300, fail_ok=False, check_interval=5):
    end_time = time.time() + timeout
    while time.time() < end_time:
        rc, output = is_ceph_healthy(con_ssh=con_ssh)
        if rc:
            return True

        time.sleep(check_interval)

    else:
        err_msg = "Ceph is not healthy  within {} seconds: {}".format(timeout, output)
        if fail_ok:
            LOG.warning(err_msg)
            return False, err_msg
        else:
            raise exceptions.TimeoutException(err_msg)

def get_storage_backend_info(backend, fail_ok=False, con_ssh=None):
    """
    Get storage backend pool allocation info

    Args:
        backend (str): storage backend to get info (e.g. ceph)
        fail_ok:
        con_ssh:

    Returns: dict  {'cinder_pool_gib': 202, 'glance_pool_gib': 20, 'ephemeral_pool_gib': 0,
                    'object_pool_gib': 0, 'ceph_total_space_gib': 222,  'object_gateway': False}

    """
    valid_backends = ['ceph', 'lvm']

    args = backend

    table_ = table_parser.table(cli.system('storage-backend-show', args, ssh_client=con_ssh, fail_ok=fail_ok))

    backend_info = {}
    if table_:
        values = table_['values']
        for value in values:
            backend_info[value[0]] = value[1]
    return backend_info

def get_configured_system_storage_backend(con_ssh=None, fail_ok=False):


    backend = []
    table_ = table_parser.table(cli.system('storage-backend-list', ssh_client=con_ssh, fail_ok=fail_ok))
    if table_:
        table_ = table_parser.filter_table(table_, state='configured')
        backend = table_parser.get_column(table_, 'backend')
    return backend


def get_storage_backend_state_value(backend, con_ssh=None, fail_ok=False):
    table_ = table_parser.table(cli.system('storage-backend-list', ssh_client=con_ssh, fail_ok=fail_ok))
    state = None
    if table_:
        table_ = table_parser.filter_table(table_, backend=backend)
        state =  table_parser.get_column(table_, 'state')[0]
    return state


def get_storage_backend_task_value(backend, con_ssh=None, fail_ok=False):
    table_ = table_parser.table(cli.system('storage-backend-list', ssh_client=con_ssh, fail_ok=fail_ok))
    task = None
    if table_:
        table_ = table_parser.filter_table(table_, backend=backend)
        task =  table_parser.get_column(table_, 'task')[0]
    return task


def add_storage_backend(backend='ceph', ceph_mon_gib='20', ceph_mon_dev=None, ceph_mon_dev_controller_0_uuid=None,
                        ceph_mon_dev_controller_1_uuid=None, con_ssh=None, fail_ok=False):
    """

    Args:
        backend (str): The backend to add. Only ceph is supported
        ceph_mon_gib(int/str): The ceph-mon-lv size in GiB. The default is 20GiB
        ceph_mon_dev (str): The disk device that the ceph-mon will be created on. This applies to both controllers. In
            case of separate device names on controllers use the options  below to specify device name for each
            controller
        ceph_mon_dev_controller_0_uuid (str): The uuid of controller-0 disk device that the ceph-mon will be created on
        ceph_mon_dev_controller_1_uuid (str): The uuid of controller-1 disk device that the ceph-mon will be created on
        con_ssh:
        fail_ok:

    Returns:

    """

    if backend is not 'ceph':
        rc = 1
        msg = "Invalid backend {} specified. Valid choices are {}".format(backend, ['ceph'])
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.CLIRejected(msg)
    if isinstance(ceph_mon_gib, int):
        ceph_mon_gib = str(ceph_mon_gib)

    cmd = 'system storage-backend-add --ceph-mon-gib {}'.format(ceph_mon_gib)
    if ceph_mon_dev:
        cmd += ' --ceph-mon-dev {}'.format(ceph_mon_dev if '/dev' in ceph_mon_dev else '/dev/' + ceph_mon_dev.strip())
    if ceph_mon_dev_controller_0_uuid:
        cmd += ' --ceph_mon_dev_controller_0_uuid {}'.format(ceph_mon_dev_controller_0_uuid)
    if ceph_mon_dev_controller_1_uuid:
        cmd += ' --ceph_mon_dev_controller_1_uuid {}'.format(ceph_mon_dev_controller_1_uuid)

    cmd += " {}".format(backend)
    controler_ssh = ControllerClient.get_active_controller()
    controler_ssh.send(cmd)
    index = controler_ssh.expect([controler_ssh.prompt, '\[yes/N\]'])
    if index == 1:
        controler_ssh.send('yes')
        controler_ssh.expect()

    rc, output = controler_ssh.process_cmd_result(cmd)
    if rc != 0:
        if fail_ok:
            return rc, output
        raise exceptions.CLIRejected("Fail Cli command cmd: {}".format(cmd))
    else:
        output = table_parser.table(output)
        return rc, output


def get_controllerfs_value(fs_name, rtn_val='Size in GiB', con_ssh=None, auth_info=Tenant.ADMIN, **filters):
    table_ = table_parser.table(cli.system('controllerfs-list --nowrap', ssh_client=con_ssh, auth_info=auth_info))

    filters['FS Name'] = fs_name
    vals = table_parser.get_values(table_, rtn_val, **filters)
    if not vals:
        LOG.warning('No value found via controllerfs-list with: {}'.format(filters))
        return None

    val = vals[0]
    if rtn_val.lower() == 'size in gib':
        val = int(val)

    return val


def get_fs_mount_path(ssh_client, fs):
    mount_cmd = 'mount | grep --color=never {}'.format(fs)
    exit_code, output = ssh_client.exec_sudo_cmd(mount_cmd, fail_ok=True)

    mounted_on = fs_type = None
    msg = "Filesystem {} is not mounted".format(fs)
    is_mounted = exit_code == 0
    if is_mounted:
        # Get the first mount point
        mounted_on, fs_type = re.findall('{} on ([^ ]*) type ([^ ]*) '.format(fs), output)[0]
        msg = "Filesystem {} is mounted on {}".format(fs, mounted_on)

    LOG.info(msg)
    return mounted_on, fs_type


def is_fs_auto_mounted(ssh_client, fs):
    auto_cmd = 'cat /etc/fstab | grep --color=never {}'.format(fs)
    exit_code, output = ssh_client.exec_sudo_cmd(auto_cmd, fail_ok=True)

    is_auto_mounted = exit_code == 0
    LOG.info("Filesystem {} is {}auto mounted".format(fs, '' if is_auto_mounted else 'not '))
    return is_auto_mounted


def mount_partition(ssh_client, disk, partition=None, fs_type=None):
    if not partition:
        partition = '/dev/{}'.format(disk)

    disk_id = ssh_client.exec_sudo_cmd('blkid | grep --color=never "{}:"'.format(partition))[1]
    if disk_id:
        mount_on, fs_type_ = get_fs_mount_path(ssh_client=ssh_client, fs=partition)
        if mount_on:
            return mount_on, fs_type_

        fs_type = re.findall('TYPE="([^ ]*)"', disk_id)[0]
        if 'swap' == fs_type:
            fs_type = 'swap'
            turn_on_swap(ssh_client=ssh_client, disk=disk, partition=partition)
            mount_on = 'none'
    else:
        mount_on = None
        if not fs_type:
            fs_type = 'ext4'

        LOG.info("mkfs for {}".format(partition))

        cmd = "mkfs -t {} {}".format(fs_type, partition)
        ssh_client.exec_sudo_cmd(cmd, fail_ok=False)

    if not mount_on:
        mount_on = '/mnt/{}'.format(disk)
        LOG.info("mount {} to {}".format(partition, mount_on))
        ssh_client.exec_sudo_cmd('mkdir -p {}; mount {} {}'.format(mount_on, partition, mount_on), fail_ok=False)
        LOG.info("{} successfully mounted to {}".format(partition, mount_on))
        mount_on_, fs_type_ = get_fs_mount_path(ssh_client=ssh_client, fs=partition)
        assert mount_on == mount_on_ and fs_type == fs_type_

    return mount_on, fs_type


def turn_on_swap(ssh_client, disk, partition=None):
    if not partition:
        partition = '/dev/{}'.format(disk)
    swap_info = ssh_client.exec_sudo_cmd('blkid | grep --color=never "{}:"'.format(partition), fail_ok=False)[1]
    swap_uuid = re.findall('UUID="(.*)" TYPE="swap"', swap_info)[0]
    LOG.info('swapon for {}'.format(partition))
    proc_swap = ssh_client.exec_sudo_cmd('cat /proc/swaps | grep --color=never "{} "'.format(partition))[1]
    if not proc_swap:
        ssh_client.exec_sudo_cmd('swapon {}'.format(partition))
        proc_swap = ssh_client.exec_sudo_cmd('cat /proc/swaps | grep --color=never "{} "'.format(partition))[1]
        assert proc_swap, "swap partition is not shown in /proc/swaps after swapon"

    return swap_uuid


def auto_mount_fs(ssh_client, fs, mount_on=None, fs_type=None, check_first=True):
    if check_first:
        if is_fs_auto_mounted(ssh_client=ssh_client, fs=fs):
            return

    if fs_type == 'swap' and not mount_on:
        raise ValueError("swap uuid required via mount_on")

    if not mount_on:
        mount_on = '/mnt/{}'.format(fs.rsplit('/', maxsplit=1)[-1])

    if not fs_type:
        fs_type = 'ext4'
    cmd = 'echo "{} {} {}  defaults 0 0" >> /etc/fstab'.format(fs, mount_on, fs_type)
    ssh_client.exec_sudo_cmd(cmd, fail_ok=False)
    ssh_client.exec_sudo_cmd('cat /etc/fstab', get_exit_code=False)


def get_storage_usage(service='cinder', rtn_val='free capacity (GiB)', con_ssh=None, auth_info=Tenant.ADMIN):
    table_ = table_parser.table(cli.system('storage-usage-list --nowrap', ssh_client=con_ssh, auth_info=auth_info))
    val = table_parser.get_values(table_, rtn_val, service=service)[0]
    return float(val)
