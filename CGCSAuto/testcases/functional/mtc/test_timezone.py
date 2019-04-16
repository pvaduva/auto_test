import time
import random
import re

from pytest import fixture, mark

from utils import table_parser, cli
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.auth import Tenant
from consts.cgcs import TIMEZONES
from keywords import host_helper, system_helper, cinder_helper,  common


TIMEZONES = TIMEZONES[:-1]      # exclude UTC
TIMESTAMP_PATTERN = '\d{4}-\d{2}-\d{2}[T| ]\d{2}:\d{2}:\d{2}'


@fixture(scope='module', autouse=True)
def revert_timezone(request):
    def _revert():
        LOG.fixture_step("Reverting timezone to UTC")
        system_helper.modify_timezone(timezone='UTC')
    request.addfinalizer(_revert)


def __select_diff_timezone(current_zone=None):
    if not current_zone:
        current_zone = system_helper.get_timezone()

    zones = list(TIMEZONES)
    if current_zone in zones:
        zones.remove(current_zone)

    return random.choice(zones)


def get_epoch_date(con_ssh=None):
    pattern = '%a %b %d %H:%M:%S %Y'
    timestamp = common.get_date_in_format(ssh_client=con_ssh, date_format=pattern)
    system_epoch = int(time.mktime(time.strptime(timestamp, pattern)))
    return system_epoch


def parse_log_time(log_line):
    date_time = re.findall(TIMESTAMP_PATTERN, log_line)[0].replace('T', ' ')
    pattern = '%Y-%m-%d %H:%M:%S'
    log_epoch = int(time.mktime(time.strptime(date_time, pattern)))
    return log_epoch


def test_modify_timezone_log_timestamps():
    """
    Test correct log timestamps after timezone change

    Prerequisites
        - N/A
    Test Setups
        - Get a random timezone for testing
        - Get system time (epoch) before timezone change
    Test Steps
        - Modify timezone
        - While to modification is pending get the last timestamp (epoch) from each log
        - Wait for out_of_date alarms to clear
        - Get system time (epoch) after timezone change
        - Ensure the timezone change effected the date by comparing system time before and after timezone change
        - For 3 minutes check each log for a new entry
        - Ensure that the new entry in each log is in line with the timezone change
    Test Teardown
        - N/A
    """
    logs = ('auth.log', 'daemon.log', 'fm-event.log', 'fsmond.log', 'kern.log', 'openstack.log',
            'pmond.log', 'user.log')
    #  'sm-scheduler.log' fails (CGTS-10475)

    LOG.tc_step("Collect timezone, system time, and log timestamps before modify timezone")

    LOG.info("Get timezones for testing")
    prev_timezone = system_helper.get_timezone()
    post_timezone = __select_diff_timezone(current_zone=prev_timezone)

    con_ssh = ControllerClient.get_active_controller()
    # Saving the last entry from the logs; If it is the same later, there is no new entry in the log.
    LOG.tc_step("Get last entry from log files and compare with system time")
    prev_timestamps = {}
    time.sleep(5)
    for log in logs:
        last_line = con_ssh.exec_cmd('tail -n 1 /var/log/{}'.format(log))[1]
        log_epoch = parse_log_time(last_line)
        prev_timestamps[log] = log_epoch

    prev_system_epoch = get_epoch_date(con_ssh=con_ssh)
    prev_check_fail = []
    for log, timestamp in prev_timestamps.items():
        if timestamp > prev_system_epoch:
            prev_check_fail.append(log)

    assert not prev_check_fail, "{} timestamp does not match system time".format(prev_check_fail)

    start_time = time.time()
    LOG.tc_step("Modify timezone from {} to {}".format(prev_timezone, post_timezone))
    system_helper.modify_timezone(timezone=post_timezone)
    end_time = time.time()
    mod_diff = end_time - start_time

    LOG.tc_step("Verify system time is updated")
    time.sleep(10)
    post_system_epoch = get_epoch_date(con_ssh=con_ssh)
    time_diff = abs(prev_system_epoch - post_system_epoch)
    assert time_diff > 3600, "Timezone change did not affect the date"
    LOG.info("system time is updated after timezone modify")

    LOG.tc_step("Wait for new logs to generate and verify timestamps for new log entries are updated")
    logs_to_test = {}
    timeout = time.time() + 300
    while time.time() < timeout:
        for log_name, value in prev_timestamps.items():
            last_line = con_ssh.exec_cmd('tail -n 1 /var/log/{}'.format(log_name))[1]
            # If last line does not exist in last_log_entries; New line is in the log; Add log to logs_to_test
            new_log_epoch = parse_log_time(last_line)
            prev_log_epoch = prev_timestamps[log_name]
            epoch_diff_prev_log_to_sys = prev_system_epoch - prev_log_epoch
            epoch_diff_prev_log = new_log_epoch - prev_log_epoch

            LOG.info('timezone modify time used: {}; pre-modify sys time - last log time: {}'.
                     format(mod_diff, epoch_diff_prev_log_to_sys))
            if abs(epoch_diff_prev_log) > max(mod_diff, 180) + epoch_diff_prev_log_to_sys:
                LOG.info("{} has new log entry. Adding to logs_to_test.".format(log_name))
                logs_to_test[log_name] = new_log_epoch
                del prev_timestamps[log_name]
                break

        if not prev_timestamps:
            break

        time.sleep(10)

    # Get latest log entries, convert to epoch
    failed_logs = {}
    for log_name, value in logs_to_test.items():
        time_diff = abs(value - post_system_epoch)
        LOG.info("log: {} time diff: {}".format(log_name, time_diff))
        if time_diff > 330:
            failed_logs[log_name] = "time_diff: {}".format(time_diff)
    assert not failed_logs, "Timestamp for following new logs are different than system time: {}".format(failed_logs)


