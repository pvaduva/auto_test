from keywords import system_helper
from utils.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG

#pv0 = SSHClient('128.224.150.73')
#ControllerClient.set_active_controller(pv0)
#pv0.connect()
#r720 = SSHClient('128.224.150.141')
#r720.connect()
#r730_3_7 = SSHClient('128.224.150.142')
#r730_3_7.connect()


def test_get_info():
    pv0_storage_nodes = system_helper.get_storage_nodes(pv0)
    assert 'storage-0' in pv0_storage_nodes and 'storage-1' in pv0_storage_nodes
    assert not system_helper.get_storage_nodes(r720)
    assert not system_helper.is_small_footprint()
    LOG.tc_func_start()
    assert system_helper.is_small_footprint(r720)
    LOG.tc_func_end()
    LOG.tc_func_start()
    assert not system_helper.is_small_footprint(r730_3_7)
    LOG.tc_func_end()
    LOG.tc_func_start()
    assert not system_helper.get_storage_nodes(r730_3_7)
    LOG.tc_func_end()

if __name__ == '__main__':
    test_get_info()
