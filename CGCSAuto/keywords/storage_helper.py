"""
This module provides helper functions for storage based testing, with a focus
on CEPH-related helper functions.
"""

import re
import time

from consts.auth import Tenant
from consts.proj_vars import ProjVar
from consts.cgcs import EventLogID, BackendState, BackendTask, MULTI_REGION_MAP

from keywords import system_helper, host_helper, keystone_helper

from utils import table_parser, cli, exceptions
from utils.clients.ssh import ControllerClient, get_cli_client
from utils.tis_log import LOG


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
    health_err = "HEALTH_ERR"
    cmd = 'ceph -s'

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    rtn_code, out = con_ssh.exec_cmd(cmd)

    if health_ok in out:
        msg = 'CEPH cluster is healthy'
        LOG.info(msg)
        return True, msg
    elif health_warn in out:
        msg = 'CEPH cluster is in health warn state'
        LOG.info(msg)
        return False, msg
    elif health_err in out:
        msg = 'CEPH cluster is in health error state'
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
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

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
    storage_hosts = system_helper.get_storage_nodes(con_ssh=con_ssh)
    for host in storage_hosts:
        table_ = table_parser.table(cli.system('host-stor-list', host, ssh_client=con_ssh))
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
        host(str|None): the host to ssh into
    Returns:
        (list) List of OSDs on the host.  Empty list if none.
    """

    def _get_osds_per_host(host_, osd_list_, con_ssh_=None):
        """
        Return the OSDs on a system.

        Args:
            host - the host to query

        Returns:
            Nothing.  Update osd_list by side-effect.
        """

        table_ = table_parser.table(cli.system('host-stor-list', host_, ssh_client=con_ssh_))
        osd_list_ = osd_list_ + table_parser.get_values(table_, 'osdid', function='osd')

        return osd_list_

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
        con_ssh

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
            cmd_ = 'wget {} --no-check-certificate -P {}'.format(url, img_dest)
            rtn_code_, out_ = con_ssh.exec_cmd(cmd_, expect_timeout=7200)
            assert not rtn_code, out_

    centos_image_location = \
        ['http://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud.qcow2',
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


def find_images(con_ssh=None, image_type='qcow2', image_name=None, location=None):
    """
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
    """

    image_names = []
    if not location:
        location = '{}/images'.format(ProjVar.get_var('USER_FILE_DIR'))
    if not con_ssh:
        con_ssh = get_cli_client()

    cmd = 'ls {}'.format(location)
    rtn_code, out = con_ssh.exec_cmd(cmd)
    image_list = out.split()
    LOG.info('Found the following files: {}'.format(image_list))
    if image_type == 'all' and not image_name:
        return image_list, location

    # Return a list of image names where the image type matches what the user
    # is looking for, e.g. qcow2
    for image in image_list:
        if image_name and image_name not in image:
            continue
        image_path = location + "/" + image
        cmd = 'qemu-img info {}'.format(image_path)
        rtn_code, out = con_ssh.exec_cmd(cmd)
        if image_type in out:
            image_names.append(image)

    LOG.info('{} images available: {}'.format(image_type, image_names))
    return image_names, location


def find_image_size(con_ssh, image_name='cgcs-guest.img', location='~/images'):
    """
    This function uses qemu-img info to determine what size of flavor to use.
    Args:
        con_ssh:
        image_name (str): e.g. 'cgcs-guest.img'
        location (str):  where to find images, e.g. '~/images'

    Returns:
        image_size(int): e.g. 8
    """

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


def modify_storage_backend(backend, cinder=None, glance=None, ephemeral=None, object_gib=None, object_gateway=None,
                           services=None, lock_unlock=False, fail_ok=False, con_ssh=None):
    """
    Modify ceph storage backend pool allocation

    Args:
        backend (str): storage backend to modify (e.g. ceph)
        cinder:
        glance:
        ephemeral:
        object_gib:
        object_gateway (bool|None)
        services (str|list|tuple):
        lock_unlock (bool): whether to wait for config out-of-date alarms against controllers and lock/unlock them
        fail_ok:
        con_ssh:

    Returns:
        0, dict of new allocation
        1, cli err message

    """
    if 'ceph' in backend:
        backend = 'ceph-store'
    elif 'lvm' in backend:
        backend = 'lvm-store'
    elif 'file' in backend:
        backend = 'file-store'

    args = ''
    if services:
        if isinstance(services, (list, tuple)):
            services = ','.join(services)
        args = '-s {} '.format(services)
    args += backend

    get_storage_backend_info(backend)

    if cinder:
        args += ' cinder_pool_gib={}'.format(cinder)

    if 'ceph' in backend:
        if glance:
            args += ' glance_pool_gib={}'.format(glance)
        if ephemeral:
            args += ' ephemeral_pool_gib={}'.format(ephemeral)
        if object_gateway is not None:
            args += ' object_gateway={}'.format(object_gateway)
        if object_gib:
            args += ' object_pool_gib={}'.format(object_gib)

    code, out = cli.system('storage-backend-modify', args, con_ssh, fail_ok=fail_ok, rtn_list=True)
    if code > 0:
        return 1, out

    if lock_unlock:
        from testfixtures.recover_hosts import HostsToRecover
        LOG.info("Lock unlock controllers and ensure config out-of-date alarms clear")
        system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, timeout=30, fail_ok=False,
                                     entity_id='controller-')

        active_controller, standby_controller = system_helper.get_active_standby_controllers(con_ssh=con_ssh)
        for controller in [standby_controller, active_controller]:
            if not controller:
                continue
            HostsToRecover.add(controller)
            host_helper.lock_host(controller, swact=True, con_ssh=con_ssh)
            wait_for_storage_backend_vals(backend=backend,
                                          **{'task': BackendTask.RECONFIG_CONTROLLER,   # TODO is this right?
                                             'state': BackendState.CONFIGURING})

            host_helper.unlock_host(controller, con_ssh=con_ssh)

        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, fail_ok=False)

    # TODO return new values of storage allocation and check they are the right values
    updated_backend_info = get_storage_backend_info(backend)
    return 0, updated_backend_info


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


def _get_storage_backend_show_table(backend, con_ssh=None, auth_info=Tenant.get('admin')):
    # valid_backends = ['ceph-store', 'lvm-store', 'file-store', 'ceph-external']
    if 'external' in backend:
        backend = 'ceph-external'
    elif 'ceph' in backend:
        backend = 'ceph-store'
    elif 'lvm' in backend:
        backend = 'lvm-store'
    elif 'file' in backend:
        backend = 'file-store'

    table_ = table_parser.table(cli.system('storage-backend-show', backend, ssh_client=con_ssh, auth_info=auth_info),
                                combine_multiline_entry=True)
    return table_


def get_storage_backend_info(backend, keys=None, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get storage backend pool allocation info

    Args:
        backend (str): storage backend to get info (e.g. ceph)
        keys (list|str): keys to return, e.g., ['name', 'backend', 'task']
        con_ssh:
        auth_info

    Returns: dict  {'cinder_pool_gib': 202, 'glance_pool_gib': 20, 'ephemeral_pool_gib': 0,
                    'object_pool_gib': 0, 'ceph_total_space_gib': 222,  'object_gateway': False}

    """
    table_ = _get_storage_backend_show_table(backend=backend, con_ssh=con_ssh, auth_info=auth_info)

    values = table_['values']
    backend_info = {}
    for line in values:
        field = line[0]
        value = line[1]
        if field in ('task', 'capabilities', 'object_gateway') or field.endswith('_gib'):
            try:
                value = eval(value)
            except:
                pass
        backend_info[field] = value

    if keys:
        if isinstance(keys, str):
            keys = [keys]
        backend_info = {key_: backend_info[key_] for key_ in keys}

    return backend_info


