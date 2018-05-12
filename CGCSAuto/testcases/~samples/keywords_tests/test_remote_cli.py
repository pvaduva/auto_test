import os

from consts.auth import Tenant
from consts.proj_vars import ProjVar
from keywords import nova_helper, cinder_helper, glance_helper, system_helper, ceilometer_helper, keystone_helper
from utils.clients.local import RemoteCLIClient
from utils.horizon.helper import HorizonDriver
from utils.tis_log import LOG


def test_remote_cli():
    LOG.info("Download openrc files from horizon")
    horizon_dir = os.path.join(ProjVar.get_var('LOG_DIR'), 'horizon')
    tenant1 = Tenant.TENANT1['tenant']
    tenant2 = Tenant.TENANT2['tenant']
    admin_openrc = '{}-openrc.sh'.format(Tenant.ADMIN['tenant'])
    tenant1_openrc = '{}-openrc.sh'.format(tenant1)
    tenant2_openrc = '{}-openrc.sh'.format(tenant2)

    # from utils.horizon.pages.project.apiaccesspage import ApiAccessPage
    from utils.horizon.pages import loginpage
    driver = HorizonDriver.get_driver()
    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_target_page()
    home_pg = login_pg.login('admin', 'Li69nux*')
    home_pg.download_rc_v3()

    # api_access_page = ApiAccessPage(home_pg.driver)
    # api_access_page.go_to_target_page()
    # api_access_page.download_openstack_rc_file()
    assert os.path.exists(os.path.join(horizon_dir, admin_openrc)), "{} not found after download".format(admin_openrc)

    # api_access_page.change_project(name=tenant1)
    # api_access_page.download_openstack_rc_file()
    home_pg.change_project(name=tenant1)
    home_pg.download_rc_v3()
    assert os.path.exists(os.path.join(horizon_dir, tenant1_openrc)), \
        "{} not found after download".format(tenant1_openrc)

    # api_access_page.change_project(name=tenant2)
    # api_access_page.download_openstack_rc_file()
    home_pg.change_project(name=tenant2)
    home_pg.download_rc_v3()
    assert os.path.exists(os.path.join(horizon_dir, tenant2_openrc)), \
        "{} not found after download".format(tenant2_openrc)

    RemoteCLIClient.get_remote_cli_client()

    nova_helper.get_basic_flavor()
    cinder_helper.get_qos_list()
    glance_helper.get_images()
    system_helper.get_computes()
    ceilometer_helper.alarm_list()
    keystone_helper.is_https_lab()


    # import sys
    # print(sys.executable)
    # try:
    #     client = RemoteCLIClient.get_remote_cli_client()
    #     cmd = ("nova --os-username 'admin' --os-password 'Li69nux*' --os-project-name admin --os-auth-url "
    #            "http://128.224.150.215:5000/v3 --os-region-name RegionOne --os-user-domain-name Default "
    #            "--os-project-domain-name Default list --a")
    #     client.exec_cmd(cmd, fail_ok=False)
    #
    #     client = RemoteCLIClient.get_remote_cli_client()
    #     client.exec_cmd(cmd)
    #
    # finally:
    #     RemoteCLIClient.remove_remote_cli_clients()
