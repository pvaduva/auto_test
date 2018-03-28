from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables
from time import sleep


class RulesTable(tables.TableRegion):
    name = 'rules'
    ADD_RULE_FORM_FIELDS = ("rule_menu", "direction", "port_or_range", "port",
                            "remote", "cidr")

    @tables.bind_table_action('add_rule')
    def create_rule(self, create_button):
        create_button.click()
        sleep(2)
        return forms.FormRegion(
            self.driver,
            field_mappings=self.ADD_RULE_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_rules_by_table(self, delete_button):
        delete_button.click()
        return forms.BaseFormRegion(self.driver, None)

    @tables.bind_row_action('delete')
    def delete_rule_by_row(self, delete_button, row):
        delete_button.click()
        return forms.BaseFormRegion(self.driver, None)


class ManageRulesPage(basepage.BasePage):

    RULES_TABLE_PORT_RANGE_COLUMN = 'Port Range'

    def __init__(self, driver):
        super(ManageRulesPage, self).__init__(driver)
        self._page_title = "Manage Security Group Rules - OpenStack Dashboard"

    def _get_row_with_port_range(self, port):
        return self.rules_table.get_row(
            self.RULES_TABLE_PORT_RANGE_COLUMN, port)

    @property
    def rules_table(self):
        return RulesTable(self.driver)

    def create_rule(self, port):
        create_rule_form = self.rules_table.create_rule()
        create_rule_form.port.text = port
        create_rule_form.submit()

    def delete_rule(self, port):
        row = self._get_row_with_port_range(port)
        modal_confirmation_form = self.rules_table.delete_rule_by_row(row)
        modal_confirmation_form.submit()

    def delete_rules(self, port):
        row = self._get_row_with_port_range(port)
        row.mark()
        modal_confirmation_form = self.rules_table.delete_rules_by_table()
        modal_confirmation_form.submit()

    def is_port_present(self, port):
        return bool(self._get_row_with_port_range(port))
