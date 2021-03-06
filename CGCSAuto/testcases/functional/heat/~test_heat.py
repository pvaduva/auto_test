import os
import time
from pytest import fixture, mark, skip, param

from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from keywords import nova_helper, heat_helper, ceilometer_helper, network_helper, cinder_helper, glance_helper, \
    host_helper, common, system_helper, vm_helper

from consts.heat import Heat, HeatUpdate
from consts.stx import HEAT_PATH, HeatStackStatus
from consts.auth import Tenant
from consts.proj_vars import ProjVar
from consts.reasons import SkipSysType


def verify_heat_resource(to_verify=None, template_name=None, stack_name=None, auth_info=None, fail_ok=False):
    """
        Verify the heat resource creation/deletion for given resources

        Args:
            to_verify (list): Resources to verify creation or deletion.
            template_name (str): template to be used to create heat stack.
            stack_name(str): stack name used to create the stack
            auth_info
            fail_ok

        Returns (int): return 0 if success 1 if failure

    """
    LOG.info("Verifying heat resource {}".format(to_verify))

    rtn_code = 0
    msg = "Heat resource {} appeared".format(to_verify)
    item_verified = to_verify

    if to_verify is 'volume':
        LOG.info("Verifying volume")
        vol_name = getattr(Heat, template_name)['vol_name']
        resource_found = cinder_helper.get_volumes(name=vol_name)

    elif to_verify is 'ceilometer_alarm':
        resource_found = ceilometer_helper.get_alarms(name=stack_name, strict=False)

    elif to_verify is 'neutron_port':
        port_name = getattr(Heat, template_name)['port_name']
        if port_name is None:
            port_name = stack_name
        resource_found = network_helper.get_ports(port_name=port_name)

    elif to_verify is 'neutron_provider_net_range':
        resource_found = network_helper.get_network_segment_ranges(field='name', physical_network='sample_physnet_X')

    elif to_verify is 'nova_server_group':
        resource_found = nova_helper.get_server_groups(name=stack_name)

    elif to_verify is 'vm':
        vm_name = getattr(Heat, template_name)['vm_name']
        resource_found = vm_helper.get_vms(vms=vm_name, strict=False)

    elif to_verify is 'nova_flavor':
        resource_found = nova_helper.get_flavors(name='sample-flavor')

    elif to_verify is 'neutron_net':
        resource_found = network_helper.get_tenant_net_id(net_name='sample-net')

    elif to_verify is 'image':
        resource_found = glance_helper.get_image_id_from_name(name='sample_image')

    elif to_verify is 'subnet':
        resource_found = network_helper.get_subnets(name='sample_subnet')

    elif to_verify is 'floating_ip':
        resource_found = network_helper.get_floating_ips()

    elif to_verify is 'router':
        resource_found = network_helper.get_tenant_router(router_name='sample_router', auth_info=auth_info)

    elif to_verify is 'router_gateway':
        item_verified = 'sample_gateway_router'
        resource_found = network_helper.get_tenant_router(router_name='sample_gateway_router', auth_info=auth_info)
        if resource_found:
            item_verified = to_verify
            resource_found = network_helper.get_router_ext_gateway_info(router_id=resource_found, auth_info=auth_info)

    elif to_verify is 'router_interface':
        item_verified = 'sample_if_router'
        router_id = network_helper.get_tenant_router(router_name='sample_if_router', auth_info=auth_info)
        resource_found = router_id
        if resource_found:
            item_verified = 'sample_if_subnet'
            subnets = network_helper.get_subnets(name='sample_if_subnet', auth_info=auth_info)
            resource_found = subnets
            if resource_found:
                item_verified = to_verify
                router_subnets = network_helper.get_router_subnets(router=router_id, auth_info=auth_info)
                resource_found = resource_found[0] in router_subnets

    elif to_verify is 'security_group':
        resource_found = network_helper.get_security_groups(name='SecurityGroupDeluxe')
    elif to_verify is 'key_pair':
        kp_name = getattr(Heat, template_name)['key_pair_name']
        resource_found = nova_helper.get_keypairs(name=kp_name)
    elif to_verify is 'neutron_qos':
        resource_found = network_helper.get_qos_policies(name='SampleQoS', auth_info=auth_info)
    else:
        raise ValueError("Unknown item to verify: {}".format(to_verify))

    if not resource_found:
        msg = "Heat stack {} resource {} does not exist".format(stack_name, item_verified)
        if fail_ok:
            rtn_code = 1
        else:
            assert resource_found, msg

    LOG.info(msg)
    return rtn_code, msg


