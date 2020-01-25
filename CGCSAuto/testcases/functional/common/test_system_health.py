from pytest import mark, fixture

from utils.tis_log import LOG
from consts.stx import PLATFORM_APP, AppStatus
from keywords import host_helper, check_helper, container_helper


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
            failures = {'core_dumps': core_dumps, 'crash_reports': crash_reports}

            if failures[report_type]:
                existing_files[host] = failures[report_type]

        assert not existing_files, "{} exist on {}".format(report_type, list(existing_files.keys()))


@mark.abslast
@mark.sanity
@mark.cpe_sanity
@mark.sx_sanity
def test_system_alarms(pre_alarms_session):
    LOG.tc_step("Gathering system alarms at the end of test session")
    check_helper.check_alarms(before_alarms=pre_alarms_session)
    LOG.info("No new alarms found after test session.")


IGNOIRE_ALARMS = ["400.003::::host=controller-0::::minor",
                  "400.003::::host=controller-1::::minor"]


@mark.absfirst
@mark.platform_sanity
def test_system_health_pre_session():
    LOG.tc_step("Check {} status".format(PLATFORM_APP))
    assert container_helper.get_apps(application=PLATFORM_APP)[0] == AppStatus.APPLIED, \
        "{} is not {}".format(PLATFORM_APP, AppStatus.APPLIED)

    LOG.tc_step("Check system alarms")
    check_helper.check_alarms(before_alarms=IGNOIRE_ALARMS, timeout=60)
    LOG.info("No new alarms found.")