def get_storage_backend_show_vals(backend, fields, con_ssh=None, auth_info=Tenant.get('admin')):
    table_ = _get_storage_backend_show_table(backend=backend, con_ssh=con_ssh, auth_info=auth_info)
    vals = []
    if isinstance(fields, str):
        fields = (fields, )

    for field in fields:
        val = table_parser.get_value_two_col_table(table_, field)
        if field in ('task', 'capabilities', 'object_gateway') or field.endswith('_gib'):
            try:
                val = eval(val)
            except:
                pass
        vals.append(val)
    return vals


def wait_for_storage_backend_vals(backend, timeout=300, fail_ok=False, con_ssh=None, **expt_values):
    if not expt_values:
        raise ValueError("At least one key/value pair has to be provided via expt_values")

    LOG.info("Wait for storage backend {} to reach: {}".format(backend, expt_values))
    end_time = time.time() + timeout
    dict_to_check = expt_values.copy()
    stor_backend_info = None
    while time.time() < end_time:
        stor_backend_info = get_storage_backend_info(backend=backend, keys=list(dict_to_check.keys()), con_ssh=con_ssh)
        dict_to_iter = dict_to_check.copy()
        for key, expt_val in dict_to_iter.items():
            actual_val = stor_backend_info[key]
            if str(expt_val) == str(actual_val):
                dict_to_check.pop(key)

        if not dict_to_check:
            return True, dict_to_check

    if fail_ok:
        return False, stor_backend_info
    raise exceptions.StorageError("Storage backend show field(s) did not reach expected value(s). "
                                  "Expected: {}; Actual: {}".format(dict_to_check, stor_backend_info))


