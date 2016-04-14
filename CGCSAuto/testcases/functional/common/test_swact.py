###
# TC451 TiS_Mapping_AutomatedTests_v2.xlsx
###

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from keywords import host_helper
from setup_consts import P1, P2, P3


# @mark.usefixtures('check_vms', 'ping_vms_from_nat', 'ping_vm_from_vm')
@mark.usefixtures('check_vms')
def test_swact_with_vms():
    LOG.tc_step('retrieve active and available controllers')
    num_controllers = len(host_helper.get_hosts(availability='available', personality='controller',
                                                administrative='unlocked', operational='enabled'))

    LOG.tc_step('execute swact cli')
    exit_code, output = host_helper.swact_host(fail_ok=True)

    # test check if there is less than 2 controller
    LOG.tc_step('verify test result')
    if num_controllers < 2:
        assert exit_code == 1, "Controllers less than TWO: expect FAIL but PASSED "
    else:
        assert exit_code == 0
