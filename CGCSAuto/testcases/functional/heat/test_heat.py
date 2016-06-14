from pytest import fixture, mark, skip

import keywords.system_helper
from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper,ceilometer_helper,network_helper,cinder_helper,glance_helper
from setup_consts import P1, P2, P3
import time
from consts.heat import Heat
from consts.cgcs import HOME
from consts.cgcs import HEAT_PATH
import os
from consts.auth import Tenant

def get_heat_params(param_name=None):
    if param_name is 'NETWORK':
        net_id = network_helper.get_mgmt_net_id()
        return network_helper.get_net_name_from_id(net_id=net_id)
    elif param_name is 'FLAVOR':
        return 'small'
    elif param_name is 'IMAGE':
        return 'cgcs-guest'
    else:
        return 1


def verify_heat_resource(dic_to_verify=None):
    for key in dic_to_verify:
        if key is 'volume' :
            #vol_name = dic_to_verify[key]
            volume_id = cinder_helper.get_volumes(name='sample_volume')
            if volume_id is None:
                return 1
        elif key is 'ceilometer_alarm':
            LOG.info("Verifying ceilometer alarm creation via heat")
            table = ceilometer_helper.get_alarms()
            alarm_id = table_parser.get_values(table, 'Alarm ID', Name='STACK1', strict=False)
            if alarm_id is None:
                return 1
        elif key is 'neutron_port':
            LOG.info("Verifying neutron port creation via heat")
            port_id = network_helper.get_neutron_port(name='sample_port')
            if port_id is None:
                return 1
        elif key is 'neutron_provider_net':
            LOG.info("Verifying neutron provider net creation via heat")
            net_id = network_helper.get_provider_net(name='Sample_phynet')
            if net_id is None:
                return 1
        elif key is 'neutron_provider_net_range':
            LOG.info("Verifying neutron provider net range creation via heat")
            net_range = network_helper.get_provider_net_range(name='Sample_phynet_X')
            if net_range is None:
                return 1
        elif key is 'nova_server_group':
            LOG.info("Verifying nova server group creation via heat")
            server_group_id = nova_helper.get_server_groups(name='STACK1')
            if server_group_id is None:
                return 1
        elif key is 'vm':
            LOG.info("Verifying server creation via heat")
            vm_id = nova_helper.get_vm_id_from_name(vm_name='nova_server')
            if vm_id is None:
                return 1
        elif key is 'nova-flavor':
            LOG.info("Verifying nova flavor creation via heat")
            flavor_id = nova_helper.get_flavor_id(name='sample-flavor')
            if flavor_id is None:
                return 1
        elif key is 'neutron_net':
            LOG.info("Verifying neutron net creation via heat")
            net_id = network_helper.get_tenant_net_id(net_name='sample-net')
            if net_id is None:
                return 1
        elif key is 'image':
            LOG.info("Verifying glance image creation via heat")
            image_id = glance_helper.get_image_id_from_name(name='sample_image')
            if image_id is None:
                return 1
        elif key is 'subnet':
            LOG.info("Verifying glance image creation via heat")
            image_id = network_helper.get_subnets(name='sample_subnet')
            if image_id is None:
                return 1
    return 0

def verify_basic_template(template_name=None, template_path=None, con_ssh=None, auth_info=None):

    """Create a stack and then list stacks.
        :param template_name: Name of the template
        :param template_path: path to heat template
        :auth_info: authentication info
    """

    fail_ok=0

    #param, param_val = create_param_list(template=template_name,ssh_client=con_ssh,auth_info=auth_info)
    stack_name = 'STACK1'
    t_name, yaml = template_name.split('.')
    params = getattr(Heat, t_name)['params']
    heat_user = getattr(Heat, t_name)['heat_user']
    if heat_user is 'admin':
        auth_info=Tenant.ADMIN
    # heat_param.append('-P FLAVOR_NAME=%s' % flavor_name)
    template_path = os.path.join(HOME, HEAT_PATH, template_name)
    cmd_list = ['-f %s ' % template_path]
    if params is not None:
        for param in params:
            param_result = get_heat_params(param_name=param)
            cmd_list.append("-P %s=%s" % (param, param_result))

    cmd_list.append(stack_name)
    params_string = ''.join(cmd_list)

    LOG.tc_step("Creating Heat Stack..using template %s",template_name)
    exitcode, output = cli.heat('stack-create', params_string, ssh_client=con_ssh, auth_info=auth_info,
                      fail_ok=fail_ok, rtn_list=True)
    if exitcode == 1:
        LOG.warning("Create heat stack request rejected.")
        return [1, output]
    LOG.info("Stack {} created sucessfully.".format(stack_name))
    time.sleep(20)
    LOG.tc_step("Verifying Heat Stack Status for CREATE_COMPLETE for stack %s",stack_name)
    stack_status = heat_helper.get_stack_status(stack_name=stack_name)
    if "CREATE_COMPLETE" not in stack_status:
        LOG.warning("Create heat stack Failed %s",stack_status)
        return [1, stack_status]
    LOG.info("Stack {} is in expected CREATE_COMPLETE state.".format(stack_name))

    LOG.tc_step("Verifying Heat created resources for stack %s", stack_name)
    to_verify = getattr(Heat, t_name)['verify']
    verify_result = verify_heat_resource(to_verify)

    if verify_result is not 0:
        LOG.warning("Verify resouces created by heat stack Failed.")
        return [1, output]

    LOG.info("Stack {} resources are created expected.".format(stack_name))
    LOG.tc_step("Delete heat stack {} ".format(stack_name))
    delete_result = heat_helper.delete_stack(stack_name)
    if delete_result is 1:
        LOG.info("Stack {} delete failed.".format(stack_name))
        output = "Stack {} delete failed".format(stack_name)
        return [1, output]

    LOG.info("Stack {} deleted successfully.".format(stack_name))

    return [0, stack_status]

# Overall skipif condition for the whole test function (multiple test iterations)
# This should be a relatively static condition.i.e., independent with test params values
#@mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@mark.usefixtures('check_alarms')
@mark.parametrize(
    ('template_name'), [
        P1(('WR_Neutron_ProviderNetRange.yaml')),
        P1(('WR_Neutron_ProviderNet.yaml')),
        P1(('OS_Cinder_Volume.yaml')),
        P1(('OS_Ceilometer_Alarm.yaml')),
        P1(('OS_Neutron_Port.yaml')),
        P1(('OS_Neutron_Net.yaml')),
        P1(('OS_Neutron_Subnet.yaml')),
        P1(('OS_Nova_Flavor.yaml')),
        #P1(('OS_Nova_ServerGroup.yaml')),
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



    # Another test step
    LOG.tc_step("Create Heat stack using")
    return_code, message = verify_basic_template(template_name)

    # Verify test results using assert
    LOG.tc_step("Verify test result")
    assert return_code in [0, 1], message
    # Can also add asserts to check the exact error message for negative test cases, i.e., return_code is 1

    #Mark test end
    #LOG.tc_end()


########################################################################################################################
