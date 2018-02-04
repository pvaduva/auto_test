import time
import random

from keywords import host_helper, system_helper, mtc_helper, cinder_helper, glance_helper, vm_helper
from utils import table_parser, cli
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import EventLogID
from testfixtures.fixture_resources import ResourceCleanup
from pytest import fixture


timezones = [
    "Asia/Hong_Kong",
    "America/Los_Angeles",
    "Canada/Eastern",
    "Canada/Central",
    "Europe/London",
    "Europe/Berlin",
    "UTC"
]


@fixture(scope='module')
def get_out_of_date_alarms():
    out_of_date_alarms = []
    hosts = host_helper.get_hosts()
    for host in hosts:
        out_of_date_alarms.append((EventLogID.CONFIG_OUT_OF_DATE, 'host={}'.format(host)))
    return out_of_date_alarms


@fixture(scope='module', autouse=True)
def revert_timezone(request, get_out_of_date_alarms):
    def _revert():
        LOG.fixture_step("Reverting timezone to UTC")
        cli.system('modify', '--timezone=UTC')
        system_helper.wait_for_alarms_gone(get_out_of_date_alarms)

    request.addfinalizer(_revert)


def get_timezone():
    table_ = table_parser.table(cli.system("show"))
    return table_parser.get_value_two_col_table(table_, "timezone")


def modify_timezone(timezone, wait_for_change=True, timeout=60):
    """
    Modify the system timezone

    Args:
        timezone:                  Change zone to timezone
        wait_for_change:           Check that the timezone changes within timeout
        timeout:                   Time to wait for timezone change

    Returns:
        True/False
    """
    LOG.info("Setting timezone to {}".format(timezone))
    cli.system("modify", "--timezone={}".format(timezone))

    if wait_for_change:
        timeout = time.time() + timeout
        while time.time() < timeout:
            if get_timezone() == timezone:
                return True
        return False
    else:
        return True


def test_modify_timezone_alarm_timestamps(get_out_of_date_alarms):
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
    LOG.tc_step("Gathering pre-modify timezone data")
    table_ = system_helper.get_events_table(num=1, uuid=True)
    event_uuid = table_parser.get_column(table_, 'UUID')
    pre_timestamp = table_parser.get_column(table_, 'Time Stamp')
    post_timestamp = ''

    current_timezone = get_timezone()
    LOG.info("Current timezone: {}".format(current_timezone))

    # Pick a random timezone to test that is not the current timezone
    test_timezone = random.choice(timezones)
    while current_timezone == test_timezone:
        test_timezone = random.choice(timezones)

    LOG.tc_step("Modify timezone to {}".format(test_timezone))
    assert modify_timezone(test_timezone), "Timezone failed to change within timeout"
    out_of_date_alarms = get_out_of_date_alarms
    system_helper.wait_for_alarms_gone(out_of_date_alarms)

    LOG.tc_step("Waiting for timezone change to effect events/alarms")
    timeout = time.time() + 30
    while time.time() < timeout:
        table_ = mtc_helper.search_event(**{"UUID": event_uuid})
        post_timestamp = table_parser.get_column(table_, 'Time Stamp')
        if pre_timestamp != post_timestamp:
            break

    LOG.tc_step("Checking timezone change effected timestamp")
    assert pre_timestamp != post_timestamp, "Timestamp did not change with timezone change."


def get_epoch_date(active_controller):
    with host_helper.ssh_to_host(active_controller) as con_ssh:
        output = con_ssh.exec_cmd('date', rm_date=False)[1]
        output = output.splitlines()[0]
        output = output.split()
        output.pop(4)
        output = ' '.join(output)
        pattern = '%a %b %d %H:%M:%S %Y'
        system_epoch = int(time.mktime(time.strptime(output, pattern)))
        LOG.info("System epoch: {}".format(system_epoch))
        return system_epoch


