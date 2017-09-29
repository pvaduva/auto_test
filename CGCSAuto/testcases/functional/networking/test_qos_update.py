from pytest import fixture
from utils import cli
from utils.tis_log import LOG
from utils import table_parser
from consts.auth import Tenant
from keywords import network_helper


def test_qos_update(reset_qos):
    """
    Tests network QoS update

    Test Steps:
        -Update internal0-net0 QoS with the external-qos
        -Update tenant2-net0 QoS with the internal-qos
        -Update tenant1-mgmt-net QoS with the internal-qos

    Test teardown:
        -Reset updated networks with original qos
    """

    LOG.tc_step("Updating QoS for internal0-net0 to external-qos.")
    qos_external = network_helper.get_qos(name="external", auth_info=Tenant.ADMIN)
    network_internal = network_helper.get_internal_net_id()
    network_helper.update_qos(network_id=network_internal,qos_id=qos_external[0])

    assert qos_external[0] == network_helper.get_qos_from_network(network_internal)

    LOG.tc_step("Updating QoS for tenant2-net0 to internal-qos.")
    qos_internal = network_helper.get_qos(name="internal", auth_info=Tenant.ADMIN)
    network_tenant = network_helper.get_tenant_net_id(net_name="net0", auth_info=Tenant.TENANT2)
    network_helper.update_qos(network_id=network_tenant, qos_id=qos_internal[0])

    assert qos_internal[0] == network_helper.get_qos_from_network(network_tenant)

    LOG.tc_step("Updating QoS for tenant1-mgmt-net to internal-qos.")
    qos_tenant1_mgmt = network_helper.get_qos(name="tenant1", auth_info=Tenant.ADMIN)
    network_mgmt = network_helper.get_mgmt_net_id(auth_info=Tenant.TENANT1)
    network_helper.update_qos(network_id=network_mgmt, qos_id=qos_tenant1_mgmt[0])

    assert qos_tenant1_mgmt[0] == network_helper.get_qos_from_network(network_mgmt)


@fixture()
def reset_qos(request):
    def reset():
        LOG.fixture_step("Resetting QoS")

        qos = network_helper.get_qos(name="internal", auth_info=Tenant.ADMIN)
        network = network_helper.get_internal_net_id()
        network_helper.update_qos(qos_id=qos[0], network_id=network)

        network = network_helper.get_tenant_net_id(net_name="net0", auth_info=Tenant.TENANT2)
        network_helper.update_qos(network_id=network)

        qos = network_helper.get_qos(name="tenant1-mgmt", auth_info=Tenant.ADMIN)
        network = network_helper.get_mgmt_net_id(auth_info=Tenant.TENANT1)
        network_helper.update_qos(qos_id=qos[0], network_id=network)

    request.addfinalizer(reset)
