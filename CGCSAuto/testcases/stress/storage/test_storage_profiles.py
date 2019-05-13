"""
This is a re-write of the existing storage profile tests.  The tests are
implemented slightly differently than before.  The test queries the system to
determine which hosts have compatible hardware based on what personality type
is being tested.  It will then determine which is the largest group with
compatible hardware and execute the tests on that.

For compute or controller+compute nodes, the tests will also take into account
the storage backing as either image or remote.  It will try to see if
there is already a host with the desired from storage backing, or already a
host with the desired to storage backing, in order to save time.  Otherwise, it
will simply pick a random host with the right hardware and perform the
necessary backend conversion(s) that the test requires, before proceeding.

Once the system has the right setup, it will create a storage profile on the
from host.  It will then lock the to host, apply the storage profile and
unlock.  It will then check if the appropriate backend is applied.

The scope of these tests are broader than the previous implementation, as the
tests support execution on controller+compute nodes (AIO-DX), compute nodes and
storage nodes.  Tests will be skipped on AIO-SX systems due to insufficient
hardware to run the tests.

Please note that profile application on controller+compute nodes and storage
nodes involves deleting the node and then reprovisioning.  As such,
lab_setup.sh will need to be re-run to reprovision the node properly.  In
addition, compute nodes with in-use partitions will need to be deleted and
reprovisioned.  Compute nodes wiht ready paritions will require partition
deletion before profile application.

Due to the node deletions, it is suggested that these tests be executed last to
avoid impacting subsequent tests.  Also, execution time is long for this suite
of tests due to locks, unlocks, deletes and fresh installs of nodes.

This test is a base for building further tests.  Here are some suggestions for
enhancements or improvements:

Additional coverage that should be added

* Default configurations for labs should be modified to cover the various
  partition types.  This is best done through lab_setup.conf changes.
  1.  All partitions Ready, nova-local on seperate disk, using whole disk
  2.  Some partitions Ready, others used by nova-local
  3.  No partitions, nova-local is using whole disk

* Additional negative tests could be added as well.  The following is
  recommended:
  1. Try to apply a storage profile on a new host where the disk is too small
  2. Try to apply a storage profile on a partition configuration that is
  duplicate to the one stored in the profile

* Check that cinder/cgts-vg information is not stored in storage profile

* Partition and nova-local information should be present in storage profile

Further work could also be done in extracting segments of the code into local
functions or porting into keywords.
"""

import random
import time

from pytest import skip, mark, fixture

from consts.cgcs import HostAvailState
from consts.proj_vars import InstallVars
from testfixtures.recover_hosts import HostsToRecover
from keywords import host_helper, system_helper, install_helper, vm_helper, storage_helper, partition_helper
from setups import _rsync_files_to_con1
from utils import cli, table_parser
from utils.tis_log import LOG
from utils.node import create_node_boot_dict, create_node_dict
from utils.clients.ssh import ControllerClient

PROFILES_TO_DELETE = []
DISK_DETECTION_TIMEOUT = 60


@fixture()
def delete_profiles_teardown(request):
    def teardown():
        """
        Delete any profiles that were created as part of the tests.
        """

        global PROFILES_TO_DELETE

        LOG.info("Deleting created profiles")
        for profile in PROFILES_TO_DELETE:
            system_helper.delete_storage_profile(profile)
    request.addfinalizer(teardown)


def get_hw_compatible_hosts(hosts):
    """
    Given a list of hosts return a dict of hardware compatible ones, if any.

    Arguments:
    - Hosts (list)

    Returns:
    - Dict mapping hash to hosts
    """

    hardware = {}
    hardware_hash = {}
    for host in hosts:
        rc, out = cli.system("host-disk-list {} --nowrap".format(host), rtn_code=True)
        table_ = table_parser.table(out)
        device_nodes = table_parser.get_column(table_, "device_node")
        device_type = table_parser.get_column(table_, "device_type")
        size_gib = table_parser.get_column(table_, "size_gib")
        hardware[host] = list(zip(device_nodes, device_type, size_gib))
        LOG.info("Hardware present on host {}: {}".format(host, hardware[host]))
        hardware_hash[host] = hash(str(hardware[host]))
        LOG.info("Host {} has hash {}".format(host, hardware_hash[host]))

    # Create reverse lookup of hash to hosts
    hash_to_hosts = {}
    for key, value in hardware_hash.items():
        hash_to_hosts.setdefault(value, []).append(key)

    LOG.info("These are the hardware compatible hosts: {}".format(hash_to_hosts))
    return hash_to_hosts


