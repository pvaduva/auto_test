import time
from pytest import fixture, mark, skip

from keywords import system_helper, host_helper
from consts.cgcs import PartitionStatus
from utils import cli, table_parser
from utils.tis_log import LOG


CP_TIMEOUT = 120
DP_TIMEOUT = 120
MP_TIMEOUT = 120


def get_partitions(hosts, state):
    """
    Return partitions based on their state.

    Arguments:
    * hosts(list) - list of host names
    * state(str) - partition state, i.e. Creating, Ready, In-use, Deleting,
    * Error, Modifying

    Return:
    * dict of hostnames mapped to partitions
    """

    partitions = {}
    for host in hosts:
        table_ = table_parser.table(cli.system('host-disk-partition-list {}'.format(host)))

        uuid = table_parser.get_values(table_, "uuid", **{"status": state})
        if not uuid:
            LOG.info("Host {} has no existing partitions in {} state".format(host, state))
        else:
            LOG.info("Host {} has partitions {} in {} state".format(host, uuid, state))
        partitions[host] = uuid

    return partitions


def delete_partition(host, uuid, fail_ok=False, timeout=DP_TIMEOUT):
    """
    Delete a partition from a specific host.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * uuid(str) - uuid of partition
    * timeout(int) - how long to wait for partition deletion (sec)

    Returns:
    * rc, out - return code and output of the host-disk-partition-delete
    """

    rc, out = cli.system('host-disk-partition-delete {} {}'.format(host, uuid), rtn_list=True, fail_ok=fail_ok)
    if rc > 0:
        return 1, out

    wait_for_partition_status(host=host, uuid=uuid, timeout=timeout, final_status=None,
                              interim_status=PartitionStatus.DELETING)
    return 0, "Partition successfully deleted"


def create_partition(host, device_node, size_gib, fail_ok=False, wait=True, timeout=CP_TIMEOUT):
    """
    Create a partition on host.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * device_node(str) - device, e.g. /dev/sdh
    * size_gib(str) - size of partition in gib
    * wait(bool) - if True, wait for partition creation.  False, return
    * immediately.
    * timeout(int) - how long to wait for partition creation (sec)

    Returns:
    * rc, out - return code and output of the host-disk-partition-command
    """
    args = '{} {} {}'.format(host, device_node, size_gib)
    rc, out = cli.system('host-disk-partition-add', args, rtn_list=True, fail_ok=fail_ok)
    if rc > 0 or not wait:
        return rc, out

    uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
    wait_for_partition_status(host=host, uuid=uuid, timeout=timeout)
    return 0, uuid


def modify_partition(host, uuid, size_gib, fail_ok=False, timeout=MP_TIMEOUT, final_status=PartitionStatus.READY):
    """
    This test modifies the size of a partition.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * uuid(str) - uuid of the partition
    * size_gib(str) - new partition size in gib
    * timeout(int) - how long to wait for partition creation (sec)

    Returns:
    * rc, out - return code and output of the host-disk-partition-command
    """

    args = '-s {} {} {}'.format(size_gib, host, uuid)
    rc, out = cli.system('host-disk-partition-modify', args, rtn_list=True, fail_ok=fail_ok)
    if rc > 0:
        return 1, out

    uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
    wait_for_partition_status(host=host, uuid=uuid, timeout=timeout, interim_status=PartitionStatus.MODIFYING, final_status=final_status)
    return 0, "Partition successfully modified"


def get_partition_info(host, uuid, param=None):
    """
    Return requested information about a partition on a given host.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * uuid(str) - uuid of partition
    * param(str) - the parameter wanted, e.g. size_gib

    Returns:
    * param_value(str) - the value of the desired parameter
    """

    param_value = None
    args = "{} {}".format(host, uuid)
    rc, out = cli.system('host-disk-partition-show', args, fail_ok=True, rtn_list=True)

    if rc == 0:
        convert_to_gib = False
        if param == 'size_gib':
            param = 'size_mib'
            convert_to_gib = True

        table_ = table_parser.table(out)
        param_value = table_parser.get_value_two_col_table(table_, param)
        if '_mib' in param:
            param_value = float(param_value)

        if convert_to_gib:
            param_value = float(param_value) / 1024

    return param_value


