import time

from datetime import datetime
from pytest import fixture
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.timeout import SysInvTimeout
from keywords import ceilometer_helper, system_helper


@fixture(scope='module', autouse=True)
def reset_retention(request):
    original = system_helper.get_retention_period()
    LOG.debug(original)

    def reset():
        system_helper.set_retention_period(period=original, fail_ok=False)
    request.addfinalizer(reset)


def test_retention_period():
    """
    TC1996
    Verify that the retention period can be changed to specified values

    Test Steps:
        - Change the retention period to different values
        - Verify that the retention period changed correctly
        - Attempt to change to invalid values
        - Verify that the changes were rejected

    Teardown:
        - reset     ('module')
    """
    times = [31536000, 604800, 3600, 86400]
    for interval in times:
        LOG.tc_step("changing retention period to: {}".format(interval))
        res, out = system_helper.set_retention_period(period=interval)
        ret_per = system_helper.get_retention_period()
        assert interval == int(ret_per), "FAIL: the retention period didn't change correctly"
        assert 0 == res, "FAIL: the retention period didn't change correctly"

    times = [3500, 32000000]
    for interval in times:
        LOG.tc_step("changing retention period to: {}".format(interval))
        res, out = system_helper.set_retention_period(period=interval, fail_ok=True)
        ret_per = system_helper.get_retention_period()
        assert interval != int(ret_per) and 0 != res, "FAIL: the retention period was changed"


def test_retention_sample():
    """
    TC1998
    Check that a sample can't be removed until after retention period

    Test Steps:
        - Change retention period to 3600 (minimum allowed)
        - Get a resource ID
        - Create a fake sample
        - Trigger /usr/bin/ceilometer-expirer and verify that fake sample is still in the list
        - Wait for retention period (1 hour)
        - Trigger the expirer again and verify that fake sample is not in the list

    Teardown:
        - reset     ('module')
    """
    system_helper.set_retention_period(period=3600)
    ret_per = system_helper.get_retention_period()
    assert 3600 == int(ret_per), "The retention period was not changed to 1 hour"

    LOG.tc_step("Choosing a resource")
    out = ceilometer_helper.get_resources(header='Resource ID')
    res_id = out[0]

    # create fake timestamp
    curr_time = datetime.utcnow()
    curr_secs = curr_time.timestamp()
    new_time = datetime.fromtimestamp(curr_secs - 3540)
    new_time = str(new_time).replace(' ', 'T')
    LOG.info("\nnow: {}\n59 min ago{}".format(curr_time, new_time))

    LOG.tc_step("Creating fake sample")

    args = {'meter-name': 'fake_sample', 'meter-type': 'gauge', 'meter-unit': 'percent',
            'sample-volume': 10, 'timestamp': new_time}
    ceilometer_helper.create_sample(resource_id=res_id, field='timestamp', auth_info=Tenant.ADMIN, **args)

    LOG.info("Waiting {} seconds for retention period change".format(SysInvTimeout.RETENTION_PERIOD_SAVED))
    time.sleep(SysInvTimeout.RETENTION_PERIOD_SAVED)
    LOG.tc_step("Ensuring the sample is listed")

    ceilometer_helper.delete_samples()
    # sample-create uses meter-name for the name of the sample.
    # sample-list uses meter to specify the name to search for.
    # probably will have to change at least one of them when they become consistent.
    samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
    assert 1 == len(samples), "FAIL: The sample is not in the list"

    if 65 - SysInvTimeout.RETENTION_PERIOD_SAVED > 0:
        LOG.info("Waiting for retention period to end.")
        time.sleep(65 - SysInvTimeout.RETENTION_PERIOD_SAVED)

    ceilometer_helper.delete_samples()

    LOG.tc_step("Ensuring the sample isn't listed anymore")
    samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
    assert 0 == len(samples), "FAIL: The sample was not removed"
