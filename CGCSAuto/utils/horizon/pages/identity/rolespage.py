from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables


class RolesTable(tables.TableRegion):

    name = "roles"

    MODIFY_ROLE_FORM_FIELDS = ('name',)

    @tables.bind_table_action('create')
    def create_role(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.MODIFY_ROLE_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_role(self, delete_button):
        delete_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_row_action('delete')
    def delete_role_by_row(self, delete_button, row):
        delete_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_row_action('edit')
    def edit_role(self, edit_button, row):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, field_mappings=self.MODIFY_ROLE_FORM_FIELDS)


class RolesPage(basepage.BasePage):

    PARTIAL_URL = 'identity/roles'

    ROLES_TABLE_NAME_COLUMN = "Role Name"

    @property
    def roles_table(self):
        return RolesTable(self.driver)

    def _get_row_with_role_name(self, name):
        return self.roles_table.get_row(self.ROLES_TABLE_NAME_COLUMN, name)

    def create_role(self, name):
        create_form = self.roles_table.create_role()
        create_form.name.text = name
        create_form.submit()

    def delete_role(self, name):
        row = self._get_row_with_role_name(name)
        row.mark()
        confirm_delete_form = self.roles_table.delete_role()
        confirm_delete_form.submit()

    def delete_role_by_row(self, name):
        row = self._get_row_with_role_name(name)
        confirm_delete_form = self.roles_table.delete_role_by_row(row)
        confirm_delete_form.submit()

    def edit_role(self, name, new_name=None):
        row = self._get_row_with_role_name(name)
        edit_form = self.roles_table.edit_role(row)
        if new_name is not None:
            edit_form.name.text = new_name
        edit_form.submit()

    def is_role_present(self, name):
        return bool(self._get_row_with_role_name(name))

    def get_role_info(self, name, header):
        row = self._get_row_with_role_name(name)
        return row.cells[header].text
