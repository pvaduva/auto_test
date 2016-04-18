###
# US51396_tc02_setting_num_hugepages_cli
###

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
    # setup up 3 1G huge page on compute-1
    LOG.info('This Test will take 10min+ to execute as it lock, modify and unlock a compute node. ')
    hostname = 'compute-1 '
    processor = "1 "
    page_config = "-2M 0 -1G 3"
    args = hostname + processor + page_config
    # lock the node
    LOG.info('Try to lock the host')
    host_helper.lock_host(hostname)

    # config the page number after lock the compute node
    LOG.info('Try to modify host memory after locking the host')
    edited_table_ = table_parser.table( cli.system('host-memory-modify', args, auth_info=Tenant.ADMIN, fail_ok=False))

    # unlock the node
    LOG.info('Try to unlock the host')
    host_helper.unlock_host(hostname)

    host = {'hostname': hostname,
            'processor': processor,
            'huge_page': page_config[-1]
            }

    # have a section that set huge_page memory back to where it was before
    # but it's gonna double the running time due to lock/edit/unlock host
    # def reset_huge_page():
    #    host_helper.lock_host(hostname)
    #    # a way to find how many huge page was there before
    #    args = hostname + processor + "-2M 2000 -1G 0 "
    #    exit_code, output = cli.system('host-memory-modify', args, auth_info=Tenant.ADMIN, fail_ok=False)
    #    host_helper.unlock_host(hostname)
    # request.addfinalizer(delete_flavor_vm)

    return host


def test_huge_page_created(modify_huge_page):

    hostname = modify_huge_page['hostname']
    processor = modify_huge_page['processor']
    expected_huge_page = modify_huge_page['huge_page']
    args = hostname+''+processor
    # args = 'compute-2 0'
    LOG.tc_step("Using system host-memory-show to retrieve update Hugepage infos")
    table_ = table_parser.table(cli.system('host-memory-show', args, auth_info=Tenant.ADMIN, fail_ok=False))
    actual_huge_page = table_parser.get_value_two_col_table(table_, 'VM  Huge Pages (1G): Total')

    LOG.tc_step("Verify actual HugePage number equal to expected HugePage number")
    assert expected_huge_page == actual_huge_page, "Expect {} HugePages . Actual {} HugePages".format(
        expected_huge_page, actual_huge_page)

    # end tc

