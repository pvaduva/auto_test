from selenium.common import exceptions

from selenium.webdriver.common import by

from utils.horizon.pages import basepage
from utils.horizon.pages.project.network.routerinterfacespage import RouterInterfacesPage
from utils.horizon.pages.project.network.routeroverviewpage import RouterOverviewPage
from utils.horizon.regions import forms
from utils.horizon.regions import tables
from time import sleep


class RoutersTable(tables.TableRegion):
    name = "routers"
    CREATE_ROUTER_FORM_FIELDS = ("name", "admin_state_up",
                                 "external_network")
    SET_GATEWAY_FORM_FIELDS = ("network_id",)

    @tables.bind_table_action('create')
    def create_router(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.CREATE_ROUTER_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_router(self, delete_button):
        delete_button.click()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_row_action('clear')
    def clear_gateway(self, clear_gateway_button, row):
        clear_gateway_button.click()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_row_action('setgateway')
    def set_gateway(self, set_gateway_button, row):
        set_gateway_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.SET_GATEWAY_FORM_FIELDS)


class RoutersPage(basepage.BasePage):

    PARTIAL_URL = 'project/routers'
    DEFAULT_ADMIN_STATE_UP = 'True'
    DEFAULT_EXTERNAL_NETWORK = 'external-net0'
    ROUTERS_TABLE_NAME_COLUMN = 'Name'
    ROUTERS_TABLE_STATUS_COLUMN = 'Status'
    ROUTERS_TABLE_NETWORK_COLUMN = 'External Network'

    _interfaces_tab_locator = (by.By.CSS_SELECTOR,
                               'a[href*="tab=router_details__interfaces"]')

    def __init__(self, driver):
        super(RoutersPage, self).__init__(driver)
        self._page_title = "Routers"

    def _get_row_with_router_name(self, name):
        return self.routers_table.get_row(
            self.ROUTERS_TABLE_NAME_COLUMN, name)

    @property
    def routers_table(self):
        return RoutersTable(self.driver)

    def create_router(self, name, admin_state_up=DEFAULT_ADMIN_STATE_UP,
                      external_network=DEFAULT_EXTERNAL_NETWORK):
        create_router_form = self.routers_table.create_router()
        create_router_form.name.text = name
        create_router_form.admin_state_up.value = admin_state_up
        create_router_form.external_network.text = external_network
        create_router_form.submit()

    def set_gateway(self, router_id,
                    network_name=DEFAULT_EXTERNAL_NETWORK):
        row = self._get_row_with_router_name(router_id)

        set_gateway_form = self.routers_table.set_gateway(row)
        set_gateway_form.network_id.text = network_name
        set_gateway_form.submit()

    def clear_gateway(self, name):
        row = self._get_row_with_router_name(name)
        confirm_clear_gateway_form = self.routers_table.clear_gateway(row)
        confirm_clear_gateway_form.submit()

    def delete_router(self, name):
        row = self._get_row_with_router_name(name)
        row.mark()
        confirm_delete_routers_form = self.routers_table.delete_router()
        confirm_delete_routers_form.submit()

    def is_router_present(self, name):
        return bool(self._get_row_with_router_name(name))

    def is_router_active(self, name):
        row = self._get_row_with_router_name(name)

        def cell_getter():
            return row.cells[self.ROUTERS_TABLE_STATUS_COLUMN]
        try:
            self._wait_till_text_present_in_element(cell_getter, 'Active')
        except exceptions.TimeoutException:
            return False
        return True

    def is_gateway_cleared(self, name):
        row = self._get_row_with_router_name(name)

        def cell_getter():
            return row.cells[self.ROUTERS_TABLE_NETWORK_COLUMN]
        try:
            self._wait_till_text_present_in_element(cell_getter, '-')
        except exceptions.TimeoutException:
            return False
        return True

    def is_gateway_set(self, name, network_name=DEFAULT_EXTERNAL_NETWORK):
        row = self._get_row_with_router_name(name)

        def cell_getter():
            return row.cells[self.ROUTERS_TABLE_NETWORK_COLUMN]
        try:
            self._wait_till_text_present_in_element(cell_getter, network_name)
        except exceptions.TimeoutException:
            return False
        return True

    def go_to_interfaces_page(self, name):
        self._get_element(by.By.LINK_TEXT, name).click()
        self._get_element(*self._interfaces_tab_locator).click()
        return RouterInterfacesPage(self.driver,  name)

    def go_to_overview_page(self, name):
        self._get_element(by.By.LINK_TEXT, name).click()
        return RouterOverviewPage(self.driver, name)
