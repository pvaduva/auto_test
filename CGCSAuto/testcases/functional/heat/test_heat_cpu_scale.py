import os
import time

from pytest import fixture, mark, skip

from utils import cli
from utils.tis_log import LOG

from setup_consts import P1, P2, P3
from consts.cgcs import HEAT_PATH, HEAT_SCENARIO_PATH, HOME, FlavorSpec

from keywords import nova_helper, vm_helper, heat_helper, ceilometer_helper, network_helper
from testfixtures.resource_mgmt import ResourceCleanup


def launch_vm_scaling_stack(con_ssh=None, auth_info=None):
    """
        Create heat stack using NestedAutoScale.yaml for vm scaling
            - Verify heat stack is created sucessfully
            - Verify heat resources are created
        Args:
            con_ssh (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.

        Returns (tuple): (rnt_code (int), message (str))

    """

    fail_ok = 0
    template_name = 'NestedAutoScale.yaml'
    t_name, yaml = template_name.split('.')
    stack_name = t_name

    template_path = os.path.join(HOME, HEAT_SCENARIO_PATH, template_name)
    cmd_list = ['-f %s ' % template_path]

    # create a flavor with Hearbeat enabled]
    fl_name = 'heartbeat'
    flavor_id = nova_helper.create_flavor(name=fl_name)[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    cmd_list.append("-P FLAVOR=%s " % fl_name)

    key_pair = vm_helper.get_any_keypair()
    cmd_list.append("-P KEYPAIR=%s " % key_pair)
    image = 'cgcs-guest'
    cmd_list.append("-P IMAGE=%s " % image)

    net_id = network_helper.get_mgmt_net_id()
    network = network_helper.get_net_name_from_id(net_id=net_id)
    cmd_list.append("-P NETWORK=%s " % network)

    cmd_list.append(" %s" % stack_name)
    params_string = ''.join(cmd_list)

    LOG.tc_step("Creating Heat Stack..using template %s", template_name)
    exitcode, output = cli.heat('stack-create', params_string, ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=fail_ok, rtn_list=True)
    if exitcode == 1:
        LOG.warning("Create heat stack request rejected.")
        return [1, output]
    LOG.info("Stack {} created sucessfully.".format(stack_name))

    # add the heat stack name for deleteion on failure
    ResourceCleanup.add(resource_type='heat_stack', resource_id=t_name)

    LOG.tc_step("Verifying Heat Stack Status for CREATE_COMPLETE for stack %s", stack_name)

    if not heat_helper.wait_for_heat_state(stack_name=stack_name, state='CREATE_COMPLETE', auth_info=auth_info):
        return [1, 'stack did not go to state CREATE_COMPLETE']
    LOG.info("Stack {} is in expected CREATE_COMPLETE state.".format(stack_name))

    return 0, stack_name


def wait_for_vm_to_scale(vm_name=None, expected_count=0, time_out=120, check_interval=3, con_ssh=None, auth_info=None):

    end_time = time.time() + time_out
    while time.time() < end_time:
        vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)
        if len(vm_id) is expected_count:
            return True

        time.sleep(check_interval)

    msg = "Heat stack {} did not go to state {} within timeout".format(vm_name, expected_count)
    LOG.warning(msg)
    return False


# Overall skipif condition for the whole test function (multiple test iterations)
# This should be a relatively static condition.i.e., independent with test params values
# @mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@mark.usefixtures('check_alarms')
@mark.parametrize('action', [
        P1('scale_up_reject_scale_down'),
        # P1(('scale_up_evacuate_scale_down')),
        # P1(('scale_up_swact_scale_down')),
    ])
# can add test fixture to configure hosts to be certain storage backing
# FIXME test func args are unused.
def test_heat_vm_scale(template_name, action):
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
    # create the heat stack
    LOG.tc_step("Creating heat stack for auto scaling Vms")
    return_code, msg = launch_vm_scaling_stack()

    assert 1 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)

    stack_name = msg
    # verify VM is created
    LOG.tc_step("Verifying first VM is created via heat stack for auto scaling")
    vm_name = stack_name
    LOG.info("Verifying server creation via heat")
    vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)
    if not vm_id:
        return 1, "Error:vm was not created by stack"

    # scale up now
    LOG.tc_step("Scaling up Vms")
    if not heat_helper.scale_up_vms(vm_name=vm_name, expected_count=3):
        assert "Failed to scale up, expected to see 3 vms in total"

    # Get the VM ids with stack_name
    vm_name_to_look = stack_name.append(".*1")
    vm_id_after_scale = nova_helper.get_vms(vm_name=vm_name_to_look, strick=True, regex=True)

    if not vm_id_after_scale:
        assert "Couldn't find the vm id for {}".format(vm_name_to_look)

    # login to vm and put a file
    LOG.tc_step("Creating /tmp/vote_no_to_stop in vm")
    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id_after_scale) as vm_ssh:
        vm_ssh.exec_cmd("touch /tmp/vote_no_to_stop")

    LOG.tc_step("Scaling down Vms")
    if not heat_helper.scale_down_vms(vm_name, expected_count=2):
        assert "Scale down failed, expect to see 2 vms"

    LOG.tc_step("Waiting for 30 sec and checking Vm count")
    # wait for 30 sec and check again to make sure that the vm is not delered
    time.sleep(30)
    if not heat_helper.scale_down_vms(vm_name, expected_count=2):
        assert "Scale down failed, expect to see 2 vms"

    # remove the tmp file in the vm
    LOG.tc_step("removing /tmp/vote_no_to_stop in vm")
    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id_after_scale) as vm_ssh:
        vm_ssh.exec_cmd("rm /tmp/vote_no_to_stop")

    # wait for vm to be deleted
    LOG.tc_step("Checking that the Vm is removed now")
    if not heat_helper.scale_down_vms(vm_name, expected_count=1):
        assert "Scale down failed, expect to see 1 vm"

    # delete heat stack
    LOG.tc_step("Deleting heat stack{}".format(stack_name))
    return_code, msg = heat_helper.delete_stack(stack_name=stack_name)
    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)
    # can check vm is deleted

