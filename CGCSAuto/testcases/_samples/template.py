from pytest import mark

import setups
from utils.tis_log import LOG


# RENAME this function to reflect the actual check item
def skip_condition_met():
    # check system to decide whether skip condition is met
    return True

@mark.skipif(skip_condition_met, reason="reason for skipping the test function")
@mark.usefixtures('check_alarms')
@mark.parametrize(
    ('test_param1', 'test_param2'), [
        ('param1_value1', 'param2_value1'),
        ('param1_value2', 'param2_value2'),
        # ('param1_value3', 'param2_value3'),
    ])
def test_func(test1_param1, test_param2):
    """
    Summary of test func

    Args:
        test1_param1:
        test_param2:

    =====
    Prerequisites:

    Test Steps:

    """

    # skip condition check based on test data set and system status

    LOG.tc_func_start()

    LOG.tc_step("I'm a test step")
    # content of the step

    LOG.tc_step("I'm another test step")
    # content of another step

    # assert test result

    LOG.tc_func_end()
