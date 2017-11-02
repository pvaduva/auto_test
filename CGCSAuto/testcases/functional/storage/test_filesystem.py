import ast
import re
import math
import time

from pytest import fixture, skip, mark

from consts.auth import Tenant
from consts.cgcs import EventLogID, HostAvailabilityState
from keywords import host_helper, system_helper, local_storage_helper, install_helper
from testfixtures.recover_hosts import HostsToRecover
from utils import cli, table_parser
from utils.tis_log import LOG
from utils.ssh import ControllerClient

@fixture()
def aio_precheck():
    if not system_helper.is_two_node_cpe() and not system_helper.is_simplex():
        skip("Test only applies to AIO-SX or AIO-DX systems")

@fixture()
def lvm_precheck():
    if system_helper.is_simplex() or system_helper.is_storage_system():
        skip("Test does not apply to AIO-SX systems or storage systems")

@fixture()
def storage_precheck():
    if not system_helper.is_storage_system():
        skip("This test only applies to storage nodes")

@mark.usefixtures("aio_precheck")
def test_reclaim_sda():
    """
    On Simplex or Duplex systems that use a dedicated disk for nova-local,
    recover reserved root disk space for use by the cgts-vg volume group to allow
    for controller filesystem expansion.

    Assumptions:
    - System is AIO-SX or AIO-DX

    Test Steps:
    - Get host list
    - Retrieve current value of cgts-vg
    - Reclaim space on hosts
    - Check for the config out-of-date alarm to raise and clear
    - Retrieve current value of cgts-vg
    - Check that the cgts-vg size is larger than before

    """

    con_ssh = ControllerClient.get_active_controller()

    hosts = host_helper.get_hosts()

    cmd = "pvs -o vg_name,pv_size --noheadings | grep cgts-vg"
    cgts_vg_regex = "([0-9.]*)g$"

    rc, out = con_ssh.exec_sudo_cmd(cmd)
    cgts_vg_val = re.search(cgts_vg_regex, out)

    LOG.info("cgts-vg is currently: {}".format(cgts_vg_val.group(1)))

    for host in hosts:
        LOG.info("Reclaiming space for {}".format(host))
        pos_args = "{} cgts-vg /dev/sda".format(host)
        table_ = table_parser.table(cli.system('host-pv-add', positional_args=pos_args))
        system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                     entity_id="host={}".format(host))

    LOG.info("Wait for config out-of-date alarms to clear")
    for host in hosts:
       system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                         entity_id="host={}".format(host))

    time.sleep(10)

    cmd = "pvs -o vg_name,pv_size --noheadings | grep cgts-vg"
    cgts_vg_regex = "([0-9.]*)g$"

    rc, out = con_ssh.exec_sudo_cmd(cmd)
    new_cgts_vg_val = re.search(cgts_vg_regex, out)

    LOG.info("cgts-vg is now: {}".format(new_cgts_vg_val.group(1)))
    assert float(new_cgts_vg_val.group(1)) > float(cgts_vg_val.group(1)), "cgts-vg size did not increase"


