from selenium import webdriver
from pyvirtualdisplay import Display
from utils.horizon.pages import loginpage
from consts import horizon
from pytest import fixture
from utils.tis_log import LOG


@fixture(scope="session")
def driver(request):
    display = Display(visible=False, size=(1920, 1080))
    display.start()
    driver = webdriver.Firefox()
    driver.maximize_window()

    def teardown():
        driver.quit()
        display.stop()
    request.addfinalizer(teardown)

    return driver


@fixture(scope='class')
def admin_home_pg(driver, request):
    LOG.fixture_step('Login as Admin')
    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_target_page()
    home_pg = login_pg.login(horizon.ADMIN_USERNAME,
                             horizon.ADMIN_PASSWORD)

    def teardown():
        LOG.fixture_step('Logout')
        home_pg.log_out()
    request.addfinalizer(teardown)
    return home_pg


@fixture(scope='class')
def tenant_home_pg(driver, request):
    LOG.fixture_step('Login as Tenant')
    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_target_page()
    home_pg = login_pg.login(horizon.TENANT_USERNAME,
                             horizon.TENANT_PASSWORD)

    def teardown():
        LOG.fixture_step('Logout')
        home_pg.log_out()
    request.addfinalizer(teardown)

    return home_pg