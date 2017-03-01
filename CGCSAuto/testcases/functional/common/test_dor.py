import time
import multiprocessing as mp
from multiprocessing import Process

from utils.tis_log import LOG
from utils import local_host
from consts.timeout import HostTimeout
from consts.vlm import VlmAction
from keywords import system_helper, vlm_helper, host_helper, vm_helper
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module

START_POWER_CUT = False


def power_off_and_on(barcode):
    while True:
        if START_POWER_CUT:
            rc, output = local_host.vlm_exec_cmd(VlmAction.VLM_TURNOFF, barcode, reserve=False)
            assert '1' == str(output), "Failed to turn off target"
            return


def test_dead_office_recovery(reserve_unreserve_all_hosts_module):
    hosts = system_helper.get_hostnames()

    barcodes = vlm_helper.get_barcodes_from_hostnames(hosts)
    new_ps = []
    for barcode in barcodes:
        new_p = Process(power_off_and_on, args=barcode)
        new_ps.append(new_p)
        new_p.start()
    global START_POWER_CUT
    START_POWER_CUT = True

    for p in new_ps:
        p.join(timeout=300)

    LOG.tc_step("Wait for 30 seconds before powering on")
    time.sleep(30)

    vlm_helper.power_on_hosts(hosts, reserve=False, reconnect_timeout=HostTimeout.REBOOT+120)
