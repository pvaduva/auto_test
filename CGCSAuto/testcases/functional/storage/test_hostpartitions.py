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

import string

from pytest import fixture, mark, skip

from consts.stx import PartitionStatus, AppStatus
from utils import cli, table_parser
from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from keywords import system_helper, host_helper, storage_helper, container_helper

CP_TIMEOUT = 120
DP_TIMEOUT = 120
MP_TIMEOUT = 120

partitions_to_restore = {}


@fixture()
def restore_partitions_teardown(request):
    def teardown():
        """
        Restore deleted partitions.
        """
        global partitions_to_restore

        for host in partitions_to_restore:
            device_node, size_gib, uuid = partitions_to_restore[host][0:3]
            available_gib = storage_helper.get_host_disk_values(host, device_node, "available_gib")[0]
            total_free = float(available_gib) - int(size_gib)
            LOG.info("Restoring deleted partition on host {} with device_node {} and size {}".format(
                host, device_node, size_gib))
            rc, out = storage_helper.create_host_partition(host, device_node, int(size_gib))
            assert rc == 0, "Partition creation failed"
            gib_after_create = storage_helper.get_host_disk_values(host, device_node, "available_gib")[0]
            assert float(gib_after_create) == total_free, \
                "Expected available_gib to be {} after creation but instead was {}".format(total_free, gib_after_create)

    request.addfinalizer(teardown)


@fixture()
def delete_partitions_teardown(request):
    def teardown():
        """
        Delete created partitions.
        """
        global partitions_to_restore

        for host in partitions_to_restore:
            LOG.info("Partitions to restore for {}: {}".format(host, partitions_to_restore[host]))
            for i in range(len(partitions_to_restore[host]) - 1, -1, -1):
                uuid = partitions_to_restore[host][i]
                device_node, partition_gib = storage_helper.get_host_partition_values(host, uuid,
                                                                                      ("device_node", "size_gib"))
                device_node = device_node.rstrip(string.digits)
                if device_node.startswith("/dev/nvme"):
                    device_node = device_node[:-1]

                available_gib = storage_helper.get_host_disk_values(host, device_node, "available_gib")[0]
                total_free = float(available_gib) + float(partition_gib)
                LOG.info("Deleting partition on host {} with uuid {}".format(host, uuid))
                rc, out = storage_helper.delete_host_partition(host, uuid)
                assert rc == 0, "Partition deletion failed"
                # Wait a few seconds for disk space release
                gib_after_del = storage_helper.get_host_disk_values(host, device_node, "available_gib")[0]
                LOG.info("GIB Before: {}".format(total_free))
                LOG.info("GIB After: {}".format(gib_after_del))
                gib_after_del = float(gib_after_del)
                offset = 1
                assert total_free - offset <= gib_after_del <= total_free + offset, \
                    "Expected available_gib to be {} after deletion but instead was {}".format(total_free,
                                                                                               gib_after_del)

    request.addfinalizer(teardown)


@mark.usefixtures('delete_partitions_teardown')
def test_delete_host_partitions():
    """
    This test creates host partitions and the teardown deletes them.

    Arguments:
    * None

    Test Steps:
    * Create a partition on each host

    Teardown:
    * Re-create those partitions
    """
    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        for disk_uuid in free_disks:
            size_gib = float(free_disks[disk_uuid])
            partition_chunks = int(size_gib)
            if partition_chunks < 2:
                LOG.info("Skip disk {} due to insufficient space".format(disk_uuid))
                continue
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, disk_uuid, "1", fail_ok=False, wait=False)
            assert rc == 0, "Partition creation was expected to succeed but instead failed"
            # Check that first disk was created
            uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, timeout=CP_TIMEOUT)
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)
            # Only test one disk on each host
            break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


