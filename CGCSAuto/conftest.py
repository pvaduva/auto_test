#
# Copyright (c) 2016 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#


import logging
import os
from time import strftime, gmtime
# import threading    # Used for formatting logger

import pytest

import setups
from consts.filepaths import BuildServerPath
from consts.proj_vars import ProjVar, InstallVars, ComplianceVar
from consts import build_server as build_server_consts
from consts import stx
from utils.mongo_reporter.cgcs_mongo_reporter import collect_and_upload_results
from utils.tis_log import LOG
from utils.cgcs_reporter import parse_log
# Kpi fixture. Do not remove!
from testfixtures.pre_checks_and_configs import collect_kpi


tc_start_time = None
tc_end_time = None
has_fail = False
repeat_count = -1
stress_count = -1
count = -1
no_teardown = False
tracebacks = []
region = None
test_count = 0
console_log = True

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
            msg = "***Failure at test {}: {}".format(call.when, call.excinfo)
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
    global test_count
    test_count += 1
    # reset tc_start and end time for next test case
    build_info = ProjVar.get_var('BUILD_INFO')
    build_id = build_info.get('BUILD_ID', '')
    build_server = build_info.get('BUILD_SERVER', '')
    build_job = build_info.get('JOB', '')

    if ProjVar.get_var("REPORT_ALL") or ProjVar.get_var("REPORT_TAG"):
        if ProjVar.get_var('SESSION_ID'):
            global tracebacks
            search_forward = True \
                if (ComplianceVar.get_var('REFSTACK_SUITE') or
                    ComplianceVar.get_var('DOVETAIL_SUITE')) else False
            try:
                from utils.cgcs_reporter import upload_results
                upload_results.upload_test_result(
                    session_id=ProjVar.get_var('SESSION_ID'),
                    test_name=test_name, result=res_in_tests,
                    start_time=tc_start_time, end_time=tc_end_time,
                    traceback=tracebacks, parse_name=True,
                    search_forward=search_forward)
            except:
                LOG.exception(
                    "Unable to upload test result to TestHistory db! "
                    "Test case: {}".format(test_name))

            finally:
                if repeat_count <= 0:
                    tracebacks = []

        try:
            upload_res = collect_and_upload_results(test_name, res_in_tests,
                                                    ProjVar.get_var('LOG_DIR'),
                                                    build=build_id,
                                                    build_server=build_server,
                                                    build_job=build_job)
            if not upload_res:
                with open(ProjVar.get_var("TCLIST_PATH"), mode='a') as f:
                    f.write('\tUPLOAD_UNSUCC')
        except Exception as e:
            LOG.exception("Unable to upload test result to mongoDB! Test case: {}\n{}".format(test_name, e.__str__()))

    tc_start_time = None


def pytest_runtest_makereport(item, call, __multicall__):
    report = __multicall__.execute()
    my_rep = MakeReport.get_report(item)
    my_rep.update_results(call, report)

    test_name = item.nodeid.replace('::()::', '::')     # .replace('testcases/', '')
    res_in_tests = ''
    res = my_rep.get_results()

    # Write final result to test_results.log
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
            if ProjVar.get_var('PING_FAILURE'):
                setups.add_ping_failure(test_name=test_name)

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

    if repeat_count > 0:
        for key, val in res.items():
            if val[0] == 'Failed':
                global tc_end_time
                tc_end_time = strftime("%Y%m%d %H:%M:%S", gmtime())
                _write_results(res_in_tests='FAIL', test_name=test_name)
                TestRes.FAILNUM += 1
                if ProjVar.get_var('PING_FAILURE'):
                    setups.add_ping_failure(test_name=test_name)

                try:
                    parse_log.parse_test_steps(ProjVar.get_var('LOG_DIR'))
                except Exception as e:
                    LOG.warning("Unable to parse test steps. \nDetails: {}".format(e.__str__()))

                pytest.exit("Skip rest of the iterations upon stress test failure")

    if no_teardown and report.when == 'call':
        for key, val in res.items():
            if val[0] == 'Skipped':
                break
        else:
            pytest.exit("No teardown and skip rest of the tests if any")

    return report

#
# def pytest_collectstart():
#     """
#     Set up the ssh session at collectstart. Because skipif condition is
#     evaluated at the collecting test cases phase.
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
    # set test name for ping vm failure
    test_name = 'test_{}'.format(item.nodeid.rsplit('::test_', 1)[-1].
                                 replace('/', '_'))
    ProjVar.set_var(TEST_NAME=test_name)
    ProjVar.set_var(PING_FAILURE=False)


def pytest_runtest_call(item):
    separator = '+' * 66
    message = "Test steps started:"
    testcase_log(message, item.nodeid, separator=separator, log_type='tc_start')


def pytest_runtest_teardown(item):
    print('')
    message = 'Teardown started:'
    testcase_log(message, item.nodeid, log_type='tc_teardown')