def get_storage_backends(rtn_val='backend', con_ssh=None, **filters):
    backends = []
    table_ = _get_storage_backend_list_table(con_ssh=con_ssh)
    if table_:
        if filters:
            table_ = table_parser.filter_table(table_, **filters)
        backends = table_parser.get_column(table_, rtn_val)
    return backends


def get_storage_backend_state(backend, con_ssh=None):
    return get_storage_backend_list_vals(backend=backend, headers=('state',), con_ssh=con_ssh)[0]


def get_storage_backend_task(backend, con_ssh=None):
    return get_storage_backend_list_vals(backend=backend, headers=('task',), con_ssh=con_ssh)[0]


def _get_storage_backend_list_table(con_ssh=None):
    return table_parser.table(cli.system('storage-backend-list', ssh_client=con_ssh), combine_multiline_entry=True)


def get_storage_backend_list_vals(backend, headers=('state', 'task'), con_ssh=None, **filters):
    table_ = _get_storage_backend_list_table(con_ssh=con_ssh)
    vals = []
    if table_:
        table_ = table_parser.filter_table(table_, backend=backend, **filters)
        if isinstance(headers, str):
            headers = (headers, )
        for header in headers:
            val = table_parser.get_values(table_, header)[0]
            if header in ('task', 'capabilities'):
                # convert to dictionary or None type. e.g.,  {u'min_replication': u'1', u'replication': u'2'}
                try:
                    val = eval(val)
                except:
                    pass
            vals.append(val)

    return vals


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
    controler_ssh = con_ssh if con_ssh else ControllerClient.get_active_controller()
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


def get_controllerfs_value(fs_name, rtn_val='Size in GiB', con_ssh=None, auth_info=Tenant.get('admin'), **filters):
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


def get_storage_usage(service='cinder', backend_type=None, backend_name=None, rtn_val='free capacity (GiB)',
                      con_ssh=None, auth_info=Tenant.get('admin')):
    auth_info_tmp = dict(auth_info)
    region = ProjVar.get_var('REGION')
    if region != 'RegionOne' and region in MULTI_REGION_MAP:
        if service != 'cinder':
            auth_info_tmp['region'] = 'RegionOne'

    kwargs = {}
    if backend_type:
        kwargs['backend type'] = backend_type
    if backend_name:
        kwargs['backend name'] = backend_name

    table_ = table_parser.table(cli.system('storage-usage-list --nowrap', ssh_client=con_ssh, auth_info=auth_info_tmp))
    val = table_parser.get_values(table_, rtn_val, service=service, **kwargs)[0]
    return float(val)


