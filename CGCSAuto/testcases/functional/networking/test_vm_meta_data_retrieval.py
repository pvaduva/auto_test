from pytest import mark, fixture
from utils.tis_log import LOG
from keywords import vm_helper, network_helper
from consts.cgcs import METADATA_SERVER
from consts.auth import Tenant
import time


@mark.sanity
def test_vm_meta_data_retrieval():
    """
    VM meta-data retrieval

    Test Steps:
        - Launch a boot-from-image vm
        - Retrieve vm meta_data within vm from metadata server
        - Ensure vm uuid from metadata server is the same as nova show

    Test Teardown:
        - Delete created vm and flavor
    """
    LOG.tc_step("Launch a boot-from-image vm")
    vm_id = vm_helper.boot_vm(source='image', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    LOG.tc_step('Retrieve vm meta_data within vm from metadata server')
    # retrieve meta instance id by ssh to VM from natbox and wget to remote server
    _access_metadata_server_from_vm(vm_id=vm_id)


@fixture()
def _router_info(request):

    LOG.fixture_step("Get router info.")
    router_id = network_helper.get_tenant_router()
    LOG.info("Router id: {}".format(router_id))
    router_name = network_helper.get_router_info(router_id=router_id, field='name')
    LOG.info("Router name: {}".format(router_name))
    gateway_ip = network_helper.get_router_ext_gateway_subnet_ip_address(router_id=router_id)
    LOG.info("Gateway IP used for router {} is {}".format(router_name, gateway_ip))
    ext_gateway_info = network_helper.get_router_ext_gateway_info(router_id=router_id)
    LOG.info("Gateway IP used for router {} is {}".format(router_name, ext_gateway_info))
    router_subnets = network_helper.get_router_subnets(router_id=router_id, mgmt_only=True)
    LOG.info("Router {} subnet ids {}".format(router_name, router_subnets))
    ext_gateway_subnet = network_helper.get_router_ext_gateway_subnet(router_id)
    LOG.info("Router {} external subnet id {}".format(router_name, ext_gateway_subnet))
    is_dvr = eval(network_helper.get_router_info(router_id, field='distributed', auth_info=Tenant.ADMIN))
    LOG.info("Router {} dvr enabled {}".format(router_name, is_dvr))

    def recover():
        LOG.fixture_step("Ensure tenant router exists")
        router_id = network_helper.get_tenant_router()
        if not router_id:
            LOG.fixture_step("Router not exist, create new router {}".format(router_name))
            router_id = network_helper.create_router(name=router_name)[1]

        LOG.fixture_step("Ensure tenant router gateway recovered")
        teardown_gateway_info = network_helper.get_router_ext_gateway_info(router_id=router_id)
        if teardown_gateway_info != ext_gateway_info:
            LOG.fixture_step("Set tenant router gateway info")
            _set_external_gatewayway_info(router_id, ext_gateway_subnet, gateway_ip, is_dvr)

        LOG.fixture_step("Ensure all interfaces added to router {}".format(router_id))
        teardown_subnets = network_helper.get_router_subnets(router_id=router_id, mgmt_only=True)
        LOG.info("Subnets attached to Interface during teardown: {}".format(teardown_subnets))
        check_sorted_subnet_teardown = set(sorted(teardown_subnets))
        check_sorted_subnet_start = set(sorted(router_subnets))
        LOG.info("Subnets attached during teardown sorted: {}".format(check_sorted_subnet_teardown))
        LOG.info("Subnets attached before starting the test sorted: {}".format(check_sorted_subnet_start))
        subnets_to_add = list(set(sorted(router_subnets)) - set(sorted(teardown_subnets)))
        LOG.info("Subnets to add: {}".format(subnets_to_add))
        if subnets_to_add:
            LOG.fixture_step("Add interfaces to router {}".format(router_id))
            _add_router_interfaces(router_id, subnets_to_add, ext_gateway_subnet)
    request.addfinalizer(recover)

    return router_id, router_name, gateway_ip, ext_gateway_info, router_subnets, ext_gateway_subnet, is_dvr


def test_vm_meta_data_access_after_delete_add_interfaces_router(_router_info):
    """
    VM meta-data retrieval

    Test Steps:
        - Launch a boot-from-image vm
        - Retrieve vm meta_data within vm from metadata server
        - Ensure vm uuid from metadata server is the same as nova show
        - Delete all Router Interfaces
        - Re-add Router Interfaces
        - Verify metadata access works
        - Delete Router
        - Create Router and Add Interfaces
        - Verify metadata access works

    Test Teardown:
        - Ensure Router exist
        - Verify the external gateway info matches
        - Ensure all interfaces exist
        - Delete created vm and flavor
    """
    router_id, router_name, gateway_ip, ext_gateway_info, router_subnets, ext_gateway_subnet, is_dvr = _router_info
    vms = []
    LOG.tc_step("Launch a boot-from-image vm")
    vm_id = vm_helper.boot_vm(source='image', cleanup='function')[1]
    vms.append(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    LOG.tc_step('Retrieve vm meta_data within vm from metadata server before Interface delete')
    _access_metadata_server_from_vm(vm_id=vm_id)

    LOG.tc_step('Delete Router Interfaces')
    _delete_router_interfaces(router_id, router_subnets, ext_gateway_subnet)
    LOG.tc_step('Re-add Router Interfaces')
    _add_router_interfaces(router_id, router_subnets, ext_gateway_subnet)

    LOG.tc_step('Retrieve vm meta_data within vm from metadata server after delete/add Router Interfaces')
    _access_metadata_server_from_vm(vm_id=vm_id)

    LOG.tc_step('Delete Router')
    network_helper.delete_router(router_id=router_id)

    LOG.tc_step('Create Router')
    router_id = network_helper.create_router(name=router_name)[1]

    LOG.tc_step('Set external gateway info for router {}'.format(router_id))
    _set_external_gatewayway_info(router_id, ext_gateway_subnet, gateway_ip, is_dvr)

    LOG.tc_step('Re-add Router Interfaces')
    _add_router_interfaces(router_id, router_subnets, ext_gateway_subnet)

    LOG.tc_step('Retrieve vm meta_data within vm from metadata server after delete/create Router')
    _access_metadata_server_from_vm(vm_id=vm_id)


def _access_metadata_server_from_vm(vm_id):

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        command = 'wget http://{}/openstack/latest/meta_data.json'.format(METADATA_SERVER)
        vm_ssh.exec_cmd(command, fail_ok=False)
        metadata = vm_ssh.exec_cmd('more meta_data.json', fail_ok=False)[1]

    LOG.tc_step("Ensure vm uuid from metadata server is the same as nova show")
    metadata = metadata.replace('\n', '')
    LOG.info(metadata)
    metadata_uuid = eval(metadata)['uuid']

    assert vm_id == metadata_uuid, "VM UUID retrieved from metadata server is not the same as nova show"


def _add_router_interfaces(router_id, router_subnets, ext_gateway_subnet):
    for subnet in router_subnets:
        if subnet != ext_gateway_subnet:
            network_helper.add_router_interface(router_id, subnet=subnet)


def _delete_router_interfaces(router_id, router_subnets, ext_gateway_subnet):
    for subnet in router_subnets:
        if subnet != ext_gateway_subnet:
            network_helper.delete_router_interface(router_id, subnet=subnet)


def _set_external_gatewayway_info(router_id, ext_gateway_subnet, gateway_ip, is_dvr):

    LOG.info("External Gateway Subnet Id: {}".format(ext_gateway_subnet))
    LOG.info("Router {} external subnet id {}".format(router_id, ext_gateway_subnet))
    network_helper.set_router_gateway(router_id=router_id, clear_first=False, fixed_ip=gateway_ip, enable_snat=False)
    network_helper.update_router_distributed(router_id=router_id, distributed=is_dvr)
