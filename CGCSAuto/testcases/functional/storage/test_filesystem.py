import re
import math

from pytest import fixture, skip, mark

from consts.auth import Tenant
from consts.cgcs import EventLogID
from keywords import host_helper, system_helper, local_storage_helper
from testfixtures.recover_hosts import HostsToRecover
from utils import cli, table_parser
from utils.tis_log import LOG
from utils.ssh import ControllerClient

@fixture()
def aio_precheck():
    if not system_helper.is_two_node_cpe() and not system_helper.is_simplex:
        skip("Test only applies to AIO-SX or AIO-DX systems")


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


def test_increase_cinder():
    """
    Increase the size of the cinder filesystem.  Note, this requires a host
    reinstall.

    """


def test_increase_ceph_mon():
    """
    Increase the size of ceph-mon.
    """


