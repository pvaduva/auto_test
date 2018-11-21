import time
import random
import re

from pytest import fixture, mark

from utils import table_parser, cli
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.auth import Tenant
from consts.cgcs import TIMEZONES
from keywords import host_helper, system_helper, cinder_helper, glance_helper, vm_helper, ceilometer_helper, \
    network_helper, common


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
    logs = ['auth.log', 'daemon.log', 'fm-event.log', 'fsmond.log', 'kern.log', 'openstack.log',
            'pmond.log', 'sm-scheduler.log', 'user.log']

    LOG.info("Get timezones for testing")
    prev_timezone = system_helper.get_timezone()
    post_timezone = __select_diff_timezone(current_zone=prev_timezone)

    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Ensure the system date is changed when the timezone is changed.")

    # Saving the last entry from the logs; If it is the same later, there is no new entry in the log.
    LOG.info("Saving the last entry from all logs.")
    prev_timestamps = {}
    time.sleep(5)
    for log in logs:
        last_line = con_ssh.exec_cmd('tail -n 1 /var/log/{}'.format(log))[1]
        log_epoch = parse_log_time(last_line)
        prev_timestamps[log] = log_epoch

    pre_system_epoch = get_epoch_date(con_ssh=con_ssh)

    system_helper.modify_timezone(timezone=post_timezone)
    post_system_epoch = get_epoch_date(con_ssh=con_ssh)
    time_diff = abs(pre_system_epoch - post_system_epoch)
    LOG.info("Time difference between {} and {} is {}".format(prev_timezone, post_timezone, time_diff))

    assert time_diff > 3600, "Timezone change did not affect the date"

    LOG.info("Wait up to 5 minutes for logs to update")
    logs_to_test = {}
    timeout = time.time() + 300
    while time.time() < timeout:
        for log_name, value in prev_timestamps.items():
            last_line = con_ssh.exec_cmd('tail -n 1 /var/log/{}'.format(log_name))[1]
            # If last line does not exist in last_log_entries; New line is in the log; Add log to
            # logs_to_test
            new_log_epoch = parse_log_time(last_line)
            epoch_diff = abs(new_log_epoch - pre_system_epoch)

            if epoch_diff > 600:
                LOG.info("{} has new timestamps. Adding to logs_to_test.".format(log_name))
                logs_to_test[log_name] = new_log_epoch
                del prev_timestamps[log_name]
                break

        # If last_log_entries is empty, break from checking logs as there is none left to check
        if len(prev_timestamps) == 0:
            break

        time.sleep(5)

    # Get latest log entries, convert to epoch
    LOG.tc_step("Verifying new timezone applied to new log entries")
    failed_logs = {}
    for log_name, value in logs_to_test.items():
        time_diff = abs(value - post_system_epoch)
        LOG.info("log: {} time diff: {}".format(log_name, time_diff))
        if time_diff > 3600:
            failed_logs[log_name] = "time_diff: {}".format(time_diff)
    assert not failed_logs, "Less than one hour time difference in some logs: {}".format(failed_logs)


def get_cli_timestamps(ceil_id, vol_id, img_id, net_id, vm_id):
    ceil_timestamp = ceilometer_helper.get_events(event_type='router.create.end', header='generated',
                                                  message_id=ceil_id)[0]

    table_ = table_parser.table(cli.cinder("show {}".format(vol_id), auth_info=Tenant.get('admin')))
    cinder_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    table_ = table_parser.table(cli.glance("image-show {}".format(img_id)))
    glance_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    table_ = table_parser.table(cli.neutron("net-show {}".format(net_id)))
    neutron_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    table_ = table_parser.table(cli.nova("show {}".format(vm_id)))
    nova_timestamp = table_parser.get_value_two_col_table(table_, 'created')

    table_ = table_parser.table(cli.system('show'))
    sysinv_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    return ceil_timestamp, cinder_timestamp, glance_timestamp, nova_timestamp, neutron_timestamp, sysinv_timestamp


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
    services = ('ceilometer', 'glance', 'cinder', 'nova', 'neutron', 'sysinv')

    prev_timezone = system_helper.get_timezone()
    post_timezone = __select_diff_timezone(current_zone=prev_timezone)

    # CHECK PRE TIMEZONE CHANGE CLI TIMESTAMPS
    LOG.tc_step("Getting CLI timestamps before timezone change for: {}".format(services))
    ceil_id = ceilometer_helper.get_events(event_type='router.create.end', limit=1)[0]
    img_id = glance_helper.get_images()[0]
    vol_id = cinder_helper.create_volume('timezone_test', cleanup='function')[1]
    vm_id = vm_helper.boot_vm(name='timezone_test', source='volume', source_id=vol_id, cleanup='function')[1]
    net_id = network_helper.get_mgmt_net_id()

    prev_timestamps = get_cli_timestamps(ceil_id, vol_id=vol_id, img_id=img_id, vm_id=vm_id, net_id=net_id)
    LOG.tc_step("Modify timezone from {} to {}".format(prev_timezone, post_timezone))
    system_helper.modify_timezone(post_timezone)

    # CHECK POST TIMEZONE CHANGE CLI TIMESTAMPS
    LOG.tc_step("Getting CLI timestamps after timezone change for: {}".format(services))
    post_timestamps = get_cli_timestamps(ceil_id, vol_id=vol_id, img_id=img_id, vm_id=vm_id, net_id=net_id)

    LOG.tc_step("Comparing timestamps from before and after timezone change for: {}".format(services))
    failed_services = []
    for i in range(len(services)):
        if prev_timestamps[i] != post_timestamps[i]:
            failed_services.append(services[i])

    assert not failed_services, "{} timestamp did not update after timezone modify".format(failed_services)