def test_increase_scratch():
    """ 
    This test increases the size of the scratch filesystem.  The scratch
    filesystem is used for activities such as uploading swift object files,
    etc.

    It also attempts to decrease the size of the scratch filesystem (which
    should fail).

    """

    con_ssh = ControllerClient.get_active_controller()

    table_ = table_parser.table(cli.system('controllerfs-show scratch'))
    scratch = table_parser.get_value_two_col_table(table_, 'size')
    LOG.info("scratch is currently: {}".format(scratch))
    scratch = int(ast.literal_eval(scratch))

    LOG.tc_step("Determine the available free space on the system")
    cmd = "vgdisplay -C --noheadings --nosuffix -o vg_free --units g cgts-vg"
    rc, out = con_ssh.exec_sudo_cmd(cmd)
    free_space = out.rstrip()
    LOG.info("Available free space on the system is: {}".format(free_space))
    free_space = int(ast.literal_eval(free_space))
    if free_space <= 10:
        skip("Not enough free space to complete test.")

    LOG.tc_step("Increase the size of the scratch filesystem")
    new_scratch = math.trunc(free_space / 10) + scratch
    cmd = "system controllerfs-modify scratch {}".format(new_scratch)
    rc, out = con_ssh.exec_cmd(cmd)
    assert rc == 0, "Modification of scratch failed"

    table_ = table_parser.table(cli.system('controllerfs-show scratch'))
    new_scratch = table_parser.get_value_two_col_table(table_, 'size')
    LOG.info("scratch is now: {}".format(new_scratch))
    new_scratch = int(ast.literal_eval(new_scratch))
    assert new_scratch > scratch, "scratch size did not increase"

    LOG.info("Wait for alarms to clear")
    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                        entity_id="host={}".format(host))

    LOG.tc_step("Attempt to decrease the size of the scratch filesystem")
    decreased_scratch = new_scratch - 1
    cmd = "system controllerfs-modify scratch {}".format(decreased_scratch)
    rc, out = con_ssh.exec_cmd(cmd, fail_ok=True)
    table_ = table_parser.table(cli.system('controllerfs-show scratch'))
    final_scratch = table_parser.get_value_two_col_table(table_, 'size')
    final_scratch = int(ast.literal_eval(final_scratch))
    LOG.info("scratch is currently {}".format(final_scratch))
    assert final_scratch != decreased_scratch, \
        "scratch was unexpectedly decreased from {} to {}".format(new_scratch, final_scratch)


def test_decrease_drbd():
    """ 
    This test attempts to decrease the size of the drbd based filesystems.
    The expectation is that this should be rejected.

    Arguments:
    - None

    Test Steps:

    1.  Query the value of each drbd partition
    2.  Attempt to decrease each partition

    Assumptions:
    - None
    """

    drbdfs = ['backup', 'cgcs', 'database', 'img-conversions']
    con_ssh = ControllerClient.get_active_controller()

    drbdfs_val = {} 
    LOG.tc_step("Determine the space available for each drbd fs")
    for fs in drbdfs:
        table_ = table_parser.table(cli.system('controllerfs-show {}'.format(fs)))
        drbdfs_val[fs] = table_parser.get_value_two_col_table(table_, 'size')

    LOG.info("Current fs values are: {}".format(drbdfs_val))

    for partition_name in drbdfs:
        LOG.tc_step("Increase the size of the backup and cgcs filesystem")
        partition_value = drbdfs_val[partition_name]
        new_partition_value = int(partition_value) - 1
        cmd = "system controllerfs-modify {} {}".format(partition_name, new_partition_value)
        rc, out = con_ssh.exec_cmd(cmd, fail_ok=True)
        assert rc != 0, "Filesystem {} was unexpectedly decreased".format(partition)