def test_modify_timezone_log_timestamps(get_out_of_date_alarms):
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
    logs = ['auth.log', 'daemon.log', 'fm-event.log', 'fsmond.log', 'io-monitor.log', 'kern.log', 'openstack.log',
            'pmond.log', 'sm-scheduler.log', 'user.log']
    out_of_date_alarms = get_out_of_date_alarms
    active_controller = system_helper.get_active_controller_name()

    LOG.info("Get timezones for testing")
    first_timezone = get_timezone()
    second_timezone = random.choice(timezones)
    while first_timezone == second_timezone:
        second_timezone = random.choice(timezones)
    LOG.info("Original timezone was {}".format(first_timezone))
    LOG.info("Timezone used for testing is {}".format(second_timezone))

    LOG.tc_step("Ensure the system date is changed when the timezone is changed.")
    pre_system_epoch = get_epoch_date(active_controller)

    if modify_timezone(second_timezone):
        # Saving the last entry from the logs; If it is the same later, there is no new entry in the log.
        LOG.info("Saving the last entry from all logs.")
        pre_timezone_change_timestamps = {}
        time.sleep(5)
        with host_helper.ssh_to_host(active_controller) as con_ssh:
            for log in logs:
                last_line = con_ssh.exec_cmd('tail -n 1 /var/log/{}'.format(log))[1]
                date_time = last_line.replace("T", " ", 1).split()
                date_time = date_time[0] + " " + date_time[1].split(".")[0]
                pattern = '%Y-%m-%d %H:%M:%S'
                log_epoch = int(time.mktime(time.strptime(date_time, pattern)))
                pre_timezone_change_timestamps[log] = log_epoch
        system_helper.wait_for_alarms_gone(out_of_date_alarms)
    else:
        assert 0, "Modify timezone cli failed"

    post_system_epoch = get_epoch_date(active_controller)
    time_diff = abs(pre_system_epoch - post_system_epoch)
    LOG.info("Time difference between {} and {} is {}".format(first_timezone, second_timezone, time_diff))

    assert time_diff > 600, "Timezone change did not effect the date or the two timezones were only a 10 minute " \
                            "difference"

    LOG.info("Wait up to 3 minutes for logs to update")
    logs_to_test = {}
    timeout = time.time() + 180
    with host_helper.ssh_to_host(active_controller) as con_ssh:
        while time.time() < timeout:
            for key, value in pre_timezone_change_timestamps.items():
                last_line = con_ssh.exec_cmd('tail -n 1 /var/log/{}'.format(key))[1]
                # If last line does not exist in last_log_entries; New line is in the log; Add log to
                # logs_to_test
                date_time = last_line.replace("T", " ", 1).split()
                date_time = date_time[0] + " " + date_time[1].split(".")[0]
                pattern = '%Y-%m-%d %H:%M:%S'
                new_log_epoch = int(time.mktime(time.strptime(date_time, pattern)))

                epoch_diff = abs(new_log_epoch - pre_timezone_change_timestamps[key])

                if epoch_diff > 600:
                    LOG.info("{} has new timestamps. Adding to logs_to_test.".format(key))
                    logs_to_test[key] = new_log_epoch
                    del pre_timezone_change_timestamps[key]
                    break
            # If last_log_entries is empty, break from checking logs as there is none left to check
            if len(pre_timezone_change_timestamps) == 0:
                break
        time.sleep(5)

    # Get latest log entries, convert to epoch
    LOG.tc_step("Verifying timezone effects new log entries")
    failed_logs = {}
    for key, value in logs_to_test.items():
        time_diff = abs(value - post_system_epoch)
        LOG.info("log: {} time diff: {}".format(key, time_diff))
        if time_diff > 600:
            failed_logs[key] = "time_diff: {}".format(time_diff)
    assert failed_logs == {}, failed_logs


def test_timezone_persists_after_swact(get_out_of_date_alarms):
    """
    Test setting the timezone persists after controller swact

    Prerequisites
        - N/A
    Test Setups
        - Get a random timezone for testing
    Test Steps
        - Modify timezone
        - Wait for out_of_date alarms to clear
        - Swact active controller
        - Verify the timezone persists after swact
    Test Teardown
        - N/A
    """
    out_of_date_alarms = get_out_of_date_alarms

    LOG.info("Get timezone for testing")
    current_timezone = get_timezone()
    new_timezone = random.choice(timezones)
    while current_timezone == new_timezone:
        new_timezone = random.choice(timezones)

    # MODIFY TIMEZONE
    LOG.tc_step("Modify timezone to {}".format(new_timezone))
    if modify_timezone(new_timezone):
        LOG.info("Waiting for config_out_of_date alarms to clear")
        system_helper.wait_for_alarms_gone(out_of_date_alarms)
    else:
        assert 0, "Modify timezone cli failed"

    host_helper.swact_host(system_helper.get_active_controller_name())

    assert get_timezone() == new_timezone


@fixture(scope='function')
def cli_timestamp_teardown(request):
    def delete_snmp_trapdest():
        cli.system("snmp-trapdest-delete 128.224.150.21")

    request.addfinalizer(delete_snmp_trapdest)


