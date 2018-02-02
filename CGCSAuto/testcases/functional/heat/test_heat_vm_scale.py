import os
import time

from pytest import mark, fixture

from utils import cli
from utils.tis_log import LOG
from utils import multi_thread
from utils.ssh import SSHClient, ControllerClient

from consts.cgcs import HEAT_SCENARIO_PATH, FlavorSpec, GuestImages
from consts.filepaths import WRSROOT_HOME
from keywords import nova_helper, vm_helper, heat_helper, network_helper, host_helper, system_helper, ceilometer_helper
from testfixtures.fixture_resources import ResourceCleanup


def check_heat_engine_log():
    """
    This will check heat engine logs for scale dowm reject msg

    Test Steps:
        - Check heat-engine.log for log entries about scale down reject
        - If there were none found, wait 30 seconds for them to be generated then check for the logs again, it will
          timeout after 5 min if not found

    """
    ssh = ControllerClient.get_active_controller()
    searching_for = ["WRS vote rejecting stop for",
                     "reason=Action rejected by instance: file /tmp/vote_no_to_stop exists"]
    found = []
    # time out to exit the while loop if log entry is not found with in 5 min
    timeout = time.time()+300

    while time.time() < timeout:
        LOG.info("Checking the logs for scale down reject entries.")
        code, out = ssh.exec_cmd('tail -n 300 /var/log/heat/heat-engine.log | grep -i reject')
        logs = out.split('\n')
        for line in logs:
            for i in range(0, len(searching_for)):
                LOG.info("Searching for logs containing: {}".format(searching_for[i]))
                if searching_for[i] not in found and line.find(searching_for[i]):
                    found.append(searching_for[i])
                    LOG.info("Found {}".format(line))
                    if len(found) == len(searching_for):
                        return True

        time.sleep(30)

    LOG.info("FAIL: expecting to find {} in the logs. Found {}.".format(searching_for, found))
    return False


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

    template_path = os.path.join(WRSROOT_HOME, HEAT_SCENARIO_PATH, template_name)
    cmd_list = ['-f %s ' % template_path]

    # create a flavor with Hearbeat enabled]
    fl_name = 'heartbeat'
    flavor_id = nova_helper.create_flavor(name=fl_name)[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    cmd_list.append("-P FLAVOR=%s " % flavor_id)

    # get the key pair and append it to the heat params
    key_pair = vm_helper.get_any_keypair()
    cmd_list.append("-P KEYPAIR=%s " % key_pair)

    image = GuestImages.DEFAULT_GUEST
    cmd_list.append("-P IMAGE=%s " % image)

    # get the network and append it to the heat params
    net_id = network_helper.get_mgmt_net_id()
    network = network_helper.get_net_name_from_id(net_id=net_id)
    cmd_list.append("-P NETWORK=%s " % network)

    high_val = 50
    cmd_list.append("-P HIGH_VALUE=%s " % high_val)

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


def wait_for_scale_up_down_vm(vm_name=None, expected_count=0, time_out=900, check_interval=5):
    if vm_name is None:
        vm_name = "NestedAutoScale_vm"

    # wait for scale up to happen
    LOG.info("Expected count of Vm is {}".format(expected_count))
    end_time = time.time() + time_out
    while time.time() < end_time:
        vm_ids = nova_helper.get_vms(strict=False, name=vm_name)
        LOG.info("length of vmid is {}".format(len(vm_ids)))
        if len(vm_ids) is expected_count:
            return True
        ceilometer_helper.alarm_list()
        time.sleep(check_interval)

    msg = "Heat stack {} did not go to vm count {} within timeout".format(vm_name, expected_count)
    LOG.warning(msg)
    return False


def ssh_vm_and_send_cmd(vm_name=None, vm_image_name=None, cmd=None):
    """
    Returns:

    """
    # create a trigger for auto scale by login to vm and issue dd cmd
    vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)

    LOG.info("Sending cmd {} for vm {} using".format(cmd, vm_id))
    if not cmd:
        cmd = 'dd if=/dev/zero of=/dev/null &'

    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id, vm_image_name=vm_image_name, close_ssh=False) as vm_ssh:
        VM_SSHS.append(vm_ssh)
        vm_ssh.exec_cmd(cmd=cmd, fail_ok=False)

    return vm_ssh


VM_SSHS = []


@fixture(scope='function', autouse=True)
def aa_close_vm_ssh(request):

    def close_ssh():
        global VM_SSHS
        for ssh_client in VM_SSHS:
            try:
                ssh_client.close()
            except Exception as e:
                LOG.warning('Unable to close ssh - {}'.format(e.__str__()))
        VM_SSHS = []
    request.addfinalizer(close_ssh)


