from utils.horizon.pages.project.compute import servergroupspage


class ServerGroupsTable(servergroupspage.ServerGroupsTable):

    name = "server_groups"

    CREATE_SERVER_GROUP_FORM_FIELDS = ("tenantP", "name", "policy", "is_best_effort", "group_size")

    pass


class ServerGroupsPage(servergroupspage.ServerGroupsPage):

    PARTIAL_URL = 'admin/server_groups'

    def __init__(self, driver):
        super(ServerGroupsPage, self).__init__(driver)
        self._page_title = 'ServerGroups'

    def create_group(self, name, project=None, policy=None, is_best_effort=False, group_size=None):
        create_form = self.groups_table.create_group()
        create_form.name.text = name
        if project is not None:
            create_form.tenantP.text = project
        create_form.tenantP.text = project
        if policy is not None:
            create_form.policy.text = policy
        if is_best_effort:
            create_form.is_best_effort.mark()
        if group_size is not None:
            create_form.group_size.text = group_size
        create_form.submit()