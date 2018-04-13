from selenium.webdriver.common import by
from utils.horizon.pages import pageobject
from utils.horizon.pages.project.compute import overviewpage
from time import sleep


class LoginPage(pageobject.PageObject):

    PARTIAL_URL = 'auth/login'

    _login_username_field_locator = (by.By.ID, 'id_username')
    _login_password_field_locator = (by.By.ID, 'id_password')
    _login_submit_button_locator = (by.By.ID, 'loginBtn')
    _login_logout_reason_locator = (by.By.ID, 'logout_reason')

    @property
    def username(self):
        return self._get_element(*self._login_username_field_locator)

    @property
    def password(self):
        return self._get_element(*self._login_password_field_locator)

    @property
    def login_button(self):
        return self._get_element(*self._login_submit_button_locator)

    def is_logout_reason_displayed(self):
        return self._get_element(*self._login_logout_reason_locator)

    def login(self, user=None, password=None):
        self.username.send_keys(user)
        self.password.send_keys(password)
        self.login_button.click()
        sleep(1)
        return overviewpage.OverviewPage(self.driver)

