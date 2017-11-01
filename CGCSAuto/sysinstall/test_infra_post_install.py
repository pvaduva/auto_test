import time
from pytest import mark, fixture, skip
from utils.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG
from keywords import install_helper, host_helper, system_helper, cinder_helper, \
    storage_helper,  local_storage_helper, glance_helper, vm_helper, nova_helper, common
from consts.cgcs import EventLogID, GuestImages,Networks
from consts.build_server import Server, get_build_server_info
from consts.auth import SvcCgcsAuto, Tenant
from consts.cgcs import Prompt
from consts.filepaths import WRSROOT_HOME, TestServerPath
from consts.proj_vars import ProjVar, InstallVars
from testfixtures.resource_mgmt import ResourceCleanup

INFRA_POST_INSTALL_SCRIPT = "lab_infra_post_install_setup.sh"
INFRA_POST_INSTALL_CONFIG = "lab_infra_post_install_setup.conf"


@fixture(scope='session', autouse=True)
def pre_infra_install_check():

    lab = ProjVar.get_var("LAB")
    lab_type = "regular"
    if "compute_nodes" not in lab:
        if len(lab["controller_nodes"]) == 1:
            skip("infra network is not supported in a AIO simplex system {}".format(lab['name']))
        else:
            lab_type = "cpe"
    elif "storage_nodes" in lab:
        lab_type = "storage"
    else:
        lab_type = "regular"

    LOG.fixture_step('Verify no infra network is currently configured in system: {}'.format(lab['name']))
    rc, infra_info = system_helper.is_infra_network_conifgured()
    if rc:
         skip("infra network is already configured  in the system {}".format(lab['name']))

    LOG.fixture_step('Verify if lab infra post install script and config file exist')
    cmd = "test -f {}".format(WRSROOT_HOME + INFRA_POST_INSTALL_SCRIPT)
    con_ssh = ControllerClient.get_active_controller()
    rc,  output = con_ssh.exec_cmd(cmd)
    if rc != 0:
        LOG.info("Down load infra post install script from test server")
        source_file = TestServerPath.TEST_SCRIPT + INFRA_POST_INSTALL_SCRIPT
        common.scp_from_test_server_to_active_controller(source_path=source_file, dest_dir=WRSROOT_HOME)
        rc,  output = con_ssh.exec_cmd(cmd)
        if rc != 0:
            msg = "The {} script file is required to configure infra post initial installation: {}".\
                format(INFRA_POST_INSTALL_SCRIPT, output)
            LOG.info(msg)
            return False, lab_type

    cmd = "test -f {}".format(WRSROOT_HOME + INFRA_POST_INSTALL_CONFIG)
    rc,  output = con_ssh.exec_cmd(cmd)
    if rc != 0:
        msg = "The {}  file is required to configure infra post initial installation: {}".\
            format(INFRA_POST_INSTALL_CONFIG, output)
        LOG.info(msg)
        return False, lab_type

    # rc, output =  system_helper.get_system_health_query()
    # if rc != 0:
    #     msg = "System {} is not healthy for adding infra post initial install: {}".format(lab['name'], output)
    #     LOG.info(msg)
    #     return False, lab_type

    return True, lab_type


def test_infra_add_post_install(pre_infra_install_check):
    """
    This test adds infra network to a lab after initial installation prior to launching any VMs. If VMs are present
    prior to running this test,  the VMs will be in an error state and need to be rebuild to recover the VMS after
    the test.

    A script lab_infra_post_install_setup,sh is required to run this testcase. The script is saved in Test Server
    /home/svc-cgcsauto/test_scripts and is downloaded during the test. An  infra interface configuration file
    ( lab_infra_post_install_setup.conf) specific  to a lab is also required and must be saved in wrsroot home
    directory. The conf file should contain:
       -  First line:
              source ${HOME}/lab_setup.conf
       -  Entry for Infra network cider:
              INFRA_NETWORK_CIDR="192.168.205.0/24"
       -  Entry for infra interface specification:
            - ethernet type:
I             INFRA_INTERFACES="ethernet|<PCIADDR+PCIDEV>|${INFRAMTU}|none"
            - valan type:
              INFRA_INTERFACES="vlan|<device-name>|${INFRAMTU}|none|<vland-id>"
            - ae
              INFRA_INTERFACES="ae|<PCIADDR+PCIDEV>, <PCIADDR+PCIDEV>|${INFRAMTU}|none/<mode>/layer2"

    Args:
        pre_infra_install_check:

    Returns:

    """
    LOG.info("Checking overall system health...")
    assert pre_infra_install_check[0], "System health must be OK for adding infra post initial install"

    system_type = pre_infra_install_check[1]
    LOG.tc_step("Locking all nodes expect active controller")
    active_controller = system_helper.get_active_controller_name()
    standby_controller = system_helper.get_standby_controller_name()
    hosts = system_helper.get_hostnames(administrative="unlocked")
    hosts.remove(active_controller)
    for host in hosts:
        host_helper.lock_host(host, force=True)

    LOG.info("Verify all hosts except active controller are locked...")
    fields = ["administrative", "availability"]
    for host in hosts:
        output = host_helper.get_hostshow_values(host, fields)
        assert output["administrative"] == "locked", "Host {} fail to lock".format(host)
        assert output["availability"] == "online", "Host {} is not not online".format(host)

    LOG.tc_step("Adding infra network ...")
    rc, output =  system_helper.add_infra_network()
    assert rc, "Fail to add infra network to the system: {}".format(output)


    LOG.tc_step("Running infra post install script to add infra interface on controllers ...")
    rc, output = install_helper.run_infra_post_install_setup()
    assert rc == 0,  "The infra post install setup script failed: {}".format(output)

    LOG.tc_step("Rebooting standby controller ...")
    host_helper.reboot_hosts(standby_controller)

    LOG.tc_step("Rebooting active controller ...")
    host_helper.reboot_hosts(active_controller)

    LOG.tc_step("Unlock standby controller after reboot...")
    host_helper.unlock_host(standby_controller)

    if system_type != "cpe":
        hosts = system_helper.get_hostnames(administrative="locked")
        LOG.tc_step("Running infra post install script to add infra interface on {} ...".format(hosts))
        rc, output = install_helper.run_infra_post_install_setup()
        assert rc == 0,  "The infra post install setup script failed: {}".format(output)
        LOG.tc_step("Unlocking remaining hosts: {} ...".format(hosts))
        for host in hosts:
            host_helper.unlock_host(host)


