import logging
import time
import re
import sys

from datetime import timedelta, datetime
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions, table_parser
from consts.auth import Tenant
from utils.ssh import ControllerClient
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper


@fixture(scope='module', autouse=True)
def reset_retention(request):
    out = cli.system('pm-show', auth_info=Tenant.ADMIN)
    table_ = table_parser.table(out)
    original = get_column_value(table_, 'retention_secs')
    LOG.info(original)

    def reset():
        out = cli.system('pm-modify', 'retention_secs={} action=apply'.format(original), auth_info=Tenant.ADMIN)
        LOG.info("Set retention period to: \n{}".format(out))
    request.addfinalizer(reset)


def get_column_value(table, search_value):
    """
    Function for getting column value

    Get value from table with two column
    :table param: parse table with two colums (dictionary)
    :search_value param: value in column for checking
    """
    column_value = None
    for col_value in table['values']:
        if search_value == col_value[0]:
            column_value = col_value[1]
    return column_value


def test_retention_period():
    """
    TC1996
    Verify that the retention period can be changed to specified values

    Test Steps:
        - Change the retention period to different values
        - Verify that the retention period changed correctly

    """
    times = [86400, 604800, 21600]
    for interval in times:
        LOG.tc_step("changing retention period to: {}".format(interval))
        out = cli.system('pm-modify', 'retention_secs={} action=apply'.format(interval), auth_info=Tenant.ADMIN)
        table_ = table_parser.table(out)
        ret_per = get_column_value(table_, 'retention_secs')
        assert interval == int(ret_per), "FAIL: the retention period didn't change correctly"

        out = cli.system('pm-show', auth_info=Tenant.ADMIN)
        table_ = table_parser.table(out)
        ret_per = get_column_value(table_, 'retention_secs')
        assert interval == int(ret_per), "FAIL: the retention period didn't change correctly"


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

    """
    LOG.tc_step("Choosing a resource")
    out = cli.ceilometer('resource-list', '--limit 10', timeout=30, auth_info=Tenant.ADMIN)
    table_ = table_parser.table(out)
    res_id = table_['values'][0][0]

    curr_time = datetime.utcnow()
    curr_secs = curr_time.timestamp()
    new_time = datetime.fromtimestamp(curr_secs - 3540)
    new_time = str(new_time).replace(' ', 'T')
    LOG.info("\nnow: {}\n59 min ago{}".format(curr_time, new_time))

    out = cli.system('pm-modify', 'retention_secs=3600 action=apply')
    table_ = table_parser.table(out)
    ret_per = get_column_value(table_, 'retention_secs')
    assert 3600 == int(ret_per), "The retention period was not changed to 1 hour"

    LOG.tc_step("Creating fake sample")
    #create sample thinking it was made 59 minutes ago
    args = '-r {} -m fake_sample --meter-type gauge --meter-unit percent --sample-volume 10 ' \
           '--timestamp {}'.format(res_id, new_time)
    out = cli.ceilometer('sample-create', args, auth_info=Tenant.ADMIN)
    LOG.info("\n{}".format(out))
    table_ = table_parser.table(out)
    time_created = get_column_value(table_, 'timestamp')

    ssh_client = ControllerClient.get_active_controller()
    ssh_client.exec_sudo_cmd('/usr/bin/ceilometer-expirer')
    LOG.tc_step("Ensuring the sample is listed")
    out = cli.ceilometer('sample-list', '-m fake_sample', auth_info=Tenant.ADMIN)
    LOG.info("\n{}".format(out))
    table_ = table_parser.table(out)

    in_list = False
    for sample in table_['values']:
        timestamp = sample[5]
        if time_created == timestamp:
            in_list = True

    assert in_list, "FAIL: The sample is not in the list"

    LOG.info("Waiting for retention period to end.")
    time.sleep(65)

    ssh_client.exec_sudo_cmd('/usr/bin/ceilometer-expirer')
    LOG.tc_step("Ensuring the sample isn't listed anymore")
    out = cli.ceilometer('sample-list', '-m fake_sample', auth_info=Tenant.ADMIN)
    LOG.info("\n{}".format(out))
    table_ = table_parser.table(out)
    for sample in table_['values']:
        timestamp = sample[5]
        assert time_created != timestamp, "FAIL: The sample was not removed"
