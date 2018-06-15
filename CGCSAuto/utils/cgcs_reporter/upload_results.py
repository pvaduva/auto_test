import re
import psycopg2
import html
from contextlib import contextmanager
from optparse import OptionParser

from consts.lab import Labs
from utils import local_host
from utils.cgcs_reporter import parse_log

HOST = 'tis-lab-auto-test-history.cumulus.wrs.com'
USER = 'PV'
PASSWORD = 'li69nux'
DB_NAME = 'TestHistory'


@contextmanager
def open_conn_and_get_cur(dbname, user, host, password, autocommit=True, close_cur=True, close_conn=True):
    conn = cursor = None
    try:
        conn = psycopg2.connect("dbname='{}' user='{}' host='{}' password='{}'".format(dbname, user, host, password),
                                connect_timeout=60)
        if autocommit:
            conn.set_session(autocommit=True)
        cursor = conn.cursor()
        yield cursor
    finally:
        if close_cur and cursor is not None:
            cursor.close()
        if close_conn and conn is not None:
            conn.close()


def get_test_id(test_name, cursor):
    """
    Get test_id from test_name. If test does not exist in database, it will first insert the test and return the id.
    Args:
        test_name (str): e.g., test_flavor_cpu_realtime_negative[2-dedicated-yes-None-None-CpuRtErr.RT_AND_ORD_REQUIRED]
        cursor: cursor object for database connection

    Returns:

    """
    converted_name = __parse_testname(test_name, force=True)

    test_id = _get_test_id_from_name(converted_name, cursor=cursor)

    if test_id is None:
        test_id = insert_testcase(cursor=cursor, test_name=test_name)

    return test_id


def _get_test_id_from_name(test_name, cursor):
    rows = __select_rows(column='name', value=test_name, cursor=cursor, table='test_info', strict=False, rtn='id')
    if rows:
        if len(rows) > 1:
            print("WARNING! More than multiple rows found for test name: {}".format(test_name))
        return rows[0][0]


def _get_lab_id_from_name(lab_name, cursor):
    rows = __select_rows(column='lab_name', value=lab_name, cursor=cursor, table='lab_info', rtn='id')
    if rows:
        if len(rows) > 1:
            print("WARNING! More than multiple rows found for lab name: {}".format(lab_name, rows))
        return rows[0][0]


def __select_rows(column, value, cursor, table='test_info', strict=True, rtn='id'):
    operator = '=' if strict else '~'
    cmd = """SELECT {} FROM {} WHERE {} {} '{}';""".format(rtn, table, column, operator, value)
    return _execute_cmd(cmd=cmd, cursor=cursor)


def _execute_cmd(cmd, cursor):
    print(cmd)
    cursor.execute(cmd)
    rows = cursor.fetchall()
    print("Rows: {}\n".format(rows))
    return rows


def insert_testcase(test_name, cursor):
    assert test_name, "Invalid test_name: '{}'".format(test_name)
    test_id = _insert_row(cursor, table_name='test_info', col_names="id,name", values="DEFAULT,'{}'".format(test_name),
                          returning='id')[0]
    return test_id


def __parse_testname(test_name, force=False):
    if "::test_" in test_name:
        test_name = re.escape('test_' + test_name.split('::test_', 1)[1])
    elif force:
        test_name = re.escape(test_name)

    return test_name


def _insert_row(cursor, table_name, col_names, values, returning=None):
    returning = '' if returning is None else ' RETURNING {}'.format(returning)
    cmd = """INSERT INTO {} ({}) VALUES ({}){};""".format(table_name, col_names, values, returning)

    return _execute_cmd(cmd, cursor=cursor)[0]


def get_lab_id(lab_name, cursor):
    lab_id = _get_lab_id_from_name(lab_name=lab_name, cursor=cursor)
    if not lab_id:
        lab_id = insert_lab(lab_name, cursor=cursor, check_first=False)[1]

    return lab_id


