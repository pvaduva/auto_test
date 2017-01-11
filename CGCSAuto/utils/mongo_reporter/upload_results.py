import os
import re
import pexpect
import glob

from consts.reporting import UploadRes

LOCAL_PATH = os.path.dirname(__file__)
WASSP_PATH = os.path.join(LOCAL_PATH, "..", "..", "..", "..", "..")
WASSP_REPORTER = os.path.join(WASSP_PATH, "wassp/host/tools/report/testReportManual.py")
WASSP_PYTHON = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")


def upload_results(file_path=None, logs_dir=None, lab=None, tags=None, tester_name=None, skip_uploaded=True):
    """
    collect the test environment variables
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
    userstory = UploadRes.USER_STORY
    release_name = UploadRes.REL_NAME
    tag = tags if tags else UploadRes.TAG
    jira = ''

    # Parse common test info from test_results.log
    lab, build, testcases_list, log_dir = __parse_common_info(file_path)

    logfile = ','.join([os.path.join(log_dir, 'TIS_AUTOMATION.log'), os.path.join(log_dir, 'pytestlog.log')])
    tester_name = tester_name if tester_name else os.environ['USER']
    result_ini = os.path.join(log_dir, 'last_record.ini')
    upload_log = os.path.join(log_dir, 'uploaded_tests.log')

    uploaded_tests = []
    if skip_uploaded and os.path.isfile(upload_log):
        with open(upload_log, mode='r') as upload_f:
            uploaded_tests = upload_f.read().strip().splitlines()
        uploaded_tests = [uploaded_name.strip() for uploaded_name in uploaded_tests]

    for record in testcases_list:
        # empty file contents
        with open(result_ini, mode='w'):
            pass

        # Parse each record
        test_name, domain, result = __parse_testcase_record(record)

        if test_name in uploaded_tests:
            print("Result for {} already uploaded. Skip uploading.".format(test_name))
            continue

        # Upload result
        if not __upload_result(result_ini=result_ini, tag=tag, tester_name=tester_name, test_name=test_name,
                               result=result, lab=lab, build=build, userstory=userstory, domain=domain, jira=jira,
                               logfile=logfile, release_name=release_name, upload_log=upload_log):
            exit(1)

    print('All results uploaded successfully from: {}'.format(file_path))


def __upload_result(result_ini, tag, tester_name, test_name, result, lab, build, userstory, domain, jira, logfile,
                    release_name, upload_log):

    upload_cmd = "{} {} -f {} 2>&1".format(WASSP_PYTHON, WASSP_REPORTER, result_ini)
    env_params = "-o '%s' -x '%s'  -n '%s' -t '%s' -r '%s' -l '%s' -b '%s' -u '%s' -d '%s' -j '%s' -a '%s' -R '%s'" \
                 % (result_ini, tag, tester_name, test_name, result,
                    lab, build, userstory, domain,
                    jira, logfile, release_name)

    print("\nComposing result ini file for {}: {}".format(test_name, result_ini))
    ini_writer = os.path.join(LOCAL_PATH, 'ini_writer.sh')
    os.system("%s %s" % (ini_writer, env_params))

    # Upload test result to the mongo database
    print("Upload cmd for {}: {}".format(test_name, upload_cmd))
    local_child = pexpect.spawn(command=upload_cmd, encoding='utf-8', timeout=120)
    try:
        local_child.expect(pexpect.EOF, timeout=120)
        res = True
    except Exception as e:
        # Don't throw exception otherwise whole test session will end
        err = "Test result for {} failed to upload. Exception caught: {}\n".format(test_name, e.__str__())
        print(err)
        res = False

    upload_output = local_child.before
    if res:
        res = re.search("Finished saving test result .* to database", upload_output)

    if res:
        # add testname to uploaded_tests.log
        with open(upload_log, mode='a') as upload_f:
            upload_f.write("\n{}".format(test_name))
        print("Test result successfully uploaded to MongoDB: {}\n".format(test_name))
    else:
        # Stop if any test failed to upload
        print("Test result failed to upload to MongoDB: {}\nPlease check result ini: {}\n{}\n".format(
                test_name, result_ini, upload_output))

    return res


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
    test_name = full_name.split(sep='::')[-1].strip()

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
    log_dir = test_results_file.replace('test_results.log', '')

    return lab, build, testcases_list, log_dir