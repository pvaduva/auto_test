from pytest import mark, fixture
from utils.tis_log import LOG
from keywords import vm_helper, network_helper
from consts.cgcs import METADATA_SERVER
from consts.auth import Tenant

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


def test_vm_meta_data_access_after_delete_add_interfaces_router():
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
        - Delete created vm and flavor
    """
    vms = []
    LOG.tc_step("Launch a boot-from-image vm")
    vm_id = vm_helper.boot_vm(source='image', cleanup='function')[1]
    vms.append(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    LOG.tc_step('Retrieve vm meta_data within vm from metadata server before Interface delete')
    _access_metadata_server_from_vm(vm_id=vm_id)

    LOG.tc_step('Retrieve Router Info')
    router_id, router_name, gateway_ip, ext_gateway_info, router_subnets, ext_gateway_subnet, is_dvr = _router_info(vm_id=vm_id)

    LOG.tc_step('Delete Router Interfaces')
    _delete_router_interfaces(router_id, router_subnets, ext_gateway_subnet)
    LOG.tc_step('Re-add Router Interfaces')
    _add_router_interfaces(router_id, router_subnets, ext_gateway_subnet)

    LOG.tc_step('Retrieve vm meta_data within vm from metadata server after delete/add Router Interfaces')
    _access_metadata_server_from_vm(vm_id=vm_id)

    LOG.tc_step('Delete Router')
    network_helper.delete_router(router_id=router_id)

    LOG.tc_step('Create Router')
    router_id = _create_router(ext_gateway_subnet, gateway_ip, is_dvr)

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


def _router_info(vm_id):

    LOG.fixture_step("Get router info.")
    #router_id = network_helper.get_tenant_router()
    router_id = network_helper.get_tenant_routers_for_vms(vms=vm_id)[0]
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
    return router_id, router_name, gateway_ip, ext_gateway_info, router_subnets, ext_gateway_subnet, is_dvr


def _add_router_interfaces(router_id, router_subnets, ext_gateway_subnet):
    for subnet in router_subnets:
        if subnet != ext_gateway_subnet:
            network_helper.add_router_interface(router_id, subnet=subnet)


def _delete_router_interfaces(router_id, router_subnets, ext_gateway_subnet):
    for subnet in router_subnets:
        if subnet != ext_gateway_subnet:
            network_helper.delete_router_interface(router_id, subnet=subnet)


def _create_router(ext_gateway_subnet, gateway_ip, is_dvr):
    router_id = network_helper.create_router()[1]
    LOG.info("Router Id: {}".format(router_id))

    LOG.info("External Gateway Subnet Id: {}".format(ext_gateway_subnet))
    LOG.info("Router {} external subnet id {}".format(router_id, ext_gateway_subnet))
    network_helper.set_router_gateway(router_id=router_id, clear_first=False, fixed_ip=gateway_ip, enable_snat=False)
    network_helper.update_router_distributed(router_id=router_id, distributed=is_dvr)

    return router_id