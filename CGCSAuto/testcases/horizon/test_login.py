from utils.horizon.pages import loginpage
from pytest import mark
from testfixtures.horizon import driver


@mark.parametrize(('username', 'password'), [
        ('admin', 'Li69nux*'),
        ('tenant1', 'Li69nux*')
    ])
def test_login(driver, username, password):
    """
    Test the login functionality:

    Test Steps:
        - Login as username with password
        - Verify is-logged-in
        - Logout
    """

    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_target_page()
    home_pg = login_pg.login(username, password)
    assert home_pg.is_logged_in
    home_pg.log_out()
