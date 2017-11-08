from copy import deepcopy

from pytest import fixture

from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient

from consts.auth import Tenant
from consts.heat import Heat
from keywords import nova_helper, vm_helper, cinder_helper, glance_helper, network_helper, heat_helper, \
    system_helper, host_helper
from testfixtures.fixture_resources import ResourceCleanup

# SIMPLEX_RECOVERED = False


@fixture(scope='function', autouse=True)
def delete_resources_func(request):
    """
    Function level fixture to delete created resources after each caller testcase.

    Notes: Auto used fixture - import it to a conftest.py file under a feature directory to auto use it on all children
        testcases.

    Examples:
        - see nova/conftest.py for importing
        - see ResourceCleanup.add function usages in nova/test_shared_cpu.py for adding resources to cleanups

    Args:
        request: pytest param present caller test function

    """
    def delete_():
        _delete(ResourceCleanup._get_resources('function'), scope='function')
        ResourceCleanup._reset('function')
    request.addfinalizer(delete_)


@fixture(scope='class', autouse=True)
def delete_resources_class(request):
    """
    Class level fixture to delete created resources after each caller testcase.

    Notes: Auto used fixture - import it to a conftest.py file under a feature directory to auto use it on all children
        testcases.

    Examples:
        - see nova/conftest.py for importing
        - see ResourceCleanup.add function usages in nova/test_shared_cpu.py for adding resources to cleanups

    Args:
        request: pytest param present caller test function

    """
    def delete_():
        _delete(ResourceCleanup._get_resources('class'), scope='class')
        ResourceCleanup._reset('class')
    request.addfinalizer(delete_)


@fixture(scope='module', autouse=True)
def delete_resources_module(request):
    """
    Module level fixture to delete created resources after each caller testcase.

    Notes: Auto used fixture - import it to a conftest.py file under a feature directory to auto use it on all children
        testcases.

    Examples:
        - see nova/conftest.py for importing
        - see ResourceCleanup.add function usages in nova/test_shared_cpu.py for adding resources to cleanups

    Args:
        request: pytest param present caller test function

    """
    def delete_():
        _delete(ResourceCleanup._get_resources('module'), scope='module')
        ResourceCleanup._reset('module')
    request.addfinalizer(delete_)


@fixture(scope='session', autouse=True)
def delete_resources_session(request):
    """
    Module level fixture to delete created resources after each caller testcase.

    Notes: Auto used fixture - import it to a conftest.py file under a feature directory to auto use it on all children
        testcases.

    Examples:
        - see nova/conftest.py for importing
        - see ResourceCleanup.add function usages in nova/test_shared_cpu.py for adding resources to cleanups

    Args:
        request: pytest param present caller test function

    """
    def delete_():
        _delete(ResourceCleanup._get_resources('session'), scope='session')
        ResourceCleanup._reset('session')
    request.addfinalizer(delete_)


@fixture(scope='module')
def flavor_id_module():
    """
    Create basic flavor and volume to be used by test cases as test setup, at the beginning of the test module.
    Delete the created flavor and volume as test teardown, at the end of the test module.
    """
    flavor = nova_helper.create_flavor()[1]
    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor


