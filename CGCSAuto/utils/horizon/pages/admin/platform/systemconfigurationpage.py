from utils.horizon.pages import basepage
from utils.horizon.regions import tables
from utils.horizon.regions import forms


class SystemsTable(tables.TableRegion):
    name = "systems"

    EDIT_SYSTEM_FORM_FIELDS = ("name", "description")

    @tables.bind_row_action('update')
    def edit_system(self, edit_button, row):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.EDIT_SYSTEM_FORM_FIELDS)


class AddressPoolsTable(tables.TableRegion):
    name = "address_pools"

    ADDRESS_POOL_FORM_FIELDS = ("name", "network", "order", "ranges")

    @tables.bind_table_action('create')
    def create_address_pool(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.ADDRESS_POOL_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_address_pool(self, delete_button):
        delete_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_row_action('update')
    def update_address_pool(self, update_button, row):
        update_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.ADDRESS_POOL_FORM_FIELDS)


class DNSTable(tables.TableRegion):
    name = "cdns_table"

    EDIT_DNS_FORM_FIELDS = ("NAMESERVER_1", "NAMESERVER_2", "NAMESERVER_3")

    @tables.bind_table_action('update_cdns')
    def edit_dns(self, edit_button):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.EDIT_DNS_FORM_FIELDS)


class NTPTable(tables.TableRegion):
    name = "cntp_table"

    EDIT_NTP_FORM_FIELDS = ("NTP_SERVER_1", "NTP_SERVER_2", "NTP_SERVER_3")

    @tables.bind_table_action('update_cntm')
    def edit_ntp(self, edit_button):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.EDIT_NTP_FORM_FIELDS)


class PTPTable(tables.TableRegion):
    name = "cptp_table"

    EDIT_PTP_FORM_FIELDS = ("NTP_SERVER_1", "NTP_SERVER_2", "NTP_SERVER_3")

    @tables.bind_table_action('update_cntm')
    def edit_ptp(self, edit_button):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.EDIT_NTP_FORM_FIELDS)


class OAMTable(tables.TableRegion):
    name = "coam_table"

    EDIT_OAM_FORM_FIELDS = ("EXTERNAL_OAM_SUBNET", "EXTERNAL_OAM_GATEWAY_ADDRESS",
                            "EXTERNAL_OAM_FLOATING_ADDRESS", "EXTERNAL_OAM_0_ADDRESS",
                            "EXTERNAL_OAM_1_ADDRESS")

    @tables.bind_table_action('update_coam')
    def edit_oam(self, edit_button):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.EDIT_NTP_FORM_FIELDS)


class StorageTable(tables.TableRegion):
    name = "storage_table"

    EDIT_FILESYSTEM_FORM_FIELDS = ("database", "cgcs", "backup", "scratch",
                                   "extension", "img_conversions")

    @tables.bind_table_action('update_storage')
    def edit_filesystem(self, edit_button):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.EDIT_FILESYSTEM_FORM_FIELDS)


class PipelinesTable(tables.TableRegion):
    name = "ceilometer_pipelines"

    UPDATE_SETTING_FORM_FIEDS = ("name", "location", "enabled", "max_bytes", "backup_count", "compress")

    @tables.bind_row_action('update_defaults')
    def update_setting(self, update_button, row):
        update_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.UPDATE_SETTING_FORM_FIEDS)



class SystemConfigurationPage(basepage.BasePage):

    PARTIAL_URL = 'admin/system_config'
    SYSTEMS_TAB_INDEX = 0
    ADDRESS_POOLS_TAB_INDEX = 1
    DNS_TAB_INDEX = 2
    NTP_TAB_INDEX = 3
    PTP_TAB_INDEX = 4
    OAM_IP_TAB_INDEX = 5
    CONTROLLER_FILESYSTEM_TAB_INDEX =6