def update_stack(stack_name, template_name=None, ssh_client=None, fail_ok=False, auth_info=Tenant.get('admin')):
    """
        Update heat stack and verify stack is updated as expected
        Args:
            stack_name (str): stack to be updated
            template_name (str): template to be used to create heat stack.
            ssh_client (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.
            fail_ok (bool): Whether to throw exception if update command fails to send

        Returns (tuple): (rtn_code (int), message (str))

    """

    t_name, yaml = template_name.split('.')
    to_verify = getattr(Heat, t_name)['verify']
    update_params = getattr(HeatUpdate, t_name)['params']
    update_vals = getattr(HeatUpdate, t_name)['new_vals']

    template_path = os.path.join(ProjVar.get_var('USER_FILE_DIR'), HEAT_PATH, template_name)
    cmd_list = [" -f %s " % template_path]

    for i in range(len(update_params)):
        cmd_list.append("-P %s=%s " % (update_params[i], update_vals[i]))

    # The -x parameter keeps the existing values of parameters not in update_params
    cmd_list.append(" -x %s" % stack_name)
    params_str = ''.join(cmd_list)
    LOG.info("Executing command: heat %s stack-update", params_str)
    exitcode, output = cli.heat('stack-update', params_str, ssh_client=ssh_client, fail_ok=fail_ok, auth_info=auth_info)

    if exitcode == 1:
        LOG.warning("Update heat stack request rejected.")
        return 1, output

    # See how long it takes to apply the update
    start_time = time.time()
    LOG.info("Stack {} updated successfully.".format(stack_name))

    LOG.tc_step("Verifying Heat Stack Status for UPDATE_COMPLETE for updated stack %s", stack_name)

    res, msg = heat_helper.wait_for_heat_status(stack_name=stack_name, status=HeatStackStatus.UPDATE_COMPLETE,
                                                auth_info=auth_info, fail_ok=fail_ok)
    if not res:
        return 2, msg

    LOG.info("Stack {} is in expected UPDATE_COMPLETE state.".format(stack_name))
    end_time = time.time()

    LOG.info("Update took %d seconds", (end_time - start_time))

    for item in to_verify:
        LOG.tc_step("Verifying Heat updated resources %s for stack %s", item, stack_name)
        verify_heat_resource(to_verify=item, template_name=t_name, stack_name=stack_name, auth_info=auth_info,
                             fail_ok=False)

    msg = "Stack {} resources are updated as expected.".format(stack_name)
    LOG.info(msg)

    return 0, msg


def verify_basic_template(template_name=None, con_ssh=None, auth_info=None, delete_after_swact=False):
    """
        Create/Delete heat stack and verify the resource are created/deleted as expeted
            - Create a heat stack with the given template
            - Verify heat stack is created sucessfully
            - Verify heat resources are created
            - Delete Heat stack and verify resource deletion
        Args:
            con_ssh (SSHClient): If None, active controller ssh will be used.
            template_name (str): template to be used to create heat stack.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.
            delete_after_swact
    """

    t_name, yaml = template_name.split('.')
    params = getattr(Heat, t_name)['params']
    heat_user = getattr(Heat, t_name)['heat_user']
    to_verify = getattr(Heat, t_name)['verify']
    if heat_user is 'admin':
        auth_info = Tenant.get('admin')

    table_ = table_parser.table(cli.heat('stack-list', auth_info=auth_info)[1])
    names = table_parser.get_values(table_, 'stack_name')
    stack_name = common.get_unique_name(t_name, existing_names=names)
    template_path = os.path.join(ProjVar.get_var('USER_FILE_DIR'), HEAT_PATH, template_name)
    if params:
        params = {param_: heat_helper.get_heat_params(param_name=param_) for param_ in params}

    LOG.tc_step("Creating Heat Stack using template %s", template_name)
    heat_helper.create_stack(stack_name=stack_name, template=template_path, parameters=params, cleanup='function',
                             auth_info=auth_info, con_ssh=con_ssh)

    for item in to_verify:
        LOG.tc_step("Verifying Heat created resources %s for stack %s", item, stack_name)
        verify_heat_resource(to_verify=item, template_name=t_name, stack_name=stack_name, auth_info=auth_info)
    LOG.info("Stack {} resources are created as expected.".format(stack_name))

    if hasattr(HeatUpdate, t_name):
        LOG.tc_step("Updating stack %s", stack_name)
        update_stack(stack_name, template_name, ssh_client=con_ssh, auth_info=auth_info, fail_ok=False)

    if delete_after_swact:
        host_helper.swact_host()

    LOG.tc_step("Delete heat stack {} ".format(stack_name))
    heat_helper.delete_stack(stack=stack_name, auth_info=auth_info, fail_ok=False)

    LOG.info("Stack {} deleted successfully.".format(stack_name))

    LOG.tc_step("Verifying resource deletion after heat stack {} is deleted".format(stack_name))
    for item in to_verify:
        LOG.tc_step("Verifying Heat resources deletion %s for stack %s", item, stack_name)
        code, msg = verify_heat_resource(to_verify=item, template_name=t_name, stack_name=stack_name, fail_ok=True,
                                         auth_info=auth_info)
        assert 1 == code, "Heat resource {} still exist after stack {} deletion".format(item, stack_name)


