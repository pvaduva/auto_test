from pytest import fixture
from utils.tis_log import LOG
from keywords import network_helper, vm_helper


def test_qos_update(setup_qos):
    """
    Tests network QoS update
    Test Setup:
    - create a qos policy
    - get tenant net id
    - get internal net id
    - record the original qos values for above two networks
    - return qos, tenant_net, internal_net

    Test Steps:
    -update networks with created qos
    -test ping over networks

    Test teardown:
    - restore the qos settings for both networks
    - delete the qos created by fixture
    - delete the vms (existing fixture)
    """

    internal_net, tenant_net, qos_new, vm1, vm2 = setup_qos
    LOG.tc_step("updating tenant network to created QoS")
    network_helper.update_net_qos(net_id=tenant_net, qos_id=qos_new)
    LOG.tc_step("Updating internal network to new QoS")
    network_helper.update_net_qos(net_id=internal_net, qos_id=qos_new)

    LOG.tc_step("Testing ping over networks")
    vm_helper.ping_vms_from_vm(to_vms=vm2, from_vm=vm1, net_types=['internal', 'data'])
    vm_helper.ping_vms_from_vm(to_vms=vm1, from_vm=vm2, net_types=['internal', 'data'])


@fixture()
def setup_qos(request):

    LOG.fixture_step("Creating new QoS")
    qos_args = {"scheduler": "weight=4"}
    qos_new = network_helper.create_qos('test', args_dict=qos_args)[1]

    LOG.fixture_step("Retrieving network ids and Qos'")
    internal_net = network_helper.get_internal_net_id()
    tenant_net = network_helper.get_tenant_net_id()
    qos_internal = network_helper.get_net_info(net_id=internal_net, field='wrs-tm:qos')
    qos_tenant = network_helper.get_net_info(net_id=tenant_net, field='wrs-tm:qos')
    mgmt_net_id = network_helper.get_mgmt_net_id()

    LOG.fixture_step("Creating new vms")
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net, 'vif-model': 'virtio'},
            {'net-id': tenant_net, 'vif-model': 'virtio'}]
    vm1 = vm_helper.boot_vm(name='vm1', nics=nics)[1]
    vm2 = vm_helper.boot_vm(name='vm2', nics=nics)[1]

    def reset():
        LOG.fixture_step("Resetting QoS for tenant and internal networks")

        network_helper.update_net_qos(net_id=internal_net, qos_id=qos_internal)
        network_helper.update_net_qos(net_id=tenant_net, qos_id=qos_tenant)

        LOG.fixture_step("Deleting created QoS")
        network_helper.delete_qos(qos_new)

        LOG.fixture_step("Deleting vms")
        vm_helper.delete_vms(vms=[vm1, vm2])

    request.addfinalizer(reset)
    return internal_net, tenant_net, qos_new, vm1, vm2
