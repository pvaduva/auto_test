"""
These tests are designed to test the host partition functionality that was
introduced in Release 5.  The user can create partitions on computes and
controllers only using available free space on the disks.  These partitions can
then be assigned to a PV such as nova-local.

The states supported by partitions are:
- Creating
- Deleting
- Modifying
- In-use
- Error
- Ready

The partition commands are:
- system host-disk-partition-list
- system host-disk-partition-add
- system host-disk-partition-show
- system host-disk-partition-delete
- system host-disk-partition-modify

Partition changes are done in service.
"""


import time

from keywords import system_helper
from utils import cli, table_parser
from utils.tis_log import LOG
from pytest import fixture, mark, skip

CP_TIMEOUT = 120
DP_TIMEOUT = 120
MP_TIMEOUT = 120

global partitions_to_restore
partitions_to_restore = {}


def get_partitions(hosts, state):
    """
    Return partitions based on their state.

    Arguments:
    * hosts(list) - list of host names
    * state(str) - partition state, i.e. Creating, Ready, In-use, Deleting, Error

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


def delete_partition(host, uuid, timeout=DP_TIMEOUT):
    """
    Delete a partition from a specific host.

    Arguments:
    * host - hostname, e.g. controller-0
    * uuid - uuid of partition
    * timeout(int) - how long to wait for partition deletion (sec)

    Returns:
    * rc, out - return code and output of the host-disk-partition-delete
    """

    rc, out = cli.system('host-disk-partition-delete {} {}'.format(host, uuid), rtn_list=True)
    end_time = time.time() + timeout
    while time.time() < end_time:
        status = get_partition_info(host, uuid, "status")
        LOG.info("Partition {} on host {} has status {}".format(uuid, host, status))
        assert status == "Deleting" or not status, "Partition has unexpected state {}".format(status)
        if not status:
            return rc, out
    assert not status, "Partition was not deleted"

    return rc, out


def create_partition(host, device_node, size_mib, fail_ok=False, timeout=CP_TIMEOUT):
    """
    Create a partition on host.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * device_node(str) - device, e.g. /dev/sdh
    * size_mib(str) - size of partition in mib
    * timeout(int) - how long to wait for partition creation (sec)

    Returns:
    * rc, out - return code and output of the host-disk-partition-command
    """

    rc, out = cli.system('host-disk-partition-add -t lvm_phys_vol {} {} {}'.format(host, device_node, size_mib), rtn_list=True, fail_ok=fail_ok)
    if fail_ok:
        return rc, out

    uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")

    end_time = time.time() + timeout
    while time.time() < end_time:
        status = get_partition_info(host, uuid, "status")
        LOG.info("Partition {} on host {} has status {}".format(uuid, host, status))
        assert status == "Creating" or status == "Ready", "Partition has unexpected state {}".format(status)
        if status == "Ready":
            LOG.info("Partition {} on host {} has {} state".format(uuid, host, status))
            return rc, out

    assert not status, "Partition was not created"


def modify_partition(host, uuid, size_mib, fail_ok=False, timeout=MP_TIMEOUT):
    """
    This test modifies the size of a partition.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * uuid(str) - uuid of the partition
    * size_mib(str) - new partition size in mib 
    * timeout(int) - how long to wait for partition creation (sec)

    Returns:
    * rc, out - return code and output of the host-disk-partition-command
    """

    rc, out = cli.system('host-disk-partition-modify -s {} {} {}'.format(size_mib, host, uuid), rtn_list=True, fail_ok=fail_ok)
    if fail_ok:
        return rc, out

    uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")

    end_time = time.time() + timeout
    while time.time() < end_time:
        status = get_partition_info(host, uuid, "status")
        LOG.info("Partition {} on host {} has status {}".format(uuid, host, status))
        assert status == "Modifying" or status == "Ready", "Partition has unexpected state {}".format(status)
        if status == "Ready":
            LOG.info("Partition {} on host {} has {} state".format(uuid, host, status))
            return rc, out

    assert not status, "Partition was not modified"


def get_partition_info(host, uuid, param=None):
    """
    Return requested information about a partition on a given host.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * uuid(str) - uuid of partition
    * param(str) - the parameter wanted, e.g. size_mib

    Returns:
    * param_value(str) - the value of the desired parameter
    """

    param_value = None
    args = "{} {}".format(host, uuid)
    rc, out = cli.system('host-disk-partition-show', args, fail_ok=True, rtn_list=True)

    if rc == 0:
        table_ = table_parser.table(out)
        param_value = table_parser.get_value_two_col_table(table_, param)

    return param_value


def get_disk_info(host, device_node, param=None):
    """
    This returns information about a disk based on the parameter the user
    specifies.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * device_node(str) - name of device, e.g. /dev/sda
    * param(str) - desired parameter, e.g. available_mib

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
        available_space = table_parser.get_value_two_col_table(table_, "available_mib")
        LOG.info("{} has disk {} with {} available".format(host, disk, available_space))
        if int(available_space) <= 0:
            LOG.info("Removing disk {} from host {} due to insufficient space".format(disk, host))
        else:
            free_disks[disk] = available_space

    return free_disks


