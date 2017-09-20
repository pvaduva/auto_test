import json
import os
import re
import glob
import logging
import sys
import datetime as dt
from consts.reporting import UploadRes
from utils.rabbitmq_reporter.rmqloghandler import RMQHandler, ConnectionError

LOCAL_PATH = os.path.dirname(__file__)
WASSP_PATH = os.path.join(LOCAL_PATH, "..", "..", "..", "..", "..")
WASSP_REPORTER = os.path.join(WASSP_PATH, "wassp/host/tools/report/testReportManual.py")
WASSP_PYTHON = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")

PUBLISHTO_EXCHANGE = 'testResults'
PUBLISHTO_ROUTING_KEY = 'xstudio.testresults'
PUBLISHTO_URL = 'ampq://user:alameda@mq.wrs.com:5672/%2F'

TOOL_NAME = 'XSTUDIO'
TOOL_VERSION = '3.1'

TESTRESULT_LOGGER_NAME = 'TestResultsLogger'


def upload_results(file_path=None, logs_dir=None, lab=None, tags=None, tester_name=os.environ['USER'],
                   skip_uploaded=True):
    """
    collect the test environment variables
	parse the result.log file from the file_path and parse it into JSON format.

	file_path = test_results.log path for a expected test result from /sandbox/AUTOMATION_LOGS/<lab>/<date>/test_results.log
	logs_dir = the path to the log
	lab = the lab the test run (i.e the <lab> from /sandbox/AUTOMATION_LOGS/<lab>/<date>/test_results.log path)
	tags = some kind string that identify the testcases_list
	tester_name = userID who execute the test. It will be environment user by default.

    """
    # Validate required function params

    if not file_path:
        if not lab:
            raise ValueError("test_results.log file path or lab name has to be provided.")
        logs_dir = logs_dir if logs_dir else os.path.expanduser("~")
        logs_dir = logs_dir.split(sep='/AUTOMATION_LOGS')[0]
        if not logs_dir.endswith('/'):
            logs_dir += '/'

        lab_dir = "{}AUTOMATION_LOGS/{}".format(logs_dir, lab.lower().replace('-', '_'))
        latest_dir = max(glob.glob(os.path.join(lab_dir, '*/')), key=os.path.getmtime)
        file_path = os.path.join(latest_dir, 'test_results.log')

    elif not str(file_path).endswith('test_results.log'):
        raise ValueError("Expect file_path ends with test_results.log")

    if not os.path.isfile(file_path):
        raise FileNotFoundError("File does not exist: {}".format(file_path))

    # Parse common test params
    # class UploadRes:
    #   USER_STORY = 'cgcsauto'
    #   REL_NAME = 'Titanium Cloud R4'
    #   TAG = 'cgcsauto'
    #

    userStory = UploadRes.USER_STORY
    release_name = UploadRes.REL_NAME
    tag = tags if tags else UploadRes.TAG
    jira = ''

    # Parse common test info from test_results.log
    lab, build, testcases_list, log_dir = __parse_common_info(file_path)

    logfile = ','.join([os.path.join(log_dir, 'TIS_AUTOMATION.log'), os.path.join(log_dir, 'pytestlog.log')])
    tester_name = tester_name if tester_name else os.environ['USER']

    upload_log = os.path.join(log_dir, 'uploaded_tests.log')

    # Set current time
    reportDate = dt.datetime.now().isoformat()

    if skip_uploaded and os.path.isfile(upload_log):
        with open(upload_log, mode='r') as upload_f:
            uploaded_tests = upload_f.read().strip().splitlines()
        uploaded_tests = [uploaded_name.strip() for uploaded_name in uploaded_tests]

    # TODO: maybe update tmp_id to something better
    tmp_id = 0
    records = []
    for testcase in testcases_list:
        # Parse each record
        test_name, domain, result = __parse_testcase_record(testcase)
        tmp_id += 1
        rec_dict = dict(
            runStartDate=reportDate,
            date_modified=reportDate,
            testResult=result,
            releaseName='Titanium Cloud R5',
            tcTotal=1,
            testExecutionTimeStamp=reportDate,
            id=tmp_id,
            testTool={'version': TOOL_VERSION, 'name': TOOL_NAME},
            testerName=tester_name,
            testName=test_name,
            tcPassed=0,
            project="XSTUDIO 3.1",
            attributes=[["board_name", "%s" % lab], ["barcode", "%s" % lab]],
            defects=[],
            tags=[tag],
            userStories=[userStory],
            environmentName="MYSQL1:2371::MYSQL1:4",
            testSuiteId="T_%s:TC_%s" % (tmp_id, tmp_id),
            environmentId='',
            detailedResult=result,
            domain=domain,
        )

        records.append(rec_dict)

    result_json = dict(records=records)

    print(result_json)
    # TODO: uncomment _upload_result when ready
    __upload_result(result_json=result_json)
    #        if test_name in uploaded_tests:
    #            print("Result for {} already uploaded. Skip uploading.".format(test_name))
    #            continue
    #
    # Upload result
    #        if not __upload_result(result_ini=result_ini, tag=tag, tester_name=tester_name, test_name=test_name,
    #                               result=result, lab=lab, build=build, userstory=userstory, domain=domain, jira=jira,
    #                               logfile=logfile, release_name=release_name, upload_log=upload_log,
    #                               build_server=build_server):
    #            exit(1)

    print('All results uploaded successfully from: {}\nTag: {}'.format(file_path, tag))


