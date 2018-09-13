from utils.tis_log import LOG

from keywords import host_helper
from consts.compliance import Dovetail
from consts.auth import ComplianceCreds

from testcases.compliance import compliance_helper
from testcases.compliance.dovetail.dovetail_fixture import pre_configs      # DO NOT remove


MAX_TIMEOUT = 20000
CUMULUS_PROMPT = '.*@.*:.* '


def test_dovetail(pre_configs):
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
    ComplianceCreds.set_host(Dovetail.TEST_NODE)
    ComplianceCreds.set_user(Dovetail.USERNAME)
    ComplianceCreds.set_password(Dovetail.PASSWORD)
    with host_helper.ssh_to_compliance_server() as server_ssh:
        LOG.tc_step("Source to env_config.sh and start Docker Container")
        server_ssh.exec_cmd('source {}'.format(Dovetail.ENV_SH), get_exit_code=False)
        server_ssh.exec_cmd('export DOVETAIL_HOME={}'.format(Dovetail.HOME_DIR), get_exit_code=False)
        docker_cmd = "docker run --privileged=true -it -e DOVETAIL_HOME=$DOVETAIL_HOME " \
                     "-v $DOVETAIL_HOME:$DOVETAIL_HOME " \
                     "-v /var/run/docker.sock:/var/run/docker.sock opnfv/dovetail:ovp.1.0.0 /bin/bash"

        with compliance_helper.start_container_shell(host_client=server_ssh, docker_cmd=docker_cmd) as docker_conn:
            LOG.tc_step("Starting Dovetail Testarea Mandatory")
            docker_conn.exec_cmd('cd compliance', get_exit_code=False)
            # docker_conn.exec_cmd('dovetail run --testsuite ovp.1.0.0', expect_timeout=600, fail_ok=False)
            docker_conn.exec_cmd('dovetail run --testarea mandatory', expect_timeout=MAX_TIMEOUT, fail_ok=False)
            LOG.info('Results can be found on tis-dovetail-test-node.cumulus.wrs.com in /home/dovetail/results')
