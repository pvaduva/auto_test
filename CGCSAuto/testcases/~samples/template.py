from pytest import mark, skip

from utils.tis_log import LOG


def check_testparam(param):
    if param == 'param2_value3':
        raise ValueError("I don't like this value")
    LOG.info('Test passed')


# @mark.skipif(1==1, reason="reason for skipping the test function")
@mark.usefixtures('check_alarms')
@mark.parametrize(('test_param1', 'test_param2'), [
    ('param1_value1', 'param2_value1'),
    ('param1_value2', 'param2_value2'),
    ('param1_value3', 'param2_value3'),
    ('param1_value4', 'param2_value4'),
])
def test_func(test_param1, test_param2):
    """
    Sample tests:
        test 1: skip
        test 2: fails at assert in test function
        test 3: fails inside a helper function
        test 4: pass

    Args:
        test_param1:
        test_param2:

    Test Steps:
        - I'm a test step
        - I'm another test step
        - I'm the last step

    """

    if test_param1 == 'param1_value1':
        skip('I want to skip param1_value1')

    LOG.tc_step("I'm a test step")
    LOG.info(test_param1)

    LOG.tc_step("I'm another test step")
    assert test_param2 != 'param2_value2'

    LOG.tc_step("I'm the last step")
    check_testparam(test_param2)
