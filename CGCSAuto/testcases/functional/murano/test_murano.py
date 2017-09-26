import time
from utils.tis_log import LOG
from keywords import system_helper, host_helper, murano_helper
from consts.cgcs import HostAvailabilityState, HostOperationalState


def test_murano():
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
            - None (any vms in bad stage)

        """

    base_pkgs = ["/var/cache/murano/meta/io.murano.zip", "/var/cache/murano/meta/io.murano.applications.zip"]

    # enable Murano and murano agent
    ret = murano_helper.enable_disable_murano(enable_disable_murano_agent=True)[0]
    if ret == 1:
        assert ret == 0, "Murano enable failed"

    # import base packages
    pkg_ids=[]
    for pkg in base_pkgs:
        code,out = murano_helper.import_package(pkg=pkg)
        if code==0:
            pkg_ids.append(out)
        else:
           LOG.info("Importing Murano package failed{}".format(pkg))


    #create Environment
    name = 'Test_env2'
    code, env_id = murano_helper.create_env(name=name)
    if ret == 1:
        assert ret == 0, "Murano env create failed"

    ret_code, msg = murano_helper.delete_env(env_id=env_id)
    if ret == 1:
        assert ret == 0, "Murano env delete failed"

    for pkg_id in pkg_ids:
        code,out = murano_helper.delete_package(package_id=pkg_id)
        if code == 0:
            LOG.info("Murano package Deleted {}".format(pkg_id))
        else:
            LOG.info("Murano package delete failed{}".format(pkg_id))

    ret = murano_helper.enable_disable_murano(enable=False, enable_disable_murano_agent=True, fail_ok=True)[0]
    if ret == 1:
        assert ret == 0, "Murano disable failed"


