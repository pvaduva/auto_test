from pytest import fixture, skip

from consts.proj_vars import ProjVar

# Import DC fixtures for testcases to use
from testfixtures.dc_fixtures import check_central_alarms_module, check_central_alarms


@fixture(scope='module', autouse=True)
def dc_only():
    if not ProjVar.get_var('IS_DC'):
        skip('Skip Distributed Cloud test cases for non-DC system.')
