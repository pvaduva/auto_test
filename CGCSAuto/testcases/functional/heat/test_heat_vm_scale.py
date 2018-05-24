import os
import time

from pytest import mark, fixture

from consts.cgcs import HEAT_SCENARIO_PATH, FlavorSpec, GuestImages, VMStatus
from consts.proj_vars import ProjVar
from keywords import nova_helper, vm_helper, heat_helper, network_helper, host_helper, system_helper, common
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG

VM_SCALE_STACK = 'NestedAutoScale'


def wait_for_reject_in_heat_engine_log(vm_name, init_time, fail_ok=False, timeout=300):
    """
    This will check heat engine logs for scale down reject msg

    Test Steps:
        - Check heat-engine.log for log entries about scale down reject
        - If there were none found, wait 30 seconds for them to be generated then check for the logs again, it will
          timeout after 5 min if not found

    """
    ssh = ControllerClient.get_active_controller()

    timeout = time.time()+timeout
    expt_content = 'WRS vote rejecting stop for .*{}.*reason=Action rejected by instance'.format(vm_name)

    LOG.info("Wait for scale in reject entries in heat-engine logs")
    while time.time() < timeout:
        out = ssh.exec_cmd("""grep --color=never -E "{}" /var/log/heat/heat-engine.log | awk '$0 > "{}"'""".
                           format(expt_content, init_time), fail_ok=True)[1]
        if out:
            return True

        LOG.info("Continue to wait...")
        time.sleep(15)

    err = "Timed out waiting for expected heat engine logs within {}s. Expt: {}".\
        format(timeout, expt_content)
    if fail_ok:
        LOG.warning(err)
        return False

    assert False, err


def __launch_vm_scale_stack():
    stack_name = VM_SCALE_STACK
    template_name = '{}.yaml'.format(stack_name)
    image = GuestImages.DEFAULT_GUEST
    high_val = 50
    template_path = os.path.join(ProjVar.get_var('USER_FILE_DIR'), HEAT_SCENARIO_PATH, template_name)
    key_pair = vm_helper.get_any_keypair()
    net_id = network_helper.get_mgmt_net_id()
    network = network_helper.get_net_name_from_id(net_id=net_id)

    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')
    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    params_string = '-f {} -P FLAVOR={} -P KEYPAIR={} -P IMAGE={} -P NETWORK={} -P HIGH_VALUE={} {}'.\
        format(template_path, flavor_id, key_pair, image, network, high_val, stack_name)

    LOG.fixture_step("Create Heat Stack for auto scalable vms using template {}".format(template_name))
    heat_helper.create_stack(stack_name=stack_name, params_string=params_string, fail_ok=False, cleanup='module')

    LOG.fixture_step("Verify first VM is created via heat stack for auto scaling")
    vm_id = nova_helper.get_vm_id_from_name(vm_name=stack_name, strict=False)
    assert vm_id

    return stack_name, vm_id


def __delete_vm_scale_stack():
    stack_name = VM_SCALE_STACK
    LOG.fixture_step("Delete heat stack{}".format(stack_name))
    heat_helper.delete_stack(stack_name=stack_name)

    LOG.fixture_step("Check heat vms are all deleted")
    heat_vms = nova_helper.get_vms(strict=False, name=stack_name)
    assert not heat_vms, "Heat vms still exist on system after heat stack deletion"


@fixture(scope='module', autouse=True)
def delete_vm_scaling_stack(request):
    """
        Create heat stack using NestedAutoScale.yaml for vm scaling
            - Verify heat stack is created successfully
            - Verify heat resources are created
    """

    def delete_stack():
        __delete_vm_scale_stack()
    request.addfinalizer(delete_stack)


@fixture(scope='function')
def vm_scaling_stack():
    stack_name = VM_SCALE_STACK
    heat_vms = nova_helper.get_vms(strict=False, name=stack_name)
    if len(heat_vms) == 1:
        return stack_name, heat_vms[0]

    if heat_vms:
        __delete_vm_scale_stack()

    stack_name, vm_id = __launch_vm_scale_stack()
    return stack_name, vm_id