@mark.usefixtures('delete_partitions_teardown')
def test_increase_host_partition_size():
    """
    Create a partition and then modify it to consume the entire disk

    Arguments:
    * None


    Test Steps:
    * Create a partition
    * Modify the partition so we consume all available space on the disk
    * Check that the disk available space goes to zero
    * Delete the partition
    * Check that the available space is freed

    Teardown:
    * Delete the partitions

    """
    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        for disk_uuid in free_disks:
            size_gib = float(free_disks[disk_uuid])
            partition_chunks = int(size_gib)
            if partition_chunks < 2:
                LOG.info("Skip disk {} due to insufficient space".format(disk_uuid))
                continue
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, disk_uuid, "1", fail_ok=False, wait=False)
            assert rc == 0, "Partition creation was expected to succeed but instead failed"
            # Check that first disk was created
            uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, timeout=CP_TIMEOUT)
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)

            device_node = storage_helper.get_host_partition_values(host, uuid, "device_node")[0]
            device_node = device_node.rstrip(string.digits)
            if device_node.startswith("/dev/nvme"):
                device_node = device_node[:-1]
            LOG.tc_step("Modifying partition {} from size 1 to size {} from host {} on device node {}".format(
                uuid, int(size_gib) - 2, host, device_node))
            storage_helper.modify_host_partition(host, uuid, str(int(size_gib) - 2))
            new_disk_available_gib = storage_helper.get_host_disk_values(host, device_node, "available_gib")[0]
            assert 0 <= int(float(new_disk_available_gib)) <= 3, \
                "Expected disk space to be consumed but instead we have {} available".format(new_disk_available_gib)
            # Only test one disk on each host
            break

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

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        for disk_uuid in free_disks:
            size_gib = float(free_disks[disk_uuid])
            partition_chunks = int(size_gib)
            if partition_chunks < 2:
                LOG.info("Skip disk {} due to insufficient space".format(disk_uuid))
                continue
            usable_disks = True
            LOG.info("Creating first partition on {}".format(host))
            rc1, out1 = storage_helper.create_host_partition(host, disk_uuid, "1", fail_ok=False, wait=False)
            LOG.info("Creating second partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, disk_uuid, "1", fail_ok=True)
            assert rc != 0, "Partition creation was expected to fail but was instead successful"
            # Check that first disk was created
            uuid = table_parser.get_value_two_col_table(table_parser.table(out1), "uuid")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, timeout=CP_TIMEOUT)
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

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        partitions_to_restore[host] = []
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue
        for disk_uuid in free_disks:
            size_gib = float(free_disks[disk_uuid])
            num_partitions = 2
            if size_gib <= num_partitions:
                LOG.info("Skipping disk {} due to insufficient space".format(disk_uuid))
                continue
            partition_chunks = int(size_gib / num_partitions)
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            # partitions_to_restore[host] = []
            for i in range(0, num_partitions):
                uuid = storage_helper.create_host_partition(host, disk_uuid, partition_chunks)[1]
                partitions_to_restore[host].append(uuid)
            # Only test one disk on each host
            break
        # Only test one host (otherwise takes too long)
        if usable_disks:
            break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


