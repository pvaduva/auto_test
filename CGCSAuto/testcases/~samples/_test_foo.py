from pytest import mark, skip

from keywords import nova_helper
from setup_consts import P1, P2
from utils.tis_log import LOG

_skip = True

# @mark.skipif(_skip, reason='test skip if')
# @mark.usefixtures('check_alarms')
@mark.parametrize(('param1', 'param2', 'param3'), [
    P1(('val1', 1, True)),
    P2(('val2', 2, False)),
    P2(('val2', 2, True)),
])
def test_dummy1(param1, param2, param3):
    LOG.tc_step("test dummy 1 step~~ \nparam1: {}, param2:{}".format(param1, param2))
    res = nova_helper.get_all_vms()
    if not param3:
        skip("param3 is : {}".format(param3))
    LOG.info("All VMs: {}".format(res))

    if param2 == 1:
        raise Exception("test failure with exception")

    assert 0, 'dummy test failed ~~~~~~'

@mark.usefixtures('check_alarms')
def test_dummy2():
    LOG.tc_step("test dummy 2 step~~")
    pass
