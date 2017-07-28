import logging
import os
import threading    # Used for formatting logger

from time import strftime, gmtime

import pytest   # Don't remove. Used in eval

import setup_consts
import setups
from consts.proj_vars import ProjVar, InstallVars
from utils.mongo_reporter.cgcs_mongo_reporter import collect_and_upload_results
from utils.tis_log import LOG


tc_start_time = None
has_fail = False
stress_iteration = -1
tracebacks = []


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
            global has_fail
            has_fail = True
            msg = "\n***Failure at test {}: {}".format(call.when, call.excinfo)
            print(msg)
            LOG.debug(msg + "\n***Details: {}".format(report.longrepr))
            global tracebacks
            tracebacks.append(str(report.longrepr))
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


def _write_results(res_in_tests, test_name):
    global tc_start_time
    with open(ProjVar.get_var("TCLIST_PATH"), mode='a') as f:
        f.write('\n{}\t{}\t{}'.format(res_in_tests, tc_start_time, test_name))

    # reset tc_start and end time for next test case
    tc_start_time = None
    build_id = ProjVar.get_var('BUILD_ID')
    build_server = ProjVar.get_var('BUILD_SERVER')
    if ProjVar.get_var("REPORT_ALL") or ProjVar.get_var("REPORT_TAG"):
        upload_res = collect_and_upload_results(test_name, res_in_tests, ProjVar.get_var('LOG_DIR'), build=build_id,
                                                build_server=build_server)
        if not upload_res:
            with open(ProjVar.get_var("TCLIST_PATH"), mode='a') as f:
                f.write('\tUPLOAD_UNSUCC')


def pytest_runtest_makereport(item, call, __multicall__):
    report = __multicall__.execute()
    my_rep = MakeReport.get_report(item)
    my_rep.update_results(call, report)

    test_name = item.nodeid.replace('::()::', '::').replace('testcases/', '')
    res_in_tests = ''
    res = my_rep.get_results()
    if report.when == 'teardown':
        res_in_log = 'Test Passed'
        fail_at = []
        for key, val in res.items():
            if val[0] == 'Failed':
                fail_at.append('test ' + key)
            elif val[0] == 'Skipped':
                res_in_log = 'Test Skipped\nReason: {}'.format(val[1])
                res_in_tests = 'SKIP'
                break
        if fail_at:
            fail_at = ', '.join(fail_at)
            res_in_log = 'Test Failed at {}'.format(fail_at)

        # Log test result
        testcase_log(msg=res_in_log, nodeid=test_name, log_type='tc_res')

        if 'Test Passed' in res_in_log:
            res_in_tests = 'PASS'
        elif 'Test Failed' in res_in_log:
            res_in_tests = 'FAIL'

        if not res_in_tests:
            res_in_tests = 'UNKNOWN'

        # count testcases by status
        TestRes.TOTALNUM += 1
        if res_in_tests == 'PASS':
            TestRes.PASSNUM += 1
        elif res_in_tests == 'FAIL':
            TestRes.FAILNUM += 1
        elif res_in_tests == 'SKIP':
            TestRes.SKIPNUM += 1

        _write_results(res_in_tests=res_in_tests, test_name=test_name)

    if stress_iteration > 0:
        for key, val in res.items():
            if val[0] == 'Failed':
                _write_results(res_in_tests='Failed', test_name=test_name)
                TestRes.FAILNUM += 1
                pytest.exit("Skip rest of the iterations upon stress test failure")

    return report

