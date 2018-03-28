from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables


class HostAggregatesTable(tables.TableRegion):
    name = "host_aggregates"

    CREATE_HOST_AGGREGATE_FORM_FIELDS = (("name",
                                          "availability_zone"),)

    @tables.bind_table_action('create')
    def create_host_aggregate(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return forms.TabbedFormRegion(self.driver,
                                      field_mappings=self.
                                      CREATE_HOST_AGGREGATE_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_host_aggregate(self, delete_button):
        delete_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver,  None)

    # Examples of how to bind to secondary actions
    @tables.bind_row_action('update')
    def update_host_aggregate(self, edit_host_aggregate_button, row):
        edit_host_aggregate_button.click()
        pass

    @tables.bind_row_action('manage')
    def modify_access(self, manage_button, row):
        manage_button.click()
        pass


class HostaggregatesPage(basepage.BasePage):
    PARTIAL_URL = 'admin/aggregates'
    HOST_AGGREGATES_TABLE_NAME_COLUMN = 'Name'

    def __init__(self, driver):
        super(HostaggregatesPage, self).__init__(driver)
        self._page_title = "Host Aggregates"

    @property
    def host_aggregates_table(self):
        return HostAggregatesTable(self.driver)

    def _get_host_aggregate_row(self, name):
        return self.host_aggregates_table.get_row(
            self.HOST_AGGREGATES_TABLE_NAME_COLUMN, name)

    def create_host_aggregate(self, name, availability_zone):
        create_host_aggregate_form = \
            self.host_aggregates_table.create_host_aggregate()
        create_host_aggregate_form.name.text = name
        create_host_aggregate_form.availability_zone.text = \
            availability_zone
        create_host_aggregate_form.submit()

    def delete_host_aggregate(self, name):
        row = self._get_host_aggregate_row(name)
        row.mark()
        modal_confirmation_form = self.host_aggregates_table.\
            delete_host_aggregate()
        modal_confirmation_form.submit()

    def is_host_aggregate_present(self, name):
        return bool(self._get_host_aggregate_row(name))