def wait_for_partition_status(host, uuid, final_status=PartitionStatus.READY, interim_status=PartitionStatus.CREATING, timeout=120,
                              fail_ok=False):
    final_status = None if not final_status else final_status
    valid_status = [final_status]

    if isinstance(interim_status, str):
        interim_status = (interim_status,)
    for status_ in interim_status:
        valid_status.append(status_)

    end_time = time.time() + timeout
    prev_status = ''
    while time.time() < end_time:
        status = get_partition_info(host, uuid, "status")
        assert status in valid_status, "Partition has unexpected state {}".format(status)

        if status == final_status:
            LOG.info("Partition {} on host {} has reached state: {}".format(uuid, host, status))
            return True
        elif status != prev_status:
            prev_status = status
            LOG.info("Partition {} on host {} is in {} state".format(uuid, host, status))

        time.sleep(5)

    msg = "Partition {} on host {} not in {} state within {} seconds".format(uuid, host, final_status, timeout)
    if fail_ok:
        LOG.warning(msg)
        return False
    assert 0, msg


def get_disk_info(host, device_node, param=None):
    """
    This returns information about a disk based on the parameter the user
    specifies.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * device_node(str) - name of device, e.g. /dev/sda
    * param(str) - desired parameter, e.g. available_gib

    Returns:
    * param_value - value of parameter requested
    """
    param_value = None
    args = "{} {}".format(host, device_node)
    rc, out = cli.system('host-disk-show', args, fail_ok=True, rtn_list=True)

    if rc == 0:
        table_ = table_parser.table(out)
        param_value = table_parser.get_value_two_col_table(table_, param)

    return param_value


def get_disks(host):
    """
    This returns disks on a host.

    Arguments:
    * host(str) - hostname, e.g. controller-0

    Returns:
    * disks(list) - list of uuids
    """

    table_ = table_parser.table(cli.system('host-disk-list {} --nowrap'.format(host)))
    disk_uuids = table_parser.get_values(table_, "uuid")
    LOG.debug("{} has {} disks".format(host, len(disk_uuids)))

    return disk_uuids


def get_disks_with_free_space(host, disk_list):
    """
    Given a list of disks, return the ones with free space.

    Arguments:
    * host(str) - hostname, e.g. ocntroller-0
    * disks(list) - list of disks

    Returns:
    * disks_free(list) - list of disks that have usable space.
    """

    free_disks = {}
    for disk in disk_list:
        LOG.info("Querying disk {} on host {}".format(disk, host))
        table_ = table_parser.table(cli.system('host-disk-show {} {}'.format(host, disk)))
        available_space = table_parser.get_value_two_col_table(table_, "available_gib")
        available_space = float(available_space)
        LOG.info("{} has disk {} with {} gib available".format(host, disk, available_space))
        if available_space <= 0:
            LOG.info("Removing disk {} from host {} due to insufficient space".format(disk, host))
        else:
            free_disks[disk] = available_space

    return free_disks


def get_rootfs(hosts):
    """
    This returns the rootfs disks of each node.

    Arguments:
    * hosts(list) - e.g. controller-0, controller-1, etc.

    Returns:
    * Dict of host mapped to rootfs disk
    """

    rootfs_uuid = {}
    for host in hosts:
        table_ = table_parser.table(cli.system('host-show {}'.format(host)))
        rootfs = table_parser.get_value_two_col_table(table_, "rootfs_device")
        LOG.debug("{} is using rootfs disk: {}".format(host, rootfs))
        table_ = table_parser.table(cli.system('host-disk-list {} --nowrap'.format(host)))
        if "/dev/disk" in rootfs:
            uuid = table_parser.get_values(table_, "uuid", **{"device_path": rootfs})
        else:
            rootfs = "/dev/" + rootfs
            uuid = table_parser.get_values(table_, "uuid", **{"device_node": rootfs})
        LOG.debug("{} rootfs disk has uuid {}".format(host, uuid))
        rootfs_uuid[host] = uuid

    LOG.info("Root disk UUIDS: {}".format(rootfs_uuid))

    return rootfs_uuid



