#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from selenium.webdriver.common import by
from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables
from utils.horizon.regions import menus
from time import sleep
import six
from selenium.common import exceptions


class LaunchInstanceForm(forms.TabbedFormRegion):

    _submit_locator = (by.By.XPATH, '//button[@class="btn btn-primary finish"]')
    _fields_locator = (by.By.XPATH, "//div[starts-with(@class,'step ng-scope')]")
    _tables_locator = (by.By.XPATH, ".//table")


    field_mappings = (
        ("name", "availability-zone", "count"),
        ("boot-source-type", "volume-size", "Delete Volume on Instance Delete"),
        (),
        (),
        (),
        (),
        (),
        ("customization-script", "load-script", "disk-partition", "config-drive"),
        (),
        (),
        (),
        ("min-inst-count",)
    )

    def _init_tab_fields(self, tab_index):
        self.src_elem = self.driver
        fieldsets = self._get_elements(*self._fields_locator)
        self.fields_src_elem = fieldsets[tab_index]
        self.src_elem = fieldsets[tab_index]
        self.FIELDS = self._get_form_fields()
        current_tab_mappings = self.field_mappings[tab_index]
        for accessor_name, accessor_expr in current_tab_mappings.items():
            if isinstance(accessor_expr, six.string_types):
                try:
                    self._dynamic_properties[accessor_name] = self.FIELDS[accessor_expr]
                except:
                    self._dynamic_properties[accessor_name] = None
            else:  # it is a class
                self._dynamic_properties[accessor_name] = accessor_expr(
                    self.driver)

    @property
    def tabs(self):
        return menus.InstancesTabbedMenuRegion(self.driver,
                                               src_elem=self.src_elem)

    @property
    def contained_tables(self):
        return self._get_elements(*self._tables_locator)

    class AllocatedTable(tables.TableRegion):
        _rows_locator = (by.By.CSS_SELECTOR, 'tbody>tr[class="ng-scope"]')

    class AvailableTable(tables.TableRegion):
        _rows_locator = (by.By.CSS_SELECTOR, 'tbody>tr[class="ng-scope"]')

    @property
    def allocated_table(self):
        return self.AllocatedTable(self.driver, self.contained_tables[0])

    @property
    def available_table(self):
        return self.AvailableTable(self.driver, self.contained_tables[1])

    def __init__(self, driver):
        super(LaunchInstanceForm, self).__init__(
            driver, field_mappings=self.field_mappings)

    def addelement(self, column_name, name):
        self.available_table.get_row(column_name, name).add()

    def addelements(self, column_name, names):
        for name in names:
            self.available_table.get_row(column_name, name).add()


class InstancesTable(tables.TableRegion):
    name = "instances"

    @tables.bind_table_action('launch-ng')
    def launch_instance(self, launch_button):
        launch_button.click()
        self.wait_till_spinner_disappears()
        return LaunchInstanceForm(self.driver)

    @tables.bind_row_action('delete')
    def delete_instance(self, delete_instance, row):
        delete_instance.click()
        return forms.BaseFormRegion(self.driver)


class InstancesPage(basepage.BasePage):
    PARTIAL_URL = 'project/instances'

    DEFAULT_SOURCE_TYPE = 'Image'
    DEFAULT_SOURCE_NAME = 'tis-centos-guest'
    DEFAULT_FLAVOR_NAME = 'small'
    DEFAULT_NETWORK_NAMES = ['tenant1-mgmt-net', 'internal0-net0']


    INSTANCES_TABLE_NAME_COLUMN = 'Instance Name'
    INSTANCES_TABLE_STATUS_COLUMN = 'Status'
    INSTANCES_TABLE_IP_COLUMN = 'IP Address'
    INSTANCES_TABLE_IMAGE_NAME_COLUMN = 'image_name'

    def __init__(self, driver):
        super(InstancesPage, self).__init__(driver)
        self._page_title = "Instances"

    def _get_row_with_instance_name(self, name):
        return self.instances_table.get_row(self.INSTANCES_TABLE_NAME_COLUMN,
                                            name)

    def _get_rows_with_instances_names(self, names):
        return [self.instances_table.get_row(
            self.INSTANCES_TABLE_IMAGE_NAME_COLUMN, n) for n in names]

    @property
    def instances_table(self):
        return InstancesTable(self.driver)

    def is_instance_present(self, name):
        return bool(self._get_row_with_instance_name(name))

    def create_instance(
            self, instance_name,
            source_type=DEFAULT_SOURCE_TYPE,
            source_name=DEFAULT_SOURCE_NAME,
            flavor_name=DEFAULT_FLAVOR_NAME,
            network_names=DEFAULT_NETWORK_NAMES):
        instance_form = self.instances_table.launch_instance()
        instance_form.FIELDS['name'].text = instance_name
        instance_form.switch_to(1)
        instance_form.FIELDS['boot-source-type'].text = source_type
        sleep(1)
        instance_form._init_tab_fields(1)
        if source_type in ['Image', 'Instance Snapshot']:
            instance_form.FIELDS['Create New Volume'].click_no()
        else:
            instance_form.FIELDS['Delete Volume on Instance Delete'].click_no()
        instance_form.addelement('Name', source_name)
        instance_form.switch_to(2)
        instance_form.addelement('Name', flavor_name)
        instance_form.switch_to(3)
        instance_form.addelements('Network', network_names)
        instance_form.submit()

    def delete_instance(self, name):
        row = self._get_row_with_instance_name(name)
        # row.mark()
        confirm_delete_instances_form = self.instances_table.delete_instance(row)
        confirm_delete_instances_form.submit()

    # def delete_instances(self, instances_names):
    #     for instance_name in instances_names:
    #         self._get_row_with_instance_name(instance_name).mark()
    #     confirm_delete_instances_form = self.instances_table.delete_instance()
    #     confirm_delete_instances_form.submit()

    def is_instance_deleted(self, name):
        return self.instances_table.is_row_deleted(
            lambda: self._get_row_with_instance_name(name))

    def are_instances_deleted(self, instances_names):
        return self.instances_table.are_rows_deleted(
            lambda: self._get_rows_with_instances_names(instances_names))

    def is_instance_active(self, name):
        def cell_getter():
            row = self._get_row_with_instance_name(name)
            try:
                return row and row.cells[self.INSTANCES_TABLE_STATUS_COLUMN]
            except exceptions.StaleElementReferenceException:
                raise

        status = self.instances_table.wait_cell_status(cell_getter,
                                                       ('Active', 'Error'))
        return status == 'Active'

    # def _get_source_name(self, instance, boot_source):
    #     if 'image' in boot_source:
    #         return instance.image_id, conf.image_name # sdfasdfasfd
    #     elif boot_source == 'Boot from volume':
    #         return instance.volume_id, self.DEFAULT_VOLUME_NAME
    #     elif boot_source == 'Boot from snapshot':
    #         return instance.instance_snapshot_id, self.DEFAULT_SNAPSHOT_NAME
    #     elif 'volume snapshot (creates a new volume)' in boot_source:
    #         return (instance.volume_snapshot_id,
    #                 self.DEFAULT_VOLUME_SNAPSHOT_NAME)

    def get_image_name(self, instance_name):
        row = self._get_row_with_instance_name(instance_name)
        return row.cells[self.INSTANCES_TABLE_IMAGE_NAME_COLUMN].text

    def get_fixed_ipv4(self, name):
        row = self._get_row_with_instance_name(name)
        ips = row.cells[self.INSTANCES_TABLE_IP_COLUMN].text
        return ips.split()[1]