# Overall skipif condition for the whole test function (multiple test iterations)
# This should be a relatively static condition.i.e., independent with test params values
# @mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@mark.usefixtures('check_alarms')
@mark.parametrize('action', [
        mark.priorities('nightly', 'sx_nightly')('scale_up_reject_scale_down'),
    ])
# can add test fixture to configure hosts to be certain storage backing
def test_heat_vm_scale(action):

    """
    Test VM auto scaling :
        Create heat stack for auto scaleing using NestedAutoScale.yaml , scale up/down/reject.

    Args:
        action

    =====
    Prerequisites (skip test if not met):
        - at least two hypervisors hosts on the system

    Test Steps:
        - Create a heat stack for auto scaling vm (NestedAutoScale)
        - Verify heat stack is created sucessfully
        - Verify heat resources are created
        - trigger auto scale by boosting cpu usage in the vm (using dd)
        - verify it scale up to the max number of vms (3)
        - place a /tmp/vote_no_to_stop in one of the vm
        - trigger scale down by killing dd in the vm
        - verify the vm scale down to (2) and the vm with the vote_no_stop is rejecting the scale down
        - check the log entries for the scale down reject msg
        - remove the vote_no_to_stop file in the vm
        - verify the vm scale down to (1)
        - Delete Heat stack and verify resource deletion
    """
    # create the heat stack

    vm_image_name = GuestImages.DEFAULT_GUEST

    LOG.tc_step("Creating heat stack for auto scaling Vms")
    return_code, msg = launch_vm_scaling_stack()

    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)

    stack_name = msg
    # verify VM is created
    LOG.tc_step("Verifying first VM is created via heat stack for auto scaling")
    vm_name = stack_name
    LOG.info("Verifying server creation via heat")
    vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)
    assert vm_id, "Error:vm was not created by stack"
    LOG.info("Found VM %s", vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    # scale up now
    LOG.tc_step("Scaling up Vms")
    dd_cmd = 'dd if=/dev/zero of=/dev/null &'
    vm_ssh_1 = ssh_vm_and_send_cmd(vm_name=vm_name, vm_image_name=vm_image_name, cmd=dd_cmd)

    LOG.tc_step("Verifying the VM is scaling to 3 Vms")
    assert wait_for_scale_up_down_vm(vm_name=vm_name, expected_count=3), \
        "Failed to scale up, expected to see 3 vms in total"

    # Get the VM ids with stack_name
    vm_ids_after_scale = nova_helper.get_vms(strict=False, name=stack_name)

    vm_id_to_stop_scale = ''
    assert vm_ids_after_scale, "Couldn't find the vm id for {}".format(stack_name)
    # find a VM to put a file to stop scale down.
    for vm in vm_ids_after_scale:
        LOG.info("vm is {}, vm id is {}".format(vm, vm_id))
        if vm != vm_id:
            vm_id_to_stop_scale = vm
            LOG.info("Found a VM to stop scale down %s", vm_id_to_stop_scale)
            break

    assert vm_id_to_stop_scale, "Failed to find a vm to stop scale down"

    # login to vm and put a file
    LOG.tc_step("Creating /tmp/vote_no_to_stop in vm %s", vm_id_to_stop_scale)
    vm_name_1 = nova_helper.get_vm_name_from_id(vm_id_to_stop_scale)
    cmd = "touch /tmp/vote_no_to_stop"
    thread1 = multi_thread.MThread(ssh_vm_and_send_cmd, vm_name_1, vm_image_name, cmd)
    thread1.start_thread(timeout=60)
    thread1.get_output(wait=True)
    thread1.end_thread()
    thread1.wait_for_thread_end(timeout=3)

    # Kill dd first
    LOG.tc_step("Killing dd in Vm")
    vm_ssh_1.exec_cmd('pkill dd')

    LOG.tc_step("Scaling down Vms")
    assert wait_for_scale_up_down_vm(vm_name=vm_name, expected_count=2), "Scale down failed, expect to see 2 vms"

    LOG.tc_step("Checking the heat-engine.log for scale down reject msg")
    assert check_heat_engine_log(), "Could not find the log entries in heat-engine.log for scale down reject"

    # remove the tmp file in the vm
    LOG.tc_step("removing /tmp/vote_no_to_stop in vm")
    cmd = "rm -f /tmp/vote_no_to_stop"
    thread_3 = multi_thread.MThread(ssh_vm_and_send_cmd, vm_name_1, vm_image_name, cmd)
    thread_3.start_thread(timeout=60)
    thread_3.get_output(wait=True)
    thread1.end_thread()
    thread1.wait_for_thread_end(timeout=3)

    # wait for vm to be deleted
    LOG.tc_step("Checking that the Vm is removed now")
    assert wait_for_scale_up_down_vm(vm_name=vm_name, expected_count=1), "Scale down failed, expect to see 1 vm"

    vm_ssh_1.close()
    global VM_SSHS
    VM_SSHS.remove(vm_ssh_1)
    # delete heat stack
    LOG.tc_step("Deleting heat stack{}".format(stack_name))
    return_code, msg = heat_helper.delete_stack(stack_name=stack_name)
    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)
    # can check vm is deleted