#
# def pytest_collectstart():
#     """
#     Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
#     """
#     global con_ssh
#     con_ssh = setups.setup_tis_ssh(ProjVar.get_var("LAB"))
#     CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
#     Tenant._set_url(CliAuth.get_var('OS_AUTH_URL'))
#     Tenant._set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_setup(item):
    global tc_start_time
    # tc_start_time = setups.get_tis_timestamp(con_ssh)
    tc_start_time = strftime("%Y%m%d %H:%M:%S", gmtime())
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
    # con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    # con_ssh.flush()


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

    # Common reporting params
    collect_all = config.getoption('collectall')
    report_all = config.getoption('reportall')
    report_tag = config.getoption('report_tag')
    resultlog = config.getoption('resultlog')

    # Test case params on installed system
    lab_arg = config.getoption('lab')
    natbox_arg = config.getoption('natbox')
    tenant_arg = config.getoption('tenant')
    bootvms_arg = config.getoption('bootvms')
    openstack_cli = config.getoption('openstackcli')
    global change_admin
    change_admin = config.getoption('changeadmin')
    global stress_iteration
    stress_iteration = config.getoption('repeat')
    install_conf = config.getoption('installconf')

    # decide on the values of custom options based on cmdline inputs or values in setup_consts
    lab = setups.get_lab_from_cmdline(lab_arg=lab_arg, installconf_path=install_conf)
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
    InstallVars.set_install_var(lab=lab)

    os.makedirs(log_dir, exist_ok=True)
    config_logger(log_dir)

    # set resultlog save location
    config.option.resultlog = ProjVar.get_var("PYTESTLOG_PATH")

    # Add 'iter' to stress test names
    # print("config_options: {}".format(config.option))
    file_or_dir = config.getoption('file_or_dir')
    origin_file_dir = list(file_or_dir)

    if stress_iteration > 0:
        for f_or_d in origin_file_dir:
            if '[' in f_or_d:
                # Below setting seems to have no effect. Test did not continue upon collection failure.
                # config.option.continue_on_collection_errors = True
                # return
                file_or_dir.remove(f_or_d)
                origin_f_or_list = list(f_or_d)

                for i in range(stress_iteration):
                    extra_str = 'iter{}-'.format(i)
                    f_or_d_list = list(origin_f_or_list)
                    f_or_d_list.insert(f_or_d_list.index('[') + 1, extra_str)
                    new_f_or_d = ''.join(f_or_d_list)
                    file_or_dir.append(new_f_or_d)

    # print("after modify: {}".format(config.option.file_or_dir))


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
    stress_help = "Number of iterations to run specified testcase(s)"
    skiplabsetup_help = "Do not run lab_setup post lab install"
    installconf_help = "Full path of lab install configuration file. Template location: " \
                       "/folk/cgts/lab/autoinstall_template.ini"
    resumeinstall_help = 'Resume install of current lab from where it stopped/failed'
    changeadmin_help = "Change password for admin user before test session starts. Revert after test session completes."

    # Common reporting options:
    parser.addoption('--collectall', '--collect_all', '--collect-all', dest='collectall', action='store_true',
                     help=collect_all_help)
    parser.addoption('--reportall', '--report_all', '--report-all', dest='reportall', action='store_true',
                     help=report_help)
    parser.addoption('--report_tag', action='store', dest='report_tag', metavar='tagname', default=None, help=tag_help)

    # Test session options on installed lab:
    parser.addoption('--lab', action='store', metavar='labname', default=None, help=lab_help)
    parser.addoption('--tenant', action='store', metavar='tenantname', default=None, help=tenant_help)
    parser.addoption('--natbox', action='store', metavar='natboxname', default=None, help=natbox_help)
    parser.addoption('--changeadmin', '--change-admin', '--change_admin', dest='changeadmin', action='store_true',
                     help=changeadmin_help)
    parser.addoption('--bootvms', '--boot_vms', '--boot-vms', dest='bootvms', action='store_true', help=bootvm_help)
    parser.addoption('--openstackcli', '--openstack_cli', '--openstack-cli', action='store_true', dest='openstackcli',
                     help=openstackcli_help)
    parser.addoption('--repeat', action='store', metavar='repeat', type=int, default=-1, help=stress_help)

    # Lab install options:
    parser.addoption('--resumeinstall', '--resume-install', dest='resumeinstall', action='store_true',
                     help=resumeinstall_help)
    parser.addoption('--skiplabsetup', '--skip-labsetup', dest='skiplabsetup', action='store_true',
                     help=skiplabsetup_help)
    parser.addoption('--installconf', '--install-conf', action='store', metavar='installconf', default=None,
                     help=installconf_help)
    # Note --lab is also a lab install option, when config file is not provided.


