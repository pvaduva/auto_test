import re
import os
from pytest import skip, fixture

from utils.tis_log import LOG
from utils.clients.local import LocalHostClient
from consts.cgcs import FlavorSpec
from consts.auth import Tenant, SvcCgcsAuto, ComplianceCreds
from consts.proj_vars import ComplianceVar, ProjVar
from consts.compliance import RefStack, VM_ROUTE_VIA
from keywords import keystone_helper, nova_helper, cinder_helper, network_helper, glance_helper, storage_helper, \
    system_helper, host_helper

from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='session')
def refstack_pre_check():
    LOG.info("Check refstack test suite path")
    refstack_suite = ComplianceVar.get_var('REFSTACK_SUITE')
    if not refstack_suite:
        skip("RefStack test list path has to be specified via --refstack-suite")

    LOG.info("Check refstack-client and test host")
    with host_helper.ssh_to_compliance_server() as refstack_host_ssh:
        if not refstack_host_ssh.file_exists(RefStack.TEMPEST_CONF):
            skip("RefStack conf file does not exist: {}".format(RefStack.TEMPEST_CONF))

        LOG.fixture_step("Remove test files from previous runs if any.")
        for file in RefStack.LOG_FILES:
            file_path = '{}/{}'.format(RefStack.TEST_HISTORY_DIR, file)
            refstack_host_ssh.exec_cmd('rm -f {}'.format(file_path), get_exit_code=False)

        LOG.fixture_step('scp test-list file to refstack-client dir')
        dest_path = '{}/test-list.txt'.format(RefStack.CLIENT_DIR)
        refstack_host_ssh.scp_on_dest(source_path=refstack_suite, source_ip=SvcCgcsAuto.SERVER,
                                      source_user=SvcCgcsAuto.USER, source_pswd=SvcCgcsAuto.PASSWORD,
                                      dest_path=dest_path, timeout=120)


@fixture(scope='session', autouse=True)
def refstack_setup(refstack_pre_check, request):
    if not system_helper.get_storage_nodes():
        skip("Ceph system is required for refstack test")

    primary_tenant = keystone_helper.get_projects(auth_info=None)[0]
    append_str = re.findall('tenant\d+(.*)', primary_tenant)[0]

    LOG.fixture_step("Create tenants, users, and update quotas")
    projects = ['admin']
    for i in range(3, 7):
        name = 'tenant{}{}'.format(i, append_str)
        keystone_helper.create_project(name=name, description=name, rtn_exist=True)
        keystone_helper.create_user(name=name, rtn_exist=True, password=RefStack.USER_PASSWORD)
        for role in ('_member_', 'admin'):
            user = 'admin' if role == 'admin' else name
            keystone_helper.add_or_remove_role(role=role, project=name, user=user)
        projects.append(name)

    for project in projects:
        nova_helper.update_quotas(tenant=project, instances=20, cores=50)
        cinder_helper.update_quotas(tenant=project, volumes=30, snapshots=20)
        network_helper.update_quotas(tenant_name=project, port=500, floatingip=50, subnet=100, network=100)

    LOG.fixture_step("Create test flavors")
    flavors = []
    for i in range(2):
        flavor_id = nova_helper.create_flavor(name='refstack', vcpus=2, ram=2048, root_disk=2)[1]
        nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated',
                                                         FlavorSpec.MEM_PAGE_SIZE: 2048})
        flavors.append(flavor_id)
        ResourceCleanup.add('flavor', flavor_id, scope='session')

    LOG.fixture_step("Get/create test images")
    images = [glance_helper.get_image_id_from_name()]
    image_id = glance_helper.create_image()[1]
    images.append(image_id)
    ResourceCleanup.add('image', image_id, scope='session')

    LOG.fixture_step("Enable object gateway for Swift if not already done")
    obj_gateway = storage_helper.get_storage_backend_show_vals(backend='ceph-store', fields='object_gateway')[0]
    if not obj_gateway:
        storage_helper.modify_storage_backend('ceph-store', object_gateway=True, lock_unlock=True)

    LOG.fixture_step("Setup public router if not already done.")
    external_net_id = network_helper.get_ext_networks()[0]
    public_router = 'public-router0'
    pub_routers = network_helper.get_routers(name=public_router, auth_info=Tenant.ADMIN)
    if not pub_routers:
        LOG.info("Create public router and add interfaces")
        public_router_id = network_helper.create_router(name=public_router, tenant=Tenant.ADMIN['tenant'])[1]
        network_helper.set_router_gateway(router_id=public_router_id, extnet_id=external_net_id)

        internal_subnet = 'internal0-subnet0-1'
        gateway = '10.1.1.1'
        network_helper.update_subnet(subnet=internal_subnet, gateway=gateway)
        network_helper.add_router_interface(router_id=public_router_id, subnet=internal_subnet, auth_info=Tenant.ADMIN)

    keystone_pub = keystone_helper.get_endpoints(rtn_val='URL', interface='public', service_name='keystone')[0]
    keystone_pub_url = keystone_pub.split('/v')[0] + '/'
    keystone_pub_url = keystone_pub_url.replace(':', '\:').replace('/', '\/')

    params_dict = {
        'image_ref': images[0],
        'image_ref_alt': images[1],
        'flavor_ref': flavors[0],
        'flavor_ref_alt': flavors[1],
        'public_network_id': external_net_id,
        'uri': keystone_pub_url + 'v2.0',
        'uri_v3': keystone_pub_url + 'v3',
    }

    LOG.fixture_step("Update tempest.conf parameters on cumulus server: \n{}".format(params_dict))
    with host_helper.ssh_to_compliance_server() as server_ssh:
        for key, val in params_dict.items():
            server_ssh.exec_cmd('sed -i "s/^{} =.*/{} = {}/g" {}'.format(key, key, val, RefStack.TEMPEST_CONF),
                                fail_ok=False)
            server_ssh.exec_cmd('grep {} {}'.format(val, RefStack.TEMPEST_CONF), fail_ok=False)

    LOG.fixture_step("Add routes to access VM from compliance server if not already done")
    cidrs = network_helper.get_subnets(name="tenant[1|2].*-mgmt0-subnet0|external-subnet0", regex=True, rtn_val='cidr')
    cidrs_to_add = ['{}.0/24'.format(re.findall('(.*).\d+/\d+', item)[0]) for item in cidrs]
    for cidr in cidrs_to_add:
        if server_ssh.exec_cmd('ip route | grep "{}"'.format(cidr))[0] != 0:
            server_ssh.exec_sudo_cmd('ip route add {} via {}'.format(cidr, VM_ROUTE_VIA))

    def scp_logs():
        LOG.info("scp test results files from refstack test host to local automation dir")
        dest_dir = os.path.join(ProjVar.get_var('LOG_DIR'), 'refstack')
        os.makedirs(path=dest_dir, exist_ok=True)
        localhost = LocalHostClient()
        localhost.connect()

        for item in RefStack.LOG_FILES:
            source_path = '{}/{}'.format(RefStack.TEST_HISTORY_DIR, item)
            localhost.scp_on_dest(source_ip=ComplianceCreds.get_host(), source_user=ComplianceCreds.get_user(),
                                  source_pswd=ComplianceCreds.get_password(), source_path=source_path,
                                  dest_path=dest_dir, timeout=300, cleanup=False)
        
        origin_name = ComplianceVar.get_var('REFSTACK_SUITE').rsplit(r'/', maxsplit=1)[-1]
        localhost.exec_cmd('mv {}/test-list.txt {}/{}'.format(dest_dir, dest_dir, origin_name))
    request.addfinalizer(scp_logs)
