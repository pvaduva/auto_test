from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import menus
from utils.horizon.regions import tables


class ProjectForm(forms.TabbedFormRegion):
    FIELDS = (("name", "description", "enabled"),
              {'members': menus.MembershipMenuRegion})

    def __init__(self, driver, tab=0):
        super(ProjectForm, self).__init__(
            driver, field_mappings=self.FIELDS, default_tab=tab)


class ProjectsTable(tables.TableRegion):
    name = 'tenants'

    @tables.bind_table_action('create')
    def create_project(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return ProjectForm(self.driver)

    @tables.bind_row_action('update')
    def update_members(self, members_button, row):
        members_button.click()
        self.wait_till_spinner_disappears()
        return ProjectForm(self.driver, tab=1)

    @tables.bind_table_action('delete')
    def delete_project(self, delete_button):
        delete_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver, None)


class ProjectsPage(basepage.BasePage):

    PARTIAL_URL = 'identity'

    DEFAULT_ENABLED = True
    PROJECTS_TABLE_NAME_COLUMN = 'Name'
    PROJECT_ID_TABLE_NAME_COLUMN = 'id'

    def __init__(self, driver):
        super(ProjectsPage, self).__init__(driver)
        self._page_title = "Projects"

    @property
    def projects_table(self):
        return ProjectsTable(self.driver)

    def _get_row_with_project_name(self, name):
        return self.projects_table.get_row(self.PROJECTS_TABLE_NAME_COLUMN,
                                           name)

    def create_project(self, project_name, description=None,
                       is_enabled=DEFAULT_ENABLED):
        create_project_form = self.projects_table.create_project()
        create_project_form.name.text = project_name
        if description is not None:
            create_project_form.description.text = description
        if not is_enabled:
            create_project_form.enabled.unmark()
        create_project_form.submit()

    def delete_project(self, project_name):
        row = self._get_row_with_project_name(project_name)
        row.mark()
        modal_confirmation_form = self.projects_table.delete_project()
        modal_confirmation_form.submit()

    def is_project_present(self, project_name):
        return bool(self._get_row_with_project_name(project_name))

    def get_project_id_from_row(self, name):
        row = self._get_row_with_project_name(name)
        return row.cells[self.PROJECT_ID_TABLE_NAME_COLUMN].text

    def allocate_user_to_project(self, user_name, roles, project_name):
        row = self._get_row_with_project_name(project_name)
        members_form = self.projects_table.update_members(row)
        members_form.members.allocate_member(user_name)
        members_form.members.allocate_member_roles(user_name, roles)
        members_form.submit()

    def get_user_roles_at_project(self, user_name, project_name):
        row = self._get_row_with_project_name(project_name)
        members_form = self.projects_table.update_members(row)
        roles = members_form.members.get_member_allocated_roles(user_name)
        members_form.cancel()
        return set(roles)