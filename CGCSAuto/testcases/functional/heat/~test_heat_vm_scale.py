import os

from pytest import mark, fixture, param

from consts.cgcs import HEAT_SCENARIO_PATH, FlavorSpec, GuestImages, VMStatus
from consts.proj_vars import ProjVar
from consts.timeout import VMTimeout
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper, network_helper, host_helper, system_helper


VM_SCALE_STACK = 'NestedAutoScale'


def __launch_vm_scale_stack():
    stack_name = VM_SCALE_STACK
    template_name = '{}.yaml'.format(stack_name)
    image = GuestImages.DEFAULT['guest']
    high_val = 50
    template_path = os.path.join(ProjVar.get_var('USER_FILE_DIR'), HEAT_SCENARIO_PATH, template_name)
    key_pair = vm_helper.get_default_keypair()
    net_id = network_helper.get_mgmt_net_id()
    network = network_helper.get_net_name_from_id(net_id=net_id)

    flavor_id = nova_helper.create_flavor(name='heartbeat', cleanup='module')[1]
    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor(flavor=flavor_id, **extra_specs)

    params = {'FLAVOR': flavor_id, 'KEYPAIR': key_pair, 'IMAGE': image, 'NETWORK': network, 'HIGH_VALUE': high_val}
    LOG.fixture_step("Create Heat Stack for auto scalable vms using template {}".format(template_name))
    heat_helper.create_stack(stack_name=stack_name, template=template_path, parameters=params, fail_ok=False,
                             cleanup='module')

    LOG.fixture_step("Verify first VM is created via heat stack for auto scaling")
    vm_id = vm_helper.get_vm_id_from_name(vm_name=stack_name, strict=False)

    return stack_name, vm_id


def __delete_vm_scale_stack():
    stack_name = VM_SCALE_STACK
    LOG.fixture_step("Delete heat stack{}".format(stack_name))
    heat_helper.delete_stack(stack=stack_name)

    LOG.fixture_step("Check heat vms are all deleted")
    heat_vms = vm_helper.get_vms(strict=False, name=stack_name)
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
    heat_vms = vm_helper.get_vms(strict=False, name=stack_name)
    if len(heat_vms) == 1:
        return stack_name, heat_vms[0]

    if heat_vms:
        __delete_vm_scale_stack()

    stack_name, vm_id = __launch_vm_scale_stack()
    return stack_name, vm_id


@mark.parametrize('actions', [
    param('live_migrate-cold_migrate-swact-host_reboot', marks=mark.p2),
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

    if not system_helper.is_aio_simplex():
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
        if system_helper.is_aio_simplex():
            host_helper.reboot_hosts('controller-0')
            vm_helper.wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, timeout=600, check_interval=10, fail_ok=False)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=VMTimeout.DHCP_RETRY)
        else:
            LOG.tc_step("evacuate vm before scale in/out")
            vm_host = vm_helper.get_vm_host(vm_id=vm_id)
            vm_helper.evacuate_vms(host=vm_host, vms_to_check=vm_id)

    LOG.tc_step("Wait for {} vms to auto scale out to {} after running dd in vm(s)".format(stack_name, 3))
    vm_helper.wait_for_auto_vm_scale_out(stack_name, expt_max=3)

    LOG.tc_step("Wait for {} vms to auto scale in to {} after killing dd processes in vms".format(stack_name, 1))
    vm_helper.wait_for_auto_vm_scale_in(stack_name, expt_min=1)
