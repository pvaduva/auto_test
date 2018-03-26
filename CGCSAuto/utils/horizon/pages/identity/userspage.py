from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables
from time import sleep

class UsersTable(tables.TableRegion):
    name = 'users'
    CREATE_USER_FORM_FIELDS = ("name", "email", "password",
                               "confirm_password", "project", "role_id")

    @tables.bind_table_action('create')
    def create_user(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver,
                                field_mappings=self.CREATE_USER_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_user(self, delete_button):
        delete_button.click()
        return forms.BaseFormRegion(self.driver)


class UsersPage(basepage.BasePage):
    PARTIAL_URL = 'identity/users'

    USERS_TABLE_NAME_COLUMN = 'User Name'

    def __init__(self, driver):
        super(UsersPage, self).__init__(driver)
        self._page_title = "Users"

    def _get_row_with_user_name(self, name):
        return self.users_table.get_row(self.USERS_TABLE_NAME_COLUMN, name)

    @property
    def users_table(self):
        return UsersTable(self.driver)

    def create_user(self, name, password,
                    project, role, email=None):
        create_user_form = self.users_table.create_user()
        create_user_form.name.text = name
        if email is not None:
            create_user_form.email.text = email
        create_user_form.password.text = password
        create_user_form.confirm_password.text = password
        create_user_form.project.text = project
        create_user_form.role_id.text = role
        create_user_form.submit()

    def delete_user(self, name):
        row = self._get_row_with_user_name(name)
        row.mark()
        confirm_delete_users_form = self.users_table.delete_user()
        confirm_delete_users_form.submit()

    def is_user_present(self, name):
        return bool(self._get_row_with_user_name(name))
