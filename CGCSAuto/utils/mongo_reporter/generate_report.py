import os
import re
import datetime
import requests

from utils import lab_info, local_host
from consts.filepaths import BuildServerPath
from keywords import host_helper

TEST_SERVER_HTTP_AUTOLOG = 'http://128.224.150.21/auto_logs/'
TEST_SERVER_FS_AUTOLOG = 'yow-cgcs-test.*:/sandbox/AUTOMATION_LOGS/'

TMP_FILE = '/tmp/cgcs_emailmessage.html'
# YELLOW = '#FFC200'
REPORT_FORMAT = """<html><basefont face="arial" size="2"> \
<b>Lab: </b>{}
<b>Load: </b>{}
<b>Build Server: </b>{}
<b>Node Config: </b>{}

<b>Overall Status: {}</b>
<b>Detailed Test Results Location: </b>{}

<b>Automated Test Results Summary: </b>
------------------------------------------------------
{}


<b>List of Test Cases: </b>
------------------------------
<pre>{}</pre>
</html>
"""


def write_report_file(sys_config=None, source='mongo', tags=None, start_date=None, end_date=None, logs_dir=None):
    """

    Args:
        source (str): 'mongo' or <local test results path>
        tags (str|list):
        start_date (str):
        end_date (str):
        logs_dir (str):

    Returns:

    """
    if source.lower() == 'mongo':
        if not tags:
            raise ValueError("tags, start_date, end_date have to be provided when query results from mongoDB")

        if not start_date:
            start_date = datetime.datetime.now() - datetime.timedelta(days=1)
            now = datetime.datetime.now() - datetime.timedelta(days=0)
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")

        lab, build, build_server, overall_status, log_path, summary, testcases_res = \
            _get_results_from_mongo(tags=tags, start_date=start_date, end_date=end_date, logs_dir=logs_dir)

    else:
        # get result from test server's from /sandbox/AUTOMATION_LOGS/<lab>/<date>/test_results.log
        res_file = 'test_results.log'
        if not res_file in source and not logs_dir:
            raise ValueError("local automation log path has to be specified via logs_dir or source")

        source = source if res_file in source else os.path.join(logs_dir, res_file)
        source = os.path.expanduser(source)
        lab, build, build_server, overall_status, log_path, summary, testcases_res = _get_local_results(source)

    log_path = re.sub(TEST_SERVER_FS_AUTOLOG, TEST_SERVER_HTTP_AUTOLOG, log_path, count=1)

    lab = lab.upper()
    if not sys_config:
        sys_config = lab_info._get_sys_type(labname=lab)

    # convert contents to html format
    testcases_res = testcases_res.replace('\t', '&#9;').\
        replace('PASS', "<font color='green'>PASS</font>").\
        replace('FAIL', "<font color='red'>FAIL</font>").\
        replace('SKIP', "<font color='#FFC200'>SKIP</font>")

    summary = summary.replace('Passed: ', '<b>Passed: </b>').replace('Failed: ', '<b>Failed: </b>').\
        replace('Skipped: ', '<b>Skipped: </b>').replace('Total Executed: ', '<b>Total Executed: </b>')

    with open(TMP_FILE, mode='w') as f:
        f.write(REPORT_FORMAT.format(lab, build, build_server, sys_config, overall_status, log_path, summary,
                                     testcases_res).replace('\n', '<br>'))
    if 'RED' in overall_status:
        raw_status = 'RED'
    elif 'GREEN' in overall_status:
        raw_status = 'GREEN'
    else:
        raw_status = 'YELLOW'

    return TMP_FILE, lab, build, build_server, raw_status