def _test_create_partition_and_associate_with_pv_nova_local():
    """
    This test attempt to create a partition and then associate it with a PV
    (physical volume), resulting in the partition being In-use.  In this case,
    the test associates with nova-local.

    Assumptions:
    * There's some free disk space available

    Test step:
    * Query hosts to determine disk space
    * Create partition
    * Associate it with nova-local PV
    * Checks the partition is in-use state
    * Attempts to delete the partition that is in-use.  It should fail.
    * Attempt to assign the in-use partition to another PV.  It should fail.

    Teardown:
    * None

    DISABLING: Dev says not to test yet.
    """

    global partitions_to_restore
    partitions_to_restore = {}

    if system_helper.is_aio_system():
        hosts = system_helper.get_controllers()
    else:
        hosts = system_helper.get_hosts(personality="compute")

    if len(hosts) == 0:
        skip("No valid nodes to test with")

    usable_disks = False
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue
        for uuid in free_disks:
            size_gib = float(free_disks[uuid])
            if size_gib <= 1:
                LOG.tc_step("Skip this disk due to insufficient space")
                continue
            usable_disks = True
            host_helper.lock_host(host)
            LOG.info("Creating partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, uuid, "1")
            uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)
            LOG.tc_step("Associating partition {} with nova-local".format(uuid))
            # cmd = "host-pv-add -t partition {} nova-local {}".format(host, uuid)
            cmd = "host-pv-add {} nova-local {}".format(host, uuid)
            rc, out = cli.system(cmd)
            assert rc == 0, "Associating partition with PV failed"

            host_helper.unlock_host(host)
            LOG.tc_step("Check that partition is In-use state")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, final_status=PartitionStatus.IN_USE,
                                                          interim_status=PartitionStatus.READY, timeout=CP_TIMEOUT)

            LOG.tc_step("Attempt to delete In-Use partition")
            rc, out = storage_helper.delete_host_partition(host, uuid, fail_ok=True)
            assert rc != 0, "Partition deletion was expected to fail but instead passed"
            LOG.tc_step("Attempt to associate the In-Use partition with another PV")
            # cmd = "host-pv-add -t partition {} cgts-vg {}".format(host, uuid)
            cmd = "host-pv-add {} cgts-vg {}".format(host, uuid)
            rc, out = cli.system(cmd)
            assert rc != 0, "Partition association succeeded but was expected to fail"
            # Only test one disk on each host
            break
        # Do it on one host only
        break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


def _test_create_partition_and_associate_with_pv_cgts_vg():
    """
    This test attempt to create a partition and then associate it with a PV
    (physical volume), resulting in the partition being In-use.

    Assumptions:
    * There's some free disk space available

    Test steps:
    * Query hosts to determine disk space
    * Create partition
    * Associate it with cgts-vg PV
    * Checks the partition is in-use state
    * Attempts to delete the partition that is in-use.  It should fail.
    * Attempt to assign the in-use partition to another PV.  It should fail.

    Teardown:
    * None

    DISABLING: This fails since the partition says 'adding on unlock'.  Should
    it be in-service?  Follow up with dev.
    """

    global partitions_to_restore
    partitions_to_restore = {}

    if not system_helper.is_aio_system():
        skip("This test requires an AIO system.")

    hosts = system_helper.get_controllers()

    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue
        for uuid in free_disks:
            size_gib = float(free_disks[uuid])
            if size_gib <= 1:
                LOG.tc_step("Skip this disk due to insufficient space")
                continue
            LOG.info("Creating partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, uuid, "1")
            uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)
            LOG.tc_step("Associating partition {} with cgts-vg".format(uuid))
            # cmd = "host-pv-add -t partition {} cgts-vg {}".format(host, uuid)
            cmd = "host-pv-add {} cgts-vg {}".format(host, uuid)
            rc, out = cli.system(cmd)
            assert rc == 0, "Associating partition with PV failed"
            LOG.tc_step("Check that partition is In-use state")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, final_status=PartitionStatus.IN_USE,
                                                          interim_status=PartitionStatus.READY, timeout=CP_TIMEOUT)
            LOG.tc_step("Attempt to delete In-Use partition")
            rc, out = storage_helper.delete_host_partition(host, uuid, fail_ok=True)
            assert rc != 0, "Partition deletion was expected to fail but instead passed"
            LOG.tc_step("Attempt to associate the In-Use partition with another PV")
            # cmd = "host-pv-add -t partition {} nova-local {}".format(host, uuid)
            cmd = "host-pv-add {} nova-local {}".format(host, uuid)
            rc, out = cli.system(cmd)
            assert rc != 0, "Partition association succeeded but was expected to fail"
            # Only test one disk on each host
            break
        # Do it on one host only
        break


def test_assign_rootfs_disk_to_pv():
    """
    This test attempts to create a PV with type Disk on the rootfs.  This is
    expected to fail.

    Assumptions:
    * None

    Test Steps:
    * Determine which disk is the rootfs
    * Attempt to create a PV on that disk using a PV type of Disk.

    Teardown:
    * None
    """

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    rootfs = storage_helper.get_hosts_rootfs(hosts)

    for host in rootfs:
        uuid = rootfs[host]
        # cmd = "host-pv-add -t disk {} cgts-vg {}".format(host, uuid[0])
        cmd = "host-pv-add {} cgts-vg {}".format(host, uuid[0])
        rc, out = cli.system(cmd, fail_ok=True)
        assert rc != 0, "Expected PV creation to fail but instead succeeded"


