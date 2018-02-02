import logging
import os
import threading    # Used for formatting logger

from time import strftime, gmtime

import pytest   # Don't remove. Used in eval

import setup_consts
import setups
from consts.proj_vars import ProjVar, InstallVars
from consts import build_server as build_server_consts
#from consts.build_server import Server, get_build_server_info
from consts import cgcs
from utils.mongo_reporter.cgcs_mongo_reporter import collect_and_upload_results
from utils.tis_log import LOG
from testfixtures.pre_checks_and_configs import collect_kpi   # Kpi fixture. Do not remove!


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
    global test_count
    test_count += 1
    # reset tc_start and end time for next test case
    build_id = ProjVar.get_var('BUILD_ID')
    build_server = ProjVar.get_var('BUILD_SERVER')

    if ProjVar.get_var("REPORT_ALL") or ProjVar.get_var("REPORT_TAG"):
        if ProjVar.get_var('SESSION_ID'):
            try:
                from utils.cgcs_reporter import upload_results
                upload_results.upload_test_result(session_id=ProjVar.get_var('SESSION_ID'), test_name=test_name,
                                                  result=res_in_tests, start_time=tc_start_time, end_time=tc_end_time,
                                                  parse_name=True)
            except Exception:
                LOG.exception("Unable to upload test result to TestHistory db! Test case: {}".format(test_name))

        try:
            upload_res = collect_and_upload_results(test_name, res_in_tests, ProjVar.get_var('LOG_DIR'), build=build_id,
                                                    build_server=build_server)
            if not upload_res:
                with open(ProjVar.get_var("TCLIST_PATH"), mode='a') as f:
                    f.write('\tUPLOAD_UNSUCC')
        except Exception:
            LOG.exception("Unable to upload test result to mongoDB! Test case: {}".format(test_name))

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
                _write_results(res_in_tests='Failed', test_name=test_name)
                TestRes.FAILNUM += 1
                if ProjVar.get_var('PING_FAILURE'):
                    setups.add_ping_failure(test_name=test_name)
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
    # set test name for ping vm failure
    test_name = 'test_{}'.format(item.nodeid.rsplit('::test_', 1)[-1].replace('/', '_'))
    ProjVar.set_var(TEST_NAME=test_name)
    ProjVar.set_var(PING_FAILURE=False)


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