def insert_lab(lab_name, cursor, check_first=True):
    if isinstance(lab_name, dict):
        lab_name = lab_name['name']
    if check_first:
        lab_id = _get_lab_id_from_name(lab_name=lab_name, cursor=cursor)
        if lab_id:
            return -1, lab_id

    lab_id = _insert_row(cursor, table_name='lab_info', col_names='lab_name', values="'{}'".format(lab_name),
                         returning='id')[0]
    return 0, lab_id


def get_test_session(cursor, session_name):
    rows = __select_rows(column='name', value=session_name, cursor=cursor, table='test_session')
    if rows:
        return rows[0][0]


def insert_test_session(cursor, **session_info):
    """
    Insert a test session row in test_session table
    Args:
        cursor:
        **session_info: Possible keys:
            id, auto-generated uuid if unspecified
            build_id (mandatory), e.g., '2017-09-07_22-01-34' (note single quotes have to be included)
            lab_id (mandatory), e.g., 4
            patch, e.g, 'TC_17.06_PATCH_0001 TC_17.06_PATCH_0002'
            sw_version, e.g., '17.06'
            tag, tag for filtering and reporting. e.g., weekly_storage, biweekly_mtc, regular_sanity
            name, automation log dir for automated test session or campaign session id for manual session via xstudio
                e.g., yow-cgcs-test:/sandbox/AUTOMATION_LOGS/wcp_3_6/201709121009/
            session_notes, system configs, etc

    Returns (str): <id> (session uuid)

    """
    col_names = ','.join(list(session_info.keys()))
    vals = list(session_info.values())
    vals = ','.join(["'{}'".format(val) if isinstance(val, str) else str(val) for val in vals])
    session_id = _insert_row(cursor=cursor, table_name='test_session', col_names=col_names, values=vals,
                             returning='id')[0]

    return session_id


def insert_test_history(cursor, **test_info):
    """
    Insert a test history record. test_id, lab_id, build_id are mandatory fields.
        start_time, end_time should also be specified when possible
    Args:
        cursor:
        **test_info: Possible keys:
            test_id, e.g., 103
            result, PASS/FAIL/SKIP
            build_id, e.g., '2017-09-07_22-01-34' (note single quotes have to be included)
            patch, e.g, 'TC_17.06_PATCH_0001 TC_17.06_PATCH_0002'
            sw_version, e.g., '17.06'
            lab_id, e.g., 4
            start_time, e.g., '2017-08-30 20:35:40'
            end_time, e.g., '2017-08-30 20:38:22'
            jira, e.g., 'CGTS-3333 CGTS2222'
            comments, e.g., 'i'm a comments'

    Returns (str):
        exec_id (uuid)

    """
    col_names = ','.join(list(test_info.keys()))
    values = __compose_vals(list(test_info.values()))
    exec_id = None
    try:
        exec_id = _insert_row(cursor=cursor, table_name='history', col_names=col_names, values=values,
                              returning='exec_id')[0]
    except psycopg2.IntegrityError as e:
        print("{}".format(e.__str__()))
        if 'already exists' not in e.__str__():
            raise

    return exec_id


def __compose_vals(values):
    return ','.join(["'{}'".format(val) if isinstance(val, str) else str(val) for val in values])


########################################################
def _get_version_and_patch(res_path=None, raw_res=None):
    if not raw_res:
        with open(res_path, mode='r') as f:
            raw_res = f.read()

    testcases_res, other_info = raw_res.split(sep='\n\n', maxsplit=1)
    sw_version = re.findall('Software Version: (.*)\n', other_info)
    sw_version = sw_version[0].strip() if sw_version else ''
    patches = re.findall('Patches:((\n.*)+)\n\n', other_info)
    patches = patches[0][0] if patches else ''

    return sw_version, patches


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