def __upload_result(result_json):
    '''
        result_json = {"records": [
                      {
                        "runStartDate": "2016-11-17T17:45:00",
                        "userStories": [],
                        "testResult": "PASS",
                        "milestone": "",
                        "tcTotal": 1,
                        "testExecutionTimeStamp": "2016-11-17T17:45:32",
                        "id": "582decd2e562904f95913d79",
                        "execResult": "PASS",
                        "buildResult": "N/A",
                        "buildResultDetail": "N/A",
                        "environmentName": "MYSQL1:4",
                        "defects": [],
                        "releaseName": "TITANIUM CLOUD R4",
                        "bootResult": "PASS",
                        "testSuiteId": "5491629d98a0a712be964652:5491713a98a0a73ff5ffc0ac",
                        "testTool":
                        {
                             "version": "2.1.2",
                             "name": "WASSP"
                        },
                        "testerName": "helmuth",
                        "rtcResultDetail": "N/A",
                        "rtcResult": "N/A",
                        "environmentId": "MYSQL1:2371::MYSQL1:4",
                        "testName": "host_test_wil",
                        "execResultDetail": "PASS",
                        "tcPassed": 0,
                        "bootResultDetail": "PASS",
                        "attributes":
                            [
                                 ["barcode", "localhost"],
                                 ["board_name", "localHost"],
                                 ["bsp", "none"],
                                 ["config_label", "localhost"],
                                 ["config_name", "none"],
                                 ["hostos", "Ubuntu 14.04.4 LTS-64bit"],
                                 ["project", "WASSP 2.1"],
                                 ["tech", "up"],
                                 ["tool", "none"]
                            ],
                        "date_modified": "2016-11-17T17:45:53.045060",
                        "detailedResult": "exec pass",
                        "project": "WASSP 2.1",
                        "tags":[
                                 "201611171100", "helmuth", "hv202gos"
                        ]
                        }
                 ]
            }
    '''
    try:
        rmqLogger = logging.getLogger('rmqlogger')
        rmqLogger.setLevel(logging.INFO)
        rmqHandler = RMQHandler(url=PUBLISHTO_URL,
                                routing_key=PUBLISHTO_ROUTING_KEY,
                                exchange=PUBLISHTO_EXCHANGE)
        rmqHandler.set_name(TESTRESULT_LOGGER_NAME)
        rmqLogger.addHandler(rmqHandler)
        # rmqLogger.info(json.dumps(result_json))
        rmqHandler.emit(json.dumps(result_json))

    except ConnectionError:
        return 1

    return 0


def __parse_testcase_record(record_line):
    """
    Get testcase specific info from test result line. Such as
    Failed	02:50:12	functional/networking/test_ping_vms.py::test_ping_vm

    Args:
        record_line (str): test record line from test_results.log

    Returns (tuple): (test_name, domain, result)

    """
    if not record_line.endswith('\n'):
        record_line += '\n'

    result, rest = record_line.split('\t', maxsplit=1)
    if not rest.endswith('\n'):
        rest += '\n'
    rest = rest.split('\tUPLOAD_UNSUCC')[0].strip()
    full_name = rest.split('\t')[-1]

    domain = re.findall('[/\t](.*)/test_.*.py', full_name)
    domain = domain[0].upper() if domain else 'UNKNOWN'
    splited_fullname = full_name.split(sep='::', maxsplit=1)
    test_name = splited_fullname[-1].strip()

    # Prepare to upload
    # Covert result to uppercase, such as PASS, FAIL, SKIP
    result = re.findall('(skip|pass|fail)', result.lower())
    result = result[0].upper() if result else 'UNKNOWN'

    return test_name, domain, result


def __parse_common_info(test_results_file):
    """
    Parse common result params from test_results.log
    Args:
        test_results_file (str): file path for test_results.log file

    Returns (tuple): (lab, build, testcases_list, log_dir)
    """

    with open(test_results_file) as f:
        raw_res = f.read()

    testcases_res, other_info = raw_res.split(sep='\n\n', maxsplit=1)
    testcases_res = testcases_res.strip()
    testcases_list = str(testcases_res).splitlines()

    if not testcases_res:
        raise LookupError("No results to upload from: {}".format(test_results_file))

    lab = re.findall('Lab: (.*)\n', other_info)[0].strip().upper()
    build = re.findall('Build ID: (.*)\n', other_info)[0].strip()
    # build_server = re.findall('Build Server: (.*)\n', other_info)[0].strip()
    log_dir = test_results_file.replace('test_results.log', '')

    return lab, build, testcases_list, log_dir


if __name__ == '__main__':
    # usage (when debugging)
    # report2json.py inputFile [outputPath]

    # __upload_result('test')

    upload_results(file_path='/sandbox/AUTOMATION_LOGS/wcp_80_84/201702231645/test_results.log', lab='',
                   logs_dir='/sandbox', tags='')

