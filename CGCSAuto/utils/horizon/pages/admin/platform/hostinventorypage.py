from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables

class HostsTable(tables.TableRegion):

    @tables.bind_row_action('update')
    def edit_host(self, edit_button, row):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.TabbedFormRegion(self.driver,
                                      field_mappings=self.EDIT_HOST_FORM_FIELDS)

    @tables.bind_row_action('lock')
    def lock_host(self, lock_button, row):
        lock_button.click()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_row_action('unlock')
    def unlock_host(self, unlock_button, row):
        unlock_button.click()


class ControllerHostsTable(HostsTable):

    EDIT_HOST_FORM_FIELDS = (("personality", "subfunctions", "hostname", "location",
                              "cpuProfile", "interfaceProfile", "diskProfile", "memoryProfile", "ttys_dcd"),
                             ("boot_device", "rootfs_device", "install_output", "console"),
                             ("bm_type", "bm_ip", "bm_username", "bm_password", "bm_confirm_password"))

    name = 'hostscontroller'

    @tables.bind_row_action('swact')
    def swact_host(self, swact_button, row):
        swact_button.click()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_table_action('create')
    def add_host(self, add_button):
        add_button.click()
        self.wait_till_spinner_disappears()
        return forms.TabbedFormRegion(self.driver,
                                      field_mappings=self.ADD_HOST_FORM_FIELDS)


class ComputeHostsTable(HostsTable):
    name = 'hostscompute'

    EDIT_HOST_FORM_FIELDS = (("personality", "location", "cpuProfile", "interfaceProfile", "ttys_dcd"),
                             ("boot_device", "rootfs_device", "install_output", "console"),
                             ("bm_type", "bm_ip", "bm_username", "bm_password", "bm_confirm_password"))

    @tables.bind_table_action('install-async')
    def install_paches(self, install_button):
        install_button.click()


class HostInventoryPage(basepage.BasePage):

    PARTIAL_URL = 'admin/inventory'

    HOSTS_TABLE_NAME_COLUMN = 'Host Name'
    HOSTS_TABLE_PERSONALITY_COLUMN = 'Personality'
    HOSTS_TABLE_ADMIN_STATE_COLUMN = 'Admin State'
    HOSTS_TABLE_OPERATIONAL_STATE_COLUMN = 'Operational State'
    HOSTS_TABLE_AVAILABILITY_STATE_COLUMN = 'Availability State'
    HOSTS_TABLE_UPTIME_COLUMN = 'Uptime'
    HOSTS_TABLE_STATUS_COLUMN = 'Status'

    def __init__(self, driver):
        super(HostInventoryPage, self).__init__(driver)
        self._page_title = "HostInventory"

    def _get_row_with_host_name(self, name):
        return self.hosts_table(name).get_row(
            self.HOSTS_TABLE_NAME_COLUMN, name)

    def hosts_table(self, name):
        if 'controller' in name:
            return ControllerHostsTable(self.driver)
        elif 'compute' in name:
            return ComputeHostsTable(self.driver)

    def edit_host(self, name):
        row = self._get_row_with_host_name(name)
        host_edit_form = self.hosts_table(name).edit_host(row)
        # ...
        host_edit_form.submit()

    def lock_host(self, name):
        row = self._get_row_with_host_name(name)
        confirm_form = self.hosts_table(name).lock_host(row)
        confirm_form.submit()

    def unlock_host(self, name):
        row = self._get_row_with_host_name(name)
        self.hosts_table(name).unlock_host(row)

    def is_host_present(self, name):
        return bool(self._get_row_with_host_name(name))

    def is_host_admin_state(self, name, state):
        def cell_getter():
            row = self._get_row_with_host_name(name)
            return row and row.cells[self.HOSTS_TABLE_ADMIN_STATE_COLUMN]

        return bool(self.hosts_table(name).wait_cell_status(cell_getter, state))

    def is_host_availability_state(self, name, state):
        def cell_getter():
            row = self._get_row_with_host_name(name)
            return row and row.cells[self.HOSTS_TABLE_AVAILABILITY_STATE_COLUMN]

        return bool(self.hosts_table(name).wait_cell_status(cell_getter, state))