# Add TC unlock during partition deletion - rejected
# Add TC unlock during partition modification - rejected

@mark.usefixtures('delete_partitions_teardown')
def test_attempt_host_unlock_during_partition_creation():
    """
    This test attempts to unlock a host while a partition is being created.  It
    is expected to fail.

    Assumptions:
    * There's some free disk space available

    Test steps:
    * Query the hosts to determine disk space
    * Lock host
    * Create a partition but don't wait for completion
    * Attempt to unlock the host that is hosting the partition that is created

    Teardown:
    * Delete created partitions

    DISABLED since unlock while creating is not blocked.

    """

    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    # Filter out active controller
    active_controller = system_helper.get_active_controller_name()
    print("This is active controller: {}".format(active_controller))
    hosts.remove(active_controller)

    usable_disks = False
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        for uuid in free_disks:
            size_gib = float(free_disks[uuid])
            if size_gib < 2.0:
                LOG.info("Skip this disk due to insufficient space")
                continue

            LOG.tc_step("Lock {} and create a partition for disk {}".format(host, uuid))
            HostsToRecover.add(host)
            host_helper.lock_host(host)
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, uuid, int(size_gib), wait=False)
            uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)

            LOG.tc_step("Attempt to unlock host and ensure it's rejected when partition is "
                        "being created")
            rc_ = host_helper.unlock_host(host, fail_ok=True, check_first=False)[0]
            assert rc_ != 0, "Unlock attempt unexpectedly passed"

            LOG.tc_step("wait for partition to be created")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, timeout=CP_TIMEOUT)

            container_helper.wait_for_apps_status(apps='platform-integ-apps',
                                                  status=AppStatus.APPLIED, check_interval=10)
            # Only test one disk on each host
            break
        # Do it on one host only
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

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        for uuid in disks:
            LOG.tc_step("Attempt to create zero sized partition on uuid {} on host {}".format(uuid, host))
            rc, out = storage_helper.create_host_partition(host, uuid, "0", fail_ok=True)
            assert rc != 0, "Partition creation was expected to fail but instead succeeded"
            # Let's do this for one disk only on each host
            break


@mark.usefixtures('delete_partitions_teardown')
def test_decrease_host_partition_size():
    """
    This test attempts to decrease the size of an existing host partition.  It
    is expected to fail since decreasing the size of a partition is not
    supported.


    Test Steps:
    * Create a partition
    * Modify the partition to decrease its size

    Teardown:
    * Delete created partition

    """
    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        for disk_uuid in free_disks:
            size_gib = float(free_disks[disk_uuid])
            partition_chunks = int(size_gib)
            if partition_chunks < 2:
                LOG.info("Skip disk {} due to insufficient space".format(disk_uuid))
                continue
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, disk_uuid, "1", fail_ok=False, wait=False)
            assert rc == 0, "Partition creation was expected to succeed but instead failed"
            # Check that first disk was created
            uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, timeout=CP_TIMEOUT)
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)

            device_node, size_gib = storage_helper.get_host_partition_values(host, uuid, ("device_node", "size_gib"))
            total_size = int(size_gib) - 1
            LOG.tc_step("Modifying partition {} from size {} to size {} from host {} on device node {}".format(
                uuid, int(size_gib), str(total_size), host, device_node[:-1]))
            rc, out = storage_helper.modify_host_partition(host, uuid, str(total_size), fail_ok=True)
            assert rc != 0, "Expected partition modification to fail and instead it succeeded"
            # Only test one disk on each host
            break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


