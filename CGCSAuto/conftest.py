import logging
import os
from time import strftime, gmtime

import pytest

import setup_consts
import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar
from utils.tis_log import LOG
from utils.mongo_reporter.cgcs_mongo_reporter import collect_and_upload_results


natbox_ssh = None
con_ssh = None
tc_start_time = None
has_fail = False
build_id = None


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    global build_id
    build_id = setups.get_build_id(con_ssh)

    os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.set_env_vars(con_ssh)

    setups.copy_files_to_con1()

    global natbox_ssh
    natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'))

    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))


@pytest.fixture(scope='function', autouse=True)
def reconnect_before_test():
    """
    Before each test function start, Reconnect to TIS via ssh if disconnection is detected
    """
    con_ssh.flush()
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    natbox_ssh.flush()
    natbox_ssh.connect(retry=False)


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
            msg = "\n***Failure at test {}: {}".format(call.when, call.excinfo)
            print(msg)
            LOG.debug(msg + "\n***Details: {}".format(report.longrepr))
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


class TestRes:
    PASSNUM = 0
    FAILNUM = 0
    SKIPNUM = 0
    TOTALNUM = 0


def pytest_runtest_makereport(item, call, __multicall__):
    report = __multicall__.execute()
    my_rep = MakeReport.get_report(item)
    my_rep.update_results(call, report)

    test_name = item.nodeid.replace('::()::', '::').replace('testcases/', '')
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

        # Log test result
        testcase_log(msg=res_in_log, nodeid=test_name, log_type='tc_res')

        if 'Test Passed' in res_in_log:
            res_in_tests = 'Passed'
        elif 'Test Failed' in res_in_log:
            global has_fail
            has_fail = True
            res_in_tests = 'Failed'

        if not res_in_tests:
            res_in_tests = 'Unknown!'

        # count testcases by status
        TestRes.TOTALNUM += 1
        if res_in_tests == 'Passed':
            TestRes.PASSNUM += 1
        elif res_in_tests == 'Failed':
            TestRes.FAILNUM += 1
        elif res_in_tests == 'Skipped':
            TestRes.SKIPNUM += 1

        global tc_start_time
        with open(ProjVar.get_var("TCLIST_PATH"), mode='a') as f:
            f.write('\n{}\t{}\t{}'.format(res_in_tests, tc_start_time, test_name))

        # reset tc_start and end time for next test case
        tc_start_time = None

        if ProjVar.get_var("REPORT_ALL") or ProjVar.get_var("REPORT_TAG"):
            upload_res = collect_and_upload_results(test_name, res_in_tests, ProjVar.get_var('LOG_DIR'), build=build_id)
            if not upload_res:
                with open(ProjVar.get_var("TCLIST_PATH"), mode='a') as f:
                    f.write('\tUPLOAD_UNSUCC')

    return report


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    con_ssh = setups.setup_tis_ssh(ProjVar.get_var("LAB"))
    CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
    Tenant._set_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant._set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_setup(item):
    global tc_start_time
    tc_start_time = setups.get_tis_timestamp(con_ssh)
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
    if log_type == 'tc_res':
        LOG.tc_result(msg=msg, tc_name=nodeid)
    elif log_type == 'tc_start':
        LOG.tc_func_start(nodeid)
    elif log_type == 'tc_setup':
        LOG.tc_setup_start(nodeid)
    elif log_type == 'tc_teardown':
        LOG.tc_teardown_start(nodeid)
    else:
        LOG.debug(logging_msg)


########################
# Command line options #
########################

