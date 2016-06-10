
from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3


# overall skip condition
def less_than_two_hypervisors():
    return len(host_helper.get_hypervisors()) < 2


@mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@fixture(scope='module')
def modify_huge_page(request):
    # setup up huge page on compute-1


    hostname = request.param[0]
    processor = request.param[1]
    page_config = request.param[2]
    host_processor = hostname + processor

    # get info before huge page changes
    table_ = table_parser.table(cli.system('host-memory-show', host_processor))
    two_m_pages = table_parser.get_value_two_col_table(table_, 'VM  Huge Pages (2M): Total')
    one_g_pages = table_parser.get_value_two_col_table(table_, 'VM  Huge Pages (1G): Total')
    LOG.info('Before Modification processor:{} have {} 2M pages, {} 1G pages'.format(processor,two_m_pages,one_g_pages))

    host = {'hostname': hostname,
            'processor': processor,
            'huge_page': page_config,
            }

    # have a section that set huge_page memory back to where it was before
    # but it's gonna double the running time due to lock/edit/unlock host
    def reset_huge_page():
        host_helper.lock_host(hostname)
        # a way to find how many huge page was there before
        args = hostname + processor + "-2M " + two_m_pages + " -1G " + one_g_pages
        cli.system('host-memory-modify', args, auth_info=Tenant.ADMIN, fail_ok=False)
        host_helper.unlock_host(hostname)
    request.addfinalizer(reset_huge_page)

    return host


@mark.parametrize('modify_huge_page', [["compute-1 ", "1 ", "-2M 0 -1G 4"]], indirect=True)
def test_valid_huge_page_input(modify_huge_page):
    """
    US51396_tc02_setting_num_hugepages_cli (50 Modify number of hugepages using CLI in sysinv testplan)
    change huge page number in a compute node and verify that it show up correctly after modification

    Args:
        modify_huge_page (list): A host that takes in infos on [name,processor and hugepage]

    Setup:
        - check if there is at least two compute nodes

    Test Steps:
        - lock compute node
        - modify the huge page on the locked compute node
        - unlock the compute node
        - compare the huge page number with the the expected huge page number

    Teardown:
        - Might be good idea to reset the host memory to what it was before

    """

    hostname = modify_huge_page['hostname']
    processor = modify_huge_page['processor']
    expected_huge_page = modify_huge_page['huge_page']
    args = hostname + processor + expected_huge_page
    show_args = hostname + processor

    LOG.tc_step('This Test will take 10min+ to execute as it lock, modify and unlock a compute node. ')
    # lock the node
    LOG.tc_step('Try to lock the host')
    host_helper.lock_host(hostname)

    # config the page number after lock the compute node
    LOG.tc_step('Try to modify host memory after locking the host')
    cli.system('host-memory-modify', args, auth_info=Tenant.ADMIN, fail_ok=False)

    # unlock the node
    LOG.tc_step('Try to unlock the host')
    host_helper.unlock_host(hostname)

    LOG.tc_step("Using system host-memory-show to retrieve update Hugepage infos")
    table_ = table_parser.table(cli.system('host-memory-show', show_args, auth_info=Tenant.ADMIN, fail_ok=False))
    actual_huge_page = table_parser.get_value_two_col_table(table_, 'VM  Huge Pages (1G): Total')

    LOG.tc_step("Verify actual HugePage number equal to expected HugePage number")
    assert expected_huge_page[-1] == actual_huge_page, "Expect {} HugePages . Actual {} HugePages".format(
        expected_huge_page[-1], actual_huge_page)

    # end tc


@mark.parametrize('modify_huge_page', [["compute-1 ", "0 ", "-2M 999999 -1G 99999"],
                                       ["compute-1 ", "0 ", "-2M asdf -1G asdf"]], indirect=True)
def test_invalid_huge_page_input(modify_huge_page):
    """
    (55 Invalid inputs for number of hugepages will be rejected GUI in sysinv testplan)
    given invalid huge page number in a compute node and verify that it failed after modification

    Args:
        modify_huge_page (list): A host that takes in infos on [name,processor and hugepage]

    Setup:
        - check if there is at least two compute nodes

    Test Steps:
        - lock compute node
        - modify the huge page on the locked compute node
        - unlock the compute node
        - compare the huge page number with the the expected huge page number

    Teardown:
        - Might be good idea to reset the host memory to what it was before

    """
    hostname = modify_huge_page['hostname']
    processor = modify_huge_page['processor']
    expected_huge_page = modify_huge_page['huge_page']
    args = hostname + processor + expected_huge_page

    print(modify_huge_page)

    LOG.tc_step('This Test will take 10min+ to execute as it lock, modify and unlock a compute node. ')
    # lock the node
    LOG.tc_step('Try to lock the host')
    host_helper.lock_host(hostname)

    # config the page number after lock the compute node
    LOG.tc_step('Try to modify host memory after locking the host')
    err,output = cli.system('host-memory-modify', args, auth_info=Tenant.ADMIN, fail_ok=True)

    # unlock the node
    LOG.tc_step('Try to unlock the host')
    host_helper.unlock_host(hostname)

    LOG.tc_step("Verify actual HugePage number failed")
    assert err == 1, "Expected Huge Page CLI to Fail. However, it passed"

    # end tc




