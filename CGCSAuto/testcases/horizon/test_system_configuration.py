from pytest import fixture

# from consts import lab
from consts import horizon
from utils.tis_log import LOG
from utils.lab_info import get_lab_floating_ip,get_lab_dict
from utils.horizon.pages.admin.platform import systemconfigurationpage
from utils.horizon import helper
from utils.horizon.regions import messages
from testfixtures.horizon import admin_home_pg

@fixture(scope='function')
def sys_config_pg(admin_home_pg, request):
    LOG.fixture_step('Go to Admin > Platform > System Configuration')
    system_configuration_pg = systemconfigurationpage.SystemConfigurationPage(admin_home_pg.driver)
    system_configuration_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to System Configuration page')
        system_configuration_pg.go_to_target_page()

    request.addfinalizer(teardown)

    return system_configuration_pg


def test_system_configuration_details_display(sys_config_pg):

    """
        Test the system configuration and details display:

        Setups:
            - Login as Admin
            - Go to Admin > Platform > System Configuration

        Teardown:
            - Back to System Configuration Page
            - Logout

        Test Steps:
            - Check system details is displayed
            - Check address pools is displayed
            - check DNS is displayed
            - Check NTP is displayed
            - Check OAM is displayed
            - Check filesystem is displayed
    """

    system_name = None
    lab_dict = get_lab_dict(system_name)
    # lab_fip=get_lab_floating_ip()
    # lab_dict=lab.get_lab_dict(lab_fip,key='floating ip')
    system_name=lab_dict['name']
    assert system_name is not None

    LOG.tc_step('Check system details is displayed')
    assert sys_config_pg.is_systems_present(system_name)
    sys_config_pg.edit_system(system_name)
    assert sys_config_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not sys_config_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Check address pools is displayed')
    sys_config_pg.go_to_address_pools_tab()
    address_name = helper.gen_resource_name('address_name')
    sys_config_pg.create_address_pool(name=address_name, network='192.168.0.0/24')
    assert sys_config_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not sys_config_pg.find_message_and_dismiss(messages.ERROR)
    assert sys_config_pg.is_address_present(address_name)
    sys_config_pg.delete_address_pool(address_name)
    assert sys_config_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not sys_config_pg.find_message_and_dismiss(messages.ERROR)
    assert not sys_config_pg.is_address_present(address_name)

    LOG.tc_step('check DNS is displayed')
    sys_config_pg.go_to_dns_tab()
    sys_config_pg.edit_dns()
    assert not sys_config_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Check NTP is displayed')
    sys_config_pg.go_to_ntp_tab()

    LOG.tc_step('Check OAM is displayed')
    sys_config_pg.go_to_oam_ip_tab()

    LOG.tc_step('Check filesystem is displayed')
    sys_config_pg.go_to_controller_filesystem_tab()
    horizon.test_result = True