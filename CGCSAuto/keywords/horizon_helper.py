import os
import fileinput

from utils.tis_log import LOG
from utils.horizon.helper import HorizonDriver
from consts.auth import Tenant
from consts.proj_vars import ProjVar


def download_openrc_files(quit_driver=True):
    """
    Download openrc files from Horizon to <LOG_DIR>/horizon/.

    """
    LOG.info("Download openrc files from horizon")
    local_dir = os.path.join(ProjVar.get_var('LOG_DIR'), 'horizon')

    from utils.horizon.pages import loginpage
    rc_files = []
    login_pg = loginpage.LoginPage()
    login_pg.go_to_target_page()
    try:
        for auth_info in (Tenant.ADMIN, Tenant.TENANT1, Tenant.TENANT2):
            user = auth_info['user']
            password = auth_info['password']
            openrc_file = '{}-openrc.sh'.format(user)
            home_pg = login_pg.login(user, password=password)
            home_pg.download_rc_v3()
            home_pg.log_out()
            openrc_path = os.path.join(local_dir, openrc_file)
            assert os.path.exists(openrc_path), "{} not found after download".format(openrc_file)
            rc_files.append(openrc_path)

    finally:
        if quit_driver:
            HorizonDriver.quit_driver()

    LOG.info("openrc files are successfully downloaded to: {}".format(local_dir))
    return rc_files