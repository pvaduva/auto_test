import pytest
from optparse import OptionParser


def repeat_tests(lab, count=10, file_path=None, test_cases=None, cgcsauto_path=None, stop_on_failure=False,
                 reporttag=None, resultlog=None, sessiondir=None):
    if file_path:
        test_cases = _get_tests_from_file(file_path=file_path)
        if not test_cases:
            print("No testcases listed in {}.".format(file_path))
            return
    elif test_cases:
        if isinstance(test_cases, str):
            test_cases = [test_cases]
    else:
        raise ValueError("Either file_path or test_cases has to be specified!")

    if cgcsauto_path:
        test_cases = ['{}/{}'.format(cgcsauto_path, t) for t in test_cases]

    repeat_param = '--repeat' if stop_on_failure else '--stress'
    repeat_param = '{}={}'.format(repeat_param, count)

    testcases_str = ' '.join(test_cases)
    params = ['--lab={}'.format(lab), repeat_param, testcases_str]
    if reporttag:
        params.append('--report_tag="{}"'.format(reporttag))
    if sessiondir:
        params.append('--sessiondir="{}"'.format(sessiondir))
    elif resultlog:
        params.append('--resultlog="{}"'.format(resultlog))

    print("pytest params: {}".format(params))
    pytest.main(params)


def _get_tests_from_file(file_path):
    tests = []
    with open(file_path, mode='r') as f:
        raw_tests = f.readlines()

    for t in raw_tests:
        t = t.strip()
        if 'test_' in t:
            tests.append(t)
    return tests


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-c', '--count', action='store', type='int', dest='count', default=10, help='How many times to repeat')
    parser.add_option('-f', '--file', action='store', type='string', dest='file_path', help='test list file path')
    parser.add_option('-t', '--test', action='store', type='string', dest='testcase', help='testcases')
    parser.add_option('--stop', action='store_true', dest='stop', default=False,
                      help='Stop session without teardown upon first failure')
    parser.add_option('--cgcsauto', action='store', dest='cgcsauto', help='CGCSAuto dir')
    parser.add_option('--sessiondir', action='store', dest='sessiondir', help='Automation session log dir')
    parser.add_option('--resultlog', action='store', dest='resultlog', help='Automation logs root dir. e.g., /home')
    parser.add_option('--reporttag', action='store', dest='reporttag', help='report tag')

    options, args = parser.parse_args()

    usage = "\nUsage: repeat_tests.py -f=<file_path>]|-t=<test_path> [--stop] <lab>"
    try:
        lab_ = args[0]
    except IndexError:
        raise ValueError("lab has to be provided!{}".format(usage))

    f_path = options.file_path
    kwargs = dict(lab=lab_, stop_on_failure=options.stop, count=options.count, cgcsauto_path=options.cgcsauto,
                  sessiondir=options.sessiondir, resultlog=options.resultlog, reporttag=options.reporttag)
    if not f_path:
        test = options.testcase
        if not test:
            raise ValueError("file_path or test has to be provided!{}".format(usage))

        kwargs['test_cases'] = test
    else:
        kwargs['file_path'] = f_path

    repeat_tests(**kwargs)