def _delete(resources, scope):
    # global SIMPLEX_RECOVERED
    # if not SIMPLEX_RECOVERED and system_helper.is_simplex():
    #     LOG.fixture_step('{} Ensure simplex host is up before cleaning up'.format(scope))
    #     host_helper.recover_simplex(fail_ok=True)
    #     SIMPLEX_RECOVERED = True

    vms_with_vols = resources['vms_with_vols']
    vms_no_vols = resources['vms_no_vols']
    volumes = resources['volumes']
    volume_types = resources['volume_types']
    qos_ids = resources['qos_ids']
    flavors = resources['flavors']
    images = resources['images']
    server_groups = resources['server_groups']
    routers = resources['routers']
    subnets = resources['subnets']
    floating_ips = resources['floating_ips']
    heat_stacks = resources['heat_stacks']
    ports = resources['ports']
    trunks = resources['trunks']
    networks = resources['networks']
    vol_snapshots = resources['vol_snapshots']
    aggregates = resources['aggregates']


    err_msgs = []
    if vms_with_vols:
        LOG.fixture_step(
            "({}) Attempt to delete following vms and attached volumes: {}".format(scope, vms_with_vols))
        code, msg = vm_helper.delete_vms(vms_with_vols, delete_volumes=True, fail_ok=True, auth_info=Tenant.ADMIN)
        if code not in [0, -1]:
            err_msgs.append(msg)

    if vms_no_vols:
        LOG.fixture_step("({}) Attempt to delete following vms: {}".format(scope, vms_no_vols))
        code, msg = vm_helper.delete_vms(vms_no_vols, delete_volumes=False, fail_ok=True, auth_info=Tenant.ADMIN)
        if code not in [0, -1]:
            err_msgs.append(msg)

    if volumes:
        LOG.fixture_step("({}) Attempt to delete following volumes: {}".format(scope, volumes))
        code, msg = cinder_helper.delete_volumes(volumes, fail_ok=True, auth_info=Tenant.ADMIN)
        if code > 0:
            err_msgs.append(msg)

    if volume_types:
        LOG.fixture_step("({}) Attempt to delete following volume_types: {}".format(scope, volume_types))
        code, msg = cinder_helper.delete_volume_types(volume_types, fail_ok=True, auth_info=Tenant.ADMIN)
        if code > 0:
            err_msgs.append(msg)

    if vol_snapshots:
        LOG.fixture_step("({}) Attempt to delete following volume snapshots: {}".format(scope, vol_snapshots))
        code, msg = cinder_helper.delete_volume_snapshots(snapshots=vol_snapshots, fail_ok=True, auth_info=Tenant.ADMIN)
        if code > 0:
            err_msgs.append(msg)

    if qos_ids:
        LOG.fixture_step("({}) Attempt to delete following qos_ids: {}".format(scope, qos_ids))
        code, msg = cinder_helper.delete_qos_list(qos_ids, fail_ok=True, auth_info=Tenant.ADMIN)
        if code > 0:
            err_msgs.append(msg)

    if flavors:
        LOG.fixture_step("({}) Attempt to delete following flavors: {}".format(scope, flavors))
        code, msg = nova_helper.delete_flavors(flavors, fail_ok=True, auth_info=Tenant.ADMIN)
        if code > 0:
            err_msgs.append(msg)

    if images:
        LOG.fixture_step("({}) Attempt to delete following images: {}".format(scope, images))
        code, msg = glance_helper.delete_images(images, fail_ok=True, auth_info=Tenant.ADMIN)
        if code > 0:
            err_msgs.append(msg)

    if server_groups:
        LOG.fixture_step("({}) Attempt to delete following server groups: {}".format(scope, server_groups))
        code, msg = nova_helper.delete_server_groups(server_groups, fail_ok=True, auth_info=Tenant.ADMIN)
        if code > 0:
            err_msgs.append(msg)

    if floating_ips:
        LOG.fixture_step("({}) Attempt to delete following floating ips: {}".format(scope, floating_ips))
        for fip in floating_ips:
            code, msg = network_helper.delete_floating_ip(fip, fip_val='ip', fail_ok=True, auth_info=Tenant.ADMIN)
            if code > 0:
                err_msgs.append(msg)

    if trunks:
        LOG.fixture_step("({}) Attempt to delete following trunks: {}".format(scope, trunks))
        for trunk in trunks:
            code, msg = network_helper.delete_trunk(trunk, auth_info=Tenant.ADMIN, fail_ok=True)
            if code > 0:
                err_msgs.append(msg)
    if ports:
        LOG.fixture_step("({}) Attempt to delete following ports: {}".format(scope, ports))
        for port in ports:
            code, msg = network_helper.delete_port(port, auth_info=Tenant.ADMIN, fail_ok=True)
            if code > 0:
                err_msgs.append(msg)

    if routers:
        LOG.fixture_step("{}) Attempt to delete following routers: {}".format(scope, routers))
        for router in routers:
            code, msg = network_helper.delete_router(router, fail_ok=True, auth_info=Tenant.ADMIN)
            if code > 0:
                err_msgs.append(msg)

    if subnets:
        LOG.fixture_step("({}) Attempt to delete following subnets: {}".format(scope, subnets))
        for subnet in subnets:
            code, msg = network_helper.delete_subnet(subnet_id=subnet, fail_ok=True, auth_info=Tenant.ADMIN)
            if code > 0:
                err_msgs.append(msg)
    if networks:
        LOG.fixture_step("({}) Attempt to delete following networks: {}".format(scope, networks))
        for network in networks:
            code, msg = network_helper.delete_network(network_id=network, fail_ok=True, auth_info=Tenant.ADMIN)
            if code > 0:
                err_msgs.append(msg)

    if heat_stacks:
        LOG.fixture_step("({}) Attempt to delete following heat stacks: {}".format(scope, heat_stacks))
        auth_info = None
        for stack in heat_stacks:
            heat_user = getattr(Heat, stack.split('-')[0])['heat_user']
            if heat_user is 'admin':
                auth_info = Tenant.ADMIN
            code, msg = heat_helper.delete_stack(stack, check_first=True, auth_info=auth_info, fail_ok=True)
            if code > 0:
                err_msgs.append(msg)

    if aggregates:
        LOG.fixture_step("({}) Attempt to delete following aggregates: {}".format(scope, aggregates))
        for aggregate in aggregates:
            code, msg = nova_helper.remove_hosts_from_aggregate(aggregate=aggregate, check_first=False)
            if code > 0:
                err_msgs.append(msg)
            code,msg=nova_helper.delete_aggregate(name=aggregate)
            if code > 0:
                err_msgs.append(msg)

    # Attempt all deletions before raising exception.
    if err_msgs:
        LOG.error("ERROR: Failed to delete resource(s). \nDetails: {}".format(err_msgs))
        # raise exceptions.CommonError("Failed to delete resource(s). Details: {}".format(err_msgs))