def testcase_log(msg, nodeid, separator=None, log_type=None):
    if separator is None:
        separator = '-----------'

    print_msg = separator + '\n' + msg
    logging_msg = '\n{}{} {}'.format(separator, msg, nodeid)
    if console_log:
        print(print_msg)
    if log_type == 'tc_res':
        global tc_end_time
        tc_end_time = strftime("%Y%m%d %H:%M:%S", gmtime())
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
@pytest.mark.tryfirst
def pytest_configure(config):
    config.addinivalue_line("markers",
                            "features(feature_name1, feature_name2, "
                            "...): mark impacted feature(s) for a test case.")
    config.addinivalue_line("markers",
                            "priorities(, cpe_sanity, p2, ...): mark "
                            "priorities for a test case.")
    config.addinivalue_line("markers",
                            "known_issue(LP-xxxx): mark known issue with "
                            "LP ID or description if no LP needed.")

    if config.getoption('help'):
        return

    # Common reporting params
    collect_all = config.getoption('collectall')
    always_collect = config.getoption('alwayscollect')
    session_log_dir = config.getoption('sessiondir')
    resultlog = config.getoption('resultlog')
    report_all = config.getoption('reportall')
    report_tag = config.getoption('report_tag')
    no_cgcs = config.getoption('nocgcsdb')
    col_kpi = config.getoption('col_kpi')
    telnet_log = config.getoption('telnetlog')

    # Test case params on installed system
    testcase_config = config.getoption('testcase_config')
    lab_arg = config.getoption('lab')
    natbox_arg = config.getoption('natbox')
    tenant_arg = config.getoption('tenant')
    horizon_visible = config.getoption('horizon_visible')
    remote_cli = config.getoption('remote_cli')
    ipv6_oam = config.getoption('ipv6_oam')

    global change_admin
    change_admin = config.getoption('changeadmin')
    global repeat_count
    repeat_count = config.getoption('repeat')
    global stress_count
    stress_count = config.getoption('stress')
    global count
    if repeat_count > 0:
        count = repeat_count
    elif stress_count > 0:
        count = stress_count

    # neccesary install params if --lab is not given
    controller_arg = config.getoption('controller')
    compute_arg = config.getoption('compute')
    storage_arg = config.getoption('storage')
    lab_file_dir = config.getoption('file_dir')
    build_server = config.getoption('build_server')

    global no_teardown
    no_teardown = config.getoption('noteardown')
    if repeat_count > 0 or no_teardown:
        ProjVar.set_var(NO_TEARDOWN=True)
    keystone_debug = config.getoption('keystone_debug')
    install_conf = config.getoption('installconf')
    global region
    region = config.getoption('region')

    collect_netinfo = config.getoption('netinfo')

    # Determine lab value.
    lab = natbox = None
    # Separate install conf parsing so that it's easy to take it out for
    # upstream project
    if install_conf and not lab_arg:
        lab = setups.get_lab_from_installconf(installconf_path=install_conf,
                                              controller_arg=controller_arg,
                                              compute_arg=compute_arg,
                                              storage_arg=storage_arg,
                                              lab_files_dir=lab_file_dir,
                                              bs=build_server)
    if lab_arg:
        lab = setups.get_lab_dict(lab_arg)
    if natbox_arg:
        natbox = setups.get_natbox_dict(natbox_arg)

    lab, natbox = setups.setup_testcase_config(testcase_config, lab=lab,
                                               natbox=natbox)
    if ipv6_oam:
        ProjVar.set_var(IPV6_OAM=True)
        lab = setups.convert_to_ipv6(lab=lab)

    tenant = tenant_arg.upper() if tenant_arg else 'TENANT1'

    # Log collection params
    collect_all = True if collect_all else False
    always_collect = True if always_collect else False
    if no_cgcs:
        ProjVar.set_var(CGCS_DB=False)
    if telnet_log:
        ProjVar.set_var(COLLECT_TELNET=True)
    if keystone_debug:
        ProjVar.set_var(KEYSTONE_DEBUG=True)
    if config.getoption('noconsolelog'):
        global console_log
        console_log = False

    # If floating ip cannot be reached, whether to try to ping/ssh
    # controller-0 unit IP, etc.
    if collect_netinfo:
        ProjVar.set_var(COLLECT_SYS_NET_INFO=True)

    # Reporting params
    report_all = True if report_all else False
    if report_all:
        report_tag = report_tag if report_tag else 'cgcsauto'

    horizon_visible = True if horizon_visible else False
    remote_cli = True if remote_cli else False
    if remote_cli:
        ProjVar.set_var(REMOTE_CLI=True)

    if col_kpi:
        ProjVar.set_var(COLLECT_KPI=True)

    # Compliance params:
    file_or_dir = config.getoption('file_or_dir')
    refstack_suite = dovetail_suite = config.getoption('compliance_suite')
    if 'refstack' in str(file_or_dir):
        if not refstack_suite:
            refstack_suite = \
                '/folk/cgts/compliance/RefStack/osPowered.2017.09/' \
                '2017.09-platform-test-list.txt'
        from consts.proj_vars import ComplianceVar
        ComplianceVar.set_var(REFSTACK_SUITE=refstack_suite)
    elif 'dovetail' in str(file_or_dir):
        if not dovetail_suite:
            dovetail_suite = '--testarea mandatory'
        from consts.proj_vars import ComplianceVar
        ComplianceVar.set_var(DOVETAIL_SUITE=dovetail_suite)

    if session_log_dir:
        log_dir = session_log_dir
    else:
        # compute directory for all logs based on resultlog arg, lab,
        # and timestamp on local machine
        resultlog = resultlog if resultlog else os.path.expanduser("~")
        if '/AUTOMATION_LOGS' in resultlog:
            resultlog = resultlog.split(sep='/AUTOMATION_LOGS')[0]
        resultlog = os.path.join(resultlog, 'AUTOMATION_LOGS')
        lab_name = lab['short_name']
        time_stamp = strftime('%Y%m%d%H%M')
        if refstack_suite:
            suite_name = os.path.basename(refstack_suite).split('.txt')[0]
            log_dir = '{}/refstack/{}/{}_{}'.format(resultlog, lab_name,
                                                    time_stamp, suite_name)
        elif dovetail_suite:
            suite_name = dovetail_suite.split(sep='--')[-1].replace(' ', '-')
            log_dir = '{}/dovetail/{}/{}_{}'.format(resultlog, lab_name,
                                                    time_stamp, suite_name)
        else:
            log_dir = '{}/{}/{}'.format(resultlog, lab_name, time_stamp)
    os.makedirs(log_dir, exist_ok=True)

    # set global constants, which will be used for the entire test session, etc
    ProjVar.init_vars(lab=lab, natbox=natbox, logdir=log_dir, tenant=tenant,
                      collect_all=collect_all,
                      report_all=report_all, report_tag=report_tag,
                      always_collect=always_collect,
                      horizon_visible=horizon_visible)

    if lab.get('central_region'):
        ProjVar.set_var(IS_DC=True,
                        PRIMARY_SUBCLOUD=config.getoption('subcloud'))

    if setups.is_vbox():
        ProjVar.set_var(IS_VBOX=True)

    InstallVars.set_install_var(lab=lab)

    config_logger(log_dir, console=console_log)

    # set resultlog save location
    config.option.resultlog = ProjVar.get_var("PYTESTLOG_PATH")


