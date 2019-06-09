import ast
import math
import time

from pytest import fixture, skip, mark

from consts.cgcs import EventLogID, HostAvailState
from keywords import host_helper, system_helper, common, storage_helper
from testfixtures.recover_hosts import HostsToRecover
from utils import cli, table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG

DRBDFS = ['backup', 'glance', 'database', 'scratch', 'extension', 'docker', 'etcd', 'docker-distribution']
DRBDFS_CEPH = ['backup', 'database', 'scratch', 'extension']


@fixture()
def freespace_check():
    """
    See if there is enough free space to run tests.
    """

    con_ssh = ControllerClient.get_active_controller()

    cmd = "vgdisplay -C --noheadings --nosuffix -o vg_free --units g cgts-vg"
    rc, out = con_ssh.exec_sudo_cmd(cmd)
    free_space = out.rstrip()
    LOG.info("Available free space on the system is: {}".format(free_space))
    free_space = int(ast.literal_eval(free_space))
    if free_space <= 20:
        skip("Not enough free space to complete test.")


@fixture(scope='function')
def post_check(request):
    """
    This is to remove the file that was created
    return: code 0/1
    """
    con_ssh = ControllerClient.get_active_controller()
    file_loc = "/opt/extension"
    cmd = "cd " + file_loc
    rm_cmd = "rm testFile"
    file_path = file_loc + "/" + "testFile"

    def rm_file():
        LOG.fixture_step("Removing the file that was created to fill the space")
        if con_ssh.file_exists(file_path=file_path):
            con_ssh.exec_cmd(cmd)
            con_ssh.exec_sudo_cmd(rm_cmd)

    request.addfinalizer(rm_file)


@mark.usefixtures("freespace_check")
def test_increase_controllerfs():
    """ 
    This test increases the size of the various controllerfs filesystems all at
    once.

    Arguments:
    - None

    Test Steps:
    - Query the filesystem for their current size
    - Increase the size of each filesystem at once

    Assumptions:
    - There is sufficient free space to allow for an increase, otherwise skip
      test.

    """
    drbdfs_val = {}
    LOG.tc_step("Determine the space available for each drbd filesystem")
    if system_helper.is_storage_system():
        drbd_filesystems = DRBDFS_CEPH
    else:
        drbd_filesystems = DRBDFS

    for fs in drbd_filesystems:
        drbdfs_val[fs] = storage_helper.get_controllerfs_values(fs)[0]
        LOG.info("Current value of {} is {}".format(fs, drbdfs_val[fs]))
        if fs == 'backup':
            drbdfs_val[fs] = drbdfs_val[fs] + 4
        else:
            drbdfs_val[fs] = drbdfs_val[fs] + 1
        LOG.info("Will attempt to increase the value of {} to {}".format(fs, drbdfs_val[fs]))

    LOG.tc_step("Increase the size of all filesystems")
    storage_helper.modify_controllerfs(**drbdfs_val)
    # Need to wait until the change takes effect before checking the
    # filesystems
    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          entity_id="host={}".format(host),
                                          timeout=600)

    LOG.tc_step("Confirm the underlying filesystem size matches what is expected")
    storage_helper.check_controllerfs(**drbdfs_val)


