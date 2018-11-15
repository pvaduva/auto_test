from pytest import fixture, skip, mark

from consts.proj_vars import ProjVar


@fixture(scope='module', autouse=True)
def dc_only():
    if not ProjVar.get_var('IS_DC'):
        skip('Skip Distributed Cloud test cases for non-DC system.')
