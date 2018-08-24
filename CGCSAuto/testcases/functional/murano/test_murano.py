from utils.tis_log import LOG
from keywords import murano_helper, host_helper, system_helper, glance_helper
from pytest import mark, fixture
from consts import build_server
from utils import cli
from consts.proj_vars import ProjVar
from utils.clients.ssh import ControllerClient


result_ = None


@fixture()
def _disable_murano(request):

    def _disable_murano_service():
        if result_ is False:
            ret, out = murano_helper.enable_disable_murano(enable=False, enable_disable_murano_agent=True,
                                                           fail_ok=True)
            assert ret == 0, "Murano disable failed"
    request.addfinalizer(_disable_murano_service)



def test_murano_thorough(_disable_murano):
    """
        Murano feature test cases

        Test Steps:
            - Enable murano and verify
            - Get images, set and update
            - Get murano applications
            - import base packages
            - Create Env
            - Create Session
            - Add app to env
            - Deploy env
            - Delete Env
            - Disable Murano


        Test Teardown:
            - None

        """

    global result_
    result_ = True

    base_pkgs = ["/var/cache/murano/meta/io.murano.zip", "/var/cache/murano/meta/io.murano.applications.zip"]

    # enable Murano and murano agent
    ret, out = murano_helper.enable_disable_murano(enable_disable_murano_agent=True)
    assert ret == 0, "Murano enable failed"

    # import and create murano image
    img_id = glance_helper.get_guest_image('debian-8-m-agent')
    LOG.info('Image with name debian-8-m-agent with id {} has been created'.format(img_id))

    # set and update image
    # cli.openstack('''image set --property murano_image_info='{"title": "Debain 8 image with murano agent", "type": "linux"}' {}'''.format(img_id))
    glance_helper.set_image(image=img_id, properties={"title": "Debain 8 image with murano agent", "type": "linux"})
    LOG.info('Image properties have been updated')

    # get murano application
    mgmt_id = murano_helper.get_application()
    LOG.info('Murano Application has been recived')

    # import base packages
    pkg_ids=[]
    for pkg in base_pkgs:
        code,out = murano_helper.import_package(pkg=pkg)
        if code==0:
            pkg_ids.append(out)
        else:
           LOG.info("Importing Murano package failed{}".format(pkg))

    standby = system_helper.get_standby_controller_name()
    assert standby
    LOG.tc_step("Swact active controller and ensure active controller is changed")
    host_helper.swact_host()

    LOG.tc_step("Check all services are up on active controller via sudo sm-dump")
    host_helper.wait_for_sm_dump_desired_states(controller=standby, fail_ok=False)

    # create Environment
    name = 'Test_env2'
    code, env_id = murano_helper.create_env(mgmt_id=mgmt_id, name=name)
    assert code == 0, "Murano env create failed"

    # create Session
    session_id = murano_helper.create_session(env_id)

    # add application to environment
    app_info = murano_helper.add_app_to_env(env_id, session_id, img_id)
    LOG.info('Application added to murano environment. Here is the information:\n {}'.format(app_info))

    # Deploy Environment
    deployment_id = murano_helper.deploy_env(env_id,session_id)
    LOG.info('Evnironment with ID {} has been deployed'.format(deployment_id))

    # delete Environment
    ret_code, msg = murano_helper.delete_env(env_id=env_id)
    assert ret_code == 0, "Murano env delete failed"

    for pkg_id in pkg_ids:
        code,out = murano_helper.delete_package(package_id=pkg_id)
        if code == 0:
            LOG.info("Murano package Deleted {}".format(pkg_id))
        else:
            LOG.info("Murano package delete failed{}".format(pkg_id))

    result_ = False


@mark.domain_sanity
def test_murano(_disable_murano):
    """
        Murano feature test cases

        Test Steps:
            - Enable murano and verify
            - import base packages
            - Enabele Murano-agent
            - Create Env
            - Delete Env
            - Disable Murano


        Test Teardown:
            - None

        """

    global result_
    result_ = True

    base_pkgs = ["/var/cache/murano/meta/io.murano.zip", "/var/cache/murano/meta/io.murano.applications.zip"]

    # enable Murano and murano agent
    ret, out = murano_helper.enable_disable_murano(enable_disable_murano_agent=True)
    assert ret == 0, "Murano enable failed"

    # import base packages
    pkg_ids=[]
    for pkg in base_pkgs:
        code,out = murano_helper.import_package(pkg=pkg)
        if code==0:
            pkg_ids.append(out)
        else:
           LOG.info("Importing Murano package failed{}".format(pkg))

    standby = system_helper.get_standby_controller_name()
    assert standby
    LOG.tc_step("Swact active controller and ensure active controller is changed")
    host_helper.swact_host()

    LOG.tc_step("Check all services are up on active controller via sudo sm-dump")
    host_helper.wait_for_sm_dump_desired_states(controller=standby, fail_ok=False)

    # create Environment
    name = 'Test_env2'
    code, env_id = murano_helper.create_env(name=name)
    assert code == 0, "Murano env create failed"

    ret_code, msg = murano_helper.delete_env(env_id=env_id)
    assert ret_code == 0, "Murano env delete failed"

    for pkg_id in pkg_ids:
        code,out = murano_helper.delete_package(package_id=pkg_id)
        if code == 0:
            LOG.info("Murano package Deleted {}".format(pkg_id))
        else:
            LOG.info("Murano package delete failed{}".format(pkg_id))

    result_ = False