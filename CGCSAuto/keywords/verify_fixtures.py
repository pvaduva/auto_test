from pytest import fixture

from consts.auth import Tenant
from utils import table_parser
from utils.tis_log import LOG
from keywords import system_helper, vm_helper


########################
# Test Fixtures Module #
########################


@fixture()
def check_alarms(request):
    """
    Check system alarms before the after test run.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    LOG.info("Gathering system alarms info before test begins.")
    before_tab = system_helper.get_alarms()
    before_rows = table_parser.get_all_rows(before_tab)

    def verify_alarms():
        LOG.debug("Verifying system alarms after test ended...")
        after_tab = system_helper.get_alarms()
        after_rows = table_parser.get_all_rows(after_tab)
        new_alarms = []
        for item in after_rows:
            if item not in before_rows:
                new_alarms.append(item)
        assert not new_alarms, "New alarm(s) found: {}".format(new_alarms)
        LOG.info("System alarms verified.")
    request.addfinalizer(verify_alarms)
    return


@fixture()
def check_hosts(request):
    LOG.debug("Gathering systems hosts status before test begins.")
    raise NotImplementedError


@fixture()
def check_vms(request):
    raise NotImplementedError
