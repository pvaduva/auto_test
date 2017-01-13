import os
import re
import datetime
import requests

from utils import lab_info, local_host

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


def write_report_file(sys_config=None, source='mongo', tags=None, start_date=None, end_date=None):
    """

    Args:
        source (str): 'mongo' or <local test results path>
        tags (str|list):
        start_date (str):
        end_date (str):

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
            _get_results_from_mongo(tags=tags, start_date=start_date, end_date=end_date)

    else:
        lab, build, build_server, overall_status, log_path, summary, testcases_res = _get_local_results(source)

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


def _get_results_from_mongo(tags, start_date, end_date, include_bld=False):
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

    panorama_url = "<a href='http://panorama.wrs.com:8181/#/testResults/?database=WASSP&view=list" \
                   "&dateField=[testExecutionTimeStamp]&programs=active&resultsMode=last" \
                   "&startDate={}&endDate={}" \
                   "&releaseName=[MYSQL1:2226]" \
                   "&tags=__in__[{}]'>Test Results Link</a>".format(start_date, end_date, ','.join(tags))

    print("Panorama query url: {}".format(panorama_url))

    overall_status = _get_overall_status(pass_rate)

    return lab, build, build_server, overall_status, panorama_url, summary, testcases_res


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


def generate_report(recipients, subject='', source='mongo', tags=None, start_date=None, end_date=None):
    tmp_file, lab, build, build_server, raw_status = write_report_file(source=source, tags=tags, start_date=start_date,
                                                                       end_date=end_date)
    subject = subject.strip()
    subject = "TiS {} Test Report {} [{}] - {}".format(subject, lab, build, raw_status)
    send_report(subject=subject, recipients=recipients)