def test_increase_controllerfs_beyond_avail_space():
    """
    This test increases the size of each controller filesystem beyond the space
    available on the system.

    Arguments:
    - None

    Test steps:
    - Determine available space for each filesystem
    - Attempt to increase filesystem size to greater than the available space.
      This should fail.

    Assumptions:
    - None
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Determine the available free space on the system")
    cmd = "vgdisplay -C --noheadings --nosuffix -o vg_free --units g cgts-vg"
    rc, out = con_ssh.exec_sudo_cmd(cmd)
    free_space = out.rstrip()
    LOG.info("Available free space on the system is: {}".format(free_space))

    for fs in DRBDFS:
        drbdfs_val = {}
        LOG.tc_step("Determine the space available for the filesystem")
        drbdfs_val[fs] = storage_helper.get_controllerfs_values(fs)[0]
        LOG.info("{} is currently {}".format(fs, drbdfs_val[fs]))
        drbdfs_val[fs] = drbdfs_val[fs] + round(float(free_space)) + 10

        LOG.tc_step("Attempt to modify {} to {}".format(fs, drbdfs_val[fs]))
        code = storage_helper.modify_controllerfs(fail_ok=True, **drbdfs_val)[0]
        assert 1 == code, "Filesystem modify succeeded while failure is expected: {}".format(drbdfs_val)


@mark.parametrize('fsvalues', ['', '0', 'fds', '$@', '-1'])
def test_modify_controllerfs_invalidargs(fsvalues):
    """
    This test modifies the controller filesystem values in an invalid way, e.g.
    set size to blank, set size to 0, set size to non-numeric value.

    Arguments:
    - None

    Test steps:
    - Set controller filesystem to an invalid value
    - All negative cases should be rejected.

    Assumptions:
    - None
    """

    for fs in DRBDFS:
        drbdfs_val = {}
        LOG.tc_step("Set {} to invalid value {}".format(fs, fsvalues))
        drbdfs_val[fs] = fsvalues
        code = storage_helper.modify_controllerfs(fail_ok=True, **drbdfs_val)[0]
        assert 1 == code, "Filesystem modify succeeded while failure is expected: {}".format(drbdfs_val)


def test_decrease_controllerfs():
    """ 
    This test attempts to decrease the size of each of the controllerfs
    filesystems.  The expectation is that this should be rejected.

    Arguments:
    - None

    Test Steps:
    1.  Query the value of each controllerfs filesystem
    2.  Attempt to decrease each filesystem individually (since we want to make
    sure each works)

    Assumptions:
    - None
    """
    for fs in DRBDFS:
        drbdfs_val = {}
        LOG.tc_step("Determine the current size of the filesystem")
        drbdfs_val[fs] = storage_helper.get_controllerfs_values(fs)[0]
        LOG.info("{} is currently {}".format(fs, drbdfs_val[fs]))
        LOG.tc_step("Decrease the size of the filesystem")
        drbdfs_val[fs] = int(drbdfs_val[fs]) - 1
        LOG.tc_step("Attempt to decrease {} to {}".format(fs, drbdfs_val[fs]))
        code = storage_helper.modify_controllerfs(fail_ok=True, **drbdfs_val)[0]
        assert 1 == code, "Filesystem modify succeeded while failure is expected: {}".format(drbdfs_val)


@mark.usefixtures("freespace_check")
def test_controllerfs_mod_when_host_locked():
    """
    This test attempts to modify controllerfs value while one of the
    controllers is locked.  All controller filesystem modification attempts
    should be rejected when any one of the controllers in not available.

    Arguments:
    - None

    Test Steps:
    1.  Lock standby controller or only controller (in the case of AIO systems)
    2.  Attempt to modify controller filesystem.  This should be rejected.

    Assumptions:
    - None

    Teardown:
    - Unlock controller
    """

    if system_helper.is_aio_simplex():
        target_host = "controller-0"
    else:
        target_host = system_helper.get_standby_controller_name()

    host_helper.lock_host(target_host)
    HostsToRecover.add(target_host, scope="function")

    drbdfs_val = {}
    fs = "backup"
    LOG.tc_step("Determine the current filesystem size")
    drbdfs_val[fs] = storage_helper.get_controllerfs_values(fs)[0]
    LOG.info("Current value of {} is {}".format(fs, drbdfs_val[fs]))
    drbdfs_val[fs] = int(drbdfs_val[fs]) + 1
    LOG.info("Will attempt to increase the value of {} to {}".format(fs, drbdfs_val[fs]))

    LOG.tc_step("Increase the size of filesystems")
    code = storage_helper.modify_controllerfs(fail_ok=True, **drbdfs_val)[0]
    assert 1 == code, "Filesystem modify succeeded while failure is expected: {}".format(drbdfs_val)


@mark.usefixtures("freespace_check")
def test_resize_drbd_filesystem_while_resize_inprogress():
    """
    This test attempts to resize a drbd filesystem while an existing drbd
    resize is in progress.  This should be rejected.

    Arguments:
    - None

    Test steps:
    1.  Increase the size of backup to allow for test to proceed.
    2.  Wait for alarms to clear and then check the underlying filesystem is
    updated
    2.  Attempt to resize the glance filesystem.  This should be successful.
    3.  Attempt to resize cgcs again immediately.  This should be rejected.

    Assumptions:
    - None

    """

    start_time = common.get_date_in_format()
    drbdfs_val = {}
    fs = "backup"
    LOG.tc_step("Increase the backup size before proceeding with rest of test")
    drbdfs_val[fs] = storage_helper.get_controllerfs_values(fs)[0]
    LOG.info("Current value of {} is {}".format(fs, drbdfs_val[fs]))
    drbdfs_val[fs] = int(drbdfs_val[fs]) + 5
    LOG.info("Will attempt to increase the value of {} to {}".format(fs, drbdfs_val[fs]))
    LOG.tc_step("Increase the size of filesystems")
    storage_helper.modify_controllerfs(**drbdfs_val)

    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_events(event_log_id=EventLogID.CONFIG_OUT_OF_DATE, start=start_time,
                                      entity_instance_id="host={}".format(host), strict=False, **{'state': 'set'})

    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          entity_id="host={}".format(host),
                                          timeout=600)

    LOG.tc_step("Confirm the underlying filesystem size matches what is expected")
    storage_helper.check_controllerfs(**drbdfs_val)

    drbdfs_val = {}
    fs = "database"
    LOG.tc_step("Determine the current filesystem size")
    value = storage_helper.get_controllerfs_values(fs)[0]
    LOG.info("Current value of {} is {}".format(fs, value))
    drbdfs_val[fs] = int(value) + 1
    LOG.info("Will attempt to increase the value of {} to {}".format(fs, drbdfs_val[fs]))

    LOG.tc_step("Increase the size of filesystems")
    storage_helper.modify_controllerfs(**drbdfs_val)

    LOG.tc_step("Attempt to increase the size of the filesystem again")
    drbdfs_val[fs] = int(drbdfs_val[fs]) + 1
    code = storage_helper.modify_controllerfs(fail_ok=True, **drbdfs_val)[0]
    assert 1 == code, "Filesystem modify succeeded while failure is expected: {}".format(drbdfs_val)

    # Appearance of sync alarm is delayed so wait for it to appear and then
    # clear
    if not system_helper.is_aio_simplex():
        system_helper.wait_for_alarm(alarm_id=EventLogID.CON_DRBD_SYNC, timeout=300)
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CON_DRBD_SYNC, timeout=300)


# Fails due to product issue
def test_modify_drdb_swact_then_reboot():
    """ 
    This test modifies the size of the drbd based filesystems, does and
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

    drbdfs = DRBDFS
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Determine the available free space on the system")
    cmd = "vgdisplay -C --noheadings --nosuffix -o vg_free --units g cgts-vg"
    rc, out = con_ssh.exec_sudo_cmd(cmd)
    free_space = out.lstrip()
    LOG.info("Available free space on the system is: {}".format(free_space))
    if float(free_space) <= 10:
        skip("Not enough free space to complete test.")

    drbdfs_val = {}
    LOG.tc_step("Determine the space available for each drbd fs")
    for fs in drbdfs:
        table_ = table_parser.table(cli.system('controllerfs-show {}'.format(fs))[1])
        drbdfs_val[fs] = table_parser.get_value_two_col_table(table_, 'size')

    LOG.info("Current fs values are: {}".format(drbdfs_val))

    LOG.tc_step("Increase the size of the backup and glance filesystem")
    partition_name = "backup"
    partition_value = drbdfs_val[partition_name]
    backup_freespace = math.trunc(float(free_space) / 10)
    new_partition_value = backup_freespace + int(partition_value)
    cmd = "controllerfs-modify {}={}".format(partition_name, new_partition_value)
    cli.system(cmd)

    partition_name = "extension"
    partition_value = drbdfs_val[partition_name]
    cgcs_freespace = math.trunc(backup_freespace / 2)
    new_partition_value = cgcs_freespace + int(partition_value)
    cmd = "controllerfs-modify {}={}".format(partition_name, new_partition_value)
    cli.system(cmd)

    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          entity_id="host={}".format(host),
                                          timeout=600)
    standby_cont = system_helper.get_standby_controller_name()
    system_helper.wait_for_host_values(standby_cont, availability=HostAvailState.AVAILABLE)
    host_helper.swact_host()

    act_cont = system_helper.get_active_controller_name()
    host_helper.reboot_hosts(act_cont)

    time.sleep(5)

    system_helper.wait_for_alarm_gone(alarm_id=EventLogID.HOST_RECOVERY_IN_PROGRESS,
                                      entity_id="host={}".format(act_cont),
                                      timeout=600)