def config_logger(log_dir):
    # logger for log saved in file
    file_name = log_dir + '/TIS_AUTOMATION.log'
    logging.Formatter.converter = gmtime
    formatter_file = "'[%(asctime)s] %(lineno)-4d%(levelname)-5s %(threadName)-8s %(filename)-10s %(funcName)-10s:: %(message)s'"
    logging.basicConfig(level=logging.NOTSET, format=formatter_file, filename=file_name, filemode='w')

    # logger for stream output
    stream_hdler = logging.StreamHandler()
    formatter_stream = logging.Formatter('[%(asctime)s] %(lineno)-4d%(levelname)-5s %(threadName)-8s %(module)s.%(funcName)-8s:: %(message)s')
    stream_hdler.setFormatter(formatter_stream)
    stream_hdler.setLevel(logging.INFO)
    LOG.addHandler(stream_hdler)


def pytest_unconfigure():
    # collect all if needed

    try:
        natbox_ssh = ProjVar.get_var('NATBOX_SSH')
        natbox_ssh.close()
    except:
        pass

    version_and_patch = ''
    try:
        from utils.ssh import ControllerClient
        con_ssh = ControllerClient.get_active_controller()
        version_and_patch = setups.get_version_and_patch_info(con_ssh=con_ssh)
    except Exception as e:
        LOG.debug(e)
        pass

    try:
        log_dir = ProjVar.get_var('LOG_DIR')
        tc_res_path = log_dir + '/test_results.log'
        build_id = ProjVar.get_var('BUILD_ID')
        build_server = ProjVar.get_var('BUILD_SERVER')

        total_exec = TestRes.PASSNUM + TestRes.FAILNUM
        # pass_rate = fail_rate = '0'
        if total_exec > 0:
            pass_rate = "{}%".format(round(TestRes.PASSNUM * 100 / total_exec, 2))
            fail_rate = "{}%".format(round(TestRes.FAILNUM * 100 / total_exec, 2))
            with open(tc_res_path, mode='a') as f:
                # Append general info to result log
                f.write('\n\nLab: {}\n'
                        'Build ID: {}\n'
                        'Build Server: {}\n'
                        'Automation LOGs DIR: {}\n'
                        '{}'.format(ProjVar.get_var('LAB_NAME'), build_id, build_server, ProjVar.get_var('LOG_DIR'),
                                    version_and_patch))
                # Add result summary to beginning of the file
                f.write('\nSummary:\nPassed: {} ({})\nFailed: {} ({})\nTotal Executed: {}\n'.
                        format(TestRes.PASSNUM, pass_rate, TestRes.FAILNUM, fail_rate, total_exec))
                if TestRes.SKIPNUM > 0:
                    f.write('------------\nSkipped: {}'.format(TestRes.SKIPNUM))

            LOG.info("Test Results saved to: {}".format(tc_res_path))
            with open(tc_res_path, 'r') as fin:
                print(fin.read())
    except Exception:
        LOG.exception("Failed to add session summary to test_results.py")

    # Below needs con_ssh to be initialized
    try:
        from utils.ssh import ControllerClient
        con_ssh = ControllerClient.get_active_controller()
    except:
        LOG.warning("No con_ssh found")
        return

    try:
        setups.list_migration_history(con_ssh=con_ssh)
    except:
        LOG.warning("Failed to run nova migration-list")

    vswitch_info_hosts = list(set(ProjVar.get_var('VSWITCH_INFO_HOSTS')))
    if vswitch_info_hosts:
        try:
            setups.scp_vswitch_log(hosts=vswitch_info_hosts, con_ssh=con_ssh)
        except Exception as e:
            LOG.warning("unable to scp vswitch log - {}".format(e.__str__()))

    if has_fail and ProjVar.get_var('COLLECT_ALL'):
        # Collect tis logs if collect all required upon test(s) failure
        # Failure on collect all would not change the result of the last test case.
        try:
            setups.collect_tis_logs(con_ssh)
        except:
            LOG.warning("'collect all' failed.")

    # close ssh session
    try:
        con_ssh.close()
    except:
        pass