def pytest_addoption(parser):
    testconf_help = "Absolute path for testcase config file. Template can be " \
                    "found from " \
                    "CGCSAuto/utils/stx-test.conf"
    lab_help = "Lab to connect to. Valid input: Hardware labs - use lab name " \
               "such as 'r720_2-7', 'yow-cgcs-r720-3_7';" \
               "if it's a new lab, use floating ip before it is added to the " \
               "automation framework. " \
               "VBox - use vbox or the floating ip of your tis system if it " \
               "is not 10.10.10.2. " \
               "Cumulus - floating ip of the cumulus tis system"
    tenant_help = "Default tenant to use when unspecified. Valid values: " \
                  "tenant1, tenant2, or admin"
    natbox_help = "NatBox to use. Default: NatBox for hardware labs. Valid " \
                  "values: nat_hw (for hardware labs), " \
                  "<your own natbox ip> (for VBox, choose the 128.224 ip), " \
                  "or nat_cumulus (for Cumulus)."
    collect_all_help = "Run collect all on TiS server at the end of test " \
                       "session if any test fails."
    logdir_help = "Directory to store test session logs. If this is " \
                  "specified, then --resultlog will be ignored."
    stress_help = "Number of iterations to run specified testcase(s). Abort " \
                  "rest of the test session on first failure"
    count_help = "Repeat tests x times - NO stop on failure"
    horizon_visible_help = "Display horizon on screen"
    no_console_log = 'Print minimal console logs'
    changeadmin_help = "Change password for admin user before test session " \
                       "starts. Revert after test session completes."
    region_help = "Multi-region parameter. Use when connected region is " \
                  "different than region to test. " \
                  "e.g., creating vm on RegionTwo from RegionOne"
    subcloud_help = "Default subcloud used for automated test when boot vm, " \
                    "etc. 'subcloud-1' if unspecified."
    report_help = "Upload results and logs to the test results database."
    tag_help = "Tag to be used for uploading logs to the test results database."
    telnetlog_help = "Collect telnet logs throughout the session"
    remote_cli_help = 'Run testcases using remote CLI'

    # Test session options on installed and configured STX system:
    parser.addoption('--testcase-config', action='store',
                     metavar='testcase_config', default=None,
                     help=testconf_help)
    parser.addoption('--lab', action='store', metavar='lab', default=None,
                     help=lab_help)
    parser.addoption('--tenant', action='store', metavar='tenantname',
                     default=None, help=tenant_help)
    parser.addoption('--natbox', action='store', metavar='natbox', default=None,
                     help=natbox_help)

    # Optional test case args
    parser.addoption('--changeadmin', '--change-admin', '--change_admin',
                     dest='changeadmin', action='store_true',
                     help=changeadmin_help)
    parser.addoption('--remote-cli', '--remotecli', '--remote_cli',
                     action='store_true', dest='remote_cli',
                     help=remote_cli_help)
    parser.addoption('--kpi', '--collect-kpi', '--collect_kpi',
                     action='store_true', dest='col_kpi',
                     help="Collect kpi for applicable test cases")

    # Debugging/Log collection options:
    parser.addoption('--sessiondir', '--session_dir', '--session-dir',
                     action='store', dest='sessiondir',
                     metavar='sessiondir', default=None, help=logdir_help)
    parser.addoption('--collectall', '--collect_all', '--collect-all',
                     dest='collectall', action='store_true',
                     help=collect_all_help)
    parser.addoption('--alwayscollect', '--always-collect', '--always_collect',
                     dest='alwayscollect',
                     action='store_true', help=collect_all_help)
    parser.addoption('--repeat', action='store', metavar='repeat', type=int,
                     default=-1, help=stress_help)
    parser.addoption('--stress', metavar='stress', action='store', type=int,
                     default=-1, help=count_help)
    parser.addoption('--no-teardown', '--no_teardown', '--noteardown',
                     dest='noteardown', action='store_true')
    parser.addoption('--netinfo', '--net-info', dest='netinfo',
                     action='store_true',
                     help="Collect system networking info if scp keyfile fails")
    parser.addoption('--horizon-visible', '--horizon_visible',
                     action='store_true', dest='horizon_visible',
                     help=horizon_visible_help)
    parser.addoption('--noconsolelog', '--noconsole', '--no-console-log',
                     '--no_console_log', '--no-console',
                     '--no_console', action='store_true', dest='noconsolelog',
                     help=no_console_log)

    parser.addoption('--no-cgcsdb', '--no-cgcs-db', '--nocgcsdb',
                     action='store_true', dest='nocgcsdb')
    parser.addoption('--telnetlog', '--telnet-log', dest='telnetlog',
                     action='store_true', help=telnetlog_help)
    parser.addoption('--keystone_debug', '--keystone-debug',
                     action='store_true', dest='keystone_debug')
    parser.addoption('--reportall', '--report_all', '--report-all',
                     dest='reportall', action='store_true',
                     help=report_help)
    parser.addoption('--report_tag', '--report-tag', action='store',
                     dest='report_tag', metavar='tagname', default=None,
                     help=tag_help)

    # Multi-region or distributed cloud options
    parser.addoption('--region', action='store', metavar='region',
                     default=None, help=region_help)
    parser.addoption('--subcloud', action='store', metavar='subcloud',
                     default='subcloud-1', help=subcloud_help)

    ##################################
    # Lab fresh_install or upgrade options #
    ##################################

    # Install
    installconf_help = "Full path of lab fresh_install configuration file. " \
                       "Template location: " \
                       "/folk/cgts/lab/autoinstall_template.ini"
    resumeinstall_help = 'Resume fresh_install of current lab from where it ' \
                         'stopped/failed or from a given step'
    wipedisk_help = 'Wipe the disk(s) on the hosts'
    boot_help = 'Select how to boot the lab. Default is pxe. Options are: \n' \
                'feed: boot from the network using pxeboot \n' \
                'usb_burn: burn the USB using iso-path and boot from it \n' \
                'usb_boot: Boot from load existing on USB \n' \
                'pxe_iso: iso install flag'
    iso_path_help = 'Full path to ISO file. Default is <build-dir'
    skip_help = "Comma seperated list of parts of the install to skip. " \
                "Usage: --skip=labsetup,config_controller \n" \
                "labsetup: Do not run lab_setup post lab install \n" \
                "pxeboot: Don't modify pxeboot.cfg \n" \
                "feed: skip setup of network feed"
    kuber_help = 'Use kubernetes option in config_controller'

    parser.addoption('--resumeinstall', '--resume-install', '--resume_install',
                     dest='resumeinstall', action='store',
                     help=resumeinstall_help, const=True, nargs='?',
                     default=False)
    parser.addoption('--stop', dest='stop_step', action='store',
                     help='Which test step to stop at', default=None)
    parser.addoption('--skip', dest='skiplist', action='store', nargs='*',
                     help=skip_help)
    parser.addoption('--wipedisk',  dest='wipedisk', action='store_true',
                     help=wipedisk_help)
    parser.addoption('--boot', dest='boot_list', action='store',
                     default='feed', help=boot_help)
    parser.addoption('--installconf', '--install-conf', action='store',
                     metavar='installconf', default=None,
                     help=installconf_help)
    parser.addoption('--security', dest='security', action='store',
                     default='standard')
    parser.addoption('--drop', dest='drop_num', action='store',
                     help='an integer representing which drop to install')
    # Ceph Post Install
    ceph_mon_device_controller0_help = "The disk device to use for ceph " \
                                       "monitor in controller-0. e.g., /dev/sdc"
    ceph_mon_device_controller1_help = "The disk device to use for ceph " \
                                       "monitor in controller-1. e.g., /dev/sdb"
    ceph_mon_gib_help = "The size of the partition to allocate on a " \
                        "controller disk for the Ceph monitor logical " \
                        "volume, in GiB (the default value is 20)"
    build_server_help = "TiS build server host name where the Titium load " \
                        "software is downloaded from." \
                        " ( default: {})".format(build_server_consts.
                                                 DEFAULT_BUILD_SERVER['name'])
    tis_builds_dir_help = "Directory name under build workspace " \
                          "(/localdisk/loadbuild/jenkins) containing " \
                          "directories for Titanium Server loads (default: " \
                          "Titanium_R6_build)  e.g. TS_15.12_Host, " \
                          "TS_16.10_Build, TS_16.10_Prestaging_Build, " \
                          "TC_17.06_Host, TC_18.03_Host, TC_18.07_Host, " \
                          "CGCS_6.0_Host, StarlingX_18.10, " \
                          "StarlingX_Upstream_build, Titanium_R6_build. " \
                          "Default is Titanium_R6_build"

    parser.addoption('--ceph-mon-dev-controller-0',
                     '--ceph_mon_dev_controller-0',
                     dest='ceph_mon_dev_controller_0',
                     action='store', metavar='DISK_DEVICE',
                     help=ceph_mon_device_controller0_help)
    parser.addoption('--ceph-mon-dev-controller-1',
                     '--ceph_mon_dev_controller-1',
                     dest='ceph_mon_dev_controller_1',
                     action='store', metavar='DISK_DEVICE',
                     help=ceph_mon_device_controller1_help)
    parser.addoption('--ceph-mon-gib', '--ceph_mon_dev_gib',
                     dest='ceph_mon_gib',
                     action='store', metavar='SIZE',  help=ceph_mon_gib_help)
    parser.addoption('--boot-server', '--boot_server', dest='boot_server',
                     help='server to boot from. Default is yow-tuxlab2')
    parser.addoption('--build-server', '--build_server',  dest='build_server',
                     action='store', metavar='SERVER',
                     default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=build_server_help)
    parser.addoption('--tis-builds-dir', '--tis_builds_dir',
                     dest='tis_builds_dir',
                     action='store', metavar='DIR',  help=tis_builds_dir_help)

    # install help
    lab_files = ["TiS_config.ini_centos", "hosts_bulk_add.xml",
                 "lab_setup.conf", "settings.ini"]
    file_dir_help = "directory that contains the following lab files: " \
                    "{}. ".format(' '.join(v[1] for v in lab_files)) +\
                    "Custom directories can be found at: " \
                    "/folk/cgts/lab/customconfigs" \
                    "Default is: <load_path>/lab/yow/<lab_name>"
    controller_help = "space-separated list of VLM barcodes for controllers"
    compute_help = "space-separated list of VLM barcodes for computes"
    storage_help = "space-separated list of VLM barcodes for storage nodes"
    guest_image_help = "The full path to the tis-centos-guest.img in " \
                       "build-server (default: {})".\
        format(BuildServerPath.DEFAULT_GUEST_IMAGE_PATH)
    heat_help = "The full path to the python heat templates" \
                "( default: {} )".format(BuildServerPath.HEAT_TEMPLATES_PREV)
    dcfloatip_help = " The distributed cloud central region floating ip if " \
                     "subcloud is specified."
    openstack_install_help = 'flag for openstack install or not; default is ' \
                             'false.'
    deploy_openstack_from_controller_1_help = ''
    ipv6_install_help = 'ipv6 OAM install; default is false.'
    dc_ipv6_help = 'Install subclouds via IPv6'
    helm_chart_path_help = 'Full path to Helm charts files. Default is ' \
                           '<build-dir>/std/build-helm/stx'
    unmanaged_install_help = \
        'flag to leave subcloud as unmanaged after install.'
    extract_deploy_help = "flag whether to extract deployment yaml files"
    vswitch_type_help = 'Select the vswitch type to install. Default is pxe. ' \
                        'Options are: \n' \
                        'ovs \n' \
                        'ovs-dpdk: a default value \n' \
                        'avs \n' \
                        'none'

    # Custom install options
    parser.addoption('--lab_file_dir', '--lab-file-dir', dest='file_dir',
                     action='store', metavar='DIR',
                     help=file_dir_help)
    parser.addoption('--controller', dest='controller', action='store',
                     help=controller_help)
    parser.addoption('--compute', dest='compute', action='store',
                     help=compute_help)
    parser.addoption('--storage', dest='storage', action='store',
                     help=storage_help)
    parser.addoption('--guest_image', '--guest-image', '--guest_image_path',
                     '--guest-image-path',
                     dest='guest_image_path', action='store',
                     metavar='guest image full path',
                     default=BuildServerPath.DEFAULT_GUEST_IMAGE_PATH,
                     help=guest_image_help)
    parser.addoption('--heat_templates', '--heat-templates',
                     '--heat_templates_path', '--heat-templates-path',
                     dest='heat_templates', action='store',
                     metavar='heat templates full path',
                     default=None, help=heat_help)
    parser.addoption('--iso-path', '--isopath', '--iso_path', dest='iso_path',
                     action='store', default=None,
                     help=iso_path_help)
    parser.addoption('--kubernetes', '--kuber', '--kub',
                     dest='kubernetes_config', action='store_true',
                     help=kuber_help)
    parser.addoption('--no-openstack', '--no-openstack-install',
                     dest='no_openstack',
                     action='store_true', default=False,
                     help=openstack_install_help)
    parser.addoption('--deploy-openstack-from-controller-1',
                     dest='deploy_openstack_from_controller_1',
                     action='store_true', default=False,
                     help=deploy_openstack_from_controller_1_help)
    parser.addoption('--helm-chart-path', '--helmchartpath',
                     '--helm_chart_path', dest='helm_chart_path',
                     action='store', default=None,  help=helm_chart_path_help)
    parser.addoption('--no-manage',  dest='no_manage', action='store_true',
                     default=False,
                     help=unmanaged_install_help)
    parser.addoption('--extract-deploy-config', '--extract-deploy',
                     '--ext-deploy',  dest='extract_deploy_config',
                     action='store_true', default=False,
                     help=extract_deploy_help)
    parser.addoption('--vswitch-type', '--vswitch', dest='vswitch_type',
                     action='store', default='ovs-dpdk',
                     help=vswitch_type_help)
    parser.addoption('--ipv6-oam', '--ipv6', dest='ipv6_oam', action='store_true', default=False,
                     help=ipv6_install_help)

    # DC Options:
    parser.addoption('--dc-float-ip', '--dc_float_ip', '--dcfip',
                     dest='dc_float_ip', action='store', default=None,
                     help=dcfloatip_help)
    parser.addoption('--dc-ipv6',  dest='dc_ipv6', action='store_true', default=False,
                     help=dc_ipv6_help)

    # Note --lab is also a lab fresh_install option, when config file
    # is not provided.

    ###############################
    #  Upgrade options #
    ###############################

    upgrade_version_help = "TiS next software version that the lab is " \
                           "upgraded to. Valid options are: {}".\
        format(' '.join(v[1] for v in stx.SUPPORTED_UPGRADES))

    upgrade_build_dir_path_help = "The path to the upgrade software release " \
                                  "build directory in build server." \
                                  " eg: /localdisk/loadbuild/jenkins/" \
                                  "TS_16.10_Host/latest_build/. " \
                                  " Otherwise the default  build dir path " \
                                  "for the upgrade software " \
                                  "version will be used"

    license_help = "The full path to the new release software license file in" \
                   " build-server. e.g /folk/cgts/lab/TiS16-full.lic or " \
                   "/folk/cgts/lab/TiS16-CPE-full.lic. Otherwise, default " \
                   "license for the upgrade release will be used"

    orchestration_help = "The point in upgrade procedure where we start to " \
                         "use orchestration. Possible options are:" \
                         "  default - to start orchestration after " \
                         "controller-1 is upgraded; " \
                         "  storage:<#> - to start orchestration after <#> " \
                         "storage (s) are upgraded normally; " \
                         "  compute:<#> - start orchestration after <#> " \
                         "compute(s) are upgraded normally; " \
                         " The default is default. Applicable only for " \
                         "upgrades from R3."

    parser.addoption('--upgrade-version', '--upgrade_version', '--upgrade',
                     dest='upgrade_version',
                     action='store', metavar='VERSION',  default=None,
                     help=upgrade_version_help)

    parser.addoption('--tis-build-dir', '--tis_build_dir',
                     dest='tis_build_dir', action='store', metavar='DIR',
                     help=upgrade_build_dir_path_help)
    parser.addoption('--license',  dest='upgrade_license', action='store',
                     metavar='license full path', help=license_help)

    parser.addoption('--orchestration', '--orchestration-after',
                     '--orchestration_after', dest='orchestration_after',
                     action='store', metavar='HOST_PERSONALITY:NUM',
                     default='default', help=orchestration_help)

    ####################
    # Patching options #
    ####################
    patch_build_server_help = "TiS Patch build server host name from where " \
                              "the upgrade release software is downloaded. " \
                              "Use default build server when unspecified"

    patch_dir_help = "Directory or file on the Build Server where the patch " \
                     "files located. Because the version must " \
                     "match that of the system software on the target lab, " \
                     "hence by default, we will deduce " \
                     "the location of the patch files and their version, " \
                     "unless users specify an absolute path " \
                     "containing valid patch files. This directory is " \
                     "usually a symbolic link in the load-build " \
                     "directory."

    patch_base_dir_help = "Directory on the Build Server under which the " \
                          "patch files are located. By default, " \
                          "it is: {}".\
        format('/localdisk/loadbuild/jenkins/CGCS_5.0_Test_Patch_Build')

    parser.addoption('--patch-build-server', '--patch_build_server',
                     dest='patch_build_server',
                     action='store', metavar='SERVER', default=None,
                     help=patch_build_server_help)

    parser.addoption('--patch-dir', '--patch_dir',  dest='patch_dir',
                     default=None,
                     action='store', metavar='DIR',  help=patch_dir_help)

    parser.addoption('--patch-base-dir', '--patch_base_dir',
                     dest='patch_base_dir', default=None,
                     action='store', metavar='BASEDIR',
                     help=patch_base_dir_help)

    ###############################
    #  Orchestration options #
    ###############################
    apply_strategy_help = \
        "How the orchestration strategy is applied:  " \
        "serial - apply orchestration strategy one node  at a time; " \
        "parallel - apply orchestration strategy in parallel; " \
        " ignore - do not apply the orchestration strategy; " \
        "If not specified,  the system will choose the option to apply the" \
        "strategy. Applicable only for upgrades from R3."
    max_parallel_compute_help = \
        "The maximum number of compute hosts to upgrade in parallel, " \
        "if parallel apply type  is selected"
    alarm_restriction_help = \
        "Indicates how to handle alarm restrictions based on the management " \
        "affecting statuses of any existing alarms. relaxed - orchestration " \
        "is allowed to proceed if no management affecting alarms present " \
        "strict - orchestration is not allowed if alarms are present"
    instance_action_help = \
        "Indicates how to VMs are moved from compute hosts when apply " \
        "reboot-required patches. There are two possible values for moving " \
        "the VMs off the compute hosts: start-stop -  This is typically used " \
        "for VMs that do not support migration.  migrate - instances are " \
        "either live migrated or cold migrated  before compute host is patched."

    parser.addoption('--controller-apply-type', '--controller_apply_type',
                     '--ctra',  dest='controller_strategy',
                     action='store',  help=apply_strategy_help)

    parser.addoption('--storage-apply-type', '--storage_apply_type',
                     '--sstra',  dest='storage_strategy',
                     action='store',  help=apply_strategy_help)

    parser.addoption('--compute-apply-type', '--compute_apply_type',
                     '--cstra', dest='compute_strategy',
                     action='store',  help=apply_strategy_help)

    parser.addoption('--max-parallel-computes', '--max_parallel_computes',
                     dest='max_parallel_computes',
                     action='store',  help=max_parallel_compute_help)

    parser.addoption('--alarm-restrictions', '--alarm_restrictions',
                     dest='alarm_restrictions', action='store',
                     default='strict',  help=alarm_restriction_help)

    parser.addoption('--instance-action', '--instance_action',
                     dest='instance_action', action='store',
                     default='stop-start',  help=instance_action_help)

    ###############################
    #  Backup and Restore options #
    ###############################

    # Backup only
    keep_backups = "Whether to keep the backupfiles from " \
                   "controller-0:/opt/backups after transfer " \
                   "to the specified destination. Default is remove."
    parser.addoption('--keep-backups', '--keep_backups',  dest='keep_backups',
                     action='store_true', help=keep_backups)

    # Common for backup and restore
    backup_server_destination_help = \
        "Whether to save/get backupfiles on/from USB. Default is test server." \
        " When true, 16G USB  or above must be plugged to controller-0 "
    backup_destination_path_help = \
        "The path the backup files are copied to/taken from if destination " \
        "is not a USB. For USB, the backup files are at mount point: " \
        "/media/sysadmin/backups. For Test Server, the default is " \
        "/sandbox/backups."

    parser.addoption('--usb', '--usb',  dest='use_usb', action='store_true',
                     help=backup_server_destination_help)
    parser.addoption('--backup-path', '--backup_path',  dest='backup_path',
                     action='store', metavar='DIR',
                     help=backup_destination_path_help)

    # Restore only
    parser.addoption('--backup-build-id', '--backup_build-id',
                     dest='backup_build_id',
                     action='store', help="The build id of the backup")

    parser.addoption('--backup-builds-dir', '--backup_builds-dir',
                     dest='backup_builds_dir', action='store',
                     help="The Titanium builds dir where the backup build id "
                          "belong. Such as CGCS_5.0_Host or TC_17.06_Host")
    parser.addoption('--cinder-backup', '--cinder_backup',
                     dest='cinder_backup', action='store_true',
                     help="Using upstream cinder-backup CLIs", default=True)

    parser.addoption('--low-latency', '--low_latency', '--lowlatency',
                     '--low-lat', '--low_lat', '--lowlat',
                     dest='low_latency', action='store_true',
                     help="Restore a low-latency lab")

    parser.addoption('--reinstall-storage', '--reinstall-storage',
                     dest='reinstall_storage',  action='store_true',
                     default=False,
                     help="Whether to reinstall storage nodes or not. By "
                          "default, do not reinstall them.")
    parser.addoption('--skip-setup-feed', '--skip_setup_feed',
                     dest='skip_setup_feed',
                     action='store_true',
                     help="Use existing feed on tuxlab (tuxlab1/2)")

    parser.addoption('--skip-reinstall', '--skip_reinstall',
                     dest='skip_reinstall',
                     action='store_true',
                     help="Reuse the lab in states without reinstall it. "
                          "This will be helpful if the lab was/will be "
                          "in customized way.")

    parser.addoption('--has-wipe-ceph-osds', '--has_wipe_ceph_osds',
                     dest='has_wipe_ceph_osds', action='store_true',
                     default=False, help='')

    parser.addoption('--wipe-ceph-osds', '--wipe_ceph_osds',
                     dest='wipe_ceph_osds', action='store_true',
                     default=False, help='')

    parser.addoption('--restore-pre-boot-controller0',
                     dest='restore_pre_boot_controller0', action='store_true',
                     default=False, help='')

    parser.addoption('--stop-before-ansible-restore',
                     dest='stop_before_ansible_restore', action='store_true',
                     default=False, help='')

    # Clone only
    parser.addoption('--dest-labs', '--dest_labs',  dest='dest_labs',
                     action='store',
                     help="Comma separated list of AIO lab short names"
                          " where the cloned image iso file is transferred "
                          "to. Eg WCP_68,67  or SM_1,SM2.")
    ####################
    #  Compliance Test #
    ####################
    compliance_help = "Compliance suite parameter." \
                      "\nRefStack: test list file path. Need to be " \
                      "accessible. e.g., " \
                      "'/folk/cgts/compliance/RefStack/osPowered." \
                      "2018.02/2018.02-platform-test-list.txt'" \
                      "\nDovetail: dovetail run parameter. " \
                      "e.g., '--testsuite ovp.1.0.0'. Default is " \
                      "'--testarea mandatory'"
    parser.addoption('--compliance_suite', '--compliance-suite',
                     dest='compliance_suite', help=compliance_help)


