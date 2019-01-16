from pytest import fixture
from utils.tis_log import LOG
from keywords import network_helper, vm_helper


def test_qos_update(setup_qos):
    """
    Tests network QoS update
    Test Setup:
    - create a qos policy
    - get mgmt net id
    - get internal net id
    - record the original qos values for above two networks
    - return qos, mgmt_net, internal_net

    Test Steps:
    -update networks with created qos
    -test ping over networks

    Test teardown:
    - restore the qos settings for both networks
    - delete the qos created by fixture
    """

    internal_net_id, mgmt_net_id, qos_new = setup_qos
    LOG.tc_step("Booting first vm.")
    nics = [{'net-id': mgmt_net_id},
            {'net-id': internal_net_id}]

    vm1 = vm_helper.boot_vm(name='vm1', nics=nics, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm1)

    LOG.tc_step("Updating mgmt and internal networks to created QoS.")
    network_helper.update_net_qos(net_id=mgmt_net_id, qos_id=qos_new)
    network_helper.update_net_qos(net_id=internal_net_id, qos_id=qos_new)

    LOG.tc_step("Booting second vm.")
    vm2 = vm_helper.boot_vm(name='vm2', nics=nics, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm2)

    LOG.tc_step("Pinging vm1 from natbox after updating QoS.")
    vm_helper.wait_for_vm_pingable_from_natbox(vm1)
    
    LOG.tc_step("Testing ping between vms.")
    vm_helper.ping_vms_from_vm(to_vms=vm2, from_vm=vm1, net_types=['internal', 'mgmt'])
    vm_helper.ping_vms_from_vm(to_vms=vm1, from_vm=vm2, net_types=['internal', 'mgmt'])


@fixture()
def setup_qos(request):

    LOG.fixture_step("Creating new QoS")
    scheduler = {'weight': 100}
    qos_new = network_helper.create_qos(scheduler=scheduler, description="Test QoS")[1]
    LOG.fixture_step("Retrieving network ids and Qos'")
    internal_net_id = network_helper.get_internal_net_id()
    mgmt_net_id = network_helper.get_mgmt_net_id()
    qos_internal = network_helper.get_net_info(net_id=internal_net_id, field='wrs-tm:qos')
    qos_mgmt = network_helper.get_net_info(net_id=mgmt_net_id, field='wrs-tm:qos')

    def reset():
        LOG.fixture_step("Resetting QoS for tenant and internal networks")

        network_helper.update_net_qos(net_id=internal_net_id, qos_id=qos_internal)
        network_helper.update_net_qos(net_id=mgmt_net_id, qos_id=qos_mgmt)

        LOG.fixture_step("Deleting created QoS")
        network_helper.delete_qos(qos_new)

    request.addfinalizer(reset)
    return internal_net_id, mgmt_net_id, qos_new