@fixture(scope='module', autouse=True)
def revert_quota(request):
    original_quotas = vm_helper.get_quota_details_info('network', detail=False)
    tenants_quotas = {}

    for tenant_id, quotas_dict in original_quotas.items():
        network_quota = quotas_dict['networks']
        subnet_quota = quotas_dict['subnets']
        tenants_quotas[tenant_id] = (network_quota, subnet_quota)

    def revert():
        LOG.fixture_step("Revert network quotas to original values.")
        for tenant_id_, quotas in tenants_quotas.items():
            network_quota_, subnet_quota_ = quotas
            vm_helper.set_quotas(tenant=tenant_id, networks=network_quota_, subnets=subnet_quota_)

    request.addfinalizer(revert)

    return tenants_quotas


@mark.usefixtures('check_alarms')
@mark.parametrize('template_name', [
    # param('WR_Neutron_ProviderNetRange.yaml', marks=mark.priorities('p2')),  # Need update due to datanetwork change
    param('OS_Cinder_Volume.yaml', marks=mark.priorities('p2')),
    # param('OS_Glance_Image.yaml'), # Stack update needed
    # https://bugs.launchpad.net/bugs/1819483
    param('OS_Ceilometer_Alarm.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_Port.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_Net.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_Subnet.yaml', marks=mark.priorities('p2')),
    param('OS_Nova_Flavor.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_FloatingIP.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_Router.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_RouterGateway.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_RouterInterface.yaml', marks=mark.priorities('p2')),
    param('OS_Neutron_SecurityGroup.yaml', marks=mark.priorities('p2')),
    # param('OS_Nova_ServerGroup.yaml', marks=mark.priorities('p2')),     # Stack update needed
    param('OS_Nova_KeyPair.yaml', marks=mark.priorities('p2')),
    # param('WR_Neutron_QoSPolicy.yaml', marks=mark.priorities('p2')),    # CGTS-10095
    param('OS_Heat_Stack.yaml', marks=mark.priorities('p2')),
    param('OS_Cinder_VolumeAttachment.yaml', marks=mark.priorities('p2')),
    param('OS_Nova_Server.yaml', marks=mark.priorities('p2')),
    param('OS_Heat_AccessPolicy.yaml', marks=mark.priorities('p2')),
    param('OS_Heat_AutoScalingGroup.yaml', marks=mark.priorities('p2')),
])
# can add test fixture to configure hosts to be certain storage backing
def test_heat_template(template_name, revert_quota):
    """
    Basic Heat template testing:
        various Heat templates.

    Args:
        template_name (str): e.g, OS_Cinder_Volume.
        revert_quota (dict): test fixture to revert network quota.

    =====
    Prerequisites (skip test if not met):
        - at least two hypervisors hosts on the system

    Test Steps:
        - Create a heat stack with the given template
        - Verify heat stack is created successfully
        - Verify heat resources are created
        - Delete Heat stack and verify resource deletion

    """
    if 'QoSPolicy' in template_name:
        if not system_helper.is_avs():
            skip("QoS policy is not supported by OVS")

    elif template_name == 'OS_Neutron_RouterInterface.yaml':
        LOG.tc_step("Increase network quota by 2 for every tenant")
        tenants_quotas = revert_quota
        for tenant_id, quotas in tenants_quotas.items():
            network_quota, subnet_quota = quotas
            vm_helper.set_quotas(tenant=tenant_id, networks=network_quota + 10, subnets=subnet_quota + 10)

    elif template_name == 'OS_Nova_Server.yaml':
        # create new image to do update later
        LOG.tc_step("Creating an Image to be used for heat update later")
        glance_helper.create_image(name='tis-centos2', cleanup='function')

    # add test step
    verify_basic_template(template_name)


@mark.usefixtures('check_alarms')
@mark.parametrize('template_name', [
    param('OS_Cinder_Volume.yaml', marks=mark.nightly),
])
# can add test fixture to configure hosts to be certain storage backing
def test_delete_heat_after_swact(template_name):
    """
    Test if a heat stack can be deleted after swact:

    Args:
        template_name (str): e.g, OS_Cinder_Volume.

    =====
    Prerequisites (skip test if not met):
        - at least two hypervisors hosts on the system

    Test Steps:
        - Create a heat stack with the given template
        - Verify heat stack is created sucessfully
        - Verify heat resources are created
        - Swact controllers
        - Delete Heat stack and verify resource deletion

    """
    if len(system_helper.get_controllers()) < 2:
        skip(SkipSysType.LESS_THAN_TWO_CONTROLLERS)

    # add test step
    verify_basic_template(template_name, delete_after_swact=True)