def config_logger(log_dir, console=True):
    # logger for log saved in file
    file_name = log_dir + '/TIS_AUTOMATION.log'
    logging.Formatter.converter = gmtime
    log_format = '[%(asctime)s] %(lineno)-5d%(levelname)-5s %(threadName)-8s ' \
                 '%(module)s.%(funcName)-8s:: %(message)s'
    tis_formatter = logging.Formatter(log_format)
    LOG.setLevel(logging.NOTSET)

    tmp_path = os.path.join(os.path.expanduser('~'), '.tmp_log')
    # clear the tmp log with best effort so it wont keep growing
    try:
        os.remove(tmp_path)
    except:
        pass
    logging.basicConfig(level=logging.NOTSET, format=log_format,
                        filename=tmp_path, filemode='w')

    # file handler:
    file_handler = logging.FileHandler(file_name)
    file_handler.setFormatter(tis_formatter)
    file_handler.setLevel(logging.DEBUG)
    LOG.addHandler(file_handler)

    # logger for stream output
    console_level = logging.INFO if console else logging.CRITICAL
    stream_hdler = logging.StreamHandler()
    stream_hdler.setFormatter(tis_formatter)
    stream_hdler.setLevel(console_level)
    LOG.addHandler(stream_hdler)

    print("LOG DIR: {}".format(log_dir))


