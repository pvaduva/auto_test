import re
from decimal import Decimal

from pytest import mark

from consts.stx import UUID
from keywords import system_helper
from utils import cli, table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


@mark.p3
def test_system_host_cpu_list():
    """
    42) Verify that the CPU data can be seen via cli from sysinv_test_plan.pdf

    Test Steps:
        -execute "system host-cpu-list" cli
        -verify the table generated contain relevant fields

    """

    hosts = system_helper.get_hosts()

    for host in hosts:
        LOG.tc_step("Verify the system host-cpu-list output table contains the expected headers.")
        table_ = table_parser.table(cli.system('host-cpu-list', host)[1])
        LOG.tc_step("Check there are 7 columns in the table")
        expt_sub_headers = ['uuid', 'log_core', 'processor', 'phy_core', 'thread', 'processor_model',
                            'assigned_function']

        # check if all 7 fields in the table is the same as the check_list provided here.
        actual_headers = table_['headers']
        assert set(expt_sub_headers) <= set(actual_headers), \
            "Expected headers to be included: {}; Actual headers: {}".format(expt_sub_headers, actual_headers)


@mark.p3
def test_system_show():
    table_ = table_parser.table(cli.system('show')[1])
    expt_sub_fields = ['name', 'system_type', 'description', 'software_version', 'uuid', 'created_at', 'updated_at']

    LOG.tc_step("Check 'system show' contains expected fields")
    actual_fields = table_parser.get_column(table_, 'Property')
    assert set(expt_sub_fields) <= set(actual_fields), "Some expected fields are not included in system show table."

    LOG.tc_step("Check 'system show' software version")
    software_version = table_parser.get_value_two_col_table(table_, 'software_version')
    assert Decimal(software_version) >= 16.00, "Software version should be no smaller than 16.00"

    LOG.tc_step("Check 'system show' uuid in expected format")
    uuid = table_parser.get_value_two_col_table(table_, 'uuid')
    assert re.match(UUID, uuid), "Actual uuid is not in expected uuid format"


@mark.p3
def test_patch_query():
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Check 'sudo sw-patch query' contains expected headers")
    output = con_ssh.exec_sudo_cmd(cmd='sw-patch query', fail_ok=False)[1]
    assert re.search(u'Patch ID\s+RR\s+Release\s+ Patch State\s+', output)
