import os
import datetime
from pytest import fixture
from pyvirtualdisplay import Display

from utils.horizon.pages import loginpage
from utils.horizon import video_recorder
from utils.horizon.helper import HorizonDriver
from utils.tis_log import LOG

from consts import horizon
from consts.proj_vars import ProjVar


@fixture(scope="session")
def driver(request):
    display = Display(visible=ProjVar.get_var('HORIZON_VISIBLE'), size=(1920, 1080))
    display.start()
    driver_ = HorizonDriver.get_driver()

    def teardown():
        HorizonDriver.quit_driver()
        display.stop()
    request.addfinalizer(teardown)
    return driver_


@fixture(scope='function')
def admin_home_pg(driver, request):
    horizon.test_result = False
    gmttime = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    video_path = ProjVar.get_var('LOG_DIR') + '/horizon/' + str(gmttime) + '.mp4'
    recorder = video_recorder.VideoRecorder(1920, 1080, os.environ['DISPLAY'], video_path)
    recorder.start()
    home_pg = None
    try:
        LOG.fixture_step('Login as Admin')
        login_pg = loginpage.LoginPage(driver)
        login_pg.go_to_target_page()
        home_pg = login_pg.login('admin', 'Li69nux*')
    finally:
        def teardown():
            if home_pg:
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
    home_pg = None

    try:
        LOG.fixture_step('Login as Tenant')
        login_pg = loginpage.LoginPage(driver)
        login_pg.go_to_target_page()
        home_pg = login_pg.login('tenant1', 'Li69nux*')
    finally:
        def teardown():
            if home_pg:
                LOG.fixture_step('Logout')
                home_pg.log_out()
            recorder.stop()
            if horizon.test_result:
                recorder.clear()
        request.addfinalizer(teardown)

    return home_pg
