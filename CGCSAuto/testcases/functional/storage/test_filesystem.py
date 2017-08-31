import ast
import re
import math

from pytest import fixture, skip, mark

from consts.auth import Tenant
from consts.cgcs import EventLogID
from keywords import host_helper, system_helper, local_storage_helper, install_helper
from testfixtures.recover_hosts import HostsToRecover
from utils import cli, table_parser
from utils.tis_log import LOG
from utils.ssh import ControllerClient

@fixture()
def aio_precheck():
    if not system_helper.is_two_node_cpe() and not system_helper.is_simplex:
        skip("Test only applies to AIO-SX or AIO-DX systems")

@fixture()
def lvm_precheck():
    if system_helper.is_simplex() or system_helper.is_storage_system():
        skip("Test does not apply to AIO-SX systems or storage systems")

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

    LOG.info("Determine the available free space on the system")
    big_value = "1000000"
    free_space_regex = "([\-0-9.]*) GiB\.$"
    cmd = "system controllerfs-modify scratch {}".format(big_value)
    rc, out = con_ssh.exec_cmd(cmd, fail_ok=True)
    free_space_match = re.search(free_space_regex, out)
    free_space = free_space_match.group(1)

    LOG.info("Available free space on the system is: {}".format(free_space))

    if int(free_space) <= 0:
        skip("Not enough free space to complete test.")
    else:
        LOG.tc_step("Increase the size of the scratch filesystem")
        new_scratch = math.trunc(int(free_space) / 10) + int(scratch)
        cmd = "system controllerfs-modify scratch {}".format(new_scratch)
        rc, out = con_ssh.exec_cmd(cmd)

    table_ = table_parser.table(cli.system('controllerfs-show scratch'))
    new_scratch = table_parser.get_value_two_col_table(table_, 'size')
    LOG.info("scratch is now: {}".format(new_scratch))
    assert int(new_scratch) > int(scratch), "scratch size did not increase"

    LOG.info("Wait for alarms to clear")
    hosts = system_helper.get_controllers()
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                        entity_id="host={}".format(host))

    LOG.tc_step("Attempt to decrease the size of the scratch filesystem")
    decreased_scratch = int(new_scratch) - 1
    cmd = "system controllerfs-modify scratch {}".format(decreased_scratch)
    rc, out = con_ssh.exec_cmd(cmd, fail_ok=True)
    table_ = table_parser.table(cli.system('controllerfs-show scratch'))
    final_scratch = table_parser.get_value_two_col_table(table_, 'size')
    LOG.info("scratch is currently {}".format(final_scratch))
    assert int(final_scratch) != int(decreased_scratch), \
        "scratch was unexpectedly decreased from {} to {}".format(new_scratch, final_scratch)


@mark.usefixtures("lvm_precheck")
def _test_increase_cinder():
    """
    Increase the size of the cinder filesystem.  Note, this requires a host
    reinstall of both nodes.

    This test does not apply to AIO-SX systems since cinder will default to max
    size.  This also doesn't apply to storage systems since cinder is stored
    in the rbd backend.
    """

    install_output_dir = "/tmp/fdsa/"

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

    LOG.tc_step("Lock the standby controller")
    act_cont = system_helper.get_active_controller_name()

    # For simplicitly, start with controller-1
    if act_cont == "controller-1":
        host_helper.swact_host(act_cont)

    host = system_helper.get_standby_controller_name()
    host_helper.lock_host(host)
    cmd = "system host-reinstall {}".format(host)
    rc, out = con_ssh.exec_cmd(cmd)
    host_helper.wait_for_host_states(host, timeout=HostTimeout.UPGRADE)

    host_helper.swact_host("controller-0")
    host = system_helper.get_standby_controller_name()
    host_helper.lock_host(host)
    mgmt_interface = install_helper.get_mgmt_boot_device(host)
    console = install_helper.open_vlm_console_thread(host, mgmt_interface)
    bring_node_console_up(host, mgmt_interface, install_output_dir, close_telnet_conn=True)
    cmd = "system host-reinstall {}".format(host)
    rc, out = con_ssh.exec_cmd(cmd)
    
    # No how to do controller-0.  It would pxeboot from tuxlab by default.
    # ipmitool (wildcat only) or port installer code over.


def _test_increase_ceph_mon():
    """
    Increase the size of ceph-mon.  Only applicable to a storage system.
    """

    ceph_mon_gib_max = 40

    table_ = table_parser.table(cli.system("system ceph-mon-list"))
    ceph_mon_gib = table_parser.get_values(table_, "ceph_mon_gib", **{"hostname": "controller-0"})
    LOG.info("ceph_mon_gib is currently: {}".format(ceph_mon_gib))

    if int(ceph_mon_gib) == 40:
        skip("Insufficient disk space to execute test")

    LOG.tc_step("Increase ceph_mon_gib to maximum value")
    hosts = system_helper.get_controllers()
    for host in hosts:
        cmd = "system ceph-mon-modify {} ceph_mon_gib={}".format(host, ceph_mon_gib_max)
        
    for host in hosts:
        system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                     entity_id="host={}".format(host))

    standby = system_helper.get_standby_controller_name()
    active = system_helper.get_active_controller_name()
    host_helper.lock_host(standby)
    host_helper.unlock_host(standby)
    host_helper.swact_host(active)
    host_helper.lock_host(active)
    host_helper.unlock_host(active)
    
    for host in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          entity_id="host={}".format(host))

