from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables


class ServerGroupsTable(tables.TableRegion):

    name = "server_groups"

    CREATE_SERVER_GROUP_FORM_FIELDS = ("name", "policy", "is_best_effort", "group_size")

    @tables.bind_table_action('create')
    def create_group(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.CREATE_SERVER_GROUP_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_group(self, delete_button):
        delete_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver)


class ServerGroupsPage(basepage.BasePage):

    PARTIAL_URL = 'project/server_groups'

    def __init__(self, driver):
        super(ServerGroupsPage, self).__init__(driver)
        self._page_title = 'ServerGroups'

    @property
    def table_name_column(self):
        return "Group Name"

    @property
    def groups_table(self):
        return ServerGroupsTable(self.driver)

    def _get_row_with_group_name(self, name):
        return self.groups_table.get_row(self.table_name_column, name)

    def create_group(self, name, policy=None, is_best_effort=False, group_size=None):
        create_form = self.groups_table.create_group()
        create_form.name.text = name
        if policy is not None:
            create_form.policy.text = policy
        if is_best_effort:
            create_form.is_best_effort.mark()
        if group_size is not None:
            create_form.group_size.text = group_size
        create_form.submit()

    def delete_group(self, name):
        row = self._get_row_with_group_name(name)
        row.mark()
        confirm_delete_form = self.groups_table.delete_group()
        confirm_delete_form.submit()

    def is_group_present(self, name):
        return bool(self._get_row_with_group_name(name))