def _test_partitions():
    """
    NOTE: Need this later for semantic checks implementation.

    This test creates a host partition if there is available space to do so,
    and validates partition states:

    a.  Creating (on Unlock) and Creating - request to create partition has been received
    b.  Ready - the partition has been successfully created
    c.  In-use - the partition is used by a physical volume
    d.  Deleting - a request to delete has been received
    e.  Error - error occurs while creating partition

    Test Steps:
    1.  Query available disk space
    2.  Create partition (Create state to Ready)
    3.  Resize partition to a larger size
    4.  Attempt to decrease partition to a smaller size (negative test)
    5.  Attach partition to physical volume (In-Use)
    6.  Delete partition (Deleting)

    """

    rootfs_uuid = {}
    # Determine which disks are used for rootfs and map device_node and
    # device_path to uuid
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


@fixture()
def restore_partitions_teardown(request):
    def teardown():
        """
        Restore deleted partitions.
        """
        global partitions_to_restore 

        for host in partitions_to_restore: 
            device_node = partitions_to_restore[host][0]
            size_mib = partitions_to_restore[host][1]
            uuid = partitions_to_restore[host][2]
            LOG.info("Restoring deleted partition on host {} with device_node {} and size {}".format(host, device_node, size_mib))
            rc, out = create_partition(host, device_node, size_mib)
            assert rc == 0, "Partition creation failed"

    request.addfinalizer(teardown)


@mark.usefixtures('restore_partitions_teardown')
def test_delete_host_partitions():
    """
    This test deletes host partitions that are in Ready state.  The teardown
    will re-create them.

    Arguments:
    * None

    Assumptions:
    * There are some partitions present in Ready state.  If not, skip the test.

    Test Steps:
    * Query the partitions on each host, and grab those hosts that have one
      partition in Ready state.
    * Delete those partitions

    Teardown:
    * Re-create those partitions

    Enhancement Ideas:
    * Create partitions (if possible) when there are none in Ready state
    * Query hosts for last partition instead of picking hosts with one
      partition.  Note, only the last partition can be modified.

    """

    global partitions_to_restore 
    partitions_to_restore = {}

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    LOG.tc_step("Find out which hosts have partitions in Ready state")
    partitions_ready = get_partitions(hosts, "Ready")

    hosts_partition_mod_ok = []
    for host in hosts:
        # ENHANCEMENT - modify to look for only the last partition
        if len(partitions_ready[host]) == 1:
            hosts_partition_mod_ok.append(host)

    if not hosts_partition_mod_ok:
        # ENHANCEMENT - modify to create partitions if they don't already exist (if possible)
        skip("Need some partitions in Ready state in order to run test")

    for host in hosts_partition_mod_ok:
        uuid = partitions_ready[host]
        size_mib = get_partition_info(host, uuid[0], "size_mib")
        device_node = get_partition_info(host, uuid[0], "device_node")
        LOG.tc_step("Deleting partition {} of size {} from host {} on device node {}".format(uuid[0], size_mib, host, device_node[:-1]))
        partitions_to_restore[host] = []
        delete_partition(host, uuid[0])
        partitions_to_restore[host].append(device_node[:-1])
        partitions_to_restore[host].append(size_mib)
        partitions_to_restore[host].append(uuid[0])