# This test is not working due to CGTS-5254
# add evacuation call
@mark.usefixtures('check_alarms')
@mark.parametrize('action', [
        mark.p1('swact_scale_up_down'),
        mark.p2('evacuate_scale_up_down'),
        mark.p2('cold_migrate_scale_up_down'),
        mark.p2('live_migrate_scale_up_down'),
    ])
# can add test fixture to configure hosts to be certain storage backing
def _test_heat_vm__action_scale_up_down(action):

    """
    Test VM auto scaling with swact:
        Create heat stack for auto scaleing using NestedAutoScale.yaml ,  swact and perform vm scale up and down.

    Args:
        action

    =====
    Prerequisites (skip test if not met):
        - at least two hypervisors hosts on the system

    Test Steps:
        - Create a heat stack for auto scaling vm ()
        - Verify heat stack is created sucessfully
        - Verify heat resources are created
        - swact to standby controller
        - trigger auto scale by boosting cpu usage in the vm (using dd)
        - verify it scale up to the max number of vms (3)
        - trigger scale down by killing dd in the vm
        - verify the vm scale down to min number (1)
        - Delete Heat stack and verify resource deletion
    """
    # create the heat stack
    vm_image_name = GuestImages.DEFAULT_GUEST
    LOG.tc_step("Creating heat stack for auto scaling Vms")
    return_code, msg = launch_vm_scaling_stack()

    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)

    stack_name = msg
    # verify VM is created
    LOG.tc_step("Verifying first VM is created via heat stack for auto scaling")
    vm_name = stack_name
    LOG.info("Verifying server creation via heat")
    vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)
    if not vm_id:
        return 1, "Error:vm was not created by stack"

    LOG.info("Found VM %s", vm_id)

    if not vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id):
        return 1, "Error:vm is not pingable from NAT Box"

    # swact here
    if action == "swact_scale_up_down":
        LOG.tc_step("Swact to standby controller before scale up/down")
        hostname = system_helper.get_active_controller_name()
        exit_code, output = host_helper.swact_host(hostname=hostname, swact_start_timeout=1, fail_ok=False)
        assert 0 == exit_code, "{} is not recognized as active controller".format(hostname)
        host_helper.wait_for_hypervisors_up(hostname)
        host_helper.wait_for_webservice_up(hostname)
    elif action == "evacuate_scale_up_down":
        LOG.tc_step("evacuate vm before scale up/down")
        # evacuate the vm
    elif action == "cold_migrate_scale_up_down":
        LOG.tc_step("cold migrate vm before scale up/down")
        vm_helper.perform_action_on_vm(vm_id=vm_id, action="cold_migrate")
    elif action == "live_migrate_scale_up_down":
        LOG.tc_step("live migrate vm before scale up/down")
        vm_helper.perform_action_on_vm(vm_id=vm_id, action="live_migrate")

    # scale up now
    LOG.tc_step("Scaling up Vms")
    dd_cmd = 'dd if=/dev/zero of=/dev/null &'
    vm_ssh_1 = ssh_vm_and_send_cmd(vm_name=vm_name, vm_image_name=vm_image_name, cmd=dd_cmd)

    LOG.tc_step("Verifying the VM is scaling to 3 Vms")
    if not wait_for_scale_up_down_vm(vm_name=vm_name, expected_count=3):
        assert "Failed to scale up, expected to see 3 vms in total"

    # Kill dd first
    LOG.tc_step("Killing dd in Vm")
    vm_ssh_1.exec_cmd("pkill dd")

    LOG.tc_step("Scaling down Vms")
    # wait for vm to be deleted
    if not heat_helper.scale_down_vms(vm_name=vm_name, expected_count=1):
        assert "Scale down failed, expect to see 1 vm"

    vm_ssh_1.close()
    # delete heat stack
    LOG.tc_step("Deleting heat stack{}".format(stack_name))
    return_code, msg = heat_helper.delete_stack(stack_name=stack_name)
    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)
    # can check vm is deleted