def pytest_configure(config):
    config.addinivalue_line("markers",
                            "features(feature_name1, feature_name2, ...): mark impacted feature(s) for a test case.")
    config.addinivalue_line("markers",
                            "priorities(sanity, cpe_sanity, p2, ...): mark priorities for a test case.")
    config.addinivalue_line("markers",
                            "known_issue(CGTS-xxxx): mark known issue with JIRA ID or description if no JIRA needed.")

    if config.getoption('help'):
        return

    # Common reporting params
    collect_all = config.getoption('collectall')
    report_all = config.getoption('reportall')
    report_tag = config.getoption('report_tag')
    resultlog = config.getoption('resultlog')
    session_log_dir = config.getoption('sessiondir')
    no_cgcs = config.getoption('nocgcsdb')
    col_kpi = config.getoption('col_kpi')
    telnet_log = config.getoption('telnetlog')

    # Test case params on installed system
    lab_arg = config.getoption('lab')
    natbox_arg = config.getoption('natbox')
    tenant_arg = config.getoption('tenant')
    bootvms_arg = config.getoption('bootvms')
    openstack_cli = config.getoption('openstackcli')
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

    global no_teardown
    no_teardown = config.getoption('noteardown')
    keystone_debug = config.getoption('keystone_debug')
    install_conf = config.getoption('installconf')
    global region
    region = config.getoption('region')

    # decide on the values of custom options based on cmdline inputs or values in setup_consts
    lab = setups.get_lab_from_cmdline(lab_arg=lab_arg, installconf_path=install_conf)
    natbox = setups.get_natbox_dict(natbox_arg) if natbox_arg else setup_consts.NATBOX
    tenant = setups.get_tenant_dict(tenant_arg) if tenant_arg else setup_consts.PRIMARY_TENANT
    is_boot = True if bootvms_arg else setup_consts.BOOT_VMS
    collect_all = True if collect_all else setup_consts.COLLECT_ALL
    report_all = True if report_all else setup_consts.REPORT_ALL
    openstack_cli = True if openstack_cli else False

    if no_cgcs:
        ProjVar.set_var(CGCS_DB=False)
    if keystone_debug:
        ProjVar.set_var(KEYSTONE_DEBUG=True)
    if col_kpi:
        ProjVar.set_var(COLLECT_KPI=True)
    if telnet_log:
        ProjVar.set_var(COLLECT_TELNET=True)

    if session_log_dir:
        log_dir = session_log_dir
    else:
        # compute directory for all logs based on resultlog arg, lab, and timestamp on local machine
        resultlog = resultlog if resultlog else os.path.expanduser("~")
        if '/AUTOMATION_LOGS' in resultlog:
            resultlog = resultlog.split(sep='/AUTOMATION_LOGS')[0]
        if not resultlog.endswith('/'):
            resultlog += '/'
        log_dir = resultlog + "AUTOMATION_LOGS/" + lab['short_name'] + '/' + strftime('%Y%m%d%H%M')
    os.makedirs(log_dir, exist_ok=True)

    if report_all:
        report_tag = report_tag if report_tag else 'cgcsauto'

    # set project constants, which will be used when scp keyfile, and save ssh log, etc
    ProjVar.set_vars(lab=lab, natbox=natbox, logdir=log_dir, tenant=tenant, is_boot=is_boot, collect_all=collect_all,
                     report_all=report_all, report_tag=report_tag, openstack_cli=openstack_cli)
    # put keyfile to home directory of localhost
    if natbox['ip'] == 'localhost':
        labname = ProjVar.get_var('LAB_NAME')
        ProjVar.set_var(KEYFILE_PATH='~/priv_keys/keyfile_{}.pem'.format(labname))

    InstallVars.set_install_var(lab=lab)

    config_logger(log_dir)

    # set resultlog save location
    config.option.resultlog = ProjVar.get_var("PYTESTLOG_PATH")
    # Add 'iter' to stress test names
    # print("config_options: {}".format(config.option))
    file_or_dir = config.getoption('file_or_dir')
    origin_file_dir = list(file_or_dir)

    if count > 1:
        print("Repeat following tests {} times: {}".format(count, file_or_dir))
        del file_or_dir[:]
        for f_or_d in origin_file_dir:
            for i in range(count):
                file_or_dir.append(f_or_d)
            # Note! Below code was a workaround for parametrized repeat.
            # if '[' in f_or_d:
            #     # Below setting seems to have no effect. Test did not continue upon collection failure.
            #     # config.option.continue_on_collection_errors = True
            #     # return
            #     file_or_dir.remove(f_or_d)
            #     origin_f_or_list = list(f_or_d)
            #
            #     for i in range(count):
            #         extra_str = 'iter{}-'.format(i)
            #         f_or_d_list = list(origin_f_or_list)
            #         f_or_d_list.insert(f_or_d_list.index('[') + 1, extra_str)
            #         new_f_or_d = ''.join(f_or_d_list)
            #         file_or_dir.append(new_f_or_d)

        # print("after modify: {}".format(config.option.file_or_dir))