@mark.usefixtures('restore_partitions_teardown')
def test_increase_host_partition_size():
    """
    This test modifies the size of existing partitions that are in Ready state.
    The partition will be deleted after modification, since decreasing the size
    is not supported.  Teardown will re-create the partition with the original
    values.

    Arguments:
    * None

    Assumptions:
    * There are some partitions present in Ready state.  If not, skip the test.

    Test Steps:
    * Query the partitions on each host, and grab those hosts that have one
      partition in Ready state.
    * Delete which of those hosts have space on the disk for resize up
    * Resize those partitions

    Teardown:
    * Delete the partitions and then re-create it with the old size.

    Enhancement Ideas:
    * Create partitions (if possible) when there are none in Ready state
    * Query hosts for last partition instead of picking hosts with one
      partition.  Note, only the last partition can be modified.
    * Check disk space goes to 0 when partition is resized 
    * Check disk space goes back to what it was when partition is re-created at
      original size
    """

    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    LOG.tc_step("Find out which hosts have partitions in Ready state")
    partitions_ready = get_partitions(hosts, "Ready")

    hosts_partition_mod_ok = []
    for host in hosts:
        # ENHANCEMENT - modify to look for only the last partition
        if len(partitions_ready[host]) == 1:
            hosts_partition_mod_ok.append(host)

    if not hosts_partition_mod_ok:
        # ENHANCEMENT - modify to create partitions if they don't already exist (if possible)
        skip("Need some partitions in Ready state in order to run test")

    usable_disks = False
    LOG.tc_step("Find out which partitions on are on a disk with available space")
    for host in hosts_partition_mod_ok:
        uuid = partitions_ready[host]
        device_node = get_partition_info(host, uuid[0], "device_node")
        size_mib = get_partition_info(host, uuid[0], "size_mib")
        disk_available_mib = get_disk_info(host, device_node[:-1], "available_mib")
        if disk_available_mib == "0":
            break
        usable_disks = True
        LOG.tc_step("Modifying partition {} from size {} to size {} from host {} on device node {}".format(uuid[0], size_mib, disk_available_mib, host, device_node[:-1]))
        modify_partition(host, uuid[0], disk_available_mib)
        partitions_to_restore[host] = []
        partitions_to_restore[host].append(device_node[:-1])
        partitions_to_restore[host].append(size_mib)
        partitions_to_restore[host].append(uuid[0])
        LOG.tc_step("Deleting partition {} of size {} from host {} on device node {}".format(uuid[0], size_mib, host, device_node[:-1]))
        delete_partition(host, uuid[0])

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


def test_create_host_partition_on_storage():
    """
    This test attempts to create a host partition on a storage node.  It is
    expected to fail, since host partition creation is only supported on
    controllers and computes.

    Assumptions:
    * We run this on a storage system, otherwise we will skip the test.
    """

    hosts = system_helper.get_storage_nodes()

    if not hosts:
        skip("This test requires storage nodes.")

    LOG.tc_step("Gather the disks available on each host")
    for host in hosts:
        disks = get_disks(host)
        free_disks = get_disks_with_free_space(host, disks)
        if not free_disks:
            skip("There are no disks with available disk space.")
        for uuid in free_disks:
            rc, out = create_partition(host, uuid, free_disks[uuid], fail_ok=True)
            assert rc != 0, "Partition creation was successful"