#   PIPELINES_TAB_INDEX = ?                      #This tag is removed in release 18.10
    SYSTEMS_TABLE_NAME_COLUMN = 'Name'
    ADDRESS_POOLS_TABLE_NAME_COLUMN = 'Name'
    PIPELINES_TABLE_NAME_CLOUMN = 'Name'

    @property
    def systems_table(self):
        return SystemsTable(self.driver)

    @property
    def address_pools_table(self):
        return AddressPoolsTable(self.driver)

    @property
    def dns_table(self):
        return DNSTable(self.driver)

    @property
    def ntp_table(self):
        return NTPTable(self.driver)

    @property
    def oam_table(self):
        return OAMTable(self.driver)

    @property
    def storage_table(self):
        return StorageTable(self.driver)

    @property
    def pipelines_table(self):
        return PipelinesTable(self.driver)

    def _get_row_with_system_name(self, name):
        return self.systems_table.get_row(self.SYSTEMS_TABLE_NAME_COLUMN, name)

    def get_system_info(self, name, header):
        row = self._get_row_with_system_name(name)
        return row.cells[header].text

    def _get_row_with_address_pool_name(self, name):
        return self.address_pools_table.get_row(self.ADDRESS_POOLS_TABLE_NAME_COLUMN, name)

    def get_address_pool_info(self, name, header):
        row = self._get_row_with_address_pool_name(name)
        return row.cells[header].text

    def _get_row_with_pipeline_name(self, name):
        return self.systems_table.get_row(self.PIPELINES_TABLE_NAME_CLOUMN, name)

    def get_pipeline_info(self, name, header):
        row = self._get_row_with_pipeline_name(name)
        return row.cells[header].text

    def go_to_systems_tab(self):
        self.go_to_tab(self.SYSTEMS_TAB_INDEX)

    def go_to_address_pools_tab(self):
        self.go_to_tab(self.ADDRESS_POOLS_TAB_INDEX)

    def go_to_dns_tab(self):
        self.go_to_tab(self.DNS_TAB_INDEX)

    def go_to_ntp_tab(self):
        self.go_to_tab(self.NTP_TAB_INDEX)

    def go_to_oam_ip_tab(self):
        self.go_to_tab(self.OAM_IP_TAB_INDEX)

    def go_to_controller_filesystem_tab(self):
        self.go_to_tab(self.CONTROLLER_FILESYSTEM_TAB_INDEX)

    def go_to_pipelines_tab(self):
       self.go_to_tab(self.PIPELINES_TAB_INDEX)

    def edit_system(self, name, new_name=None, new_description=None):
        row = self._get_row_with_system_name(name)
        edit_form = self.systems_table.edit_system(row)
        if new_name is not None:
            edit_form.name.text = new_name
        if new_description is not None:
            edit_form.description.text = new_description
        edit_form.submit()

    def is_systems_present(self,name):
        return bool(self._get_row_with_system_name(name))

    def create_address_pool(self, name, network, order=None, ranges=None):
        create_form = self.address_pools_table.create_address_pool()
        create_form.name.text = name
        create_form.network.text = network
        if order is not None:
            create_form.order.text = order
        if ranges is not None:
            create_form.ranges.text = ranges
        create_form.submit()

    def delete_address_pool(self, name):
        row = self._get_row_with_address_pool_name(name)
        row.mark()
        confirm_delete_form = self.address_pools_table.delete_address_pool()
        confirm_delete_form.submit()

    def update_address_pool(self, name, new_name=None, new_order=None, new_ranges=None):
        row = self._get_row_with_address_pool_name(name)
        edit_form = self.address_pools_table.update_address_pool(row)
        if new_name is not None:
            edit_form.name.text = new_name
        if new_order is not None:
            edit_form.order.text = new_order
        if new_ranges is not None:
            edit_form.ranges.text = new_ranges
        edit_form.submit()

    def is_address_present(self, name):
        return bool(self._get_row_with_address_pool_name(name))

    def edit_dns(self, server1=None, server2=None, server3=None):
        edit_form = self.dns_table.edit_dns()
        if server1 is not None:
            edit_form.NAMESERVER_1.text = server1
        if server2 is not None:
            edit_form.NAMESERVER_2.text = server2
        if server3 is not None:
            edit_form.NAMESERVER_3.text = server3
        edit_form.submit()

    def edit_ntp(self, server1=None, server2=None, server3=None):
        edit_form = self.ntp_table.edit_ntp()
        if server1 is not None:
            edit_form.NTP_SERVER_1.text = server1
        if server2 is not None:
            edit_form.NTP_SERVER_2.text = server2
        if server3 is not None:
            edit_form.NTP_SERVER_3.text = server3
        edit_form.submit()

    def edit_oam(self, subnet=None, gateway=None, floating=None, controller0=None, controller1=None):
        edit_form = self.oam_table.edit_oam()
        if subnet is not None:
            edit_form.EXTERNAL_OAM_SUBNET.text = subnet
        if gateway is not None:
            edit_form.EXTERNAL_OAM_GATEWAY_ADDRESS.text = gateway
        if floating is not None:
            edit_form.EXTERNAL_OAM_FLOATING_ADDRESS.text = floating
        if controller0 is not None:
            edit_form.EXTERNAL_OAM_0_ADDRESS.text = controller0
        if controller1 is not None:
            edit_form.EXTERNAL_OAM_1_ADDRESS.text = controller1
        edit_form.submit()

    def edit_filesystem(self, database=None, cgcs=None, backup=None,
                        scratch=None, extension=None, img_conversions=None):
        edit_form = self.storage_table.edit_filesystem()
        if database is not None:
            edit_form.database.value = database
        if cgcs is not None:
            edit_form.cgcs.value = cgcs
        if backup is not None:
            edit_form.backup.value = backup
        if scratch is not None:
            edit_form.scratch.value = scratch
        if extension is not None:
            edit_form.extension.value = extension
        if img_conversions is not None:
            edit_form.img_conversions.value = img_conversions
        edit_form.submit()

    def update_pipelines_settings(self, name, location=None,
                                  is_enabled=None, max_bytes=None,
                                  backup_count=None, is_compress=None):
        row = self._get_row_with_pipeline_name(name)
        edit_form = self.pipelines_table.update_setting(row)
        if location is not None:
            edit_form.location.text = location
        if is_enabled is False:
            edit_form.enabled.unmark()
        if is_enabled is True:
            edit_form.enabled.mark()
        if max_bytes is not None:
            edit_form.max_bytes.value = max_bytes
        if backup_count is not None:
            edit_form.backup_count.value = backup_count
        if is_compress is False:
            edit_form.compress.unmark()
        if is_compress is True:
            edit_form.compress.mark()
        edit_form.submit()

    def is_pipeline_present(self, name):
        return bool(self._get_row_with_pipeline_name(name))