def pytest_addoption(parser):
    lab_help = "Lab to connect to. Valid input: Hardware labs - use lab name such as 'r720_2-7', 'yow-cgcs-r720-3_7';" \
               "if it's a new lab, use floating ip before it is added to the automation framework. " \
               "VBox - use vbox or the floating ip of your tis system if it is not 10.10.10.2. " \
               "Cumulus - floating ip of the cumulus tis system"
    tenant_help = "Default tenant to use when unspecified. Valid values: tenant1, tenant2, or admin"
    natbox_help = "NatBox to use. Default: NatBox for hardware labs. Valid values: nat_hw (for hardware labs), " \
                  "<your own natbox ip> (for VBox, choose the 128.224 ip), or nat_cumulus (for Cumulus)."
    bootvm_help = "Boot 2 vms at the beginning of the test session as background VMs."
    collect_all_help = "Run collect all on TiS server at the end of test session if any test fails."
    report_help = "Upload results and logs to the test results database."
    tag_help = "Tag to be used for uploading logs to the test results database."
    logdir_help = "Directory to store test session logs. If this is specified, then --resultlog will be ignored."
    openstackcli_help = "Use openstack cli whenever possible. e.g., 'neutron net-list' > 'openstack network list'"
    stress_help = "Number of iterations to run specified testcase(s). Abort rest of the test session on first failure"
    count_help = "Repeat tests x times - NO stop on failure"
    skiplabsetup_help = "Do not run lab_setup post lab install"
    installconf_help = "Full path of lab install configuration file. Template location: " \
                       "/folk/cgts/lab/autoinstall_template.ini"
    resumeinstall_help = 'Resume install of current lab from where it stopped/failed'
    changeadmin_help = "Change password for admin user before test session starts. Revert after test session completes."
    region_help = "Multi-region parameter. Use when connected region is different than region to test. " \
                  "e.g., creating vm on RegionTwo from RegionOne"
    telnetlog_help = "Collect telnet logs throughout the session"

    # Common reporting options:
    parser.addoption('--collectall', '--collect_all', '--collect-all', dest='collectall', action='store_true',
                     help=collect_all_help)
    parser.addoption('--reportall', '--report_all', '--report-all', dest='reportall', action='store_true',
                     help=report_help)
    parser.addoption('--report_tag', '--report-tag', action='store', dest='report_tag', metavar='tagname', default=None,
                     help=tag_help)
    parser.addoption('--sessiondir', '--session_dir', '--session-dir', action='store', dest='sessiondir',
                     metavar='sessiondir', default=None, help=logdir_help)
    parser.addoption('--no-cgcsdb', '--no-cgcs-db', '--nocgcsdb', action='store_true', dest='nocgcsdb')

    # Test session options on installed lab:
    parser.addoption('--lab', action='store', metavar='lab', default=None, help=lab_help)
    parser.addoption('--tenant', action='store', metavar='tenantname', default=None, help=tenant_help)
    parser.addoption('--natbox', action='store', metavar='natbox', default=None, help=natbox_help)
    parser.addoption('--changeadmin', '--change-admin', '--change_admin', dest='changeadmin', action='store_true',
                     help=changeadmin_help)
    parser.addoption('--bootvms', '--boot_vms', '--boot-vms', dest='bootvms', action='store_true', help=bootvm_help)
    parser.addoption('--openstackcli', '--openstack_cli', '--openstack-cli', action='store_true', dest='openstackcli',
                     help=openstackcli_help)
    parser.addoption('--repeat', action='store', metavar='repeat', type=int, default=-1, help=stress_help)
    parser.addoption('--stress', metavar='stress', action='store', type=int, default=-1, help=count_help)
    parser.addoption('--no-teardown', '--no_teardown', '--noteardown', dest='noteardown', action='store_true')
    parser.addoption('--keystone_debug', '--keystone-debug', action='store_true', dest='keystone_debug')
    parser.addoption('--kpi', '--collect-kpi', '--collect_kpi', action='store_true', dest='col_kpi',
                     help="Collect kpi for applicable test cases")
    parser.addoption('--region', action='store', metavar='region', default=None, help=region_help)
    parser.addoption('--telnetlog', '--telnet-log', dest='telnetlog', action='store_true', help=telnetlog_help)

    ##################################
    # Lab install or upgrade options #
    ##################################
    # Install
    parser.addoption('--resumeinstall', '--resume-install', dest='resumeinstall', action='store_true',
                     help=resumeinstall_help)
    parser.addoption('--skiplabsetup', '--skip-labsetup', dest='skiplabsetup', action='store_true',
                     help=skiplabsetup_help)
    parser.addoption('--installconf', '--install-conf', action='store', metavar='installconf', default=None,
                     help=installconf_help)
    # Ceph Post Install
    ceph_mon_device_controller0_help = "The disk device to use for ceph monitor in controller-0. e.g., /dev/sdc"
    ceph_mon_device_controller1_help = "The disk device to use for ceph monitor in controller-1. e.g., /dev/sdb"
    ceph_mon_gib_help = "The size of the partition to allocate on a controller disk for the Ceph monitor logical " \
                        "volume, in GiB (the default value is 20)"
    parser.addoption('--ceph-mon-dev-controller-0', '--ceph_mon_dev_controller-0',  dest='ceph_mon_dev_controller_0',
                     action='store', metavar='DISK_DEVICE',  help=ceph_mon_device_controller0_help)
    parser.addoption('--ceph-mon-dev-controller-1', '--ceph_mon_dev_controller-1',  dest='ceph_mon_dev_controller_1',
                     action='store', metavar='DISK_DEVICE',  help=ceph_mon_device_controller1_help)
    parser.addoption('--ceph-mon-gib', '--ceph_mon_dev_gib',  dest='ceph_mon_gib',
                     action='store', metavar='SIZE',  help=ceph_mon_gib_help)
    # Note --lab is also a lab install option, when config file is not provided.

    ###############################
    #  Upgrade options #
    ###############################

    upgrade_version_help = "TiS next software version that the lab is upgraded to. " \
                           "Valid options are: {}".format(' '.join(v[1] for v in cgcs.SUPPORTED_UPGRADES))
    build_server_help = "TiS build server host name where the upgrade release software is downloaded from." \
                        " ( default: {})".format(build_server_consts.DEFAULT_BUILD_SERVER['name'])
    upgrade_build_dir_path = "The path to the upgrade software release build directory in build server." \
                             " eg: /localdisk/loadbuild/jenkins/TS_16.10_Host/latest_build/. " \
                             " Otherwise the default  build dir path for the upgrade software " \
                             "version will be used"

    license_help = "The full path to the new release software license file in build-server. " \
                   "e.g /folk/cgts/lab/TiS16-full.lic or /folk/cgts/lab/TiS16-CPE-full.lic." \
                   " Otherwise, default license for the upgrade release will be used"

    orchestration_help = "The point in upgrade procedure where we start to use orchestration. Possible options are:" \
                         "  default - to start orchestration after controller-1 is upgraded; " \
                         "  storage:<#> - to start orchestration after <#> storage (s) are upgraded normally; " \
                         "  compute:<#> - start orchestration after <#> compute(s) are upgraded normally; " \
                         " The default is default. Applicable only for upgrades from R3."
    apply_strategy_help = "How the orchestration strategy is applied:" \
                          "  serial - apply orchestration strategy one node  at a time; " \
                          "  parallel - apply orchestration strategy in parallel; " \
                          "  ignore - do not apply the orchestration strategy; " \
                          " If not specified,  the system will choose the option to apply the strategy. " \
                          "Applicable only for upgrades from R3."
    max_parallel_compute_help = "The maximum number of compute hosts to upgrade in parallel, if parallel apply type" \
                                " is selected"
    alarm_restriction_help = """Inidcates how to handle alarm restrictions based on the management affecting statuses
                             of any existing alarms.
                                 relaxed -  orchestration is allowed to proceed if none managment affecting alarms are
                                            present
                                 strict -  orchestration is not allowed if alarms are present
                             """

    parser.addoption('--upgrade-version', '--upgrade_version', '--upgrade', dest='upgrade_version',
                     action='store', metavar='VERSION',  default=None, help=upgrade_version_help)
    parser.addoption('--build-server', '--build_server',  dest='build_server',
                     action='store', metavar='SERVER', default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=build_server_help)
    parser.addoption('--tis-build-dir', '--tis_build_dir',  dest='tis_build_dir',
                     action='store', metavar='DIR',  help=upgrade_build_dir_path)
    parser.addoption('--license',  dest='upgrade_license', action='store',
                     metavar='license full path', help=license_help)

    parser.addoption('--orchestration', '--orchestration-after', '--orchestration_after', dest='orchestration_after',
                     action='store', metavar='HOST_PERSONALITY:NUM', default='default', help=orchestration_help)

    parser.addoption('--storage-apply-type', '--storage_apply_type', '--sstra',  dest='storage_strategy',
                     action='store',  help=apply_strategy_help)

    parser.addoption('--compute-apply-type', '--compute_apply_type', '--cstra', dest='compute_strategy',
                     action='store',  help=apply_strategy_help)

    parser.addoption('--max-parallel-computes', '--max_parallel_computes', dest='max_parallel_computes',
                     action='store',  help=max_parallel_compute_help)

    parser.addoption('--alarm-restrictions', '--alarm_restrictions', dest='alarm_restrictions',
                     action='store', default='strict',  help=alarm_restriction_help)

    ####################
    # Patching options #
    ####################
    patch_build_server_help = "TiS Patch build server host name from where the upgrade release software is " \
                              "downloaded. Use default build server when unspecified"

    patch_dir_help = "Directory or file on the Build Server where the patch files located. Because the version must " \
                     "match that of the system software on the target lab, hence by default, we will deduce " \
                     "the location of the patch files and their version, unless users specify an absolute path " \
                     "containing valid patch files. This directory is usually a symbolic link in the load-build " \
                     "directory."

    patch_base_dir_help = "Directory on the Build Server under which the patch files are located. By default, " \
                          "it is: {}".format('/localdisk/loadbuild/jenkins/CGCS_5.0_Test_Patch_Build')

    parser.addoption('--patch-build-server', '--patch_build_server',  dest='patch_build_server',
                     action='store', metavar='SERVER', default=None,
                     help=patch_build_server_help)

    parser.addoption('--patch-dir', '--patch_dir',  dest='patch_dir', default=None,
                     action='store', metavar='DIR',  help=patch_dir_help)

    parser.addoption('--patch-base-dir', '--patch_base_dir',  dest='patch_base_dir', default=None,
                     action='store', metavar='BASEDIR',  help=patch_base_dir_help)

    ###############################
    #  Backup and Restore options #
    ###############################

    # Backup only
    keep_backups = "Whether to keep the backupfiles from controller-0:/opt/backups after transfer " \
                   "to the specified destination. Default is remove."
    parser.addoption('--keep-backups', '--keep_backups',  dest='keep_backups', action='store_true', help=keep_backups)

    # Common for backup and restore
    backup_server_destination_help = "Whether to save/get backupfiles on/from USB. Default is test server." \
                                     "When true, 16G USB  or above must be plugged to controller-0 "
    backup_destination_path_help = "The path the backup files are copied to/taken from if destination is not a USB. " \
                                   "For USB, the backup files are at mount point: /media/wrsroot/backups. " \
                                   "For Test Server, the default is /sandbox/backups."

    parser.addoption('--usb', '--usb',  dest='use_usb', action='store_true',  help=backup_server_destination_help)
    parser.addoption('--backup-path', '--backup_path',  dest='backup_path',
                     action='store', metavar='DIR', help=backup_destination_path_help)

    # Restore only
    parser.addoption('--backup-build-id', '--backup_build-id',  dest='backup_build_id',
                     action='store', help="The build id of the backup")
    parser.addoption('--backup-builds-dir', '--backup_builds-dir',  dest='backup_builds_dir',
                     action='store', help="The Titanium builds dir where the backup build id belong. "
                                          "Such as CGCS_5.0_Host or TC_17.06_Host")

    parser.addoption('--skip-setup-feed', '--skip_setup_feed',  dest='skip_setup_feed',
                     action='store_true', help="Reuse the existing feed on the pxeboot server (tuxlab1/2) instead of "
                                          "setup feed from scratch")
    parser.addoption('--skip-reinstall', '--skip_reinstall',  dest='skip_reinstall',
                     action='store_true', help="Reuse the lab in states without reinstall it. "
                                                "This will be helpful if the lab was/will be in customized way.")
    parser.addoption('--low-latency', '--low_latency',  dest='low_latency',
                     action='store_true', help="Restore a low-latency lab")

    # Clone only
    parser.addoption('--dest-labs', '--dest_labs',  dest='dest_labs',
                     action='store',  help="Comma separated list of AIO lab short names where the cloned image iso "
                                           "file is transferred to. Eg WCP_68,67  or SM_1,SM2.")