def pytest_configure(config):
    config.addinivalue_line("markers",
                            "features(feature_name1, feature_name2, ...): mark impacted feature(s) for a test case.")
    config.addinivalue_line("markers",
                            "priorities(sanity, cpe_sanity, p2, ...): mark priorities for a test case.")
    config.addinivalue_line("markers",
                            "known_issue(CGTS-xxxx): mark known issue with JIRA ID or description if no JIRA needed.")

    lab_arg = config.getoption('lab')
    natbox_arg = config.getoption('natbox')
    tenant_arg = config.getoption('tenant')
    bootvms_arg = config.getoption('bootvms')
    collect_all = config.getoption('collectall')
    report_all = config.getoption('reportall')
    report_tag = config.getoption('report_tag')
    resultlog = config.getoption('resultlog')
    openstack_cli = config.getoption('openstackcli')

    # decide on the values of custom options based on cmdline inputs or values in setup_consts
    lab = setups.get_lab_dict(lab_arg) if lab_arg else setup_consts.LAB
    natbox = setups.get_natbox_dict(natbox_arg) if natbox_arg else setup_consts.NATBOX
    tenant = setups.get_tenant_dict(tenant_arg) if tenant_arg else setup_consts.PRIMARY_TENANT
    is_boot = True if bootvms_arg else setup_consts.BOOT_VMS
    collect_all = True if collect_all else setup_consts.COLLECT_ALL
    report_all = True if report_all else setup_consts.REPORT_ALL
    openstack_cli = True if openstack_cli else False

    # compute directory for all logs based on resultlog arg, lab, and timestamp on local machine
    resultlog = resultlog if resultlog else os.path.expanduser("~")
    if '/AUTOMATION_LOGS' in resultlog:
        resultlog = resultlog.split(sep='/AUTOMATION_LOGS')[0]
    if not resultlog.endswith('/'):
        resultlog += '/'
    log_dir = resultlog + "AUTOMATION_LOGS/" + lab['short_name'] + '/' + strftime('%Y%m%d%H%M')

    # set project constants, which will be used when scp keyfile, and save ssh log, etc
    ProjVar.set_vars(lab=lab, natbox=natbox, logdir=log_dir, tenant=tenant, is_boot=is_boot, collect_all=collect_all,
                     report_all=report_all, report_tag=report_tag, openstack_cli=openstack_cli)

    os.makedirs(log_dir, exist_ok=True)
    config_logger(log_dir)

    # set resultlog save location
    config.option.resultlog = ProjVar.get_var("PYTESTLOG_PATH")


def pytest_addoption(parser):
    lab_help = "Lab to connect to. Valid input: lab name such as 'cgcs-r720-3_7', or floating ip such as " \
               "'128.224.150.142'. If it's a new lab, use floating ip before it is added to the automation framework."
    tenant_help = "Default tenant to use when unspecified. Valid values: tenant1, tenant2, or admin"
    natbox_help = "NatBox to use. Valid values: nat_hw, or nat_cumulus."
    bootvm_help = "Boot 2 vms at the beginning of the test session as background VMs."
    collect_all_help = "Run collect all on TiS server at the end of test session if any test fails."
    report_help = "Upload results and logs to the test results database."
    tag_help = "Tag to be used for uploading logs to the test results database."
    openstackcli_help = "Use openstack cli whenever possible. e.g., 'neutron net-list' > 'openstack network list'"

    parser.addoption('--lab', action='store', metavar='labname', default=None, help=lab_help)
    parser.addoption('--tenant', action='store', metavar='tenantname', default=None, help=tenant_help)
    parser.addoption('--natbox', action='store', metavar='natboxname', default=None, help=natbox_help)
    parser.addoption('--report_tag', action='store', dest='report_tag', metavar='tagname', default=None, help=tag_help)

    parser.addoption('--bootvms', '--boot_vms', '--boot-vms', dest='bootvms', action='store_true', help=bootvm_help)
    parser.addoption('--collectall', '--collect_all', '--collect-all', dest='collectall', action='store_true',
                     help=collect_all_help)
    parser.addoption('--reportall', '--report_all', '--report-all', dest='reportall', action='store_true',
                     help=report_help)
    parser.addoption('--openstackcli', '--openstack_cli', '--openstack-cli', action='store_true', dest='openstackcli',
                     help=openstackcli_help)