def _get_local_results(res_path):
    with open(res_path, mode='r') as f:
        raw_res = f.read()

    testcases_res, other_info = raw_res.split(sep='\n\n', maxsplit=1)
    testcases_res = testcases_res.strip()
    testcases_res = testcases_res.replace('Passed\t', 'PASS\t').replace('Failed\t', 'FAIL\t').\
        replace('Skipped\t', 'SKIP\t')
    testcases_res = re.sub(r'\t[^\t]*::test', r'\ttest', testcases_res)

    lab = re.findall('Lab: (.*)\n', other_info)[0].strip()
    build = re.findall('Build ID: (.*)\n', other_info)[0].strip()
    build_server = re.findall('Build Server: (.*)\n', other_info)[0].strip()
    log_path = re.findall('Automation LOGs DIR: (.*)\n', other_info)[0].strip()
    hostname = local_host.get_host_name()
    log_path = "{}:{}".format(hostname, log_path)
    pass_rate = re.findall("Passed: .* \((.*)%\)\n", other_info)[0].strip()
    summary = other_info.split(sep='\nSummary:')[-1].strip()
    overall_status = _get_overall_status(pass_rate)

    return lab, build, build_server, overall_status, log_path, summary, testcases_res


def _get_results_from_mongo(tags, start_date, end_date, include_bld=False, logs_dir=None):
    if isinstance(tags, str):
        tags = [tags]

    # Query results from mongoDB in json format
    query_url = "http://report.wrs.com/mongoexport/?" \
                "testExecutionTimeStamp_start={}" \
                "&testExecutionTimeStamp_end={}" \
                "&tags=[{}]".format(start_date, end_date, tags)
    print("MongoDB results query url: {}".format(query_url))

    total = failed = passed = skipped = 0
    records = requests.get(query_url).json()['records']
    # sort records by execution timestamp
    records = sorted(records, key=lambda record: record['testExecutionTimeStamp']['$date'], reverse=True)
    test_names = []
    last_records = []
    for item in records:
        test_name = item['testName']
        if test_name not in test_names:
            test_names.append(test_name)
            last_records.append(item)

    # print(last_records)
    # resort the records so tests run first will be shown first
    last_records = sorted(last_records, key=lambda record: record['testExecutionTimeStamp']['$date'])
    testresults_list = []
    for item in last_records:
        test_name = item['testName']
        test_res = item['testResult']
        total += 1
        if 'pass' in test_res.lower():
            passed += 1
        elif 'fail' in test_res.lower():
            failed += 1
        elif 'skip' in test_res.lower():
            skipped += 1

        extra_str = ''
        if include_bld:
            test_build = item['attributes'][1][1]
            extra_str = '\t{}'.format(test_build)

        testresults_list.append('{}{}\t{}'.format(test_res, extra_str, test_name))

    testcases_res = '\n'.join(testresults_list)
    testcases_res = testcases_res.replace('Skipped\t', 'SKIP\t')
    total_exec = passed + failed
    pass_rate = fail_rate = '0'
    if total_exec > 0:
        pass_rate = "{}%".format(round(passed * 100 / total_exec, 2))
        fail_rate = "{}%".format(round(failed * 100 / total_exec, 2))
    summary = "Passed: {} ({})\nFailed: {} ({})\nTotal Executed: {}".format(
            passed, pass_rate, failed, fail_rate, total_exec)
    if skipped > 0:
        summary += '\n------------\nSkipped: {}'.format(skipped)

    # example "attributes" : [ [ "board_name", "WCP_76_77" ], [ "build", "2017-01-05_22-02-35" ],
    # [ "domain", "COMMON" ], [ "kernel", "3.10.71-ovp-rt74-r1_preempt-rt" ], [ "lab", "WCP_76_77" ],
    # [ "project", "CGCS 2.0" ] ]
    lab = build = build_server = ''
    first_rec = last_records[0]
    for attr in first_rec['attributes']:
        if attr[0] == 'board_name':
            lab = attr[1]
        elif attr[0] == 'build':
            build = attr[1]
        elif attr[0] == 'build_server':
            build_server = attr[1]

    if not logs_dir or lab.lower().replace('-', '-') not in str(logs_dir):
        panorama_url = "<a href='http://panorama.wrs.com:8181/#/testResults/?database=RNT&view=list" \
                       "&dateField=[testExecutionTimeStamp]&programs=active&resultsMode=last" \
                       "&startDate={}&endDate={}" \
                       "&releaseName=[MYSQL1:2226]" \
                       "&tags=__in__[{}]'>Test Results Link</a>".format(start_date, end_date, ','.join(tags))

        print("Panorama query url: {}".format(panorama_url))
        log_path = panorama_url
    else:
        logs_dir = logs_dir.replace('test_results.py', '')
        logs_dir = os.path.expanduser(logs_dir)
        hostname = local_host.get_host_name()
        log_path = "{}:{}".format(hostname, logs_dir)

    overall_status = _get_overall_status(pass_rate)

    return lab, build, build_server, overall_status, log_path, summary, testcases_res


