import os

from utils.tis_log import LOG
from utils.clients.local import LocalHostClient

from keywords import host_helper
from consts.proj_vars import ProjVar, ComplianceVar
from consts.compliance import Dovetail
from consts.auth import ComplianceCreds
from utils.exceptions import DovetailError

from testcases.compliance import compliance_helper
from testcases.compliance.dovetail.dovetail_fixture import pre_configs      # DO NOT remove


MAX_TIMEOUT = 20000
CUMULUS_PROMPT = '.*@.*:.* '


def test_dovetail(pre_configs):
    """
    Test the Dovetail Compliance Suite through Cumulus Server

    Setups:
      On tis system:
        - Modify sshd_config, add root password and restart sshd service on hosts to allow root access on all hosts
        - Update Quotas for admin tenant

      On dovetail test node:
        - Update OS_PROJECT_ID and OS_AUTH_URL in /home/dovetail/pre_config/env_config.sh
        - Update min_compute_nodes in /home/dovetail/pre_config/tempest_conf.yaml
        - Update nova-api processes count in monitor_process.py
        - Add routes to access VM via management vif
        - Update /home/dovetail/pre_config/pod.yaml with hosts management ips

    Test steps:
        - source /home/dovetail/pre_config/env_config.sh
        - start docker container
        - cd compliance
        - dovetail run --testarea mandatory

    Teardown:
        - Remove root user access

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
            docker_conn.exec_cmd('cd compliance', fail_ok=False)
            dovetail_suite = ComplianceVar.get_var('DOVETAIL_SUITE')
            docker_conn.exec_cmd('dovetail run {}'.format(dovetail_suite), expect_timeout=MAX_TIMEOUT, fail_ok=False)

        LOG.info("Change permissions for results files")
        server_ssh.exec_sudo_cmd('chmod -R 755 {}'.format(Dovetail.RESULTS_DIR))
        failed_tests = server_ssh.exec_cmd('grep --color=never -E "^-.*FAIL" {}/dovetail.log'.
                                           format(Dovetail.RESULTS_DIR))[1]

    LOG.tc_step("Process dovetail test results and scp logs")
    scp_and_parse_logs()
    if failed_tests:
        raise DovetailError(failed_tests)
    else:
        LOG.info("All Dovetail testcases passed with param: {}.".format(dovetail_suite))


def scp_and_parse_logs():
    LOG.info("scp test results files from dovetail test host to local automation dir")
    dest_dir = ProjVar.get_var('LOG_DIR')
    os.makedirs(dest_dir, exist_ok=True)
    localhost = LocalHostClient()
    localhost.connect()
    localhost.scp_on_dest(source_ip=ComplianceCreds.get_host(), source_user=ComplianceCreds.get_user(),
                          source_pswd=ComplianceCreds.get_password(), source_path=Dovetail.RESULTS_DIR,
                          dest_path=dest_dir, timeout=300, cleanup=False, is_dir=True)

    # Attempt to change the log file permission so anyone can edit them.
    localhost.exec_cmd('chmod -R 755 {}/results'.format(dest_dir), get_exit_code=False)
    localhost.exec_cmd('mv {}/results {}/compliance'.format(dest_dir, dest_dir), fail_ok=False)

    # parse logs to summary.txt
    localhost.exec_cmd('grep --color=never -E "Pass Rate|pass rate|FAIL|SKIP|TestSuite|Duration: " '
                       '{}/compliance/dovetail.log > {}/compliance/summary.txt'.format(dest_dir, dest_dir))