# TODO for Maria. Current issue: config out-of-date status is not cleared after lock/unlock standby controller
@mark.usefixtures("freespace_check")
def _test_increase_ceph_mon():
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
    table_ = table_parser.table(cli.system("ceph-mon-list")[1])
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
    for host in storage_hosts:
        HostsToRecover.add(host)
        host_helper.lock_host(host)
        host_helper.unlock_host(host)
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(host))
        time.sleep(10)

    standby = system_helper.get_standby_controller_name()
    active = system_helper.get_active_controller_name()
    HostsToRecover.add(standby)
    host_helper.lock_host(standby)
    host_helper.unlock_host(standby)
    system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(standby))
    time.sleep(10)
    host_helper.swact_host(active)
    HostsToRecover.add(active)
    host_helper.lock_host(active)
    host_helper.unlock_host(active)
    system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(active))

    table_ = table_parser.table(cli.system("ceph-mon-list")[1])
    ceph_mon_gib = table_parser.get_values(table_, "ceph_mon_gib", **{"hostname": "controller-0"})[0]
    assert ceph_mon_gib != new_ceph_mon_gib, "ceph-mon did not change"


@mark.usefixtures("freespace_check")
@mark.usefixtures("post_check")
def test_increase_extensionfs_with_alarm():
    """
    This test increases the size of the extenteion controllerfs filesystems while there is an alarm condition for the
    fs.

    Arguments:
    - None

    Test Steps:
    - Query the filesystem for their current size
    - cause an alarm condition by filling the space on that fs
    - verify controller-0 is degraded
    - Increase the size of extension filesystem.
    - Verify alarm is gone

    Assumptions:
    - There is sufficient free space to allow for an increase, otherwise skip
      test.
    """
    file_loc = "/opt/extension"
    cmd = "cd " + file_loc
    file_path = file_loc + "/" + "testFile"
    drbdfs_val = {}
    fs = "extension"

    active_controller = system_helper.get_active_controller_name()

    LOG.tc_step("Determine the space available for extension filesystem")
    drbdfs_val[fs] = storage_helper.get_controllerfs_values(fs)[0]
    LOG.info("Current value of {} is {}".format(fs, drbdfs_val[fs]))

    # get the 91% of the current size
    LOG.info("Will attempt to fill up the space to 90% of fs {} of value of {}".format(fs, drbdfs_val[fs]))
    file_size = int((drbdfs_val[fs] * 0.91) * 1000)
    file_size = str(file_size) + "M"
    cmd1 = "fallocate -l {} testFile".format(file_size)
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.exec_cmd(cmd)
    con_ssh.exec_sudo_cmd(cmd1)
    if not con_ssh.file_exists(file_path=file_path):
        LOG.info("File {} is not created".format(file_path))
        return 0

    # fill_in_fs(size=file_size)
    LOG.tc_step("Verifying that the alarm is created after filling the fs space in {}".format(fs))
    system_helper.wait_for_alarm(alarm_id="100.104", entity_id=active_controller, timeout=600, strict=False)

    # verify the controller is in degraded state
    LOG.tc_step("Verifying controller is degraded after filling the fs space in {}".format(fs))
    system_helper.wait_for_host_values(active_controller, availability='degraded')

    drbdfs_val[fs] = drbdfs_val[fs] + 2

    LOG.info("Will attempt to increase the value of {} to {}".format(fs, drbdfs_val[fs]))

    LOG.tc_step("Increase the size of extension filesystem")
    storage_helper.modify_controllerfs(**drbdfs_val)

    # Need to wait until the change takes effect before checking the
    # filesystems
    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          entity_id="host={}".format(host),
                                          timeout=600)
        LOG.tc_step("Verifying that the alarm is cleared after increasing the fs space in {}".format(fs))
        system_helper.wait_for_alarm_gone(alarm_id="100.104", entity_id="host={}".format(host), timeout=600,
                                          strict=False)

    LOG.tc_step("Confirm the underlying filesystem size matches what is expected")
    storage_helper.check_controllerfs(**drbdfs_val)

    # verify the controller is in available state
    LOG.tc_step("Verifying that the controller is in available state after increasing the fs space in {}".format(fs))
    system_helper.wait_for_host_values(active_controller, availability='available')
