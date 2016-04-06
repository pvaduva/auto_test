from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper
from setup_consts import P1, P2, P3

_skip = True

@mark.skipif(_skip, reason='test skip if')
@mark.usefixtures('check_alarms')
@mark.parametrize(('param1', 'param2', 'param3'), [
    P1('val1', 1, True),
    P2('val2', 2, False),
    P2('val2', 2, True),
])
def test_dummy1(param1, param2, param3):
    LOG.tc_step("test dummy 1 step~~ \nparam1: {}, param2:{}".format(param1, param2))
    res = nova_helper.get_all_vms()
    if not param3:
        skip("param3 is : {}".format(param3))
    LOG.info("All VMs: {}".format(res))

    assert 1, 'dummy test failed ~~~~~~'

def test_dummy2():
    LOG.step("test dummy 2 step~~")
    pass