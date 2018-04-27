from selenium import webdriver
from pyvirtualdisplay import Display
from utils.horizon.pages import loginpage
from utils.horizon import video_recorder
from pytest import fixture
from utils.tis_log import LOG
import os
from consts.proj_vars import ProjVar
import datetime
from consts import horizon


@fixture(scope="session")
def driver(request):
    os.makedirs(ProjVar.get_var('LOG_DIR') + '/horizon', exist_ok=True)
    display = Display(visible=ProjVar.get_var('HORIZON_VISIBLE'), size=(1920, 1080))
    display.start()
    driver = webdriver.Firefox()
    driver.maximize_window()

    def teardown():
        driver.quit()
        display.stop()
    request.addfinalizer(teardown)

    return driver


@fixture(scope='function')
def admin_home_pg(driver, request):
    horizon.test_result = False
    gmttime = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    video_path = ProjVar.get_var('LOG_DIR') + '/horizon/' + str(gmttime) + '.mp4'
    recorder = video_recorder.VideoRecorder(1920, 1080, os.environ['DISPLAY'], video_path)
    recorder.start()
    LOG.fixture_step('Login as Admin')
    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_target_page()
    home_pg = login_pg.login('admin', 'Li69nux*')

    def teardown():
        LOG.fixture_step('Logout')
        home_pg.log_out()
        recorder.stop()
        if horizon.test_result:
            recorder.clear()
    request.addfinalizer(teardown)
    return home_pg


@fixture(scope='function')
def tenant_home_pg(driver, request):
    horizon.test_result = False
    gmttime = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    video_path = ProjVar.get_var('LOG_DIR') + '/horizon/' + str(gmttime) + '.mp4'
    recorder = video_recorder.VideoRecorder(1920, 1080, os.environ['DISPLAY'], video_path)
    recorder.start()
    LOG.fixture_step('Login as Tenant')
    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_target_page()
    home_pg = login_pg.login('tenant1', 'Li69nux*')

    def teardown():
        LOG.fixture_step('Logout')
        home_pg.log_out()
        recorder.stop()
        if horizon.test_result:
            recorder.clear()
    request.addfinalizer(teardown)

    return home_pg