def test_modify_timezone_cli_timestamps(cli_timestamp_teardown, get_out_of_date_alarms):
    """
    Test correct timestamps in:
        - ceilometer
        - cinder
        - glance
        - neutron
        - nova
        - snmp

    Prerequisites
        - N/A
    Test Setups
        - Get a random timezone for testing
        - Create cinder volume
        - Boot a vm
        - Create snmp-trapdest
    Test Steps
        - Save the pre-timezone-change timestamps from each cli domain
        - Modify the timezone
        - Wait for out_of_date alarms to clear
        - Save the post-timezone-change timestamps from each cli domain
        - Verify the timestamps have changed to be in line with the timezone change
    Test Teardown
        - Deleted cinder volume
        - Delete the vm
        - Delete snmp-trapdest
    """
    failed_tests = []
    out_of_date_alarms = get_out_of_date_alarms

    LOG.info("Get timezones for testing")
    first_timezone = get_timezone()
    second_timezone = random.choice(timezones)
    while first_timezone == second_timezone:
        second_timezone = random.choice(timezones)
    LOG.info("Original timezone was {}".format(first_timezone))
    LOG.info("Timezone used for testing is {}".format(second_timezone))

    # CHECK PRE TIMEZONE CHANGE CLI TIMESTAMPS
    LOG.tc_step("Getting timestamps before timezone change")

    LOG.info("Getting ceilometer timestamp")
    table_ = table_parser.table(cli.ceilometer("event-list", "--limit 1", auth_info=Tenant.ADMIN))
    ceilometer_event_id = table_parser.get_column(table_, 'Message ID')[0]
    ceilometer_pre_timestamp = table_parser.get_column(table_, 'Generated')[0]

    LOG.info("Getting cinder timestamp")
    cinder_volume_id = cinder_helper.create_volume(auth_info=Tenant.ADMIN)[1]
    ResourceCleanup.add('volume', cinder_volume_id)
    table_ = table_parser.table(cli.cinder("show {}".format(cinder_volume_id), auth_info=Tenant.ADMIN))
    cinder_pre_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    LOG.info("Getting glance timestamp")
    glance_image_id = glance_helper.get_images()[0]
    table_ = table_parser.table(cli.glance("image-show {}".format(glance_image_id)))
    glance_pre_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    LOG.info("Getting neutron timestamp")
    table_ = table_parser.table(cli.neutron("net-list"))
    neutron_net_id = table_parser.get_column(table_, 'id')[0]
    table_ = table_parser.table(cli.neutron("net-show {}".format(neutron_net_id)))
    neutron_pre_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    LOG.info("Getting nova timestamp")
    nova_vm_id = vm_helper.boot_vm(name='test', source='image', cleanup='function')[1]
    table_ = table_parser.table(cli.nova("show {}".format(nova_vm_id)))
    nova_pre_timestamp = table_parser.get_value_two_col_table(table_, 'created')

    LOG.info("Getting snmp timestamp")
    table_parser.table(cli.system("snmp-trapdest-add", "-i 128.224.150.21 -c public"))
    table_ = table_parser.table(cli.system("snmp-trapdest-show 128.224.150.21"))
    snmp_pre_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    # MODIFY TIMEZONE
    LOG.tc_step("Modify timezone to {}".format(second_timezone))
    if modify_timezone(second_timezone):
        LOG.info("Waiting for config_out_of_date alarms to clear")
        system_helper.wait_for_alarms_gone(out_of_date_alarms)
    else:
        assert 0, "Modify timezone cli failed"

    # CHECK POST TIMEZONE CHANGE CLI TIMESTAMPS
    LOG.tc_step("Getting timestamps after timezone change")

    LOG.info("Getting ceilometer timestamp")
    table_ = table_parser.table(cli.ceilometer("event-show {}".format(ceilometer_event_id), auth_info=Tenant.ADMIN))
    ceilometer_post_timestamp = table_parser.get_value_two_col_table(table_, 'generated')

    LOG.info("Getting cinder timestamp")
    table_ = table_parser.table(cli.cinder("show {}".format(cinder_volume_id), auth_info=Tenant.ADMIN))
    cinder_post_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    LOG.info("Getting glance timestamp")
    table_ = table_parser.table(cli.glance("image-show {}".format(glance_image_id)))
    glance_post_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    LOG.info("Getting neutron timestamp")
    table_ = table_parser.table(cli.neutron("net-show {}".format(neutron_net_id)))
    neutron_post_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    LOG.info("Getting nova timestamp")
    table_ = table_parser.table(cli.nova("show {}".format(nova_vm_id)))
    nova_post_timestamp = table_parser.get_value_two_col_table(table_, 'created')

    LOG.info("Getting snmp timestamp")
    table_ = table_parser.table(cli.system("snmp-trapdest-show 128.224.150.21"))
    snmp_post_timestamp = table_parser.get_value_two_col_table(table_, 'created_at')

    LOG.tc_step("Comparing timestamps from before and after timezone change")
    if ceilometer_pre_timestamp == ceilometer_post_timestamp:
        failed_tests.append("Ceilometer timestamps did not change")
    if cinder_pre_timestamp == cinder_post_timestamp:
        failed_tests.append("Cinder timestamps did not change")
    if glance_pre_timestamp == glance_post_timestamp:
        failed_tests.append("Glance timestamps did not change")
    if neutron_pre_timestamp == neutron_post_timestamp:
        failed_tests.append("Neutron timestamps did not change")
    if nova_pre_timestamp == nova_post_timestamp:
        failed_tests.append("Nova timestamps did not change")
    if snmp_pre_timestamp == snmp_post_timestamp:
        failed_tests.append("SNMP timestamps did not change")

    assert not failed_tests
