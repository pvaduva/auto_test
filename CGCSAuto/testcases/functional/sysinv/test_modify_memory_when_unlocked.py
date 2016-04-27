###
# US51396_tc04_cannt_modify_unlocked
###

from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3

'''
[wrsroot@controller-1 ~(keystone_admin)]$ system host-memory-modify compute-0 1 -1G 1
Host must be locked.
[wrsroot@controller-1 ~(keystone_admin)]$ echo $?
1
[wrsroot@controller-1 ~(keystone_admin)]$ system host-lock compute-0

'''


# overall skip condition
def less_than_two_hypervisors():
    return len(host_helper.get_hypervisors()) < 2


@mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@mark.parametrize('hostname', [
                  'compute-0 ',
                  'compute-1 '])
def test_modify_memory_when_unlocked(hostname):
    """

    US51396_tc04_cannt_modify_unlocked (53 Cannot modify memory setting when unlocked using CLI)

    Attempt to modify memory when it's unlocked, and ensure it's rejected.

    Args:
        modify_huge_page (str): compute nodes

    Setup:
        - check if there is at least two compute nodes
        - check if the compute node is in unlocked state (TODO)

    Test Steps:
        - modify the huge page on the unlocked compute node
        - make sure it fail as expected

    Teardown:
        - Nothing

    """

    # Check if the node is locked
    LOG.tc_step("Verify that the host is in unlocked state and unlock it if it's not")
    host_helper.unlock_host(hostname,fail_ok=False)

    # execute command
    LOG.tc_step("Try to the modify memory of unlocked host")
    processor = "1 "
    opt_arg = "-2M 4 "
    args = hostname + processor + opt_arg
    exit_code, output = cli.system('host-memory-modify', args, auth_info=Tenant.ADMIN, fail_ok=True)

    # verify result
    LOG.tc_step("Verify host-memory-modify command failed as expected")
    assert exit_code == 1, "Modify host memory before locking the host. expect Fail but Passed"

    # nothing to teardown
    # end tc
