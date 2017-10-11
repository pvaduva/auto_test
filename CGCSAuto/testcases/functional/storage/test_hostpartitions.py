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
    * state(str) - partition state, i.e. Creating, Ready, In-use, Deleting, Error, Modifying

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


def get_last_partition(host):
    """
    This function returns the last partition on a host.  This is useful since
    only the last partition can be modified.

    Arguments:
    * host - hostname, e.g. controller-0

    Returns:
    * None if no partitions are found
    * uuid if partition is found
    """

    table_ = table_parser.table(cli.system('host-disk-partition-list {}'.format(host)))
    device_node = table_parser.get_values(table_, "device_node")
    print(device_node)
    #TODO
    

def delete_partition(host, uuid, timeout=DP_TIMEOUT):
    """
    Delete a partition from a specific host.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * uuid(str) - uuid of partition
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


def create_partition(host, device_node, size_mib, fail_ok=False, wait=True, timeout=CP_TIMEOUT):
    """
    Create a partition on host.

    Arguments:
    * host(str) - hostname, e.g. controller-0
    * device_node(str) - device, e.g. /dev/sdh
    * size_mib(str) - size of partition in mib
    * wait(bool) - if True, wait for partition creation.  False, return immediately.
    * timeout(int) - how long to wait for partition creation (sec)

    Returns:
    * rc, out - return code and output of the host-disk-partition-command
    """

    rc, out = cli.system('host-disk-partition-add -t lvm_phys_vol {} {} {}'.format(host, device_node, size_mib), rtn_list=True, fail_ok=fail_ok)
    if fail_ok or not wait:
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


@fixture()
def delete_partitions_teardown(request):
    def teardown():
        """
        Delete created partitions.
        """
        global partitions_to_restore

        for host in partitions_to_restore:
            print(partitions_to_restore[host])
            for i in range(len(partitions_to_restore[host]) - 1, -1, -1):
                uuid = partitions_to_restore[host][i]
                LOG.info("Deleting partition on host {} with uuid {}".format(host, uuid))
                rc, out = delete_partition(host, uuid)
                assert rc == 0, "Partition deletion failed"

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
        if len(partitions_ready[host]) == 1:
            hosts_partition_mod_ok.append(host)

    if not hosts_partition_mod_ok:
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
    * Determine which partitions are on a disk with available space
    * Modify the partition so we consume all available space on the disk
    * Check that the disk available space goes to zero
    * Delete the partition
    * Check that the available space is freed

    Teardown:
    * Delete the partitions and then re-create it with the old size.

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
        if len(partitions_ready[host]) == 1:
            hosts_partition_mod_ok.append(host)

    if not hosts_partition_mod_ok:
        skip("Need some partitions in Ready state in order to run test")

    usable_disks = False
    LOG.tc_step("Find out which partitions on are on a disk with available space")
    for host in hosts_partition_mod_ok:
        uuid = partitions_ready[host]
        device_node = get_partition_info(host, uuid[0], "device_node")
        size_mib = get_partition_info(host, uuid[0], "size_mib")
        disk_available_mib = get_disk_info(host, device_node[:-1], "available_mib")
        if disk_available_mib == "0":
            continue
        usable_disks = True
        total_size = int(size_mib) + int(disk_available_mib)
        LOG.tc_step("Modifying partition {} from size {} to size {} from host {} on device node {}".format(uuid[0], size_mib, str(total_size), host, device_node[:-1]))
        modify_partition(host, uuid[0], str(total_size))
        new_disk_available_mib = get_disk_info(host, device_node[:-1], "available_mib")
        assert new_disk_available_mib == "0", "Expected disk space to be consumed but instead we have {} available".format(new_disk_available_mib)
        partitions_to_restore[host] = []
        partitions_to_restore[host].append(device_node[:-1])
        partitions_to_restore[host].append(size_mib)
        partitions_to_restore[host].append(uuid[0])
        LOG.tc_step("Deleting partition {} of size {} from host {} on device node {}".format(uuid[0], total_size, host, device_node[:-1]))
        delete_partition(host, uuid[0])
        new_disk_available_mib = get_disk_info(host, device_node[:-1], "available_mib")
        assert new_disk_available_mib == str(total_size), "Expected {} in disk space to be freed but instead we have {} available".format(total_size, new_disk_available_mib)

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


@mark.usefixtures('delete_partitions_teardown')
def test_create_multiple_partitions_on_single_host():
    """
    This test attempts to create multiple partitions at once on a single host.
    While the first partition is being created, we will attempt to create a
    second partition.  The creation of the second partition should be rejected
    but the creation of the first partition should be successful.

    Assumptions:
    * There's some free disk space available 

    Test steps:
    * Query the hosts to determine disk space
    * Create a small partition but don't wait for creation
    * Immediately create a second small partition
    * Check that the second partition creation is rejected
    * Check the first partition was successfully created
    * Repeat on all applicable hosts

    Teardown:
    * Delete created partitions

    """

    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = get_disks(host)
        free_disks = get_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        for disk_uuid in free_disks:
            size_mib = int(free_disks[disk_uuid])
            partition_chunks = size_mib / 1024
            if partition_chunks < 2:
                LOG.info("Skip disk {} due to insufficient space".format(disk_uuid))
                continue
            usable_disks = True
            LOG.info("Creating first partition on {}".format(host))
            rc1, out1 = create_partition(host, disk_uuid, "1024", fail_ok=False, wait=False)
            LOG.info("Creating second partition on {}".format(host))
            rc, out = create_partition(host, disk_uuid, "1024", fail_ok=True)
            assert rc != 0, "Partition creation was expected to fail but was instead successful"
            # Check that first disk was created
            uuid = table_parser.get_value_two_col_table(table_parser.table(out1), "uuid")

            partition_created = False
            end_time = time.time() + CP_TIMEOUT 
            while time.time() < end_time:
                status = get_partition_info(host, uuid, "status")
                LOG.info("Partition {} on host {} has status {}".format(uuid, host, status))
                assert status == "Creating" or status == "Ready", "Partition has unexpected state {}".format(status)
                if status == "Ready":
                    LOG.info("Partition {} on host {} has {} state".format(uuid, host, status))
                    partition_created = True
                    break
            assert partition_created, "First partition was not successfully created"
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)
            # Only test one disk on each host
            break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


@mark.usefixtures('delete_partitions_teardown')
def test_create_many_small_host_partitions_on_a_single_host():
    """
    This test attempts to create multiple tiny partitions on a single host.

    Assumptions:
    * There's some free disk space available 

    Test steps:
    * Query the hosts to determine disk space
    * Create small partitions until the disk space is consumed 
    * Repeat on all applicable hosts

    Teardown:
    * Delete created partitions

    """

    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = get_disks(host)
        free_disks = get_disks_with_free_space(host, disks)
        if not free_disks:
            continue
        for disk_uuid in free_disks:
            size_mib = int(free_disks[disk_uuid])
            num_partitions = 30
            if size_mib <= num_partitions:
                LOG.info("Skipping disk {} due to insufficient space".format(disk_uuid))
                continue
            partition_chunks = size_mib / num_partitions
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            partitions_to_restore[host] = []
            for i in range(0, num_partitions):
                rc, out = create_partition(host, disk_uuid, int(partition_chunks))
                uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
                partitions_to_restore[host].append(uuid)
            # Only test one disk on each host
            break
        # Only test one host (otherwise takes too long)
        break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


@mark.usefixtures('delete_partitions_teardown')
def _test_attempt_host_unlock_during_partition_creation():
    """
    DISABLE SINCE SEMANTIC CHECK IS NOT IN TIS CODE YET.

    This test attempts to unlock a host while a partition is being created.  It
    is expected to fail.

    Assumptions:
    * There's some free disk space available 

    Test steps:
    * Query the hosts to determine disk space
    * Create a partition but don't wait for completion
    * Attempt to lock the host that is hosting the partition that is created

    Teardown:
    * Delete created partitions

    """

    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = get_disks(host)
        free_disks = get_disks_with_free_space(host, disks)
        if not free_disks:
            continue
        for uuid in free_disks:
            size_mib = int(free_disks[uuid])
            if size_mib == 0:
                LOG.tc_step("Skip this disk due to insufficient space")
                continue
            rc, out = system_helper.lock_host(host)
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            rc, out = create_partition(host, uuid, size_mib, wait=False)
            uuid = table_parser.get_value_two_col_table(table_parser.table(out1), "uuid")
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)
            rc, out = system_helper.unlock_host(host, fail_ok=True)
            assert rc != 0, "Lock attempt unexpectedly passed"
            # Only test one disk on each host
            break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


def test_create_zero_sized_host_partition():
    """
    This test attempts to create a partition of size zero once on each host.
    This should be rejected.

    Test steps:
    * Create partition of size zero
    * Ensure the provisioning is rejected

    Teardown:
    * None
    """

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    for host in hosts:
        disks = get_disks(host)
        for uuid in disks:
            LOG.tc_step("Attempt to create zero sized partition on uuid {} on host {}".format(uuid, host))
            rc, out = create_partition(host, uuid, "0", fail_ok=True)
            assert rc != 0, "Partition creation was expected to fail but instead succeeded"
            # Let's do this for one disk only on each host
            break


def test_decrease_host_partition_size():
    """
    This test attempts to decrease the size of an existing host partition.  It
    is expected to fail since decreasing the size of a partition is not
    supported.

    Assumptions:
    * Partitions are available in Ready state.

    Test Steps:
    * Query hosts to determine Ready partitions
    * Query the partition to get the partition size
    * Modify the partition to decrease its size

    Teardown:
    * None

    Enhancement Ideas:
    * Create partitions (if possible) when there are none in Ready state
    * Query hosts for last partition instead of picking hosts with one
      partition.  Note, only the last partition can be modified.

    """

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    LOG.tc_step("Find out which hosts have partitions in Ready state")
    partitions_ready = get_partitions(hosts, "Ready")

    hosts_partition_mod_ok = []
    for host in hosts:
        if len(partitions_ready[host]) == 1:
            hosts_partition_mod_ok.append(host)

    if not hosts_partition_mod_ok:
        skip("Need some partitions in Ready state in order to run test")

    for host in hosts_partition_mod_ok:
        uuid = partitions_ready[host]
        device_node = get_partition_info(host, uuid[0], "device_node")
        size_mib = get_partition_info(host, uuid[0], "size_mib")
        total_size = int(size_mib) - 1
        LOG.tc_step("Modifying partition {} from size {} to size {} from host {} on device node {}".format(uuid[0], size_mib, str(total_size), host, device_node[:-1]))
        rc, out = modify_partition(host, uuid[0], str(total_size), fail_ok=True)
        assert rc != 0, "Expected partition modification to fail and instead it succeeded"


def test_increase_host_partition_size_beyond_avail_disk_space():
    """
    This test attempts to increase the size of an existing host partition
    beyond the available space on disk.  It is expected to fail.

    Assumptions:
    * Partitions are available in Ready state.

    Test steps:
    * Query hosts to determine Ready partitions
    * Query the disk the partition is located on to get the available size
    * Modify the partition to consume over than the available disk space

    Teardown:
    * None

    Enhancement Ideas:
    * Create partitions (if possible) when there are none in Ready state
    * Query hosts for last partition instead of picking hosts with one
      partition.  Note, only the last partition can be modified.

    """

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    LOG.tc_step("Find out which hosts have partitions in Ready state")
    partitions_ready = get_partitions(hosts, "Ready")

    hosts_partition_mod_ok = []
    for host in hosts:
        if len(partitions_ready[host]) == 1:
            hosts_partition_mod_ok.append(host)

    if not hosts_partition_mod_ok:
        skip("Need some partitions in Ready state in order to run test")

    for host in hosts_partition_mod_ok:
        uuid = partitions_ready[host]
        device_node = get_partition_info(host, uuid[0], "device_node")
        size_mib = get_partition_info(host, uuid[0], "size_mib")
        disk_available_mib = get_disk_info(host, device_node[:-1], "available_mib")
        total_size = int(size_mib) + int(disk_available_mib) + 1
        LOG.tc_step("Modifying partition {} from size {} to size {} from host {} on device node {}".format(uuid[0], size_mib, str(total_size), host, device_node[:-1]))
        rc, out = modify_partition(host, uuid[0], str(total_size), fail_ok=True)
        assert rc != 0, "Expected partition modification to fail and instead it succeeded"


def test_create_parition_using_valid_uuid_of_another_host():
    """
    This test attempts to create a partition using a vaild uuid that belongs to
    another host.  It is expected to fail.

    Arguments:
    * None

    Test steps:
    * Query the hosts for disk uuids with free space
    * Attempt to create a partition for a different uuid
    
    Teardown:
    * None

    CGTS-7901
    """

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    if len(hosts) == 1:
        skip("This test requires more than one host")

    sut = "controller-0"
    hosts.remove(sut)
    free_disks = []
    LOG.tc_step("Determine which hosts have free disks")
    for host in hosts:
        disks = get_disks(host)
        free_disks = get_disks_with_free_space(host, disks)
        if free_disks:
            donor = host
            break

    if not free_disks:
        skip("Insufficient disk space to to complete test.")

    for uuid in free_disks:
        LOG.info("Creating partition on {} using disk from {}".format(sut, donor))
        rc, out = create_partition(sut, uuid, free_disks[uuid], fail_ok=True)
        assert rc != 0, "Partition creation should be rejected but instead it was successful"
        # Break since we only need to do this once
        break


def _test_modify_previous_partition():
    """
    This test attempts to modify a partition that is not the last.  It is
    expected to fail, since only the very last partition can be modified.

    Arguments:
    * None

    Test steps:
    * Retrieve the partitions on a host
    * Determine which partition is the last
    * Modify the previous partition

    Teardown:
    * None
    """

    node = "compute-4"
    get_last_partition("compute-4")


def test_create_partition_using_non_existant_device_node():
    """
    This test attempts to create a partition using an invalid disk.  It is
    expected to fail.

    Arguments:
    * None

    Steps:
    * Attempt to create a partition on a valid host using an invalid device
      node, e.g. /dev/sdz

    Teardown:
    * None
    """

    # Safely hard-coded since we don't have enough physical slots for this to be
    # possible
    device_node = "/dev/sdz"
    size_mib = "1"

    computes = system_helper.get_hostnames(personality="compute")
    hosts = system_helper.get_controllers() + computes

    for host in hosts:
        LOG.tc_step("Creating partition on host {} with size {} using device node {}".format(host, size_mib, device_node))
        rc, out = create_partition(host, device_node, size_mib, fail_ok=True)
        assert rc != 0, "Partition creation was successful"


def test_create_host_partition_on_storage():
    """
    This test attempts to create a host partition on a storage node.  It is
    expected to fail, since host partition creation is only supported on
    controllers and computes.

    Assumptions:
    * We run this on a storage system, otherwise we will skip the test.

    Test steps:
    * Query storage nodes for available disk space 
    * Attempt to create a partition on a storage node
    * Check it is rejected
    """

    hosts = system_helper.get_storage_nodes()

    if not hosts:
        skip("This test requires storage nodes.")

    LOG.tc_step("Gather the disks available on each host")
    for host in hosts:
        disks = get_disks(host)
        free_disks = get_disks_with_free_space(host, disks)
        if not free_disks:
            continue
        for uuid in free_disks:
            rc, out = create_partition(host, uuid, free_disks[uuid], fail_ok=True)
            assert rc != 0, "Partition creation was successful"