def wait_for_disks(host, timeout=DISK_DETECTION_TIMEOUT, wait_time=10):
    """
    Check for presence of disks

    Arguments:
    - Host (str) - e.g. controller-0
    - timeout (int/seconds) - e.g. 60

    Returns:
    - (bool) True if found, False if not Found

    """

    # Even though the host is online, doesn't mean disks are detected yet
    # and we can't apply profiles if the disks aren't present.
    end_time = time.time() + timeout
    while time.time() < end_time:
        out = partition_helper.get_disks(host)
        if out:
            LOG.info("Found disks {} on host {}".format(out, host))
            return True
        time.sleep(wait_time)

    return False


def delete_lab_setup_files(con_ssh, host, files):
    """
    This will delete specified lab_setup files.

    Arguments:
    - con_ssh
    - host (str) - e.g. controller-0
    - files (list) - e.g. interfaces

    Returns:
    - Nothing
    """

    for filename in files:
        con_ssh.exec_cmd("rm .lab_setup.done.group0.{}.{}".format(host, filename))


@mark.parametrize(('personality', 'from_backing', 'to_backing'), [
    mark.p1(('compute', 'image', 'remote')),
    mark.p1(('compute', 'remote', 'image')),
    mark.p1(('storage', None, None)),
])
@mark.usefixtures('delete_profiles_teardown')
def _test_storage_profile(personality, from_backing, to_backing):
    """
    This test creates a storage profile and then applies it to a node with
    identical hardware, assuming one exists.

    Storage profiles do not apply on controller nodes.  Storage profiles can be
    applied on controller+compute nodes, compute nodes and storage nodes.

    Arguments:
    - personality (string) - controller, compute or storage
    - from_backing (string) - image, remote or None
    - to_backing (string) - image, remote or None

    Test Steps:
    1.  Query system and determine which nodes have compatible hardware.
    2.  Create a storage profile on one of those nodes
    3.  Apply the created storage profile on a compatible node*
    4.  Ensure the storage profiles have been successfully applied.

    * If the node is a compute node or a controller+compute, we will also change
      the backend if required for additional coverage.

    Returns:
    - Nothing
    """

    global PROFILES_TO_DELETE
    PROFILES_TO_DELETE = []

    # Skip if test is not applicable to hardware under test
    if personality == 'controller' and not system_helper.is_small_footprint():
        skip("Test does not apply to controller hosts without subtype compute")

    hosts = system_helper.get_hostnames(personality=personality)
    if not hosts:
        skip("No hosts of type {} available".format(personality))

    if (from_backing == "remote" or to_backing == "remote") and not system_helper.is_storage_system():
        skip("This test doesn't apply to systems without storage hosts")

    LOG.tc_step("Identify hardware compatible hosts")
    hash_to_hosts = get_hw_compatible_hosts(hosts)

    # Pick the hardware group that has the most compatible hosts
    current_size = 0
    candidate_hosts = []
    for value in hash_to_hosts:
        candidate_size = len(hash_to_hosts[value])
        if candidate_size > current_size:
            current_size = candidate_size
            candidate_hosts = hash_to_hosts[value]
    LOG.info("This is the total set of candidate hosts: {}".format(candidate_hosts))

    if len(candidate_hosts) < 2:
        skip("Insufficient hardware compatible hosts to run test")

    # Rsync lab setup dot files between controllers
    con_ssh = ControllerClient.get_active_controller()
    _rsync_files_to_con1(con_ssh=con_ssh, file_to_check="force.txt")

    # Take the hardware compatible hosts and check if any of them already have
    # the backend that we want.  This will save us test time.
    new_to_backing = None
    if personality == "compute":
        from_hosts = []
        to_hosts = []
        for host in candidate_hosts:
            host_backing = host_helper.get_host_instance_backing(host)
            if host_backing == from_backing:
                from_hosts.append(host)
            elif host_backing == to_backing:
                to_hosts.append(host)
            else:
                pass
        LOG.info("Candidate hosts that already have the right from backing {}: {}".format(from_backing, from_hosts))
        LOG.info("Candidate hosts that already have the right to backing {}: {}".format(to_backing, to_hosts))

        # Determine what hosts to use
        if not from_hosts and to_hosts:
            to_host = random.choice(to_hosts)
            candidate_hosts.remove(to_host)
            from_host = random.choice(candidate_hosts)
        elif not to_hosts and from_hosts:
            from_host = random.choice(from_hosts)
            candidate_hosts.remove(from_host)
            to_host = random.choice(candidate_hosts)
        elif not to_hosts and not from_hosts:
            to_host = random.choice(candidate_hosts)
            candidate_hosts.remove(to_host)
            from_host = random.choice(candidate_hosts)
        else:
            to_host = random.choice(to_hosts)
            from_host = random.choice(from_hosts)

        LOG.info("From host is: {}".format(from_host))
        LOG.info("To host is: {}".format(to_host))

        LOG.tc_step("Check from host backing and convert to {} if necessary".format(from_backing))
        orig_from_host_backing = host_helper.get_host_instance_backing(from_host)
        new_from_backing = host_helper.set_host_storage_backing(from_host, from_backing)
        host_helper.wait_for_host_values(from_host, availability=HostAvailState.AVAILABLE, timeout=120, fail_ok=False)

        LOG.tc_step("Check to host backing and convert to {} if necessary".format(to_backing))
        orig_to_host_backing = host_helper.get_host_instance_backing(to_host)
        new_to_backing = host_helper.set_host_storage_backing(to_host, to_backing)
    elif personality == "controller":
        # For now, we don't want to host reinstall controller-0 since it will default to
        # pxeboot, but this could be examined as a possible enhancement.
        from_host = "controller-0"
        to_host = "controller-1"

        LOG.info("From host is: {}".format(from_host))
        LOG.info("To host is: {}".format(to_host))

        LOG.tc_step("Check from host backing and convert to {} if necessary".format(from_backing))
        orig_from_host_backing = host_helper.get_host_instance_backing(from_host)
        new_from_backing = host_helper.set_host_storage_backing(from_host, from_backing)

        LOG.tc_step("Check to host backing and convert to {} if necessary".format(to_backing))
        orig_to_host_backing = host_helper.get_host_instance_backing(to_host)
        new_to_backing = host_helper.set_host_storage_backing(to_host, to_backing)
    else:
        # Backing doesn't apply to storage nodes so just pick from compatible hardware
        from_host = random.choice(candidate_hosts)
        candidate_hosts.remove(from_host)
        to_host = random.choice(candidate_hosts)

    LOG.tc_step("Create storage and interface profiles on the from host {}".format(from_host))
    prof_name = 'storprof_{}_{}'.format(from_host, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
    prof_uuid = system_helper.create_storage_profile(from_host, profile_name=prof_name)
    PROFILES_TO_DELETE.append(prof_name)

    # Deleting VMs in case the remaining host(s) cannot handle all VMs
    # migrating on lock, particularly important in the case of AIO-DX systems.
    LOG.tc_step("Delete all VMs and lock the host before applying the storage profile")
    vm_helper.delete_vms()
    HostsToRecover.add(to_host, scope='function')
    host_helper.wait_for_host_values(from_host, availability=HostAvailState.AVAILABLE, timeout=120, fail_ok=False)
    host_helper.wait_for_host_values(to_host, availability=HostAvailState.AVAILABLE, timeout=120, fail_ok=False)

    # Negative test #1 - attempt to apply profile on unlocked host (should be rejected)
    LOG.tc_step('Apply the storage-profile {} onto unlocked host:{}'.format(prof_name, to_host))
    cmd = 'host-apply-storprofile {} {}'.format(to_host, prof_name)
    rc, msg = cli.system(cmd, rtn_code=True, fail_ok=True)
    assert rc != 0, msg
    host_helper.lock_host(to_host, swact=True)

    # 3 conditions to watch for: no partitions, ready partitions and in-use
    # partitions on the compute.  If in-use, delete and freshly install host.
    # If ready, delete all ready partitions to make room for potentially new
    # partitions.  If no partitions, just delete nova-local lvg.
    if personality == "compute":

        # Negative test #2 - attempt to apply profile onto host with existing
        # nova-local (should be rejected)
        LOG.tc_step('Apply the storage-profile {} onto host with existing nova-local:{}'.format(prof_name, to_host))
        cmd = 'host-apply-storprofile {} {}'.format(to_host, prof_name)
        rc, msg = cli.system(cmd, rtn_code=True, fail_ok=True)
        assert rc != 0, msg

        # If we were simply switching backing (without applying a storage
        # profile), the nova-local lvg deletion can be omitted according to design
        LOG.tc_step("Delete nova-local lvg on to host {}".format(to_host))
        cli.system("host-lvg-delete {} nova-local".format(to_host))

        in_use = partition_helper.get_partitions([to_host], "In-Use")

        if len(in_use[to_host]) != 0:

            # Negative test #3 - attempt to apply profile onto host with existing
            # in-use partitions (should be rejected)
            LOG.tc_step('Apply the storage-profile {} onto host with existing \
                         in-use partitions:{}'.format(prof_name, to_host))
            cmd = 'host-apply-storprofile {} {}'.format(to_host, prof_name)
            rc, msg = cli.system(cmd, rtn_code=True, fail_ok=True)
            assert rc != 0, msg

            LOG.tc_step("In-use partitions found.  Must delete the host and freshly install before proceeding.")
            LOG.info("Host {} has in-use partitions {}".format(to_host, in_use))
            lab = InstallVars.get_install_var("LAB")
            lab.update(create_node_dict(lab['compute_nodes'], 'compute'))
            lab['boot_device_dict'] = create_node_boot_dict(lab['name'])
            install_helper.open_vlm_console_thread(to_host)

            LOG.tc_step("Delete the host {}".format(to_host))
            cli.system("host-bulk-export")
            cli.system("host-delete {}".format(to_host), rtn_code=True)
            assert len(system_helper.get_controllers()) > 1, "Host deletion failed"

            cli.system("host-bulk-add hosts.xml")
            host_helper.wait_for_host_values(to_host, timeout=6000, availability=HostAvailState.ONLINE)

            wait_for_disks(to_host)

        ready = partition_helper.get_partitions([to_host], "Ready")
        if len(ready[to_host]) != 0:
            LOG.tc_step("Ready partitions have been found.  Must delete them before profile application")
            LOG.info("Host {} has Ready partitions {}".format(to_host, ready))
            for uuid in reversed(ready[to_host]):
                rc, out = partition_helper.delete_partition(to_host, uuid)
            # Don't bother restoring in this case since the system should be
            # functional after profile is applied.

        LOG.tc_step('Apply the storage-profile {} onto host:{}'.format(prof_name, to_host))
        cli.system('host-apply-storprofile {} {}'.format(to_host, prof_name))

        LOG.tc_step("Unlock to host")
        host_helper.unlock_host(to_host)

        to_host_backing = host_helper.get_host_instance_backing(to_host)
        LOG.info("To host backing was {} and is now {}".format(new_to_backing, to_host_backing))
        assert to_host_backing == from_backing, "Host backing was not changed on storage profile application"

    if personality == "storage":
        if not storage_helper.is_ceph_healthy():
            skip("Cannot run test when ceph is not healthy")

        LOG.tc_step("Delete the host {}".format(to_host))
        cli.system("host-bulk-export")
        cli.system("host-delete {}".format(to_host), rtn_code=True)
        cli.system("host-bulk-add hosts.xml")
        host_helper.wait_for_host_values(to_host, timeout=6000, availability=HostAvailState.ONLINE)

        wait_for_disks(to_host)

        LOG.tc_step('Apply the storage-profile {} onto host:{}'.format(prof_name, to_host))
        cli.system('host-apply-storprofile {} {}'.format(to_host, prof_name))

        # Re-provision interfaces through lab_setup.sh
        LOG.tc_step("Reprovision the host as necessary")
        files = ['interfaces']
        con_ssh = ControllerClient.get_active_controller()
        delete_lab_setup_files(con_ssh, to_host, files)

        rc, msg = install_helper.run_lab_setup()
        assert rc == 0, msg

        LOG.tc_step("Unlock to host")
        host_helper.unlock_host(to_host)

    if personality == "controller":

        # Note, install helper doesn't work on all labs.  Some labs don't
        # display BIOS type which causes install helper to fail
        lab = InstallVars.get_install_var("LAB")
        lab.update(create_node_dict(lab['controller_nodes'], 'controller'))
        lab['boot_device_dict'] = create_node_boot_dict(lab['name'])
        install_helper.open_vlm_console_thread(to_host)

        LOG.tc_step("Delete the host {}".format(to_host))
        cli.system("host-bulk-export")
        cli.system("host-delete {}".format(to_host), rtn_code=True)
        assert len(system_helper.get_controllers()) > 1, "Host deletion failed"

        cli.system("host-bulk-add hosts.xml")
        host_helper.wait_for_host_values(to_host, timeout=6000, availability=HostAvailState.ONLINE)

        wait_for_disks(to_host)

        LOG.tc_step("Apply the storage-profile {} onto host:{}".format(prof_name, to_host))
        cli.system("host-apply-storprofile {} {}".format(to_host, prof_name))

        # Need to re-provision everything on node through lab_setup (except storage)
        LOG.tc_step("Reprovision the host as necessary")
        files = ['interfaces', 'cinder_device', 'vswitch_cpus', 'shared_cpus', 'extend_cgts_vg', 'addresses']
        con_ssh = ControllerClient.get_active_controller()
        delete_lab_setup_files(con_ssh, to_host, files)

        rc, msg = install_helper.run_lab_setup()
        assert rc == 0, msg

        LOG.tc_step("Unlock to host")
        host_helper.unlock_host(to_host)

        to_host_backing = host_helper.get_host_instance_backing(to_host)
        LOG.info("To host backing was {} and is now {}".format(new_to_backing, to_host_backing))
        assert to_host_backing == from_backing, "Host backing was not changed on storage profile application"
