import os
import re

from utils import lab_info
from utils.mongo_reporter import generate_report
from utils.cgcs_reporter import download_results


TEST_SERVER_HTTP_AUTOLOG = generate_report.TEST_SERVER_HTTP_AUTOLOG
TMP_FILE = '/tmp/cgcs_sanity_email_report.html'
FAILED_CASES_IN_DEFECT_TABLE = []
TEST_CATEGORY = ["Setup", "Containers", "Platform", "Openstack"]
REPORT_FORMAT = """
<html><font face="arial" size="2">
<b>Subject: </b>{} <br>
<b>Lab: </b>{} <br>
<b>Load: </b>{} <br>
<b>Job: </b>{} <br>
<b>Build Server: </b>{} <br>
<b>Node Config: </b>{} <br>
<b>Software Version: </b>{} <br>
<br>
<b>Detailed Test Results Location: </b>{} <br>
<b>Automated Test Results Summary: </b> 
<br>
-----------------------------------------------------
{}
<br>
<b>Test Details by Category</b><br>
-------------------------------------
<br>
{}
<br>
<b>Defect List</b><br>
-----------------
{}
</html>
"""

DEFECT_TABLE_FORMAT = """
<pre>
<table border='1' cellpadding='5' cellspacing = 0 >
<tr>
<td><font size="2" face="arial"><b>Defect</b></font></td> 
<td><font size="2" face="arial"><b>\t\t\tTest Cases</b></font></td>
</tr>
<tr>
<td rowspan=1></td>
<td>{}</td>
</tr>
</table>
</pre>
"""


def write_report_file(tags):
    """
    Get info from test_history db and write a html email.

    Args:
        tags(list of str)

    Saved file as: /tmp/cgcs_sanity_email_report.html'
    """
    lab, build, job, build_server, node_config, sw, log_path = parser_results_form_cgcs_db(tags)
    summary, total_failed, total_passed, overall_status = _get_test_summary(tags)
    lab = lab_info.get_lab_dict(lab).get("short_name").upper()
    subject = "{} Test Report {} [{}] - {}".format("Sanity", lab, build, overall_status)

    testcases = get_formated_test_results(tags)

    # color the test result
    testcases = testcases.replace('\t', '&#9;'). \
        replace('PASS', "<font color='green'>PASS</font>"). \
        replace('FAIL', "<font color='red'>FAIL</font>"). \
        replace('SKIP', "<font color='#FFC200'>SKIP</font>")

    failed_case_names = ""
    for name in FAILED_CASES_IN_DEFECT_TABLE:
        failed_case_names += name + "<br>"

    with open(TMP_FILE, mode='w') as f:
        f.write(REPORT_FORMAT.format(subject, lab, build, job, build_server, node_config, sw, log_path, summary,
                                     testcases, DEFECT_TABLE_FORMAT.format(failed_case_names)))
    return subject


def parser_results_form_cgcs_db(tags):
    """
    This function is used to parser the results from cgcs_database

    Arg:
        tag (list of str):
    Returns:
        lab name, build_id, build_server, sw_version, log_path from test_history database
        build job and node config from ssh connection
    """
    lab = ""
    build = ""
    build_server = ""
    sw = ""
    session_names = set()  # the session_name in db is actually a log_path
    log_paths = "<br>"
    for tag in tags:
        tc_list = download_results.download_test_results(tag)

        lab = tc_list[0].get("lab_name")
        build = tc_list[0].get("build_id")
        build_server = tc_list[0].get("build_server")
        sw = tc_list[0].get("sw_version")

        for test in tc_list:
            session_names.add(test.get("log_path"))

    # these two steps are very slow because it will build a ssh connection
    sys_config = lab_info._get_sys_type(labname=lab)
    job = lab_info.get_build_info(labname=lab)[1]
    for path in list(session_names):
        path = _convert_log_path_to_http(path)
        log_paths += path + "<br>"
    return lab, build, job, build_server, sys_config, sw, log_paths


def get_formated_test_results(tags):
    """
    Get all test cases in html format.

    Arg:
        tags (list of str):
    Returns:
        test cases (html)
    """
    # Get all test cases from all tags:

    test_results_html = ""
    for tag in tags:
        test_results = download_results.download_test_results(tag)
        test_results_html += _convert_test_results_to_html(tag, test_results)
    return test_results_html


def _convert_test_results_to_html(tag, test_results):
    """
    Convert test results to html format.
    e.g. PASS	2019-06-21 15:27:07	test_system_alarms
    """
    section_name_format = "<b><u>{}</u></b>"
    testcases = ""
    section_name = _get_category_name_from_tag(tag)
    section_name_format = section_name_format.format(section_name)

    for test in test_results:
        testcases += test.get("result") + "\t" + str(test.get("start_time")) + "\t" + test.get("name") + "\n"
    content = "<pre>{}</pre>".format(testcases)
    return section_name_format + content


def _convert_log_path_to_http(log_path):
    log_path = re.sub("/sandbox/AUTOMATION_LOGS/", TEST_SERVER_HTTP_AUTOLOG, log_path)
    return log_path


def _get_test_summary(tags):
    summary_format = ""
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    for tag in tags:
        test_results = download_results.download_test_results(tag)
        passed, failed, skipped, pass_rate = _get_test_stastics(test_results)
        total_passed += passed
        total_failed += failed
        total_skipped += skipped
        section_name = _get_category_name_from_tag(tag)
        status = generate_report.get_overall_status(pass_rate)
        summary = section_name.ljust(16) + str(passed) + "/" + str(failed+passed+skipped).ljust(3) + "(" + pass_rate + \
            ")".ljust(4) + status + "\n"
        summary_format += summary
    total = total_passed + total_failed + total_skipped
    overall_pass_rate = "{}%".format(round(total_passed * 100 / total, 2))
    overall_status = generate_report.get_overall_status(overall_pass_rate)
    summary_format = "<pre>{}" \
                     "--------------------------------------\n" \
                     "Overall:\t{}/{} ({}) {} \n" \
                     "Skipped:\t{}</pre>".format(summary_format, total_passed,total, overall_pass_rate,
                                                 overall_status, total_skipped)
    return summary_format, total_passed, total_failed, overall_status


def _get_test_stastics(data=None):
    row_dict_list = data
    failed = passed = skipped = 0
    for test_case in row_dict_list:
        if test_case.get("result") == "FAIL":
            failed += 1
            FAILED_CASES_IN_DEFECT_TABLE.append(test_case.get("name"))
        elif test_case.get("result") == "PASS":
            passed += 1
        elif test_case.get("result") == "SKIP":
            skipped += 1
    total_exec = failed + passed
    pass_rate = "{}%".format(round(passed * 100 / total_exec, 2))

    return passed, failed, skipped, pass_rate


def _get_category_name_from_tag(tag):
    for name in TEST_CATEGORY:
        if name in tag:
            return "Sanity-" + name
        else:
            return tag


def generate_sanity_report(recipients, *tags):
    subject = write_report_file(list(tags))
    recipients = recipients.strip()
    if ' ' in recipients and ';' not in recipients:
        recipients = ';'.join(recipients.split())
    generate_report.send_report(subject=subject, recipients=recipients, msg_file=TMP_FILE)
