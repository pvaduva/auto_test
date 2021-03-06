from utils.horizon.regions import messages
from utils.horizon.pages.project.network import routerspage as project_routerspage
from utils.horizon.pages.admin.network import routerspage as admin_routerspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG
from consts import horizon


@fixture(scope='function')
def routers_pg(admin_home_pg_container, request):
    LOG.fixture_step('Go to Project > Network > Routers')
    router_name = helper.gen_resource_name('router')
    routers_pg = project_routerspage.RoutersPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    routers_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Routers page')
        routers_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return routers_pg, router_name


@fixture(scope='function')
def routers_pg_action(routers_pg, request):
    routers_pg, router_name = routers_pg
    LOG.fixture_step('Create new router {}'.format(router_name))
    routers_pg.create_router(router_name, external_network='external-net0')

    def teardown():
        LOG.fixture_step('Delete router {}'.format(router_name))
        routers_pg.delete_router(router_name)

    request.addfinalizer(teardown)
    return routers_pg, router_name


def test_horizon_router_create(routers_pg):
    """
    Test router creation and deletion functionality:

    Setups:
        - Login as Admin
        - Go to Admin > Network > Routers

    Teardown:
        - Logout

    Test Steps:
        - Create a new router
        - Verify the router appears in the routers table as active
        - Delete the newly created router
        - Verify the router does not appear in the table after deletion
    """
    routers_pg, router_name = routers_pg
    LOG.tc_step('Create new router {} and Verify the router appears in the routers table as active'
                .format(router_name))
    routers_pg.create_router(router_name, external_network='external-net0')
    assert routers_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not routers_pg.find_message_and_dismiss(messages.ERROR)
    assert routers_pg.is_router_present(router_name)
    assert routers_pg.get_router_info(router_name, 'Status') == 'Active'

    LOG.tc_step('Delete router {} and Verify the router does not appear in the table after deletion'
                .format(router_name))
    routers_pg.delete_router_by_row(router_name)
    assert routers_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not routers_pg.find_message_and_dismiss(messages.ERROR)
    assert not routers_pg.is_router_present(router_name)
    horizon.test_result = True


def test_horizon_router_gateway(routers_pg_action):
    """
    Test the gateway set/clear functionality:

    Setups:
        - Login as Admin
        - Go to Project > Network > Routers
        - Create a new router
    Teardown:
        - Logout

    Test Steps:
        - Clear the default gateway of the router
        - Verify the gateway does not appear in the gateway table
        - Set new gateway to the router
        - Verify the new set gateway appears in the gateway table
        - Delete the newly created router
    """
    routers_pg, router_name = routers_pg_action
    
    LOG.tc_step('Clear the default gateway of the router')
    routers_pg.clear_gateway(router_name)
    assert routers_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not routers_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the gateway does not appear in the gateway table')
    assert routers_pg.get_router_info(router_name, 'External Network') == '-'

    LOG.tc_step('Set new gateway to the router')
    routers_pg.set_gateway(router_name, external_network='external-net0')
    assert routers_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not routers_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the new set gateway appears in the gateway table')
    assert routers_pg.get_router_info(router_name, 'External Network') == 'external-net0'
    horizon.test_result = True


def test_horizon_router_add_delete_interface(routers_pg_action):
    """
    Test the router interface creation and deletion functionality:

    Setups:
        - Login as Admin
        - Go to Project > Network > Routers
        - Create a new router

    Teardown:
        - Delete the newly created router
        - Back to Routers page
        - Logout

    Test Steps:
        - Move to the Interfaces page/tab
        - Delete the default interface
        - Verify the interface is no longer in the interfaces table
        - Add a new interface
        - Verify the new interface is in the routers table
    """
    routers_pg, router_name = routers_pg_action
    LOG.tc_step('Move to the Interfaces page/tab')
    router_interfaces_page = routers_pg.go_to_interfaces_page(router_name)

    LOG.tc_step('Delete the default interface and Verify the interface is no longer in the interfaces table')
    interface_name = router_interfaces_page.interfaces_names[0]
    router_interfaces_page.delete_interface(interface_name)
    assert router_interfaces_page.find_message_and_dismiss(messages.SUCCESS)
    assert not router_interfaces_page.find_message_and_dismiss(messages.ERROR)
    assert not router_interfaces_page.is_interface_present(interface_name)

    router_interfaces_page.create_interface()
    assert router_interfaces_page.find_message_and_dismiss(messages.SUCCESS)
    assert not router_interfaces_page.find_message_and_dismiss(messages.ERROR)
    interface_name = router_interfaces_page.interfaces_names[0]
    assert router_interfaces_page.is_interface_present(interface_name)
    assert router_interfaces_page.is_interface_status(interface_name, 'Down')

    LOG.tc_step('Add a new interface and Verify the new interface is in the routers table')
    routers_pg.go_to_target_page()
    horizon.test_result = True


def test_horizon_router_overview_data(routers_pg_action):
    """
    Test the router overview data is correct:

    Setups:
        - Login as Admin
        - Go to Project > Network > Routers
        - Create a new router

    Teardown:
        - Delete the newly created router
        - Back to Routers page
        - Logout

    Test Steps:
        - Create a new router
        - Go to routers overview page and verify info is correct
        - Go to networks overview page and verify info is correct
        - Back to project routers page and Delete the router
    """
    routers_pg, router_name = routers_pg_action
    LOG.tc_step('Go to routers overview page and verify info is correct')
    router_overview_page = routers_pg.go_to_overview_page(router_name)
    assert router_overview_page.is_router_name_present(router_name)
    assert router_overview_page.is_router_status("Active")

    LOG.tc_step('Go to networks overview page and verify info is correct')
    network_overview_page = router_overview_page.go_to_router_network()
    assert network_overview_page.is_network_name_present()
    assert network_overview_page.is_network_status("Active")

    LOG.tc_step('Back to project routers page and Delete router {}'.format(router_name))
    routers_pg.go_to_target_page()
    horizon.test_result = True


def test_horizon_router_admin_edit(routers_pg_action):
    """
    Test admin edit on router:

    Setups:
        - Login as Admin
        - Go to Project > Network > Routers

    Teardown:
        - Logout

    Test Steps:
        - Create a new router
        - Go to Admin > Network > Routers
        - Edit the router name
        - Verify the name is edited successfully
        - Delete the newly created router
    """
    routers_pg, router_name = routers_pg_action
    LOG.tc_step('Go to Admin > Network > Routers')
    admin_routers_page = admin_routerspage.RoutersPage(routers_pg.driver, port=routers_pg.port)
    admin_routers_page.go_to_target_page()
    assert admin_routers_page.is_router_present(router_name)
    assert admin_routers_page.get_router_info(router_name, 'Status') == 'Active'

    LOG.tc_step('Edit the router name')
    new_name = "edited_" + router_name
    admin_routers_page.edit_router(router_name, new_name=new_name)
    assert admin_routers_page.find_message_and_dismiss(messages.SUCCESS)
    assert not admin_routers_page.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the name is edited successfully')
    assert admin_routers_page.is_router_present(new_name)
    assert admin_routers_page.get_router_info(new_name, 'Status') == 'Active'

    admin_routers_page.edit_router(new_name, new_name=router_name)
    horizon.test_result = True