@mark.usefixtures('delete_partitions_teardown')
def test_increase_host_partition_size_beyond_avail_disk_space():
    """
    This test attempts to increase the size of an existing host partition
    beyond the available space on disk.  It is expected to fail.

    Assumptions:
    * Partitions are available in Ready state.

    Test steps:
    * Create partition
    * Modify the partition to consume over than the available disk space

    Teardown:
    * Delete created partitions

    """

    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    usable_disks = False
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        for disk_uuid in free_disks:
            size_gib = float(free_disks[disk_uuid])
            partition_chunks = int(size_gib)
            if partition_chunks < 2:
                LOG.info("Skip disk {} due to insufficient space".format(disk_uuid))
                continue
            usable_disks = True
            LOG.info("Creating partition on {}".format(host))
            rc, out = storage_helper.create_host_partition(host, disk_uuid, "1", fail_ok=False, wait=False)
            assert rc == 0, "Partition creation was expected to succeed but instead failed"
            # Check that first disk was created
            uuid = table_parser.get_value_two_col_table(table_parser.table(out), "uuid")
            storage_helper.wait_for_host_partition_status(host=host, uuid=uuid, timeout=CP_TIMEOUT)
            partitions_to_restore[host] = []
            partitions_to_restore[host].append(uuid)

            device_node = storage_helper.get_host_partition_values(host, uuid, "device_node")[0]
            device_node = device_node.rstrip(string.digits)
            if device_node.startswith("/dev/nvme"):
                device_node = device_node[:-1]
            size_gib += 1
            LOG.tc_step("Modifying partition {} from size 1 to size {} from host {} on device node {}".format(
                uuid, int(size_gib), host, device_node))
            rc, out = storage_helper.modify_host_partition(host, uuid, str(int(size_gib)), fail_ok=True)
            assert rc != 0, "Expected partition modification to fail and instead it succeeded"
            LOG.info(out)
            # Only test one disk on each host
            break

    if not usable_disks:
        skip("Did not find disks with sufficient space to test with.")


