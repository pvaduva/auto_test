from pytest import fixture, mark, skip
from keywords import network_helper
from utils.tis_log import LOG
from keywords import nova_helper
from setup_consts import P1, P2, P3
from utils.ssh import ControllerClient
_skip = True


def test_create():
    LOG.tc_step("Test FIP CREATE")
    #con_ssh = ControllerClient.get_active_controller()
    retcode, msg = network_helper.floatingip_create(con_ssh=None, extnet_id = network_helper.get_ext_net_ids(con_ssh=None, auth_info=None)[0])
    floting_ip = network_helper.floatingip_list(con_ssh=None)
    print(floting_ip[0] )
    floting_ipid = network_helper.floatingip_list_id(con_ssh=None)
    print(floting_ipid[0])
    assert network_helper.floatingip_delete(con_ssh=None,floating_ip_id=floting_ipid[0]), "Test Float IP DELETE failure"