def config_logger(log_dir):
    # logger for log saved in file
    file_name = log_dir + '/TIS_AUTOMATION.log'
    logging.Formatter.converter = gmtime
    log_format = '[%(asctime)s] %(lineno)-5d%(levelname)-5s %(threadName)-8s %(module)s.%(funcName)-8s:: %(message)s'
    tis_formatter = logging.Formatter(log_format)
    LOG.setLevel(logging.NOTSET)

    tmp_path = os.path.join(os.path.expanduser('~'), '.tmp_log')
    # clear the tmp log with best effort so it wont keep growing
    try:
        os.remove(tmp_path)
    except:
        pass
    logging.basicConfig(level=logging.NOTSET, format=log_format, filename=tmp_path, filemode='w')

    # file handler:
    file_handler = logging.FileHandler(file_name)
    file_handler.setFormatter(tis_formatter)
    file_handler.setLevel(logging.DEBUG)
    LOG.addHandler(file_handler)

    # logger for stream output
    stream_hdler = logging.StreamHandler()
    stream_hdler.setFormatter(tis_formatter)
    stream_hdler.setLevel(logging.INFO)
    LOG.addHandler(stream_hdler)


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

    try:
        log_dir = ProjVar.get_var('LOG_DIR')
        tc_res_path = log_dir + '/test_results.log'
        build_id = ProjVar.get_var('BUILD_ID')
        build_server = ProjVar.get_var('BUILD_SERVER')
        session_id = ProjVar.get_var('SESSION_ID')
        session_tag = ProjVar.get_var('REPORT_TAG')
        session_str = 'Session Tag: {}\nSession ID: {}\n'.format(session_tag, session_id) if session_id else ''
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
                        'Ends at: {}\n'
                        '{}'    # test session id and tag
                        '{}'.format(ProjVar.get_var('LAB_NAME'), build_id, build_server, ProjVar.get_var('LOG_DIR'),
                                    tc_end_time, session_str, version_and_patch))
                # Add result summary to beginning of the file
                f.write('\nSummary:\nPassed: {} ({})\nFailed: {} ({})\nTotal Executed: {}\n'.
                        format(TestRes.PASSNUM, pass_rate, TestRes.FAILNUM, fail_rate, total_exec))
                if TestRes.SKIPNUM > 0:
                    f.write('------------\nSkipped: {}'.format(TestRes.SKIPNUM))

            LOG.info("Test Results saved to: {}".format(tc_res_path))
            with open(tc_res_path, 'r') as fin:
                print(fin.read())
    except Exception as e:
        LOG.exception("Failed to add session summary to test_results.py. \nDetails: {}".format(e.__str__()))
    # Below needs con_ssh to be initialized
    try:
        from utils.ssh import ControllerClient
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
        setups.list_migration_history(con_ssh=con_ssh)
    except:
        LOG.warning("Failed to run nova migration-list")

    vswitch_info_hosts = list(set(ProjVar.get_var('VSWITCH_INFO_HOSTS')))
    if vswitch_info_hosts:
        try:
            setups.scp_vswitch_log(hosts=vswitch_info_hosts, con_ssh=con_ssh)
        except Exception as e:
            LOG.warning("unable to scp vswitch log - {}".format(e.__str__()))

    if test_count > 0 and (ProjVar.get_var('ALWAYS_COLLECT') or (has_fail and ProjVar.get_var('COLLECT_ALL'))):
        # Collect tis logs if collect all required upon test(s) failure
        # Failure on collect all would not change the result of the last test case.
        try:
            setups.collect_tis_logs(con_ssh)
        except:
            LOG.warning("'collect all' failed.")

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

    pass
    # NOTE! repeat using parameters are commented out. Tests are now repeated by modifying the tests list
    # Stress fixture
    # global count
    # if count > 0:
    #     # Add autorepeat fixture and parametrize the fixture
    #     param_name = 'autorepeat'
    #     metafunc.parametrize(param_name, range(count), indirect=True, ids=__params_gen)
    #
    # print(str(count))
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


# Note! parametrized repeat is replaced with test list modification
# @pytest.fixture(autouse=True)
# def autorepeat(request):
#     try:
#         return request.param
#     except:
#         return None


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


def pytest_sessionfinish(session):
    if ProjVar.get_var('TELNET_THREADS'):
        threads, end_event = ProjVar.get_var('TELNET_THREADS')
        end_event.set()
        for thread in threads:
            thread.join()

    if repeat_count > 0 and has_fail:
        # _thread.interrupt_main()
        print('Printing traceback: \n' + '\n'.join(tracebacks))
        pytest.exit("Abort upon stress test failure")

    if no_teardown:
        pytest.exit("Stop session after first test without teardown")