def modify_swift(enable=True, check_first=True, fail_ok=False, apply=True, con_ssh=None):
    """
    Enable/disable swift service
    Args:
        enable:
        check_first:
        fail_ok:
        apply:
        con_ssh

    Returns (tuple):
        (-1, "swift service parameter is already xxx")      only apply when check_first=True
        (0, <success_msg>)
        (1, <std_err>)      system service-parameter-modify cli got rejected.

    """
    if enable:
        expt_val = 'true'
        extra_str = 'enable'
    else:
        expt_val = 'false'
        extra_str = 'disable'

    if check_first:
        swift_endpoints = keystone_helper.get_endpoints(service_name='swift', con_ssh=con_ssh, cli_filter=False)
        if enable is bool(swift_endpoints):
            msg = "swift service parameter is already {}d. Do nothing.".format(extra_str)
            LOG.info(msg)
            return -1, msg

    LOG.info("Modify system service parameter to {} Swift".format(extra_str))
    code, msg = system_helper.modify_service_parameter(service='swift', section='config', name='service_enabled',
                                                       value=expt_val, apply=apply, check_first=False,
                                                       fail_ok=fail_ok, con_ssh=con_ssh)

    if apply and code == 0:
        LOG.info("Check Swift endpoints after service {}d".format(extra_str))
        swift_endpoints = keystone_helper.get_endpoints(service_name='swift', con_ssh=con_ssh, cli_filter=False)
        if enable is not bool(swift_endpoints):
            raise exceptions.SwiftError("Swift endpoints did not {} after modify".format(extra_str))
        msg = 'Swift is {}d successfully'.format(extra_str)

    return code, msg


def get_qemu_image_info(image_filename, ssh_client, fail_ok=False):
    """
    Provides information about the disk image filename, like file format, virtual size and disk size
    Args:
        image_filename (str); the disk image file name
        ssh_client:
        fail_ok:

    Returns:
        0, dict { image: <image name>, format: <format>, virtual size: <size>, disk size: <size}
        1, error msg

    """
    img_info = {}
    cmd = 'qemu-img info {}'.format(image_filename)
    rc, output = ssh_client.exec_cmd(cmd, fail_ok=True)
    if rc == 0:
        lines = output.split('\n')
        for line in lines:
            key = line.split(':')[0].strip()
            value = line.split(':')[1].strip()
            img_info[key] = value

        return 0, img_info
    else:
        msg = "qemu-img info failed: {}".format(output)
        LOG.warning(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.CommonError(msg)


def convert_image_format(src_image_filename, dest_image_filename, dest_format, ssh_client, source_format=None,
                         fail_ok=False):
    """
    Converts the src_image_filename to  dest_image_filename using format dest_format
    Args:
       src_image_filename (str):  the source disk image filename to be converted
       dest_image_filename (str): the destination disk image filename
       dest_format (str): image format to convert to. Valid formats are: qcow2, qed, raw, vdi, vpc, vmdk
       source_format(str): optional - source image file format
       ssh_client:
       fail_ok:

    Returns:

    """

    args_ = ''
    if source_format:
        args_ = ' -f {}'.format(source_format)

    cmd = 'qemu-img convert {} {} {}'.format(args_, src_image_filename, dest_image_filename)
    rc, output = ssh_client.exec_cmd(cmd, fail_ok=True)
    if rc == 0:
        return 0, "Disk image {} converted to {} format successfully".format(dest_image_filename, dest_format)
    else:
        msg = "qemu-img convert failed: {}".format(output)
        LOG.warning(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.CommonError(msg)