# Fails due to product issue
def _test_modify_drdb():
    """ 
    This test modifies the size of the drbd based filesystems, does an
    immediate swact and then reboots the active controller.

    Arguments:
    - None

    Test Steps:
    - Determine how much free space we have available
    - Increase backup
    - Increase cgcs
    - Initiate a controller swact
    - Initate a controller reboot

    Assumptions:
    - None

    """

    drbdfs = ['backup', 'cgcs', 'database', 'img-conversions']
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Determine the available free space on the system")
    cmd = "vgdisplay -C --noheadings --nosuffix -o vg_free --units g cgts-vg"
    rc, out = con_ssh.exec_sudo_cmd(cmd)
    free_space = out.rstrip()
    free_space = out.lstrip()
    LOG.info("Available free space on the system is: {}".format(free_space))
    if float(free_space) <= 2:
        skip("Not enough free space to complete test.")

    drbdfs_val = {} 
    LOG.tc_step("Determine the space available for each drbd fs")
    for fs in drbdfs:
        table_ = table_parser.table(cli.system('controllerfs-show {}'.format(fs)))
        drbdfs_val[fs] = table_parser.get_value_two_col_table(table_, 'size')

    LOG.info("Current fs values are: {}".format(drbdfs_val))

    LOG.tc_step("Increase the size of the backup and cgcs filesystem")
    partition_name = "backup"
    partition_value = drbdfs_val[partition_name]
    if float(free_space) > 10:
        backup_freespace = math.trunc(float(free_space) / 10)
    else:
        backup_freespace = 1
    new_partition_value = backup_freespace + int(partition_value)
    cmd = "system controllerfs-modify {} {}".format(partition_name, new_partition_value)
    rc, out = con_ssh.exec_cmd(cmd)
    partition_name = "cgcs"
    partition_value = drbdfs_val[partition_name]
    cgcs_free_space = math.trunc(backup_freespace / 2)
    new_partition_value = backup_freespace + int(partition_value)
    cmd = "system controllerfs-modify {} {}".format(partition_name, new_partition_value)
    rc, out = con_ssh.exec_cmd(cmd)


    hosts = system_helper.get_controllers()
    for host in hosts:
       system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                         entity_id="host={}".format(host),
                                         timeout=600)
    standby_cont = system_helper.get_standby_controller_name()
    host_helper.wait_for_host_states(standby_cont, availability=HostAvailabilityState.AVAILABLE)
    host_helper.swact_host()

    act_cont = system_helper.get_active_controller_name()
    host_helper.reboot_hosts(act_cont)


@mark.usefixtures("lvm_precheck")
def _test_increase_cinder():
    """
    Increase the size of the cinder filesystem.  Note, host reinstall is no
    longer required.

    This test does not apply to AIO-SX systems since cinder will default to max
    size.  This also doesn't apply to storage systems since cinder is stored
    in the rbd backend.

    LEAVE DISABLED until in-service cinder feature is submitted.

    Test steps:
    1.  Query the size of cinder
    2.  Determine the available space on the disk hosting cinder
    3.  Increase the size of the cinder filesystem
    4.  Wait for config out-of-date to raise and clear
    5.  Check cinder to see if the filesystem is increased

    Enhancement:
    1.  Check on the physical filesystem rather than depending on TiS reporting
    """

    table_= table_parser.table(cli.system("storage-backend-show lvm"))
    cinder_gib = table_parser.get_value_two_col_table(table_, "cinder_gib")
    LOG.info("cinder is currently {}".format(cinder_gib))

    cinder_device_dict = ast.literal_eval(table_parser.get_value_two_col_table(table_, "cinder_device"))
    cont0_devpath = cinder_device_dict["controller-0"]
    LOG.info("The cinder device path for controller-0 is: {}".format(cont0_devpath))

    table_ = table_parser.table(cli.system("host-disk-list controller-0 --nowrap"))
    cont0_dev_node = table_parser.get_values(table_, "device_node", **{"device_path": cont0_devpath})
    cont0_total_mib = table_parser.get_values(table_, "size_mib", **{"device_path": cont0_devpath})
    cont0_avail_mib = table_parser.get_values(table_, "available_mib", **{"device_path": cont0_devpath})

    if cont0_total_mib[0] == cont0_avail_mib[0]:
        skip("Insufficient disk space to execute test")

    LOG.info("The cinder device node for controller-0 is: {}".format(cont0_dev_node))
    LOG.info("Total disk space in MiB is: {}".format(cont0_total_mib[0]))
    LOG.info("Available free space in MiB is: {}".format(cont0_avail_mib[0]))

    cont0_total_gib = math.trunc(int(cont0_total_mib[0]) / 1024)
    cont0_avail_gib = math.trunc(int(cont0_avail_mib[0]) / 1024)
    LOG.info("Total disk space in GiB is: {}".format(cont0_total_gib))
    LOG.info("Available free space in GiB is: {}".format(cont0_avail_gib))

    LOG.tc_step("Increase the size of the cinder filesystem")
    new_cinder_val = math.trunc(int(cont0_avail_gib) / 10) + int(cinder_gib)
    cmd = "system controllerfs-modify cinder {}".format(new_cinder_val)
    rc, out = con_ssh.exec_cmd(cmd)
    
    LOG.tc_step("Wait for config out-of-date alarms to raise")
    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                     entity_id="host={}".format(host))

    LOG.tc_step("Wait for config out-of-date alarms to clear")
    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          entity_id="host={}".format(host))

    LOG.tc_step("Validate cinder size is increased")
    table_= table_parser.table(cli.system("storage-backend-show lvm"))
    cinder_gib2 = table_parser.get_value_two_col_table(table_, "cinder_gib")
    LOG.info("cinder is currently {}".format(cinder_gib2))
    assert int(cinder_gib2) == int(new_cinder_val), "Cinder size did not increase"


