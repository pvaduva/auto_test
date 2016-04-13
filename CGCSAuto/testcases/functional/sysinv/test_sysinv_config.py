from keywords import system_helper
from consts.cgcs import SystemType
from utils import cli, table_parser
from utils.tis_log import LOG
from setup_consts import LAB_NAME
from consts.auth import Tenant

def test_system_type():
    """
    Verify the System Type can be retrieved and is correct

    Args:

    Test setups:

    Skip conditions:

    Returns:

    """

    LOG.tc_step('Determine the real System Type for {}'.format(LAB_NAME))
    if system_helper.is_small_footprint():
        expt_system_type = SystemType.CPE
    else:
        expt_system_type = SystemType.STANDARD

    LOG.tc_step('Get System Type from system inventory')
    table_ = table_parser.table(cli.system('show'))
    displayed_system_type = table_parser.get_value_two_col_table(table_, 'system_type')

    LOG.tc_step('Verify the expected System Type is the same as that from System Inventory')
    assert displayed_system_type == expt_system_type, 'Expected system_type is: {}; Displayed system type: {}.'.\
        format(expt_system_type, displayed_system_type)


def test_system_type_is_readonly():
    """
    Verify System Type is readonly

    Args:

    Test setups:

    Skip conditions:

    Returns:

    """

    LOG.tc_step('Determine the real System Type for {}'.format(LAB_NAME))
    if system_helper.is_small_footprint():
        cur_system_type = SystemType.CPE
    else:
        cur_system_type = SystemType.STANDARD

    LOG.tc_step('Attempt to modify System Type')
    change_to_system_type = SystemType.CPE
    if cur_system_type == SystemType.CPE:
        change_to_system_type = SystemType.STANDARD
    code, msg = system_helper.set_system_info(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN,
                                              system_type='"' + change_to_system_type + '"')

    LOG.tc_step('Attempt to modify System Type to {}, expecting been rejectecd'.format(change_to_system_type))
    LOG.info('attempt to modify System Type and got {} {}'.format(code, msg))
    assert code == 1, msg