def pytest_collection_modifyitems(items):
    # print("Collection modify")
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

    # # # Stress test iterations
    # # TODO: Reorder stress testcases if more than one test collected.

    # original_items = list(items)
    # if stress_iteration > 0:
    #     for item in original_items:
    #         testname = item.nodeid
    #         if '[' not in testname:
    #             testname += '[]'
    #
    #         items.remove(item)
    #         items_to_add = []
    #         for i in range(stress_iteration):
    #             items_to_add.append(item)
    #
    #         for i in range(stress_iteration):
    #             item_to_add = items_to_add[i]
    #             testname_list = list(testname)
    #             index_ = testname_list.index('[') + 1
    #             extra_str = 'iter{}'.format(i)
    #             new_name = testname_list.insert(index_, extra_str)
    #
    #             # Do not work: cannot set attribute nodeid
    #             item_to_add.nodeid = new_name
    #             items.append(item_to_add)
    #
    # print("New items : {}".format(items))


def pytest_generate_tests(metafunc):
    # Modify the order of the fixtures to delete resources before revert host
    # config_host_fixtures = {'class': 'config_host_class', 'module': 'config_host_module'}
    # metafunc.fixturenames = list(set(list(metafunc.fixturenames)))
    # for key, config_fixture in config_host_fixtures.items():
    #     delete_res_fixture = 'delete_resources_{}'.format(key)
    #
    #     if config_fixture in metafunc.fixturenames and delete_res_fixture in metafunc.fixturenames:
    #         index = list(metafunc.fixturenames).index(delete_res_fixture)
    #         index = max([0, index-1])
    #         metafunc.fixturenames.remove(config_fixture)
    #         metafunc.fixturenames.insert(index, config_fixture)

    # Stress fixture
    if metafunc.config.option.repeat > 0:
        # Add autorepeat fixture and parametrize the fixture
        param_name = 'autorepeat'

        count = int(metafunc.config.option.repeat)
        metafunc.parametrize(param_name, range(count),indirect=True, ids=__params_gen(count))

    # print("{}".format(metafunc.fixturenames))


##############################################################
# Manipulating fixture orders based on following pytest rules
# session > module > class > function
# autouse > non-autouse
# alphabetic after full-filling above criteria
#
# Orders we want on fixtures of same scope:
# check_alarms > delete_resources > config_host
#############################################################

@pytest.fixture(scope='session')
def check_alarms():
    LOG.debug("Empty check alarms")
    return


@pytest.fixture(scope='session')
def config_host_class():
    LOG.debug("Empty config host class")
    return


@pytest.fixture(scope='session')
def config_host_module():
    LOG.debug("Empty config host module")


@pytest.fixture(autouse=True)
def a1_fixture(check_alarms):
    return


@pytest.fixture(scope='module', autouse=True)
def c1_fixture(config_host_module):
    return


@pytest.fixture(scope='class', autouse=True)
def c2_fixture(config_host_class):
    return


@pytest.fixture(autouse=True)
def autorepeat(request):
    return


@pytest.fixture(autouse=True)
def autostart(request):
    if change_admin:
        return request.getfuncargvalue('change_admin_password_session')


def __params_gen(iterations):
    ids = []
    for i in range(iterations):
        ids.append('iter{}'.format(i))

    return ids

#####################################
# End of fixture order manipulation #
#####################################


def pytest_sessionfinish(session):

    if stress_iteration > 0 and has_fail:
        # _thread.interrupt_main()
        print('Printing traceback: \n' + '\n'.join(tracebacks))
        pytest.exit("Abort upon stress test failure")
