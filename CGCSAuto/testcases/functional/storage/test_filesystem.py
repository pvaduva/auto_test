import re

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

    LOG.info("cgts-vg is currently: {}".format(cgts_vg_val.group(0)))

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

    cmd = "pvs -o vg_name,pv_size --noheadings | grep cgts-vg"
    cgts_vg_regex = "([0-9.]*)g$"

    rc, out = con_ssh.exec_sudo_cmd(cmd)
    new_cgts_vg_val = re.search(cgts_vg_regex, out)

    LOG.info("cgts-vg is currently: {}".format(cgts_vg_val.group(0)))
    assert new_cgts_vg_val <= cgts_vg_val, "cgts-vg size did not increase"


#def test_increase_scratch():
#    """ 
#    This test increases the size of the scratch filesystem.  The scratch
#    filesystem is used for activities such as uploading swift object files,
#    etc.
#
#    """


