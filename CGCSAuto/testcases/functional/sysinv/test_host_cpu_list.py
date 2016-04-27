
from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3


@mark.parametrize('host_name', ['controller-0',
                                'controller-1',
                                'compute-0',
                                'compute-1'])
def test_host_cpu_list(host_name):
    """
    42) Verify that the CPU data can be seen via cli from sysinv_test_plan.pdf

    Verify the version number (or str) exist for the system when execute the "system show" cli

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        -execute "system host-cpu-list" cli
        -verify the table generated contain relevant fields

    Teardown:
        - Nothing

    """

    LOG.tc_step("Verify the system-cpu-list is working for a specific node")
    table_ = table_parser.table(cli.system('host-cpu-list', host_name))
    LOG.tc_step("Check there are 7 columns in the table")
    check_list = ['uuid', 'log_core', 'processor', 'phy_core', 'thread', 'processor_model', 'assigned_function']
    # check if all 7 fields in the table is the same as the check_list provided here.
    assert all(field in check_list for field in table_['headers']), "Expected the table to have 7 columns. " \
                                                                    "However, some are missing"
