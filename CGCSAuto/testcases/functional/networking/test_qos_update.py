from pytest import fixture
from utils.tis_log import LOG
from keywords import network_helper, vm_helper


def _test_qos_update(reset_qos):
    """
    Tests network QoS update

    Test Steps:


    Test teardown:


    #for tenant net
    - update to remove qos (using keyword with verifications done inside the keyword)
    - update to add qos that was created by fixture (verification in keyword)

    # for internal net:
    - update qos to the one created by test fixture

    - launch two vms with above two networks
    - ping between vms over above two networks
    """

    network_internal, network_tenant, qos_new = reset_qos
    # TODO:Update with actual keyword
    LOG.tc_step("Updating internal network to new QoS")
    network_helper.update_qos(qos_new, network_internal)
    LOG.tc_step("Testing ping over networks")
    vm_helper.ping_vms_from_vm(to_vms='vm2', from_vm='vm1', net_types=['internal', 'data'])
    vm_helper.ping_vms_from_vm(to_vms=vm1, from_vm=vm2)

@fixture()
def reset_qos(request):
    """
    Setup
    - create a qos policy
    - get tenant net id
    - get internal net id
    - record the original qos values for above two networks
    - return qos, tenant_net, internal_net

    Teardown:
    - restore the qos settings for both networks
    - delete the qos created by fixture
    - delete the vms (existing fixture)

    """
    LOG.fixture_step("Creating new QoS")
    code, qos_new, output = network_helper.create_qos('test', 'test qos', scheduler='weight=4')

    network_internal = network_helper.get_internal_net_id()
    network_tenant = network_helper.get_tenant_net_id(net_name="net0")

    qos_internal = network_helper.get_net_info(net_id=network_internal, field='wrs-tm:qos')
    qos_tenant = network_helper.get_net_info(net_id=network_tenant, field='wrs-tm:qos')

    LOG.fixture_step("Creating new vms")


    def reset():
        LOG.fixture_step("Resetting QoS for tenant and internal networks")
        #TODO:Update with actual keyword
        network_helper.update_qos(qos_internal, network_internal)
        network_helper.update_qos(qos_id=qos_tenant, network_id=network_tenant)

        LOG.fixture_step("Deleting created QoS")
        network_helper.delete_qos(qos_new)

        LOG.fixture_step("Deleting vms")
        vm_helper.delete_vms(vms=[vm1[1], vm2[1]])

    request.addfinalizer(reset)
    return network_internal, network_tenant, qos_new


def test_create_qos(request):
    LOG.fixture_step("Creating QoS")
    exit_code, qos_id, output = network_helper.create_qos("test", description="Test QoS", scheduler="weight=4",
                                                          tenant_name='tenant1')
    assert exit_code == 0

    def delete_qos():
        LOG.fixture_step("Deleting created qos")
        code, output = network_helper.delete_qos(qos_id)
        assert code == 0
    delete_qos()