@mark.parametrize(('scale_up_to', 'action'), [
    mark.priorities('nightly', 'sx_nightly')((2, None)),
    (3, 'vote_no_to_stop'),
])
def test_heat_vm_auto_scale(vm_scaling_stack, scale_up_to, action):

    """
    Test VM auto scaling :
        Create heat stack for auto scaling using NestedAutoScale.yaml, scale in/out/reject.

    Test Steps:
        - Create a heat stack for auto scaling vm (NestedAutoScale)
        - Verify heat stack is created successfully
        - Verify heat resources are created
        - trigger auto scale by boosting cpu usage in the vm (using dd)
        - verify it scale up to the given number of vms
        - (place a /tmp/vote_no_to_stop in one of the vm)
        - trigger scale down by killing dd processes in the vm(s)
        - (verify the vm scale down to 2 and the vm with the vote_no_stop is rejecting the scale down)
        - (check the log entries for the scale down reject msg)
        - (remove the vote_no_to_stop file in the vm)
        - (verify the vm scale down to (1))
        - Delete Heat stack and verify resource deletion
    """
    vm_name, vm_id = vm_scaling_stack

    func = init_time = None
    kwargs = {}
    msg = ''
    expt_min = 1
    if action == 'vote_no_to_stop':
        func = vm_helper.touch_remove_vm_voting_file
        kwargs = {'filename': action}
        msg = ', and touch vote_no_to_stop in second vm'
        expt_min = 2
        init_time = common.get_date_in_format(date_format='%Y-%m-%d %T')

    LOG.tc_step("Wait for {} vms to scale out to {} after running dd in vm(s){}".format(vm_name, scale_up_to, msg))
    second_vm = vm_helper.wait_for_auto_vm_scale_out(vm_name, expt_max=scale_up_to, func_second_vm=func, **kwargs)
    if action == 'vote_no_to_stop':
        assert second_vm, "vm id for second vm is not returned, check automation"
        GuestLogs.add(second_vm)

    LOG.tc_step("Wait for {} vms to scale in to {} after killing dd processes in vm(s)".format(vm_name, expt_min))
    vm_helper.wait_for_auto_vm_scale_in(vm_name=vm_name, expt_min=expt_min)

    if action == 'vote_no_to_stop':
        LOG.tc_step("Check scale-in rejected due to vote_no_to_stop via heat-engine.log")
        wait_for_reject_in_heat_engine_log(vm_name=vm_name, init_time=init_time)
        LOG.tc_step("Remove voting file in second vm and Wait for {} vms to scale in to {}".format(vm_name, 1))
        vm_helper.touch_remove_vm_voting_file(vm_id=second_vm, touch=False, filename=action)
        vm_helper.wait_for_auto_vm_scale_in(vm_name=vm_name, expt_min=1)
        GuestLogs.remove(second_vm)


@mark.parametrize('actions', [
    mark.p2('live_migrate-cold_migrate-swact-host_reboot'),
])
def test_heat_vm_scale_after_actions(vm_scaling_stack, actions):

    """
    Test VM auto scaling with swact:
        Create heat stack for auto scaling using NestedAutoScale.yaml,  swact and perform vm scale up and down.

    Test Steps:
        - Create a heat stack for auto scaling vm ()
        - Verify heat stack is created successfully
        - Verify heat resources are created
        - live migrate the vm if not sx
        - cold migrate the vm if not sx
        - swact if not sx
        - reboot -f vm host
        - trigger auto scale by boosting cpu usage in the vm (using dd)
        - verify it scale up to the max number of vms (3)
        - trigger scale down by killing dd in the vm
        - verify the vm scale down to min number (1)
        - Delete Heat stack and verify resource deletion
    """
    stack_name, vm_id = vm_scaling_stack
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    if not system_helper.is_simplex():
        actions = actions.split('-')
        if "swact" in actions:
            LOG.tc_step("Swact before scale in/out")
            host_helper.swact_host()

        if "live_migrate" in actions:
            LOG.tc_step("live migrate vm before scale in/out")
            vm_helper.live_migrate_vm(vm_id)

        if "cold_migrate" in actions:
            LOG.tc_step("cold migrate vm before scale in/out")
            vm_helper.cold_migrate_vm(vm_id)

    if "host_reboot" in actions:
        if system_helper.is_simplex():
            host_helper.reboot_hosts('controller-0', wait_for_reboot_finish=True)
            vm_helper.wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, timeout=600, check_interval=10, fail_ok=False)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        else:
            LOG.tc_step("evacuate vm before scale in/out")
            vm_host = nova_helper.get_vm_host(vm_id=vm_id)
            vm_helper.evacuate_vms(host=vm_host, vms_to_check=vm_id)

    LOG.tc_step("Wait for {} vms to auto scale out to {} after running dd in vm(s)".format(stack_name, 3))
    vm_helper.wait_for_auto_vm_scale_out(stack_name, expt_max=3)

    LOG.tc_step("Wait for {} vms to auto scale in to {} after killing dd processes in vms".format(stack_name, 1))
    vm_helper.wait_for_auto_vm_scale_in(stack_name, expt_min=1)
