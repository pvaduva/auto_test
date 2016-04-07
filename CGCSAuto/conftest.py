import pytest

import setups
from keywords.verify_fixtures import *

con_ssh = None


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(request):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    setups.create_tmp_dir()
    setups.setup_primary_tenant()
    setups.setup_natbox_ssh()
    setups.boot_vms()

    def teardown():
        try:
            con_ssh.close()
        except:
            pass
    request.addfinalizer(teardown)


@pytest.fixture(scope='function', autouse=True)
def reconnect_before_test():
    """
    Before each test function start, Reconnect to TIS via ssh if disconnection is detected
    """
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()


@pytest.fixture(scope='function', autouse=False)
def tis_ssh():
    """
    Used when a test function wants to get active controller ssh handle.
    This is usually useful when multiple ssh sessions are created, and test func needs to explicitly specify which ssh
    session to run which command.

    Returns: ssh client of the active controller session
    """
    return con_ssh


class MakeReport:
    nodeid = None
    instances = {}

    def __init__(self, item):
        MakeReport.nodeid = item.nodeid
        self.test_pass = None
        self.test_results = {}
        MakeReport.instances[item.nodeid] = self

    def update_results(self, call, report):
        if report.failed:
            LOG.info("\n***Failure at test {}: {}".format(call.when, call.excinfo))
            LOG.debug("\n***Details: {}".format(report.longrepr))
            self.test_results[call.when] = ['Failed', call.excinfo]
        elif report.skipped:
            self.test_results[call.when] = ['Skipped', call.excinfo]
        elif report.passed:
            self.test_results[call.when] = ['Passed', '']

    def get_results(self):
        return self.test_results

    @classmethod
    def get_report(cls, item):
        if item.nodeid == cls.nodeid:
            return cls.instances[cls.nodeid]
        else:
            return cls(item)


@pytest.mark.tryfirst
def pytest_runtest_makereport(item, call, __multicall__):
    report = __multicall__.execute()

    my_rep = MakeReport.get_report(item)
    my_rep.update_results(call, report)

    if report.when == 'teardown':
        test_res = 'Test Passed'
        fail_at = []
        res = my_rep.get_results()
        for key, val in res.items():
            if val[0] == 'Failed':
                fail_at.append('test ' + key)
            elif val[0] == 'Skipped':
                test_res = "Test Skipped\nReason: {}".format(val[1])
                break
        if fail_at:
            fail_at = ', '.join(fail_at)
            test_res = 'Test Failed at {}'.format(fail_at)

        testcase_log(msg=test_res, nodeid=item.nodeid, log_type='tc_end')

    return report


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    con_ssh = setups.setup_tis_ssh()


def pytest_runtest_setup(item):
    print('')
    message = "Setup started:"
    testcase_log(message, item.nodeid, log_type='tc_setup')


def pytest_runtest_call(item):
    separator = '++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++'
    message = "Test steps started:"
    testcase_log(message, item.nodeid, separator=separator, log_type='tc_start')


def pytest_runtest_teardown(item):
    print('')
    message = 'Teardown started:'
    testcase_log(message, item.nodeid, log_type='tc_teardown')
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()


# TODO: add support for feature marks


def testcase_log(msg, nodeid, separator=None, log_type=None):
    if separator is None:
        separator = '-----------'

    print_msg = separator + '\n' + msg
    logging_msg = '\n{}{} {}'.format(separator, msg, nodeid)
    print(print_msg)
    if log_type == 'tc_end':
        LOG.tc_end(msg=msg, tc_name=nodeid)
    elif log_type == 'tc_start':
        LOG.tc_start(nodeid)
    elif log_type == 'tc_setup':
        LOG.tc_setup(nodeid)
    elif log_type == 'tc_teardown':
        LOG.tc_teardown(nodeid)
    else:
        LOG.debug(logging_msg)
