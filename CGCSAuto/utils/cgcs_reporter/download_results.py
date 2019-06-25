import psycopg2
from contextlib import contextmanager

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


def download_test_results(tag):
    """
    Get test history info by tag.
    Args:
        tag (str): e.g., regular_sanity_20190611T000451Z_WCP_71_75

    Returns (list of dict):
    list of all test cases under a specific tag, each element is a dictionary with column name as key
        eg:
        [{'tag': 'regular_sanity_20190611T000451Z_WCP_71_75', 'sw_version': '19.01', 'session_notes': None,
        'patch': None, 'test_id': 5, 'name': '/sandbox/AUTOMATION_LOGS/wcp_71_75/201906111040',
        'created_at': datetime.datetime(2019, 6, 11, 9, 42, 58), 'comments': None, 'lab_name': 'yow-cgcs-wildcat-71_75',
        'end_time': datetime.datetime(2019, 6, 11, 14, 41, 27), 'session_id': '8e81f1ce-219f-4e8f-a1ee-4de5cb6e56c9',
        'lab_id': 35, 'jira': None, 'build_id': '20190611t000451z', 'build_server': 'starlingx_mirror',
        'log_path': 'test_ssh_to_hosts', 'result': 'PASS', 'start_time': datetime.datetime(2019, 6, 11, 14, 40, 35)}
        ...]
        the dict keys are:
        ['result', 'name', 'start_time', 'end_time', 'session_id', 'log_path', 'tag', 'lab_id', 'sw_version',
        'lab_name', 'build_id', 'build_server', 'patch', 'session_notes', 'created_at', 'jira', 'comments', 'id']

    """

    try:
        with open_conn_and_get_cur(dbname=DB_NAME, user=USER, host=HOST, password=PASSWORD) as cur:
            cur.execute("select lab_name FROM test_session, lab_info WHERE "
                        "test_session.tag='{}' AND lab_id=lab_info.id;".format(tag))
            lab_name = cur.fetchall()[0][0]

            cur.execute(
                "SELECT result, test_info.name, start_time, end_time, session_id, test_session.name, tag, lab_id, "
                "sw_version, build_id, build_server, patch, session_notes, history.created_at, jira, comments, "
                "test_id "
                "FROM test_session, history, test_info "
                "WHERE test_session.tag='{}'AND test_session.id = history.session_id "
                "AND test_info.id=history.test_id;".format(tag))

            raw_data = cur.fetchall()
            column_names = [desc[0] for desc in cur.description]
            column_names[5] = 'log_path'  # avoid repeat column names
            row_dict_list = []

            for row in raw_data:
                row_dict = dict(zip(column_names, row))
                row_dict.update({"lab_name": lab_name})
                row_dict_list.append(row_dict)
            return row_dict_list

    except Exception as e:
        print("Unable to download test results. Details: {}".format(e.__str__()))
