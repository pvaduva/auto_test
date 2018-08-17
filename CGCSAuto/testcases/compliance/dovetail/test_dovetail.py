import time
from utils.tis_log import LOG
from consts.auth import HostLinuxCreds, ComplianceCreds
from keywords import vlm_helper, host_helper, system_helper, nova_helper, network_helper, cinder_helper
from utils.clients.ssh import ControllerClient, SSHClient
from consts.compliance import Dovetail
from consts.proj_vars import ProjVar
from testcases.compliance.dovetail import pre_config
from pytest import fixture, skip, mark

TESTAREA_MANDATORY_MAX_TIMEOUT = 20000
CUMULUS_PROMPT = '.*@.*:.* '

@mark.usefixtures('restore_sshd_file_teardown')
def test_dovetail():
    """
    Test the Dovetail Compliance Suite through Cumulus Server

    Test Steps:
        -SSH into a provisioned Cumulus server
        -Modify Config Files on Cumulus
        -Enable Root on TiS
        -Modify monitor.py file on Cumulus
        -Update Quotas on TiS
        -Source config files and launch Docker Container on Cumulus
        -Run Dovetail test in Docker Container
    Teardown:
        -Disable Root login on TiS

    """

    with host_helper.ssh_to_compliance_server(prompt=CUMULUS_PROMPT) as server_ssh:
        LOG.info("Sourcing config files")
        server_ssh.exec_cmd('source {}/pre_config/env_config.sh'.format(Dovetail.DOVETAIL_HOME))

        LOG.info("Starting Docker Container")
        code, output = server_ssh.exec_sudo_cmd(
            "docker run --privileged=true -it -e DOVETAIL_HOME={} -v {}:{} -v /var/run/docker.sock:/var/run/docker.sock opnfv/dovetail:ovp.1.0.0 /bin/bash".format(Dovetail.DOVETAIL_HOME, Dovetail.DOVETAIL_HOME, Dovetail.DOVETAIL_HOME))
        print(output)
        LOG.info("Starting Dovetail Testarea Mandatory")
        server_ssh.exec_cmd('dovetail run --testarea mandatory', expect_timeout=TESTAREA_MANDATORY_MAX_TIMEOUT, fail_ok=False)
        LOG.info('Results can be found on tis-dovetail-test-node.cumulus.wrs.com in /home/dovetail/results')