def _get_local_results(res_path):
    with open(res_path, mode='r') as f:
        raw_res = f.read()

    testcases_res, other_info = raw_res.split('\n\n', maxsplit=1)
    testcases_res = testcases_res.strip()
    testcases_res = testcases_res.replace('Passed\t', 'PASS\t').replace('Failed\t', 'FAIL\t').\
        replace('Skipped\t', 'SKIP\t')
    testcases_res = re.sub(r'\t[^\t]*::test', r'\ttest', testcases_res)

    lab = re.findall('Lab: (.*)\n', other_info)[0].strip()
    build = re.findall('Build ID: (.*)\n', other_info)[0].strip()
    build_server = re.findall('Build Server: (.*)\n', other_info)[0].strip()
    tag = re.findall('Session Tag: (.*)\n', other_info)
    tag = tag[0].strip().lower() if tag else None
    sw_version, patches = _get_version_and_patch(raw_res=raw_res)
    log_path = re.findall('Automation LOGs DIR: (.*)\n', other_info)[0].strip()
    hostname = local_host.get_host_name()
    log_path = "{}:{}".format(hostname, log_path)
    ends_at = re.findall('Ends at: (.*)\n', other_info)
    ends_at = ends_at[0].strip() if ends_at else ''
    pass_rate = re.findall("Passed: .* \((.*)%\)\n", other_info)[0].strip()
    summary = other_info.split('\nSummary:')[-1].strip()
    overall_status = _get_overall_status(pass_rate)

    return lab, build, build_server, overall_status, log_path, summary, testcases_res, sw_version, patches, ends_at, tag
##########################################################################################################


def __get_testcases_info(testcases_res, ends_at=None):
    testcases = testcases_res.strip().splitlines()
    tests_res_list = []
    end_time = ends_at
    for test_res in reversed(testcases):
        values = test_res.split('\t')
        res, start_time, test_name = values[:3]
        test_res_dict = {'test_name': test_name,
                         'result': res,
                         'start_time': start_time,
                         }
        if end_time:
            test_res_dict['end_time'] = end_time

        tests_res_list.insert(0, test_res_dict)
        end_time = start_time

    return tests_res_list


def upload_test_results(cursor, log_dir, tag=None):
    lab, build, build_server, overall_status, log_path, summary, testcases_res, sw_version, patches, ends_at, \
        default_tag = _get_local_results("{}/test_results.log".format(log_dir))

    session_id = get_test_session(cursor=cursor, session_name=log_dir)
    if session_id and tag:
        existing_tag = __select_rows(column='id', value=session_id, cursor=cursor, table='test_session', rtn='tag')[0]
        if existing_tag != tag:
            print("WARNING! Session with tag {} already exist. Cannot re-upload with new tag: {}".format(existing_tag,
                                                                                                         tag))
    if not session_id:
        session_info = dict(name=log_dir)
        session_info['build_id'] = build
        session_info['sw_version'] = sw_version
        session_info['patch'] = patches.strip()
        lab_id = get_lab_id(lab_name=_get_lab_full_name(lab), cursor=cursor)
        session_info['lab_id'] = lab_id
        tag = tag if tag else default_tag
        if tag:
            session_info['tag'] = tag
        # print("{}".format(session_info))
        session_id = insert_test_session(cursor=cursor, **session_info)

    tracebacks = parse_log.get_parsed_failures(log_dir)
    tests_info = __get_testcases_info(testcases_res=testcases_res, ends_at=ends_at)
    for test_info in tests_info:    # type: dict
        test_info['session_id'] = session_id
        test_name = test_info.pop('test_name')
        if test_name in tracebacks:
            test_info['comments'] = "<pre>" + html.escape(tracebacks[test_name]) + "</pre>"
        # print("{}".format(test_name))
        test_id = get_test_id(test_name, cursor=cursor)
        test_info['test_id'] = test_id
        insert_test_history(cursor=cursor, **test_info)

    return session_id


