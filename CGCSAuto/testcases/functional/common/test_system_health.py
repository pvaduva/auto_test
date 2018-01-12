import time
from pytest import mark, fixture

from utils.tis_log import LOG
from consts.cgcs import EventLogID
from keywords import host_helper, system_helper, network_helper


# Do not check alarms for test in this module, which are read only tests.
@fixture()
def check_alarms():
    pass


class TestCoreDumpsAndCrashes:
    @fixture(scope='class')
    def post_coredumps_and_crash_reports(self):
        LOG.fixture_step("Gather core dumps and crash reports info for all hosts")
        return host_helper.get_coredumps_and_crashreports()

    @mark.abslast
    @mark.sanity
    @mark.cpe_sanity
    @mark.sx_sanity
    @mark.parametrize('report_type', [
        'core_dumps',
        'crash_reports',
    ])
    def test_system_coredumps_and_crashes(self, report_type, post_coredumps_and_crash_reports):

        LOG.tc_step("Check {} does not exist on any host".format(report_type))
        existing_files = {}
        for host in post_coredumps_and_crash_reports:
            core_dumps, crash_reports = post_coredumps_and_crash_reports[host]

            if eval(report_type):
                existing_files[host] = core_dumps

        assert not existing_files, "{} exist on {}. Details: \n{}".format(report_type, existing_files.keys(),
                                                                          existing_files)


@mark.abslast
@mark.sanity
@mark.cpe_sanity
@mark.sx_sanity
def test_system_alarms(pre_alarms_session):
    LOG.tc_step("Gathering system alarms at the end of test session")
    post_alarms = system_helper.get_alarms()

    new_alarms = []
    for alarm in post_alarms:
        if alarm not in pre_alarms_session:
            alarm_id, entity_id = alarm.split('::::')
            if alarm_id == EventLogID.PROVIDER_NETWORK_FAILURE:
                # Providernet connectivity alarm handling
                LOG.fixture_step("Providernet connectivity alarm found, schedule providernet connectivity test")
                network_helper.schedule_providernet_connectivity_test()
            elif alarm_id == EventLogID.NTP_ALARM:
                # NTP alarm handling
                LOG.fixture_step("NTP alarm found, checking ntpq stats")
                host = entity_id.split('host=')[1].split('.ntp')[0]
                host_helper.wait_for_ntp_sync(host=host, fail_ok=False)
                continue

            new_alarms.append(alarm)

    if new_alarms:
        LOG.tc_step("New alarm(s) found. Waiting for new alarms to clear.")

        # Set max wait time to 10 minutes to wait for NTP alarm clear if any.
        end_time = time.time() + 600
        while time.time() < end_time:
            current_alarms = system_helper.get_alarms()
            alarms_to_check = list(current_alarms)
            for alarm in current_alarms:
                if alarm in pre_alarms_session:
                    alarms_to_check.remove(alarm)

            if not alarms_to_check:
                LOG.info("New alarms are cleared.")
                return

        assert False, "New alarms found and not cleared within timeout: {}".format(alarms_to_check)

    LOG.info("No new alarms found after test session.")
