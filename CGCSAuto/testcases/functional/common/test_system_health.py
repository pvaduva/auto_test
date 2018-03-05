from pytest import mark, fixture

from utils.tis_log import LOG
from keywords import host_helper, check_helper


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
    check_helper.check_alarms(before_alarms=pre_alarms_session)
    LOG.info("No new alarms found after test session.")
