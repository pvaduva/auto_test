from selenium import webdriver
from utils.horizon.pages import loginpage
from consts import horizon
from pytest import fixture
import contextlib
import tempfile
import os
import time
from utils.tis_log import LOG


driver0 = webdriver.Firefox()
driver0.maximize_window()


class Browser:
    @fixture(scope="session")
    def driver(self, request):
        driver = driver0

        def teardown():
            driver.quit()
        request.addfinalizer(teardown)

        return driver


class AdminTestCase(Browser):

    @fixture(scope='class')
    def home_pg(self, driver, request):
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


class TenantTestCase(Browser):

    @fixture(scope='class')
    def home_pg(self, driver, request):
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


@contextlib.contextmanager
def gen_temporary_file(name='', suffix='.qcow2', size=10485760):
    """Generate temporary file with provided parameters.

    :param name: file name except the extension /suffix
    :param suffix: file extension/suffix
    :param size: size of the file to create, bytes are generated randomly
    :return: path to the generated file
    """
    with tempfile.NamedTemporaryFile(prefix=name, suffix=suffix) as tmp_file:
        tmp_file.write(os.urandom(size))
        yield tmp_file.name


def gen_resource_name(resource="", timestamp=True):
    """Generate random resource name using uuid and timestamp.

    Input fields are usually limited to 255 or 80 characters hence their
    provide enough space for quite long resource names, but it might be
    the case that maximum field length is quite restricted, it is then
    necessary to consider using shorter resource argument or avoid using
    timestamp by setting timestamp argument to False.
    """
    fields = ['test']
    if resource:
        fields.append(resource)
    if timestamp:
        tstamp = time.strftime("%d-%m-%H-%M-%S")
        fields.append(tstamp)
    return "_".join(fields)