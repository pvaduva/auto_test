import time, os
from utils.tis_log import LOG
from keywords import murano_helper, host_helper, system_helper, glance_helper, common, network_helper
from pytest import mark, fixture
from consts.filepaths import MuranoPath, WRSROOT_HOME
from utils.clients.ssh import ControllerClient
from consts.proj_vars import ProjVar

result_ = None


@fixture(scope='session', autouse=True)
def _disable_murano(request):

    LOG.tc_func_start("MURANO_TEST")

    def _disable_murano_service():
        global result_
        results = system_helper.get_service_parameter_values(service="murano", section="engine",
                                                             name='disable_murano_agent')
        if len(results) > 0:
            if results[0] == 'false':
                result_ = False

        if result_ is False:
            env_ids = murano_helper.get_environment_list_table()
            for i in env_ids:
                murano_helper.delete_env(i)
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
    LOG.tc_step("Enable Murano and Murano aget... ")
    ret, out = murano_helper.enable_disable_murano(enable_disable_murano_agent=True)
    assert ret == 0, "Murano enable failed"

    # import and create murano image
    LOG.tc_step("Importing and Creating Murano image... ")
    img_id = glance_helper.get_guest_image('debian-8-m-agent')
    LOG.info('Image with name debian-8-m-agent with id {} has been created'.format(img_id))

    # set and update image
    LOG.tc_step("Setting and Updating  Murano image... ")
    glance_helper.set_image(image=img_id, properties={"title": "Debain 8 image with murano agent", "type": "linux"})
    LOG.info('Image properties have been updated')

    # getting tenant mgmt subnet id
    tenant = ProjVar.get_var('PRIMARY_TENANT')['user']
    subnet_name = "{}-mgmt0-subnet0".format(tenant)
    LOG.tc_step("Getting {} subnet id ... ".format(subnet_name))
    mgmt_id = network_helper.get_subnets(name=subnet_name)
    assert len(mgmt_id) > 0, "Fail to get {} subnet id".format(subnet_name)
    LOG.info("Subnet mgmt id {}".format(mgmt_id))

    # import base packages
    LOG.tc_step("Importing base packages... ")
    pkg_ids = []
    for pkg in MuranoPath.BASE_PACKAGES:
        code, out = murano_helper.import_package(pkg=pkg)
        assert code == 0,  "Fail to import Murano package {}".format(pkg)
        pkg_ids.append(out)

    standby = system_helper.get_standby_controller_name()
    assert standby, "Unable to get the standby controller hostname"

    LOG.tc_step("Swact active controller and ensure active controller is changed")
    host_helper.swact_host()

    LOG.tc_step("Check all services are up on active controller via sudo sm-dump")
    host_helper.wait_for_sm_dump_desired_states(controller=standby, fail_ok=False)

    # create Environment
    name = 'Test_env2'
    LOG.tc_step("Creating Murano environment {} ...".format(name))
    code, env_id = murano_helper.create_env(mgmt_id=mgmt_id, name=name)
    assert code == 0, "Murano environment create failed"
    LOG.info('Murano enviroment {} has been created successfully'.format(env_id))

    # create Session
    LOG.tc_step("Creating Murano session ...")
    rc, session_id = murano_helper.create_session(env_id)
    assert rc == 0, "Fail to create murano session withe environment id {}".format(env_id)
    LOG.info('Murano session {} has been created successfully'.format(session_id))

    # add application to environment
    LOG.tc_step("Adding application to  Murano enviroment ...")
    app_info = add_app_to_env(env_id, session_id, img_id, mgmt_id)
    assert app_info,  "Fail to add application to Murano enviroment: env_id {}; session_id {} img_id {}"\
        .format(env_id, session_id, img_id)
    LOG.info('Application added to murano environment:\n {}'.format(app_info))

    # Deploy Environment
    LOG.tc_step("Deploying Murano enviroment ...")
    code, deployment_id = murano_helper.deploy_env(env_id, session_id)
    assert code == 0,  "Fail to deploy environment: {}".format(deployment_id)
    LOG.info('Evnironment with ID {} has been deployed'.format(deployment_id))

    LOG.tc_step("Waiting for  Murano enviroment to be deployed ...")
    # TODO: change to wait function
    time.sleep(120)

    # delete Environment
    LOG.tc_step("Deleting Murano enviroment ...")
    ret_code, msg = murano_helper.delete_env(env_id=env_id)
    assert ret_code == 0, "Murano env delete failed"
    LOG.info('Murano Evnironment with ID {} has been deleted successfully'.format(env_id))

    LOG.tc_step("Deleting Murano packages ...")
    for pkg_id in pkg_ids:
        code, out = murano_helper.delete_package(package_id=pkg_id)
        assert code == 0, "Murano package delete failed {}".format(pkg_id)
        LOG.info("Murano package deleted {}".format(pkg_id))

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


def add_app_to_env(env_id, session_id, image_id, mgmt_id):
    if env_id is None:
        rc, env_id = murano_helper.create_env('test_env', mgmt_id)
        assert rc == 0, "Fail to create Muraon environment"
    if session_id is None:
        rc, session_id = murano_helper.create_session(env_id)
        assert rc == 0, "Unable to create Muraon session for evironment id {}".format(env_id)

    common.scp_from_test_server_to_active_controller(MuranoPath.APP_DEMO_PATH, WRSROOT_HOME)
    demo_app = os.path.splitext(os.path.basename(MuranoPath.APP_DEMO_PATH))[0]
    file = ('\n'
            '[\n'
            '    {{ "op": "add", "path": "/-", "value":\n'
            '        {{\n'
            '            "instance": {{\n'
            '                "availabilityZone": "nova",\n'
            '                "name": "xwvupifdxq27t1",\n'
            '                "image": "{}",\n'
            '                "keyname": "",\n'
            '                "flavor": "medium.dpdk",\n'
            '                "assignFloatingIp": false,\n'
            '                "?": {{\n'
            '                    "type": "io.murano.resources.LinuxMuranoInstance",\n'
            '                    "id": "===id1==="\n'
            '                }}\n'
            '            }},\n'
            '            "name": "Titanium Murano Demo App",\n'
            '            "enablePHP": true,\n'
            '            "?": {{\n'
            '                "type": "{}",\n'
            '                "id": "===id2==="\n'
            '            }}\n'
            '        }}\n'
            '    }}\n'
            ']').format(image_id, demo_app)

    object_model = murano_helper.edit_environment_object_mode(env_id, session_id=session_id, object_model_file=file)[1]

    return object_model