@mark.usefixtures("storage_precheck")
def test_increase_ceph_mon():
    """
    Increase the size of ceph-mon.  Only applicable to a storage system.

    Fails until CGTS-8216

    Test steps:
    1.  Determine the current size of ceph-mon
    2.  Attempt to modify ceph-mon to invalid values
    3.  Check if there is free space to increase ceph-mon
    4.  Attempt to increase ceph-mon
    5.  Wait for config out-of-date alarms to raise
    6.  Lock/unlock all affected nodes (controllers and storage)
    7.  Wait for alarms to clear
    8.  Check that ceph-mon has the correct updated value

    Enhancement:
    1.  Possibly check there is enough disk space for ceph-mon to increase.  Not sure if
    this is required since there always seems to be some space on the rootfs.
    """

    con_ssh = ControllerClient.get_active_controller()

    table_ = table_parser.table(cli.system("ceph-mon-list"))
    ceph_mon_gib = table_parser.get_values(table_, "ceph_mon_gib", **{"hostname": "controller-0"})[0]
    LOG.info("ceph_mon_gib is currently: {}".format(ceph_mon_gib))

    LOG.tc_step("Attempt to modify ceph-mon to invalid values")
    invalid_cmg = ['19', '41', 'fds']
    for value in invalid_cmg:
        host = "controller-0"
        cli.system("ceph-mon-modify {} ceph_mon_gib={}".format(host, value), fail_ok=True)

    if int(ceph_mon_gib) >= 30:
        skip("Insufficient disk space to execute test")

    ceph_mon_gib_avail = 40 - int(ceph_mon_gib)
    new_ceph_mon_gib = math.trunc(ceph_mon_gib_avail / 10) + int(ceph_mon_gib)

    LOG.tc_step("Increase ceph_mon_gib to {}".format(new_ceph_mon_gib))
    hosts = system_helper.get_controllers()
    for host in hosts:
        cli.system("ceph-mon-modify {} ceph_mon_gib={}".format(host, new_ceph_mon_gib))
        # We only need to do this for one controller now and it applies to both
        break

    LOG.info("Wait for expected alarms to appear")
    storage_hosts = system_helper.get_storage_nodes()
    total_hosts = hosts + storage_hosts
    for host in total_hosts:
        system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                     entity_id="host={}".format(host))

    LOG.tc_step("Lock/unlock all affected nodes")
    standby = system_helper.get_standby_controller_name()
    active = system_helper.get_active_controller_name()
    host_helper.lock_host(standby)
    host_helper.unlock_host(standby)
    time.sleep(10)
    host_helper.swact_host(active)
    host_helper.lock_host(active)
    host_helper.unlock_host(active)

    for host in storage_hosts:
        host_helper.lock_host(host)
        host_helper.unlock_host(host)
        time.sleep(10)
  
    total_hosts = hosts.append(storage_hosts)
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          entity_id="host={}".format(host))

    table_ = table_parser.table(cli.system("ceph-mon-list"))
    ceph_mon_gib = table_parser.get_values(table_, "ceph_mon_gib", **{"hostname": "controller-0"})[0]
    assert ceph_mon_gib != new_ceph_mon_gib, "ceph-mon did not change"