def pytest_unconfigure(config):
    # collect all if needed
    if config.getoption('help'):
        return

    try:
        natbox_ssh = ProjVar.get_var('NATBOX_SSH')
        natbox_ssh.close()
    except:
        pass

    version_and_patch = ''
    try:
        version_and_patch = setups.get_version_and_patch_info()
    except Exception as e:
        LOG.debug(e)
        pass
    log_dir = ProjVar.get_var('LOG_DIR')
    if not log_dir:
        try:
            from utils.clients.ssh import ControllerClient
            ssh_list = ControllerClient.get_active_controllers(fail_ok=True)
            for con_ssh_ in ssh_list:
                con_ssh_.close()
        except:
            pass
        return

    log_dir = ProjVar.get_var('LOG_DIR')
    if not log_dir:
        try:
            from utils.clients.ssh import ControllerClient
            ssh_list = ControllerClient.get_active_controllers(fail_ok=True)
            for con_ssh_ in ssh_list:
                con_ssh_.close()
        except:
            pass
        return

    try:
        tc_res_path = log_dir + '/test_results.log'
        build_info = ProjVar.get_var('BUILD_INFO')
        build_id = build_info.get('BUILD_ID', '')
        build_job = build_info.get('JOB', '')
        build_server = build_info.get('BUILD_HOST', '')
        session_id = ProjVar.get_var('SESSION_ID')
        session_tag = ProjVar.get_var('REPORT_TAG')
        system_config = ProjVar.get_var('SYS_TYPE')
        session_str = 'Session Tag: {}\nSession ID: {}\n'.format(
            session_tag, session_id) if session_id else ''
        total_exec = TestRes.PASSNUM + TestRes.FAILNUM
        # pass_rate = fail_rate = '0'
        if total_exec > 0:
            pass_rate = "{}%".format(
                round(TestRes.PASSNUM * 100 / total_exec, 2))
            fail_rate = "{}%".format(
                round(TestRes.FAILNUM * 100 / total_exec, 2))
            with open(tc_res_path, mode='a') as f:
                # Append general info to result log
                f.write('\n\nLab: {}\n'
                        'Build ID: {}\n'
                        'Job: {}\n'
                        'Build Server: {}\n'
                        'System Type: {}\n'
                        'Automation LOGs DIR: {}\n'
                        'Ends at: {}\n'
                        '{}'  # test session id and tag
                        '{}'.format(ProjVar.get_var('LAB_NAME'), build_id,
                                    build_job, build_server, system_config,
                                    ProjVar.get_var('LOG_DIR'), tc_end_time,
                                    session_str, version_and_patch))
                # Add result summary to beginning of the file
                f.write(
                    '\nSummary:\nPassed: {} ({})\nFailed: {} ({})\nTotal '
                    'Executed: {}\n'.
                    format(TestRes.PASSNUM, pass_rate, TestRes.FAILNUM,
                           fail_rate, total_exec))
                if TestRes.SKIPNUM > 0:
                    f.write('------------\nSkipped: {}'.format(TestRes.SKIPNUM))

            LOG.info("Test Results saved to: {}".format(tc_res_path))
            with open(tc_res_path, 'r') as fin:
                print(fin.read())
    except Exception as e:
        LOG.exception(
            "Failed to add session summary to test_results.py. "
            "\nDetails: {}".format(e.__str__()))
    # Below needs con_ssh to be initialized
    try:
        from utils.clients.ssh import ControllerClient
        con_ssh = ControllerClient.get_active_controller()
    except:
        LOG.warning("No con_ssh found")
        return

    if ProjVar.get_var('COLLECT_KPI'):
        try:
            from utils.kpi import upload_kpi
            upload_kpi.upload_kpi(kpi_file=ProjVar.get_var('KPI_PATH'))
        except Exception as e:
            LOG.warning("Unable to upload KPIs. {}".format(e.__str__()))

    try:
        parse_log.parse_test_steps(ProjVar.get_var('LOG_DIR'))
    except Exception as e:
        LOG.warning(
            "Unable to parse test steps. \nDetails: {}".format(e.__str__()))

    if test_count > 0 and (ProjVar.get_var('ALWAYS_COLLECT') or (
            has_fail and ProjVar.get_var('COLLECT_ALL'))):
        # Collect tis logs if collect all required upon test(s) failure
        # Failure on collect all would not change the result of the last test
        # case.
        try:
            setups.collect_tis_logs(con_ssh)
        except Exception as e:
            LOG.warning("'collect all' failed. {}".format(e.__str__()))

    ssh_list = ControllerClient.get_active_controllers(fail_ok=True,
                                                       current_thread_only=True)
    for con_ssh_ in ssh_list:
        try:
            con_ssh_.close()
        except:
            pass


