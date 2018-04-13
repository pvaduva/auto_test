from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables
from time import sleep


class KeypairForm:

    def setname(self, name):
        name_element = self.driver.find_element_by_css_selector("div.modal-body input")
        name_element.send_keys(name)

    def submit(self):
        submit_btn = self.driver.find_elements_by_css_selector("button.btn.btn-primary")[0]
        submit_btn.click()

    def done(self):
        submit_btn = self.driver.find_elements_by_css_selector("button.btn.btn-primary")[2]
        submit_btn.click()

    def __init__(self, driver):
        self.driver = driver


class KeypairsTable(tables.TableRegion):
    name = "keypairs"
    CREATE_KEY_PAIR_FORM_FIELDS = ('name',)

    @tables.bind_table_action('create-keypair-ng')
    def create_keypair(self, create_button):
        create_button.click()
        sleep(3)
        return KeypairForm(self.driver)

    @tables.bind_row_action('delete')
    def delete_keypair_by_row(self, delete_button, row):
        delete_button.click()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_table_action('delete')
    def delete_keypair(self, delete_button):
        delete_button.click()
        return forms.BaseFormRegion(self.driver)


class KeypairsPage(basepage.BasePage):
    PARTIAL_URL = 'project/key_pairs'

    KEY_PAIRS_TABLE_ACTIONS = ("create", "import", "delete")
    KEY_PAIRS_TABLE_ROW_ACTION = "delete"
    KEY_PAIRS_TABLE_NAME_COLUMN = 'Key Pair Name'

    def __init__(self, driver):
        super(KeypairsPage, self).__init__(driver)
        self._page_title = "Access & Security"

    def _get_row_with_keypair_name(self, name):
        return self.keypairs_table.get_row(self.KEY_PAIRS_TABLE_NAME_COLUMN,
                                           name)

    @property
    def keypairs_table(self):
        return KeypairsTable(self.driver)

    @property
    def delete_keypair_form(self):
        return forms.BaseFormRegion(self.driver, None)

    def is_keypair_present(self, name):
        return bool(self._get_row_with_keypair_name(name))

    def get_keypair_info(self, name, header):
        row = self._get_row_with_keypair_name(name)
        return row.cells[header].text

    def create_keypair(self, keypair_name):
        create_keypair_form = self.keypairs_table.create_keypair()
        create_keypair_form.setname(keypair_name)
        sleep(1)
        create_keypair_form.submit()
        sleep(1)
        create_keypair_form.done()

    def delete_keypair_by_row(self, name):
        row = self._get_row_with_keypair_name(name)
        delete_keypair_form = self.keypairs_table.delete_keypair(row)
        delete_keypair_form.submit()

    def delete_keypair(self, name):
        row = self._get_row_with_keypair_name(name)
        row.mark()
        delete_keypair_form = self.keypairs_table.delete_keypair()
        delete_keypair_form.submit()
