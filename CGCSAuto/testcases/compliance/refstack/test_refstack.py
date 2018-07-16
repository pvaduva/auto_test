from pytest import mark, skip

from consts.proj_vars import ComplianceVar
from consts.compliance import RefStack
from utils.tis_log import LOG
from utils.exceptions import RefStackError
from keywords import host_helper


TEST_MAX_TIMEOUT = 20000


def test_refstack():
    """
    Test refstack suite specified via cmdline arg

    Setups:
        - copy test files to refstack host
        - Create 6 tenants, update quotas for each tenant
        - Create test flavors
        - Ensure two glance images exist for refstack test
        - Enable Swift
        - Create and set up public router

    Test Steps:
        - ssh to refstack host and run the test
        - parse the test results

    """
    LOG.tc_step("Run RefStack test in venv")
    with host_helper.ssh_to_compliance_server() as compliance_ssh:
        compliance_ssh.exec_cmd('cd {}'.format(RefStack.CLIENT_DIR))

        # activate venv
        LOG.info('activate venv')
        origin_prompt = compliance_ssh.get_prompt()
        venv_prompt = '(.*) {}'.format(origin_prompt)
        compliance_ssh.set_prompt(venv_prompt)
        compliance_ssh.exec_cmd('source .venv/bin/activate', fail_ok=False)

        try:
            # run refstack tests
            LOG.info('run refstack tests')
            run_cmd = 'refstack-client test -c {} -v --test-list test-list.txt > {}/test_run.log'.format(
                RefStack.TEMPEST_CONF, RefStack.TEST_HISTORY_DIR)
            code, output = compliance_ssh.exec_cmd(run_cmd, expect_timeout=TEST_MAX_TIMEOUT, fail_ok=True)
            if code == 0:
                print('Refstack test output: {}'.format(output))
            else:
                failing_path = '{}/failing'.format(RefStack.TEST_HISTORY_DIR)
                failed_tests = compliance_ssh.exec_cmd('grep --color=never "test: " {}'.format(failing_path))[1]
                raise RefStackError(failed_tests)
        finally:
            # deactivate venv
            LOG.info('deactivate venv')
            compliance_ssh.set_prompt(origin_prompt)
            compliance_ssh.exec_cmd('deactivate')

            # parse results and compose summary refstack host
            LOG.info("Compose refstack summary.")
            cmd = "awk -f {}/parseResults.awk {}/[0-9]* > {}/summary.txt".\
                format(RefStack.CLIENT_DIR, RefStack.TEST_HISTORY_DIR, RefStack.TEST_HISTORY_DIR)
            compliance_ssh.exec_cmd(cmd, fail_ok=False)

            log_files = []
            for file in RefStack.LOG_FILES:
                file_path = '{}/{}'.format(RefStack.TEST_HISTORY_DIR, file)
                if compliance_ssh.file_exists(file_path):
                    compliance_ssh.exec_cmd('chmod 755 {}'.format(file_path))
                    log_files.append(file)
            RefStack.LOG_FILES = log_files