def upload_test_result(session_id, test_name, result, start_time, end_time, traceback=None, parse_name=False,
                       **extra_info):
    """
    Upload result for single testcase to database
    Args:
        session_id:
        test_name:
        result:
        start_time:
        end_time:
        traceback (None|str|list):
        parse_name (bool): whether to parse test_name
        **extra_info: valid keys: jira

    Returns (str|None): exec_id or None if record already exists
    """

    if parse_name:
        test_name = 'test_{}'.format(test_name.split('::test_', 1)[-1])

    with open_conn_and_get_cur(dbname=DB_NAME, user=USER, host=HOST, password=PASSWORD) as cursor:
        test_id = get_test_id(test_name, cursor=cursor)
        test_info = dict(session_id=session_id, test_id=test_id, result=result, start_time=start_time,
                         end_time=end_time)

        if traceback:
            if isinstance(traceback, list):
                traceback = traceback[0]
            traceback = parse_log.get_parsed_failure(traceback)
            test_info['comments'] = "<pre>" + html.escape(traceback) + "</pre>"

        for key in 'jira':
            val = extra_info.get(key, None)
            if val:
                test_info[key] = val

        return insert_test_history(cursor, **test_info)


def upload_test_session(lab_name, build_id, log_dir, tag=None, build_server=None, sw_version=None, patches=None,
                        session_notes=None):
    session_info = {
        'build_id': build_id.lower(),
        'name': log_dir,
    }

    optional_info = {
        'build_server': build_server.lower() if build_server else None,
        'sw_version': sw_version,
        'patch': patches,
        'session_notes': session_notes,
        'tag': tag
    }

    for key, val in optional_info.items():
        if val:
            session_info[key] = val

    with open_conn_and_get_cur(dbname=DB_NAME, user=USER, host=HOST, password=PASSWORD) as cursor:
        lab_id = get_lab_id(lab_name=lab_name, cursor=cursor)
        session_info['lab_id'] = lab_id
        return insert_test_session(cursor=cursor, **session_info)


def get_exec_id(cursor, test_name, session, is_uuid=True):
    session_id = session
    if not is_uuid:
        session_id = get_test_session(cursor=cursor, session_name=session)

    rows = __select_rows(column='session_id', value=session_id, table='history', strict=True, cursor=cursor,
                         rtn='exec_id')
    if not rows:
        raise ValueError("test record for {} in session {} does not exist".format(test_name, session_id))

    return rows[0][0]


def update_test_record(cursor, exec_id, **test_info):
    raise NotImplementedError


def _get_lab_full_name(lab_short_name):
    labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]
    for lab in labs:
        if isinstance(lab, dict):
            if lab.get('short_name', None) == lab_short_name:
                return lab.get('name')
    raise ValueError("No lab found with short_name: {}".format(lab_short_name))


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-t', '--tag', action='store', type='string', dest='session_tag', help='test session tag')
    parser.add_option('--lab', '--labs', action='store_true', dest='upload_lab', help='Upload labs to lab_info table')

    options, args = parser.parse_args()

    print(str(options.upload_lab))

    if options.upload_lab:
        labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]

        lab_names = sorted([lab_['name'] for lab_ in labs if isinstance(lab_, dict) and lab_['name'].startswith('yow')])

        try:
            with open_conn_and_get_cur(dbname=DB_NAME, user=USER, host=HOST, password=PASSWORD) as cur:
                for lab_name in lab_names:
                    insert_lab(lab_name, cursor=cur, check_first=True)

            print("All labs are uploaded!")
        except Exception as e:
            print("Unable to upload. Details: {}".format(e.__str__()))

    else:
        try:
            logdir = args[0]
        except IndexError:
            raise ValueError("Automation session log directory has to be provided!\n"
                             "Usage: upload_results.py <log_dir>")

        try:
            with open_conn_and_get_cur(dbname=DB_NAME, user=USER, host=HOST, password=PASSWORD) as cur:
                upload_test_results(cursor=cur, log_dir=logdir, tag=options.session_tag)
        except Exception as e:
            "Unable to upload test results. Details: {}".format(e.__str__())
