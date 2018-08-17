import os
import time

from pytest import mark

from consts.cgcs import HEAT_SCENARIO_PATH, FlavorSpec, GuestImages
from consts.proj_vars import ProjVar
from keywords import nova_helper, vm_helper, heat_helper, network_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs
from utils.tis_log import LOG


def launch_cpu_scaling_stack(vcpus, min_vcpus):
    """
        Create heat stack using VMAutoScaling.yaml for vcpu scaling
            - Verify heat stack is created sucessfully
            - Verify heat resources are created
        Args:
            vcpus: max vcpu to be used
            min_vcpus: min vcpu to be used

        Returns (tuple): (rnt_code (int), message (str))

    """

    template_name = 'VMAutoScaling.yaml'
    LOG.tc_step("Creating Heat Stack using template %s", template_name)

    stack_name = template_name.split('.')[0]
    vm_name = 'vm_cpu_scale'
    image = GuestImages.DEFAULT_GUEST
    template_path = os.path.join(ProjVar.get_var('USER_FILE_DIR'), HEAT_SCENARIO_PATH, template_name)
    key_pair = vm_helper.get_any_keypair()
    net_id = network_helper.get_mgmt_net_id()
    network = network_helper.get_net_name_from_id(net_id=net_id)

    # create a flavor with scaling enabled]
    fl_name = 'cpu_scale'
    flavor_id = nova_helper.create_flavor(vcpus=vcpus, ram=1024, root_disk=2, name=fl_name)[1]
    ResourceCleanup.add('flavor', flavor_id)
    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.MIN_VCPUS: min_vcpus}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    params_string = '-f {} -P FLAVOR={} -P KEYPAIR={} -P IMAGE={} -P VM_NAME={} -P NETWORK={} {}'.\
        format(template_path, flavor_id, key_pair, image, vm_name, network, stack_name)

    ResourceCleanup.add(resource_type='heat_stack', resource_id=stack_name)
    heat_helper.create_stack(stack_name=stack_name, params_string=params_string, fail_ok=False)

    return stack_name


@mark.usefixtures('check_alarms')
@mark.parametrize(('vcpus', 'min_vcpus', 'live_mig', 'swact'), [
    mark.priorities('nightly', 'sx_nightly')((3, 2, None, None)),
    mark.p1((3, 1, 'live_migrate', 'swact')),
])
def test_heat_cpu_scale(vcpus, min_vcpus, live_mig, swact):
    """
    Vcpu auto scale via  Heat template testing:

    Args:
        vcpus (int): Max number of vcpus to use in the flavor
        min_vcpus (Int): min number of vcpus use in  the flavor
        live_mig: trigger scale down, live-migrate and check
        swact: trigger scale down and swact anc check

    =====
    Prerequisites (skip test if not met):
        - at least two hypervisors hosts on the system

    Test Steps:
        - Create a heat stack for vcpu auto scale
        - Verify heat stack is created sucessfully
        - Verify heat resources are created
        - Verify the max number of vcpus are in use at first (after the boot)
        - Verify the vcpu goes down to min
        - Trigger a scale up (dd with in the guest)
        - Verify the number of vccpus
        - Delete Heat stack and verify resource deletion

    """
    # create the heat stack
    LOG.tc_step("Creating heat stack for auto scaling Vms")
    stack_name = launch_cpu_scaling_stack(vcpus=vcpus, min_vcpus=min_vcpus)

    # verify VM is created
    LOG.tc_step("Verifying VM is created via heat stack for vcpu scaling")
    vm_name = 'vm_cpu_scale'
    vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)
    assert vm_id, "Error:vm was not created by stack"

    GuestLogs.add(vm_id)
    # Verify Vcpus
    expt_min_cpu = min_vcpus
    expt_max_cpu = vcpus

    LOG.tc_step("Check vm vcpus in nova show is as specified in flavor")
    expt_current_cpu = expt_max_cpu
    vm_helper.wait_for_vcpu_count(vm_id, current_cpu=expt_current_cpu, min_cpu=expt_min_cpu, max_cpu=expt_max_cpu)

    LOG.tc_step("Nova scale vm cpu down to {}".format(expt_min_cpu))
    for i in range(expt_current_cpu - expt_min_cpu):
        vm_helper.scale_vm(vm_id, direction='down', resource='cpu')
        time.sleep(10)

    LOG.tc_step("Check vm cpu auto scale up/down by running/killing dd processes in vm")
    vm_helper.wait_for_auto_cpu_scale(vm_id=vm_id, expt_max=expt_max_cpu, expt_min=expt_min_cpu)

    expt_current_cpu = min_vcpus
    is_sx = system_helper.is_simplex()
    if live_mig and not is_sx:
        vm_host = nova_helper.get_vm_host(vm_id)
        LOG.tc_step("Live migrating the vm after triggering scale down")
        vm_helper.live_migrate_vm(vm_id=vm_id)
        vm_helper.wait_for_vcpu_count(vm_id, expt_current_cpu, min_cpu=expt_min_cpu, max_cpu=expt_max_cpu)

        if not vm_host == nova_helper.get_vm_host(vm_id):
            vm_helper.live_migrate_vm(vm_id=vm_id, destination_host=vm_host)
            vm_helper.wait_for_vcpu_count(vm_id, expt_current_cpu, min_cpu=expt_min_cpu, max_cpu=expt_max_cpu)

    if swact and not is_sx:
        standby = system_helper.get_standby_controller_name()
        assert standby

        LOG.tc_step("Swact active controller and ensure active controller is changed")
        host_helper.swact_host()

        LOG.tc_step("Check all services are up on active controller via sudo sm-dump")
        host_helper.wait_for_sm_dump_desired_states(controller=standby, fail_ok=False)

        vm_helper.wait_for_vcpu_count(vm_id, current_cpu=expt_current_cpu, min_cpu=expt_min_cpu, max_cpu=expt_max_cpu)

    # delete heat stack
    LOG.tc_step("Deleting heat stack{}".format(stack_name))
    return_code, msg = heat_helper.delete_stack(stack_name=stack_name)
    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)
    # can check vm is deleted

    GuestLogs.remove(vm_id)
