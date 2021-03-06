from pytest import mark, skip

from consts.auth import Tenant
from utils.horizon.pages import loginpage
from keywords import container_helper


@mark.parametrize(('username', 'service'), [
    ('admin', 'platform'),
    ('tenant1', 'container')
])
def test_horizon_login(driver, username, service):
    """
    Test the login functionality:

    Test Steps:
        - Login as username with password
        - Verify is-logged-in
        - Logout
    """
    if service == 'container' and not container_helper.is_stx_openstack_deployed():
        skip('Skip OpenStack horizon test when stx-openstack not deployed')

    port = 31000 if service == 'container' else None
    login_pg = loginpage.LoginPage(driver, port=port)
    login_pg.go_to_target_page()
    password = Tenant.get(username)['password']
    home_pg = login_pg.login(username, password=password)
    assert home_pg.is_logged_in
    home_pg.log_out()
