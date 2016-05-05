import os
import logging
import importlib
from os.path import expanduser
from time import strftime

import pytest

import setups
import setup_consts
from consts.lab import Labs
# from testfixtures.verify_fixtures import *
from utils.tis_log import LOG
# LOG_DIR = setup_consts.LOG_DIR
# TCLIST_PATH = setup_consts.TCLIST_PATH
# PYTESTLOG_PATH = setup_consts.PYTESTLOG_PATH

con_ssh = None

@pytest.fixture(scope='session', autouse=True)
def setup_test_session(request):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    setups.create_tmp_dir()
    setups.setup_primary_tenant()
    setups.set_env_vars(con_ssh)
    setups.setup_natbox_ssh(GlobVar.KEYFILE_PATH)
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
    con_ssh.flush()
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)


@pytest.fixture(scope='function', autouse=False)
def tis_ssh():
    """
    Used when a test function wants to get active controller ssh handle.
    This is usually useful when multiple ssh sessions are created, and test func needs to explicitly specify which ssh
    session to run which command.

    Returns: ssh client of the active controller session
    """
    return con_ssh


################################
# Process and log test results #
################################

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
            sep = 'Skipped: '
            skipreason_list = str(call.excinfo).split(sep=sep)[1:]
            skipreason_str = sep.join(skipreason_list)
            self.test_results[call.when] = ['Skipped', skipreason_str]
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

    test_name = item.nodeid
    res_in_tests = ''
    if report.when == 'teardown':
        res_in_log = 'Test Passed'
        fail_at = []
        res = my_rep.get_results()
        for key, val in res.items():
            if val[0] == 'Failed':
                fail_at.append('test ' + key)
            elif val[0] == 'Skipped':
                res_in_log = 'Test Skipped\nReason: {}'.format(val[1])
                res_in_tests = 'Skipped'
                break
        if fail_at:
            fail_at = ', '.join(fail_at)
            res_in_log = 'Test Failed at {}'.format(fail_at)

        testcase_log(msg=res_in_log, nodeid=test_name, log_type='tc_end')

        if 'Test Passed' in res_in_log:
            res_in_tests = 'Passed'
        elif 'Test Failed' in res_in_log:
            res_in_tests = 'Failed'

        if not res_in_tests:
            res_in_tests = 'Unknow!'

        with open(GlobVar.TCLIST_PATH, mode='a') as f:
            f.write('{}\t{}\n'.format(res_in_tests, test_name))

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


########################
# Command line options #
########################

def pytest_cmdline_preparse(args):
    pytestlog_opt = "--resultlog={}".format(GlobVar.PYTESTLOG_PATH)
    args.append(pytestlog_opt)

def pytest_addoption(parser):
    config_logger_and_path()


def config_logger_and_path():
    # if lab is passed via cmdline: do following
    # global LOG_DIR, TEMP_DIR, KEYFILE_NAME, KEYFILE_PATH, TCLIST_PATH, PYTESTLOG_PATH, LAB_NAME
    LAB = Labs.IP_1_4
    # setup_consts.set_lab(LAB)
    importlib.reload(setup_consts)
    print("HEY ADD OPTION is here")
    print("HHHHHH CREATING DIRECTORY")
    # print(FILE_NAME)
    # LAB_NAME = LAB['short_name']

    GlobVar.set_vars(LAB)
    LOG_DIR = expanduser("~") + "/AUTOMATION_LOGS/" + LAB['short_name'] + '/' + strftime('%Y%m%d%H%M')
    #
    # TCLIST_PATH = LOG_DIR + '/testcases.lst'
    # PYTESTLOG_PATH = LOG_DIR + '/pytestlog.log'
    # TEMP_DIR = LOG_DIR + '/tmp_files'
    #
    # KEYFILE_NAME = 'keyfile_{}.pem'.format(LAB_NAME)
    # KEYFILE_PATH = '/home/wrsroot/.ssh/' + KEYFILE_NAME
    # print(TCLIST_PATH)
    # print(PYTESTLOG_PATH)
    # print(LOG_DIR)
    FILE_NAME = LOG_DIR + '/TIS_AUTOMATION.log'
    os.makedirs(LOG_DIR, exist_ok=True)
    FORMAT = "'%(asctime)s %(levelname)-5s %(filename)-10s %(funcName)-10s: %(message)s'"
    logging.basicConfig(level=logging.NOTSET, format=FORMAT, filename=FILE_NAME, filemode='w')
    # handler = logging.FileHandler(FILE_NAME, 'w')
    print("are you there1....")

    # LOG.addHandler(handler)
    # screen output handler
    handler2 = logging.StreamHandler()
    formatter = logging.Formatter('%(lineno)-4d%(levelname)-5s %(module)s.%(funcName)-8s: %(message)s')
    handler2.setFormatter(formatter)
    handler2.setLevel(logging.INFO)
    LOG.addHandler(handler2)

# TODO: add support for feature marks
class GlobVar:
    # KEYFILE_PATH = KEYFILE_NAME = LOG_DIR = TCLIST_PATH = PYTESTLOG_PATH = LAB_NAME = TEMP_DIR = None

    @classmethod
    def set_vars(cls, lab):
        print("SET VARSSSSSSSS")
        cls.LAB_NAME = lab['short_name']

        cls.LOG_DIR = expanduser("~") + "/AUTOMATION_LOGS/" + cls.LAB_NAME + '/' + strftime('%Y%m%d%H%M')

        cls.TCLIST_PATH = cls.LOG_DIR + '/testcases.lst'
        cls.PYTESTLOG_PATH = cls.LOG_DIR + '/pytestlog.log'
        cls.TEMP_DIR = cls.LOG_DIR + '/tmp_files'

        cls.KEYFILE_NAME = 'keyfile_{}.pem'.format(cls.LAB_NAME)
        cls.KEYFILE_PATH = '/home/wrsroot/.ssh/' + cls.KEYFILE_NAME
        print(dir(cls))
        print(getattr(cls, "LOG_DIR"))

    @classmethod
    def get_glob_var(cls, var_name):
        return getattr(cls, var_name)