def pytest_collection_modifyitems(items):
    move_to_last = []
    absolute_last = []

    for item in items:
        # re-order tests:
        trylast_marker = item.get_closest_marker('trylast')
        abslast_marker = item.get_closest_marker('abslast')

        if abslast_marker:
            absolute_last.append(item)
        elif trylast_marker:
            move_to_last.append(item)

        priority_marker = item.get_closest_marker('priorities')
        if priority_marker is not None:
            priorities = priority_marker.args
            for priority in priorities:
                item.add_marker(eval("pytest.mark.{}".format(priority)))

        feature_marker = item.get_closest_marker('features')
        if feature_marker is not None:
            features = feature_marker.args
            for feature in features:
                item.add_marker(eval("pytest.mark.{}".format(feature)))

        # known issue marker
        known_issue_mark = item.get_closest_marker('known_issue')
        if known_issue_mark is not None:
            issue = known_issue_mark.args[0]
            msg = "{} has a workaround due to {}".format(item.nodeid, issue)
            print(msg)
            LOG.debug(msg=msg)
            item.add_marker(eval("pytest.mark.known_issue"))

        # add dc maker to all tests start with test_dc_xxx
        dc_maker = item.get_marker('dc')
        if not dc_maker and 'test_dc_' in item.nodeid:
            item.add_marker(pytest.mark.dc)

    # add trylast tests to the end
    for item in move_to_last:
        items.remove(item)
        items.append(item)

    for i in absolute_last:
        items.remove(i)
        items.append(i)

    # Repeat collected test cases x times
    if count and count > 1:
        print(' Run collected test cases {} times'.format(count))
        items[:] = items * count
        # print('items: {}'.format(items))


