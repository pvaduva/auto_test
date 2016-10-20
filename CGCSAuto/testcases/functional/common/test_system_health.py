import time
from pytest import mark, fixture

from utils.tis_log import LOG
from keywords import host_helper, system_helper


class TestCoreDumpsAndCrashes:
    @fixture(scope='class')
    def post_coredumps_and_crash_reports(self):
        LOG.fixture_step("Gather core dumps and crash reports info for all hosts")
        return host_helper.get_coredumps_and_crashreports()

    @mark.abslast
    @mark.sanity
    @mark.cpe_snaity
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

    # @mark.abslast
    # @mark.sanity
    # @mark.cpe_snaity
    # @mark.parametrize('report_type', [
    #     'core_dumps',
    #     'crash_reports',
    # ])
    # def test_system_coredumps_and_crash_reports(self, report_type, pre_coredumps_and_crash_reports_session,
    #                                             post_coredumps_and_crash_reports):
    #
    #     LOG.tc_step("Compare post test {} with pre test record".format(report_type))
    #     new_files = {}
    #     for host in post_coredumps_and_crash_reports:
    #         post_coredumps, post_crash_reports = post_coredumps_and_crash_reports[host]
    #         if not post_coredumps and not post_crash_reports:
    #             LOG.debug("No core dumps or crash_reports found for {}".format(host))
    #             continue
    #
    #         if host not in pre_coredumps_and_crash_reports_session:
    #             LOG.warning("No pre session cores dumps and crash_reports info for {}".format(host))
    #
    #             if report_type == 'core_dumps' and post_coredumps:
    #                 new_files[host] = post_coredumps
    #             elif report_type == 'crash_reports' and post_crash_reports:
    #                 new_files[host] = post_crash_reports
    #
    #         else:
    #             pre_coredumps, pre_crash_reports = pre_coredumps_and_crash_reports_session[host]
    #             if report_type == 'core_dumps':
    #                 new_coredumps = list(set(post_coredumps) - set(pre_coredumps))
    #                 if new_coredumps:
    #                     new_files[host] = new_coredumps
    #
    #             else:
    #                 new_crash_reports = list(set(post_crash_reports) - set(pre_crash_reports))
    #                 if new_crash_reports:
    #                     new_files[host] = new_crash_reports
    #
    #     assert not new_files, "New {} found: {}".format(report_type, new_files)


@mark.abslast
@mark.sanity
@mark.cpe_sanity
def test_system_alarms(pre_alarms_session):
    LOG.tc_step("Gathering system alarms at the end of test session")
    post_alarms = system_helper.get_alarms()

    new_alarms = []
    for alarm in post_alarms:
        if alarm not in pre_alarms_session:
            new_alarms.append(alarm)

    if new_alarms:
        LOG.tc_step("New alarm(s) found. Waiting for new alarms to clear.")
        end_time = time.time() + 300
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