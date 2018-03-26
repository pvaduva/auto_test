from utils.horizon.pages.project.network \
    import routerspage
from utils.horizon.regions import forms
from utils.horizon.regions import tables


class RoutersTable(routerspage.RoutersTable):
    EDIT_ROUTER_FORM_FIELDS = ("name", "admin_state")

    @tables.bind_row_action('update')
    def edit_router(self, edit_button, row):
        edit_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(self.driver, None,
                                self.EDIT_ROUTER_FORM_FIELDS)


class RoutersPage(routerspage.RoutersPage):
    PARTIAL_URL = 'admin/routers'

    @property
    def routers_table(self):
        return RoutersTable(self.driver)

    def edit_router(self, name, new_name, admin_state=None):
        row = self._get_row_with_router_name(name)
        edit_router_form = self.routers_table.edit_router(row)
        edit_router_form.name.text = new_name
        if admin_state is not None:
            edit_router_form.admin_state.text = admin_state
        edit_router_form.submit()