def config_logger(log_dir):
    # logger for log saved in file
    file_name = log_dir + '/TIS_AUTOMATION.log'
    logging.Formatter.converter = gmtime
    formatter_file = "'[%(asctime)s] %(lineno)-4d%(levelname)-5s %(filename)-10s %(funcName)-10s:: %(message)s'"
    logging.basicConfig(level=logging.NOTSET, format=formatter_file, filename=file_name, filemode='w')

    # logger for stream output
    stream_hdler = logging.StreamHandler()
    formatter_stream = logging.Formatter('[%(asctime)s] %(lineno)-4d%(levelname)-5s %(module)s.%(funcName)-8s:: %(message)s')
    stream_hdler.setFormatter(formatter_stream)
    stream_hdler.setLevel(logging.INFO)
    LOG.addHandler(stream_hdler)


def pytest_unconfigure():
    # collect all if needed
    if has_fail and ProjVar.get_var('COLLECT_ALL'):
        # Collect tis logs if collect all required upon test(s) failure
        # Failure on collect all would not change the result of the last test case.
        setups.collect_tis_logs(con_ssh)

    # close ssh session
    try:
        con_ssh.close()
    except:
        pass

    try:
        natbox_ssh.close()
    except:
        pass

    tc_res_path = ProjVar.get_var('LOG_DIR') + '/test_results.log'

    total_exec = TestRes.PASSNUM + TestRes.FAILNUM
    pass_rate = round(TestRes.PASSNUM / total_exec, 2)
    fail_rate = round(TestRes.FAILNUM / total_exec, 2)
    with open(tc_res_path, mode='a') as f:
        # Append general info to result log
        f.write('\n\nLab: {}\n'
                'Build ID: {}\n'
                'Automation LOGs DIR: {}\n'.format(ProjVar.get_var('LAB_NAME'), build_id, ProjVar.get_var('LOG_DIR')))
        # Add result summary to beginning of the file
        f.write('\nSummary:\nPassed: {} ({})\nFailed: {} ({})\nTotal: {}\n'.
                format(TestRes.PASSNUM, pass_rate, TestRes.FAILNUM, fail_rate, TestRes.TOTALNUM))
        if TestRes.SKIPNUM > 0:
            f.write('Skipped: {}'.format(TestRes.SKIPNUM))

    LOG.info("Test Results saved to: {}".format(tc_res_path))
    with open(tc_res_path, 'r') as fin:
        print(fin.read())


def pytest_collection_modifyitems(items):
    move_to_last = []
    absolute_last = []

    for item in items:
        # re-order tests:
        trylast_marker = item.get_marker('trylast')
        abslast_marker = item.get_marker('abslast')

        if abslast_marker:
            absolute_last.append(item)
        elif trylast_marker:
            move_to_last.append(item)

        priority_marker = item.get_marker('priorities')
        if priority_marker is not None:
            priorities = priority_marker.args
            for priority in priorities:
                item.add_marker(eval("pytest.mark.{}".format(priority)))

        feature_marker = item.get_marker('features')
        if feature_marker is not None:
            features = feature_marker.args
            for feature in features:
                item.add_marker(eval("pytest.mark.{}".format(feature)))

        # known issue marker
        known_issue_mark = item.get_marker('known_issue')
        if known_issue_mark is not None:
            issue = known_issue_mark.args[0]
            msg = "{} has a workaround due to {}".format(item.nodeid, issue)
            print(msg)
            LOG.debug(msg=msg)
            item.add_marker(eval("pytest.mark.known_issue"))

    # add trylast tests to the end
    for item in move_to_last:
        items.remove(item)
        items.append(item)

    for i in absolute_last:
        items.remove(i)
        items.append(i)


def pytest_generate_tests(metafunc):
    # Modify the order of the fixtures to delete resources before revert host
    config_host_fixtures = {'class': 'config_host_class', 'module': 'config_host_module'}

    for key, value in config_host_fixtures.items():
        delete_res_func = 'delete_resources_{}'.format(key)

        if value in metafunc.fixturenames and delete_res_func in metafunc.fixturenames:
            index = list(metafunc.fixturenames).index('delete_resources_{}'.format(key))
            index = max([0, index-1])
            metafunc.fixturenames.remove(value)
            metafunc.fixturenames.insert(index, value)