def _get_overall_status(pass_rate):
    pass_rate = str(pass_rate).split(sep='%')[0]
    pass_rate = float(pass_rate)
    if pass_rate == 100:
        res = "<font color='green'>GREEN</font>"
    elif 75 <= pass_rate < 100:
        res = "<font color='#FFC200'>YELLOW</font>"
    else:
        res = "<font color='red'>RED</font>"

    return res


def mark_status_on_build_server(status, build_server, build_id=None, builds_dir=None, build_path=None):
    """
    This is for marking the load RED/YELLOW/GREEN.
    e.g., touch /localdisk/loadbuild/jenkins/CGCS_4.0_Centos_Build/2017-05-08_22-01-14/GREEN

    Args:
        status (str): GREEN, YELLOW or RED
        build_server (str): yow-cgts4-lx, etc
        build_id (str|None): e.g., 2017-05-08_22-01-14. Only used if build_path is None
        builds_dir (str|None): e.g, /localdisk/loadbuild/jenkins/CGCS_4.0_Centos_Build. Only used if build_path is None
        build_path (str|None): e.g., /localdisk/loadbuild/jenkins/CGCS_4.0_Centos_Build/2017-05-08_22-01-14/
    """
    if status not in ['RED', 'YELLOW', 'GREEN']:
        raise ValueError("Invalid status {}".format(status))

    if not build_path:
        if not build_id:
            raise ValueError("Either build_id or build_dir has to be provided")
        if not builds_dir:
            builds_dir = BuildServerPath.DEFAULT_HOST_BUILDS_DIR

        build_path = builds_dir + '/' + build_id

    with host_helper.ssh_to_build_server(bld_srv=build_server) as bld_srv_ssh:
        if not bld_srv_ssh.file_exists(file_path=build_path):
            raise ValueError("Build path {} does not exist!".format(build_path))

        status_file = '{}/{}'.format(build_path, status)
        bld_srv_ssh.exec_cmd('touch {}'.format(status_file), fail_ok=False)
        if not bld_srv_ssh.file_exists(file_path=status_file):
            raise FileNotFoundError("Touched file {} does not exist!".format(status_file))

        print("{} is successfully touched on {}".format(status_file, build_server))

        if status == 'GREEN':
            green_path = '{}/latest_green_build'.format(builds_dir)
            bld_srv_ssh.exec_cmd('rm -f {}'.format(green_path))
            bld_srv_ssh.exec_cmd('ln -s {} {}'.format(build_path, green_path), fail_ok=False)


def send_report(subject, recipients, msg_file=TMP_FILE):
    """
    send report to specified recipients

    Args:
        subject (str):
        recipients (str):
        msg_file (str):

    Returns:

    """

    # cmd = '''/usr/bin/mutt -e "set from='svc-cgcsauto@windriver.com'" -e "set realname='svc-cgcsauto'"
    #          -e "set content_type=text/html" -s "{}" -- "{}" < "{}"'''.format(subject, recipients, msg_file)

    cmd = '''mutt -e "set content_type=text/html" -s "{}" -- "{}" < "{}"'''.format(subject, recipients, msg_file)
    os.system(cmd)


def generate_report(recipients, subject='', source='mongo', tags=None, start_date=None, end_date=None, logs_dir=None,
                    mark_status=False):
    tmp_file, lab, build, build_server, raw_status = write_report_file(source=source, tags=tags, start_date=start_date,
                                                                       end_date=end_date, logs_dir=logs_dir)
    try:
        if mark_status in [True, 'true', 'True', 'TRUE']:
            mark_status_on_build_server(status=raw_status, build_server=build_server, build_id=build)
    except:
        raise
    finally:
        subject = subject.strip()
        subject = "TiS {} Test Report {} [{}] - {}".format(subject, lab, build, raw_status)
        send_report(subject=subject, recipients=recipients)