def get_cli_timestamps(vol_id):

    table_ = table_parser.table(cli.system('show'))
    sysinv_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    table_ = table_parser.table(cli.openstack('volume show', vol_id, auth_info=Tenant.get('admin')))
    openstack_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    return  sysinv_timestamp, openstack_timestamp


def test_modify_timezone_cli_timestamps():
    """
    Test correct timestamps in:
        - ceilometer
        - cinder
        - glance
        - neutron
        - nova
        - sysinv

    Setups
        - Get a random timezone for testing
        - Create cinder volume
        - Boot a vm

    Test Steps
        - Save the pre-timezone-change timestamps from each cli domain
        - Modify the timezone
        - Wait for out_of_date alarms to clear
        - Save the post-timezone-change timestamps from each cli domain
        - Verify the timestamps have changed to be in line with the timezone change

    Teardown
        - Deleted cinder volume
        - Delete the vm

    """
    services = ('sysinv', 'openstack')

    prev_timezone = system_helper.get_timezone()
    post_timezone = __select_diff_timezone(current_zone=prev_timezone)

    # CHECK PRE TIMEZONE CHANGE CLI TIMESTAMPS
    LOG.tc_step("Getting CLI timestamps before timezone change for: {}".format(services))
    vol_id = cinder_helper.create_volume('timezone_test', cleanup='function')[1]

    prev_timestamps = get_cli_timestamps(vol_id=vol_id)
    LOG.tc_step("Modify timezone from {} to {}".format(prev_timezone, post_timezone))
    system_helper.modify_timezone(post_timezone)

    # CHECK POST TIMEZONE CHANGE CLI TIMESTAMPS
    time.sleep(10)
    LOG.tc_step("Getting CLI timestamps after timezone change for: {}".format(services))
    post_timestamps = get_cli_timestamps(vol_id=vol_id)

    LOG.tc_step("Comparing timestamps from before and after timezone change for: {}".format(services))
    failed_services = []
    for i in range(len(services) - 1):      # -1 to ignore last item opentack cli (CGTS-10475)
        if prev_timestamps[i] == post_timestamps[i]:
            failed_services.append(services[i])

    assert not failed_services, "{} timestamp did not update after timezone modify".format(failed_services)


@mark.dc
def test_modify_timezone_sys_event_timestamp():
    """
    Test alarm timestamps line up with a timezone change

    Prerequisites
        - N/A
    Test Setups
        - Get a random timezone for testing
    Test Steps
        - Get the UUID and timestamp from the most recent event
        - Change the timezone and wait until the change is complete
        - Wait for out_of_date alarms to clear
        - Compare the timestamp from the event using the UUID
        - Verify the timestamp changed with the timezone change
    Test Teardown
        - N/A
    """
    LOG.tc_step("Gathering pre-modify timestamp for last event in system event-list")
    event = system_helper.get_events(rtn_vals=('UUID', 'Event Log ID', 'Entity Instance ID', 'State', 'Time Stamp'),
                                     limit=1, combine_entries=False)[0]
    event_uuid, event_log_id, entity_instance_id, event_state, pre_timestamp = event

    # Pick a random timezone to test that is not the current timezone
    timezone_to_test = __select_diff_timezone()

    LOG.tc_step("Modify timezone to {}".format(timezone_to_test))
    system_helper.modify_timezone(timezone=timezone_to_test)

    LOG.tc_step("Waiting for timezone for previous event to change in system event-list")
    timeout = time.time() + 60
    post_timestamp = None
    while time.time() < timeout:
        post_timestamp = system_helper.get_events(rtn_vals='Time Stamp', event_id=event_log_id, uuid=event_uuid,
                                                  entity_id=entity_instance_id, state=event_state)[0][0]
        if pre_timestamp != post_timestamp:
            break

        time.sleep(5)
    else:
        assert pre_timestamp != post_timestamp, "Timestamp did not change with timezone change."

    if not system_helper.is_simplex():
        LOG.tc_step("Swact and verify timezone persists")
        host_helper.swact_host()
        post_swact_timezone = system_helper.get_timezone()
        assert post_swact_timezone == timezone_to_test

        post_swact_timestamp = system_helper.get_events(rtn_vals='Time Stamp', event_id=event_log_id, uuid=event_uuid,
                                                        entity_id=entity_instance_id, state=event_state)[0][0]
        assert post_swact_timestamp == post_timestamp
