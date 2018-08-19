from utils.tis_log import LOG
from keywords import murano_helper, host_helper, system_helper
from pytest import mark, fixture

result_ = None


@fixture()
def _disable_murano(request):

    def _disable_murano_service():
        if result_ is False:
            ret, out = murano_helper.enable_disable_murano(enable=False, enable_disable_murano_agent=True,
                                                           fail_ok=True)
            assert ret == 0, "Murano disable failed"
    request.addfinalizer(_disable_murano_service)


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
