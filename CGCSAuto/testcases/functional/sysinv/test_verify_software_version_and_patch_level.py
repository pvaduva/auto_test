###
# Testcase 14 of the 2016-04-04 sysinv_test_plan.pdf
# Get the information of the Software Version and Patch Level using CLI
###

from utils import cli
from utils import table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG


def test_verify_software_version():
    """
    Verify the version number (or str) exist for the system when execute the "system show" cli

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        -execute "system show" clivalue
        -verify a string is listed under value for 'software_version' row

    Teardown:
        - Nothing

    """
    LOG.tc_step("Verify the software_version row exist under 'system show' cli with none empty string")
    table_ = table_parser.table(cli.system('show'))
    sys_version = table_parser.get_value_two_col_table(table_, 'software_version')
    assert sys_version, "Expect system version to be a string but is actually Empty"


def test_verify_patch_level():
    """
    since if there are no patch in the patch query under cli "sudo sw-patch query", only empty rows are displayed
    Therefore, this test will only verify the existence of cli "sudo sw-patch query"

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        -verify that "sudo sw-patch query" can be executed with no error output

    Teardown:
        - Nothing

    """
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Verify 'sudo sw-patch query' can be executed with no error output")
    code, output = con_ssh.exec_sudo_cmd(cmd='sw-patch query')
    assert code == 0, "Expect 'sudo sw-patch query' to be executed. Actual return error: {} and " \
                      "output: {} ".format(code, output)
