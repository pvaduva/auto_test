from pytest import fixture, mark, skip

import keywords.system_helper
from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper,ceilometer_helper,network_helper,cinder_helper,glance_helper,\
    host_helper, common
from setup_consts import P1, P2, P3
import time
from consts.heat import Heat
from consts.filepaths import WRSROOT_HOME
from consts.cgcs import HEAT_PATH
import os
from consts.auth import Tenant
from testfixtures.resource_mgmt import ResourceCleanup


def verify_heat_resource(to_verify=None,template_name=None,stack_name=None,auth_info=None):
    """
        Verify the heat resource creation/deletion for given resources

        Args:
            to_verify (list): Resources to verify creation or deletion.
            template_name (str): template to be used to create heat stack.
            stack_name(str): stack name used to create the stack

        Returns (int): return 0 if success 1 if failure

    """

    if to_verify is 'volume' :
        LOG.info("Verifying volume")
        vol_name = getattr(Heat, template_name)['vol_name']
        volume_id = cinder_helper.get_volumes(name=vol_name)
        if volume_id:
            return 0
    elif to_verify is 'ceilometer_alarm':
        LOG.info("Verifying ceilometer")
        table = ceilometer_helper.get_alarms()
        alarm_id = table_parser.get_values(table, 'Alarm ID', Name=stack_name, strict=False)
        if alarm_id:
            return 0
    elif to_verify is 'neutron_port':
        port_name = getattr(Heat, template_name)['port_name']
        if port_name is None:
            port_name = stack_name
        LOG.info("Verifying neutron port")
        port_id = network_helper.get_neutron_port(name=port_name)
        if port_id:
            return 0
    elif to_verify is 'neutron_provider_net':
        LOG.info("Verifying neutron provider net")
        net_id = network_helper.get_providernets(name='physnetX')
        if net_id:
            return 0
    elif to_verify is 'neutron_provider_net_range':
        LOG.info("Verifying neutron provider net range")
        net_range = network_helper.get_providernet_ranges_dict(providernet_name='sample_physnet_X')
        if net_range:
            return 0
    elif to_verify is 'nova_server_group':
        LOG.info("Verifying nova server group")
        server_group_id = nova_helper.get_server_groups(name=stack_name)
        if server_group_id:
            return 0
    elif to_verify is 'vm':
        vm_name = getattr(Heat, template_name)['vm_name']
        LOG.info("Verifying server")
        vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)
        if vm_id:
            return 0
    elif to_verify is 'nova_flavor':
        LOG.info("Verifying nova flavor")
        flavor_id = nova_helper.get_flavor_id(name='sample-flavor')
        if flavor_id:
            return 0
    elif to_verify is 'neutron_net':
        LOG.info("Verifying neutron net")
        net_id = network_helper.get_tenant_net_id(net_name='sample-net')
        if net_id:
            return 0
    elif to_verify is 'image':
        LOG.info("Verifying glance image")
        image_id = glance_helper.get_image_id_from_name(name='sample_image')
        if image_id:
            return 0
    elif to_verify is 'subnet':
        LOG.info("Verifying subnet image")
        subnet_id = network_helper.get_subnets(name='sample_subnet')
        if subnet_id:
            return 0
    elif to_verify is 'floating_ip':
        LOG.info("Verifying floating ip")
        floating_ip_id = network_helper.get_floating_ips()
        if floating_ip_id:
            return 0
    elif to_verify is 'router':
        LOG.info("Verifying router")
        router_id = network_helper.get_tenant_router(router_name='sample_router', auth_info=auth_info)
        if router_id:
            return 0
    elif to_verify is 'router_gateway':
        LOG.info("Verifying router gateway")
        router_id = network_helper.get_tenant_router(router_name='sample_gateway_router', auth_info=auth_info)
        if not router_id:
            return 1
        gateway_info = network_helper.get_router_ext_gateway_info(router_id=router_id, auth_info=auth_info)
        if gateway_info:
            return 0
    elif to_verify is 'router_interface':
        LOG.info("Verifying router interface")
        router_id = network_helper.get_tenant_router(router_name='sample_if_router', auth_info=auth_info)
        if not router_id:
            return 1
        LOG.info("Verifying subnet")
        subnet_id = network_helper.get_subnets(name='sample_if_subnet', auth_info=auth_info)
        if not subnet_id:
            return 1
        router_subnets = network_helper.get_router_subnets(router_id=router_id, auth_info=auth_info)
        if subnet_id in router_subnets:
            return 0
    elif to_verify is 'security_group':
        LOG.info("Verifying neutron security group")
        security_group = network_helper.get_security_group(name='SecurityGroupDeluxe')
        if security_group:
            return 0
    elif to_verify is 'key_pair':
        kp_name = getattr(Heat, template_name)['key_pair_name']
        LOG.info("Verifying nova key pair")
        key_pair_name = nova_helper.get_key_pair(name=kp_name)
        if key_pair_name:
            return 0
    elif to_verify is 'neutron_qos':
        LOG.info("Verifying neutron qos policy")
        qos_id = network_helper.get_qos(name='SampleQoS', auth_info=auth_info)
        if qos_id:
            return 0
    return 1


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

        Returns (tuple): (rnt_code (int), message (str))

    """

    fail_ok=0

    t_name, yaml = template_name.split('.')
    params = getattr(Heat, t_name)['params']
    heat_user = getattr(Heat, t_name)['heat_user']
    to_verify = getattr(Heat, t_name)['verify']
    if heat_user is 'admin':
        auth_info=Tenant.ADMIN

    table_ = table_parser.table(cli.heat('stack-list', auth_info=auth_info))
    names = table_parser.get_values(table_, 'stack_name')
    stack_name = common.get_unique_name(t_name, existing_names=names)

    template_path = os.path.join(WRSROOT_HOME, HEAT_PATH, template_name)
    cmd_list = ['-f %s ' % template_path]

    if params is not None:
        for param in params:
            param_result = heat_helper.get_heat_params(param_name=param)
            cmd_list.append("-P %s=%s " % (param, param_result))

    cmd_list.append(" %s" % stack_name)
    params_string = ''.join(cmd_list)

    LOG.tc_step("Creating Heat Stack..using template %s",template_name)
    exitcode, output = cli.heat('stack-create', params_string, ssh_client=con_ssh, auth_info=auth_info,
                      fail_ok=fail_ok, rtn_list=True)
    if exitcode == 1:
        LOG.warning("Create heat stack request rejected.")
        return [1, output]
    LOG.info("Stack {} created sucessfully.".format(stack_name))

    ### add the heat stack name for deleteion on failure
    ResourceCleanup.add(resource_type='heat_stack', resource_id=stack_name)

    LOG.tc_step("Verifying Heat Stack Status for CREATE_COMPLETE for stack %s",stack_name)

    if not heat_helper.wait_for_heat_state(stack_name=stack_name,state='CREATE_COMPLETE',auth_info=auth_info):
        return [1, 'stack did not go to state CREATE_COMPLETE']
    LOG.info("Stack {} is in expected CREATE_COMPLETE state.".format(stack_name))

    for item in to_verify:
        LOG.tc_step("Verifying Heat created resources %s for stack %s", item, stack_name)
        verify_result = verify_heat_resource(to_verify=item, template_name=t_name,stack_name=stack_name,
                                             auth_info=auth_info)
        if verify_result is not 0:
            LOG.warning("Verify resouces %s created by heat stack Failed.", item)
            return [1, "Heat resource verification failed"]

    LOG.info("Stack {} resources are created as expected.".format(stack_name))

    if delete_after_swact:
        swact_result=host_helper.swact_host()
        if swact_result is 0:
            return [1, "swact host failed"]

    LOG.tc_step("Delete heat stack {} ".format(stack_name))
    del_res,del_output = heat_helper.delete_stack(stack_name=stack_name, auth_info=auth_info, fail_ok=True)
    if del_res > 0:
        LOG.info("Stack {} delete failed.".format(stack_name))
        output = "Stack {} delete failed".format(stack_name)
        return [1, output]

    LOG.info("Stack {} deleted successfully.".format(stack_name))

    LOG.tc_step("Verifying resource deletion after heat stack {} is deleted".format(stack_name))
    for item in to_verify:
        LOG.tc_step("Verifying Heat resources deletion %s for stack %s", item, stack_name)
        verify_result = verify_heat_resource(to_verify=item, template_name=t_name, stack_name=stack_name,
                                             auth_info=auth_info)
        if verify_result is not 1:
            LOG.warning("Verify resouces %s deletion by heat stack Failed.", item)
            return [1, output]

    return [0, 'stack_status']


# Overall skipif condition for the whole test function (multiple test iterations)
# This should be a relatively static condition.i.e., independent with test params values
#@mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@mark.usefixtures('check_alarms')
@mark.parametrize(
    ('template_name'), [
        mark.sanity(('WR_Neutron_ProviderNetRange.yaml')),
        P1(('WR_Neutron_ProviderNet.yaml')),
        P1(('OS_Cinder_Volume.yaml')),
        P1(('OS_Ceilometer_Alarm.yaml')),
        P1(('OS_Neutron_Port.yaml')),
        P1(('OS_Neutron_Net.yaml')),
        P1(('OS_Neutron_Subnet.yaml')),
        P1(('OS_Nova_Flavor.yaml')),
        P1(('OS_Neutron_FloatingIP.yaml')),
        P1(('OS_Neutron_Router.yaml')),
        P1(('OS_Neutron_RouterGateway.yaml')),
        P1(('OS_Neutron_SecurityGroup.yaml')),
        P1(('OS_Nova_ServerGroup.yaml')),
        P1(('OS_Nova_KeyPair.yaml')),
        P1(('WR_Neutron_QoSPolicy.yaml')),
        P1(('OS_Heat_Stack.yaml')),
        P1(('OS_Cinder_VolumeAttachment.yaml')),
        P1(('OS_Nova_Server.yaml')),
        P1(('OS_Heat_AccessPolicy.yaml')),
        P1(('OS_Heat_AutoScalingGroup.yaml')),

    ])
# can add test fixture to configure hosts to be certain storage backing
def test_heat_template(template_name):
    """
    Basic Heat template testing:
        various Heat templates.

    Args:
        template_name (str): e.g, OS_Cinder_Volume.

    =====
    Prerequisites (skip test if not met):
        - at least two hypervisors hosts on the system

    Test Steps:
        - Create a heat stack with the given template
        - Verify heat stack is created sucessfully
        - Verify heat resources are created
        - Delete Heat stack and verify resource deletion

    """



    # add test step

    return_code, msg = verify_basic_template(template_name)

    # Verify test results using assert
    LOG.tc_step("Verify test result")
    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)


# Overall skipif condition for the whole test function (multiple test iterations)
# This should be a relatively static condition.i.e., independent with test params values
#@mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@mark.usefixtures('check_alarms')
@mark.parametrize(
    ('template_name'), [
        P1(('OS_Cinder_Volume.yaml')),
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
        - Sawct controllers
        - Delete Heat stack and verify resource deletion

    """



    # add test step
    return_code, msg = verify_basic_template(template_name,delete_after_swact=True)

    # Verify test results using assert
    LOG.tc_step("Verify test result")
    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)


########################################################################################################################
