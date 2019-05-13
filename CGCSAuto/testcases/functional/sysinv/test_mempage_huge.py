import random
from pytest import fixture, mark

from utils import cli, table_parser
from utils.tis_log import LOG

from keywords import host_helper, system_helper
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='function', autouse=True)
def check_alarms():
    pass


@fixture(scope='module')
def get_host():
    if system_helper.is_two_node_cpe():
        hostname = system_helper.get_standby_controller_name()
    else:
        hostname = host_helper.get_up_hypervisors()[0]

    return hostname


def test_modify_memory_when_unlocked_negative(get_host):
    """

    US51396_tc04_cannt_modify_unlocked (53 Cannot modify memory setting when unlocked using CLI)

    Attempt to modify memory when it's unlocked, and ensure it's rejected.

    Setup:
        - check if there is at least two compute nodes
        - check if the compute node is in unlocked state (TODO)

    Test Steps:
        - modify the huge page on the unlocked compute node
        - make sure it fail as expected

    Teardown:
        - Nothing

    """
    hostname = get_host

    LOG.tc_step("Attempt to the modify memory of unlocked host")
    args = "-2M 4 {} 1".format(hostname)
    exit_code, output = cli.system('host-memory-modify', args, fail_ok=True, rtn_code=True)

    LOG.tc_step("Verify host-memory-modify command rejected when host is unlocked")
    assert exit_code == 1, "system host-memory-modify is not rejected when {} is unlocked".format(hostname)


# @fixture(scope='module')
# def host_to_modify(request):
#     hypervisors = host_helper.get_hypervisors()
#
#     if system_helper.is_two_node_cpe():
#         hostname = system_helper.get_standby_controller_name()
#     else:
#         hostname = hypervisors[0]
#
#     pre_mem_tab = system_helper.get_host_mem_list(host=hostname)
#     pre_procs = table_parser.get_column(pre_mem_tab, 'processor')
#     pre_2m_pages = table_parser.get_column(pre_mem_tab, 'vm_hp_total_2M')
#     pre_1g_pages = table_parser.get_column(pre_mem_tab, 'vm_hp_total_1G')
#
#     HostsToRecover.add(hostname, scope='module')
#
#     def reset_huge_page():
#
#         LOG.fixture_step("Lock host and revert huge pages to original setting")
#         host_helper.lock_host(hostname)
#
#         for i in range(len(pre_procs)):
#             args = "{} {} -2M {} -1G {}".format(hostname, pre_procs[i], pre_2m_pages[i], pre_1g_pages[i])
#             cli.system('host-memory-modify', args, fail_ok=False)
#
#         LOG.fixture_step("Unlock host after reverting huge pages")
#         host_helper.unlock_host(hostname, check_hypervisor_up=True)
#
#     request.addfinalizer(reset_huge_page)
#
#     return hostname
#
#
# # Remove below test - already covered by nova mem config tests
# @mark.parametrize(('proc', 'huge_pages'), [
#     (1, 4)
# ])
# def _test_modify_hugepages_positive(host_to_modify, proc, huge_pages):
#     """
#     US51396_tc02_setting_num_hugepages_cli (50 Modify number of hugepages using CLI in sysinv testplan)
#     change huge page number in a compute node and verify that it show up correctly after modification
#
#     Setup:
#         - check if there is at least two compute nodes
#
#     Test Steps:
#         - lock compute node
#         - modify the huge page on the locked compute node
#         - unlock the compute node
#         - compare the huge page number with the the expected huge page number
#
#     Teardown:
#         - Might be good idea to reset the host memory to what it was before
#
#     """
#     LOG.tc_step('Lock the host')
#     host_helper.lock_host(host_to_modify)
#     HostsToRecover.add(host_to_modify)
#
#     # config the page number after lock the compute node
#     LOG.tc_step('Modify host memory with {} 1G pages'.format(huge_pages))
#     system_helper.set_host_1g_pages(host_to_modify, proc, hugepage_num=huge_pages)
#
#     # unlock the node
#     LOG.tc_step('Ensure host can be unlocked after modifying huge pages')
#     host_helper.unlock_host(host_to_modify, check_hypervisor_up=True)
#
#     LOG.tc_step("Check Hugepage numbers modified successfully post unlock")
#     memshow_tab = system_helper.get_host_memory_values(host_to_modify, proc)
#     actual_huge_page = int(table_parser.get_value_two_col_table(memshow_tab, 'VM  Huge Pages (1G): Total'))
#
#     assert huge_pages == actual_huge_page, "Expected huge pages: {}; actual: {}".format(huge_pages, actual_huge_page)


class TestHugepageNegative:

    @mark.parametrize(('proc', 'pages'), [
        (0, '-2M 999999 -1G 99999'),
        (1, '-2M asdf -1G asdf'),
    ])
    def test_invalid_huge_page_input(self, get_host, proc, pages):
        """
        (55 Invalid inputs for number of hugepages will be rejected GUI in sysinv testplan)
        given invalid huge page number in a compute node and verify that it failed after modification

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
        host_to_modify = get_host

        LOG.tc_step("Lock host")
        HostsToRecover.add(host_to_modify, scope='class')
        host_helper.lock_host(host_to_modify)

        # config the page number after lock the compute node
        LOG.tc_step('Attempt to modify host memory with invalid page input and ensure it is rejected')
        args = "{} {} {}".format(host_to_modify, proc, pages)
        code, output = cli.system('host-memory-modify', args, fail_ok=True, rtn_code=True)

        assert 1 == code, "host-memory-modify allows invalid args: {}".format(args)
