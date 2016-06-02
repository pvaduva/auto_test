import logging
import os
from time import strftime

import pytest

import setups
import setup_consts
from utils.tis_log import LOG
from consts.proj_vars import ProjVar
from utils.cgcs_mongo_reporter import collect_and_upload_results

con_ssh = None
has_fail = False


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(request):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.set_env_vars(con_ssh)
    setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'))
    setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    def teardown():
        if has_fail and ProjVar.get_var('COLLECT_ALL'):
            # Collect tis logs if collect all required upon test(s) failure
            # Failure on collect all would not change the result of the last test case.
            setups.collect_tis_logs(con_ssh)

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
            global has_fail
            has_fail = True
            res_in_tests = 'Failed'

        if not res_in_tests:
            res_in_tests = 'Unknown!'

        with open(ProjVar.get_var("TCLIST_PATH"), mode='a') as f:
            f.write('{}\t{}\n'.format(res_in_tests, test_name))

        if(ProjVar.get_var("REPORT_ALL")):
            collect_and_upload_results(test_name, res_in_tests, ProjVar.get_var('LOG_DIR'))

    return report


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    con_ssh = setups.setup_tis_ssh(ProjVar.get_var("LAB"))


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

def pytest_configure(config):
    lab_arg = config.getoption('lab')
    natbox_arg = config.getoption('natbox')
    tenant_arg = config.getoption('tenant')
    bootvms_arg = config.getoption('bootvms')
    collect_all = config.getoption('collectall')
    report_all = config.getoption('reportall')

    # decide on the values of custom options based on cmdline inputs or values in setup_consts
    lab = setups.get_lab_dict(lab_arg) if lab_arg else setup_consts.LAB
    natbox = setups.get_natbox_dict(natbox_arg) if natbox_arg else setup_consts.NATBOX
    tenant = setups.get_tenant_dict(tenant_arg) if tenant_arg else setup_consts.PRIMARY_TENANT
    is_boot = True if bootvms_arg else setup_consts.BOOT_VMS
    collect_all = True if collect_all else setup_consts.COLLECT_ALL
    report_all = True if report_all else setup_consts.REPORT_ALL

    # compute directory for all logs based on the lab and timestamp on local machine
    log_dir = os.path.expanduser("~") + "/AUTOMATION_LOGS/" + lab['short_name'] + '/' + strftime('%Y%m%d%H%M')

    # set project constants, which will be used when scp keyfile, and save ssh log, etc
    ProjVar.set_vars(lab=lab, natbox=natbox, logdir=log_dir, tenant=tenant, 
                     is_boot=is_boot, 
                      collect_all=collect_all,
                      report_all=report_all)

    os.makedirs(log_dir, exist_ok=True)
    config_logger(log_dir)

    # set resultlog save location
    resultlog = config.getoption('resultlog')
    if not resultlog:
        config.option.resultlog = ProjVar.get_var("PYTESTLOG_PATH")


def pytest_addoption(parser):
    lab_help = "Lab to connect to. Valid input: lab name such as 'cgcs-r720-3_7', or floating ip such as " \
               "'128.224.150.142'. If it's a new lab, use floating ip before it is added to the automation framework."
    tenant_help = "Default tenant to use when unspecified. Valid values: tenant1, tenant2, or admin"
    natbox_help = "NatBox to use. Valid values: nat_hw, or nat_cumulus."
    bootvm_help = "Boot 2 vms at the beginning of the test session as background VMs."
    collect_all_help = "Run collect all on TiS server at the end of test session if any test fails."
    report_help = "Upload results and logs to the test results database."
    parser.addoption('--lab', action='store', metavar='labname', default=None, help=lab_help)
    parser.addoption('--tenant', action='store', metavar='tenantname', default=None, help=tenant_help)
    parser.addoption('--natbox', action='store', metavar='natboxname', default=None, help=natbox_help)
    parser.addoption('--bootvms', '--boot_vms', '--boot-vms', dest='bootvms', action='store_true', help=bootvm_help)
    parser.addoption('--collectall', '--collect_all', '--collect-all', dest='collectall', action='store_true',
                     help=collect_all_help)
    parser.addoption('--reportall', '--report_all', '--report-all', dest='reportall', action='store_true', help=report_help)

def config_logger(log_dir):
    # logger for log saved in file
    file_name = log_dir + '/TIS_AUTOMATION.log'
    formatter_file = "'%(asctime)s %(levelname)-5s %(filename)-10s %(funcName)-10s: %(message)s'"
    logging.basicConfig(level=logging.NOTSET, format=formatter_file, filename=file_name, filemode='w')

    # logger for stream output
    stream_hdler = logging.StreamHandler()
    formatter_stream = logging.Formatter('%(lineno)-4d%(levelname)-5s %(module)s.%(funcName)-8s: %(message)s')
    stream_hdler.setFormatter(formatter_stream)
    stream_hdler.setLevel(logging.INFO)
    LOG.addHandler(stream_hdler)


# TODO: add support for feature marks
