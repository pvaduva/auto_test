import os
import datetime
from pytest import fixture

from utils.horizon.pages import loginpage
from utils.horizon import video_recorder
from utils.horizon.helper import HorizonDriver
from utils.tis_log import LOG

from consts import horizon
from consts.auth import Tenant, CliAuth
from consts.proj_vars import ProjVar
from keywords import container_helper, system_helper


@fixture(scope="session")
def driver(request):
    auth_info = Tenant.get('admin_platform')
    if CliAuth.get_var('HTTPS') and container_helper.is_stx_openstack_deployed(auth_info=auth_info):
        openstack_domain = system_helper.get_service_parameter_values(
            service='openstack', section='helm', name='endpoint_domain', auth_info=auth_info)
        domain = openstack_domain[0] if openstack_domain else None
        ProjVar.set_var(openstack_domain=domain)

    driver_ = HorizonDriver.get_driver()

    def teardown():
        HorizonDriver.quit_driver()
    request.addfinalizer(teardown)
    return driver_


@fixture(scope='function')
def admin_home_pg(driver, request):
    return __login_base(request=request, driver=driver, auth_info=Tenant.get('admin_platform'))


@fixture(scope='function')
def admin_home_pg_container(stx_openstack_required, driver, request):
    return __login_base(request=request, driver=driver, auth_info=Tenant.get('admin'))


@fixture(scope='function')
def tenant_home_pg_container(stx_openstack_required, driver, request):
    return __login_base(request=request, driver=driver, auth_info=Tenant.get_primary())


def __login_base(request, driver, auth_info, port=None):

    horizon.test_result = False
    if not auth_info:
        auth_info = Tenant.get_primary()

    user = auth_info['user']
    password = auth_info['password']
    project = auth_info['tenant']
    if not port and not auth_info.get('platform'):
        port = 31000

    gmttime = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    video_path = ProjVar.get_var('LOG_DIR') + '/horizon/' + str(gmttime) + '.mp4'
    recorder = video_recorder.VideoRecorder(1920, 1080, os.environ['DISPLAY'], video_path)
    recorder.start()
    home_pg = None

    try:
        LOG.fixture_step('Login as {}'.format(user))
        login_pg = loginpage.LoginPage(driver, port=port)
        login_pg.go_to_target_page()
        home_pg = login_pg.login(user=user, password=password)
        home_pg.change_project(name=project)
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