def pytest_generate_tests(metafunc):
    # Prefix 'remote_cli' to test names so they are reported as a different
    # testcase
    if ProjVar.get_var('REMOTE_CLI'):
        metafunc.parametrize('prefix_remote_cli', ['remote_cli'])
    # Append compliance suite to test name
    elif ComplianceVar.get_var('REFSTACK_SUITE'):
        suite = ComplianceVar.get_var('REFSTACK_SUITE').strip().rsplit(
            r'/', maxsplit=1)[-1]
        metafunc.parametrize('compliance_suite', [suite])
    elif ComplianceVar.get_var('DOVETAIL_SUITE'):
        suite = ComplianceVar.get_var('DOVETAIL_SUITE').strip().split(
            sep='--')[-1].replace(' ', '-')
        metafunc.parametrize('compliance_suite', [suite])


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


@pytest.fixture(scope='session', autouse=True)
def prefix_remote_cli():
    return


@pytest.fixture(scope='session', autouse=True)
def compliance_suite():
    return


@pytest.fixture(autouse=True)
def autostart(request):
    if change_admin:
        return request.getfuncargvalue('change_admin_password_session')


def __params_gen(index):
    return 'iter{}'.format(index)


@pytest.fixture(scope='session')
def global_setup():
    os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
    os.makedirs(ProjVar.get_var('PING_FAILURE_DIR'), exist_ok=True)
    os.makedirs(ProjVar.get_var('GUEST_LOGS_DIR'), exist_ok=True)

    if region:
        setups.set_region(region=region)

#####################################
# End of fixture order manipulation #
#####################################


def pytest_sessionfinish():
    if ProjVar.get_var('TELNET_THREADS'):
        threads, end_event = ProjVar.get_var('TELNET_THREADS')
        end_event.set()
        for thread in threads:
            thread.join()

    if repeat_count > 0 and has_fail:
        # _thread.interrupt_main()
        print('Printing traceback: \n' + '\n'.join(tracebacks))
        pytest.exit("\n========== Test failed - "
                    "Test session aborted without teardown to leave the "
                    "system in state ==========")

    if no_teardown:
        pytest.exit(
            "\n========== Test session stopped without teardown after first "
            "test executed ==========")