def test_create_partition_using_valid_uuid_of_another_host():
    """
    This test attempts to create a partition using a valid uuid that belongs to
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

    hosts = system_helper.get_hosts(personality=('worker', 'controller'))

    if len(hosts) == 1:
        skip("This test requires more than one host")

    sut = "controller-0"
    hosts.remove(sut)
    free_disks = []
    donor = None
    LOG.tc_step("Determine which hosts have free disks")
    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if free_disks:
            donor = host
            break

    if not free_disks:
        skip("Insufficient disk space to to complete test.")

    for uuid in free_disks:
        LOG.info("Creating partition on {} using disk from {}".format(sut, donor))
        rc, out = storage_helper.create_host_partition(sut, uuid, int(free_disks[uuid]), fail_ok=True)
        assert rc != 0, "Partition creation should be rejected but instead it was successful"
        # Break since we only need to do this once
        break


@mark.usefixtures('delete_partitions_teardown')
def test_modify_second_last_partition():
    """
    This test attempts to modify a partition that is not the last.  It is
    expected to fail, since only the very last partition can be modified.

    Arguments:
    * None

    Test steps:
    * Create partition1
    * Create partition2
    * Attempt to modify partition1

    Teardown:
    * None
    """

    global partitions_to_restore
    partitions_to_restore = {}

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    for host in hosts:
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue

        partitions_to_restore[host] = []
        for disk_uuid in free_disks:
            size_gib = float(free_disks[disk_uuid])
            partition_size = "1"
            partition_chunks = size_gib / int(partition_size)
            if partition_chunks < 3:
                LOG.info("Skip disk {} due to insufficient space".format(disk_uuid))
                continue

            LOG.info("Creating first partition on {}".format(host))
            uuid = storage_helper.create_host_partition(host, disk_uuid, partition_size)[1]
            partitions_to_restore[host].append(uuid)

            LOG.info("Creating second partition on {}".format(host))
            uuid1 = storage_helper.create_host_partition(host, disk_uuid, partition_size)[1]
            partitions_to_restore[host].append(uuid1)

            LOG.tc_step("Modifying partition {} from size {} to size {} from host {} on disk {}".format(
                uuid, partition_size, int(partition_size) + 1, host, disk_uuid))
            rc, out = storage_helper.modify_host_partition(host, uuid, int(partition_size) + 1, fail_ok=True)
            assert rc != 0, "Partition modification was expected to fail but instead was successful"


def test_create_partition_using_non_existent_device_node():
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
    size_gib = "1"

    computes = system_helper.get_hosts(personality="compute")
    hosts = system_helper.get_controllers() + computes

    for host in hosts:
        LOG.tc_step("Creating partition on host {} with size {} using device node {}".format(host, size_gib,
                                                                                             device_node))
        rc, out = storage_helper.create_host_partition(host, device_node, size_gib, fail_ok=True)
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
        disks = storage_helper.get_host_disks(host)
        free_disks = storage_helper.get_host_disks_with_free_space(host, disks)
        if not free_disks:
            continue
        for uuid in free_disks:
            rc, out = storage_helper.create_host_partition(host, uuid, int(free_disks[uuid]), fail_ok=True)
            assert rc != 0, "Partition creation was successful"


def test_host_disk_wipe_rootfs():
    """
    This test attempts to run system host-disk-wipe on a node using the rootfs
    disk.  Command format is:

    system host-disk-wipe [--confirm] <hostname or id> <disk uuid>

    Note, host-disk-wipe is only applicable to controller and compute nodes. It
    cannot be used on the rootfs disk.  It cannot be used for a disk that is
    used by a PV or has partitions used by a PV.

    Arguments:
    - None

    Test Steps:
    1.  Determine which is the rootfs disk
    2.  Attempt to wipe the disk
    3.  Expect it to fail for every node

    Assumptions:
    - None
    """
    computes = system_helper.get_hosts(personality="compute")
    storage = system_helper.get_hosts(personality="storage")
    hosts = system_helper.get_controllers() + computes + storage

    LOG.tc_step("Gather rootfs disks")
    rootfs = storage_helper.get_hosts_rootfs(hosts)

    for host in rootfs:
        uuid = rootfs[host]
        LOG.tc_step("Attempting to wipe {} from {}".format(uuid[0], host))
        cmd = 'host-disk-wipe --confirm {} {}'.format(host, uuid[0])
        rc, out = cli.system(cmd, fail_ok=True)
        assert rc != 0, "Expected wipe disk to fail but instead succeeded"


def test_host_disk_wipe_unassigned_disk():
    """
    This test attempts to run system host-disk-wipe on a node using any
    unassigned disk.

    Command format is:

    system host-disk-wipe [--confirm] <hostname or id> <disk uuid>

    Note, host-disk-wipe is only applicable to controller and compute nodes. It
    cannot be used on the rootfs disk.  It cannot be used for a disk that is
    used by a PV or has partitions used by a PV.

    Arguments:
    - None

    Test Steps:
    1.  Determine which disks are unassigned by comparing size_gib to
    available_gib in system host-disk-list
    2.  Attempt to wipe the disk
    3.  Expect it to pass

    Assumptions:
    - None
    """
    computes = system_helper.get_hosts(personality="compute", availability="available")
    controllers = system_helper.get_hosts(personality="controller", availability="available")
    hosts = controllers + computes

    found_disk = False
    for host in hosts:
        LOG.info("Query disks on host {}".format(host))
        disks = storage_helper.get_host_disks(host)
        for disk_uuid in disks:
            cmd = "host-disk-show {} {}".format(host, disk_uuid)
            rc, out = cli.system(cmd)
            size_gib = table_parser.get_value_two_col_table(table_parser.table(out), "size_gib")
            available_gib = table_parser.get_value_two_col_table(table_parser.table(out), "available_gib")
            if int(float(size_gib)) == int(float(available_gib)):
                found_disk = True
                LOG.tc_step("Attempting to wipe disk {} from host {}".format(disk_uuid, host))
                cmd = 'host-disk-wipe --confirm {} {}'.format(host, disk_uuid)
                rc, out = cli.system(cmd, fail_ok=True)
                assert rc == 0, "Expected wipe disk to pass but instead failed"
                break

    if not found_disk:
        skip("No unassigned disks to run test")
