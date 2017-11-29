import os
import time

from pytest import mark, fixture

from consts.cgcs import HEAT_SCENARIO_PATH, FlavorSpec, GuestImages
from consts.filepaths import WRSROOT_HOME
from keywords import nova_helper, vm_helper, heat_helper, network_helper
from testfixtures.fixture_resources import ResourceCleanup
from utils.tis_log import LOG


def launch_cpu_scaling_stack(vcpus, min_vcpus, con_ssh=None, auth_info=None):
    """
        Create heat stack using VMAutoScaling.yaml for vcpu scaling
            - Verify heat stack is created sucessfully
            - Verify heat resources are created
        Args:
            vcpus: max vcpu to be used
            min_vcpus: min vcpu to be used
            con_ssh (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.

        Returns (tuple): (rnt_code (int), message (str))

    """

    fail_ok = False
    template_name = 'VMAutoScaling.yaml'
    t_name, yaml = template_name.split('.')
    stack_name = t_name
    vm_name = 'vm_cpu_scale'

    template_path = os.path.join(WRSROOT_HOME, HEAT_SCENARIO_PATH, template_name)
    cmd_list = ['-f %s ' % template_path]

    # create a flavor with Hearbeat enabled]
    fl_name = 'cpu_scale'
    flavor_id = nova_helper.create_flavor(vcpus=vcpus, ram=1024, root_disk=2, name=fl_name)[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.MIN_VCPUS: min_vcpus}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    cmd_list.append("-P FLAVOR=%s " % flavor_id)

    key_pair = vm_helper.get_any_keypair()
    cmd_list.append("-P KEYPAIR=%s " % key_pair)
    # image = 'cgcs-guest'
    image = GuestImages.DEFAULT_GUEST
    cmd_list.append("-P IMAGE=%s " % image)

    cmd_list.append("-P VM_NAME=%s " % vm_name)

    net_id = network_helper.get_mgmt_net_id()
    network = network_helper.get_net_name_from_id(net_id=net_id)
    cmd_list.append("-P NETWORK=%s " % network)

    cmd_list.append(" %s" % stack_name)
    params_string = ''.join(cmd_list)

    LOG.tc_step("Creating Heat Stack..using template %s", template_name)

    code, msg = heat_helper.create_stack(stack_name=stack_name, params_string=params_string, fail_ok=fail_ok)
    assert code == 0, "Failed to create heat stack"

    # add the heat stack name for deleteion on failure
    ResourceCleanup.add(resource_type='heat_stack', resource_id=t_name)

    return 0, stack_name


def wait_for_cpu_to_scale(vm_id, min_cpu, current_cpu, max_cpu, time_out=600, check_interval=3,
                          con_ssh=None, auth_info=None):

    end_time = time.time() + time_out
    while time.time() < end_time:
        actual_vcpus = eval(nova_helper.get_vm_nova_show_value(vm_id=vm_id, field='wrs-res:vcpus', con_ssh=con_ssh,
                                                               use_openstack_cmd=True))
        if [min_cpu, current_cpu, max_cpu] == actual_vcpus:
            return True

        time.sleep(check_interval)

    msg = "VM vcpu numbers{} did not go to expected numbers {} " \
          "within timeout".format(vm_id, [min_cpu, current_cpu, max_cpu])
    LOG.warning(msg)
    return False


def scale_up_vcpu(vm_name=None,  con_ssh=None, auth_info=None,cpu_num=1):
    """
    Returns:

    """
    # create a trigger for auto scale by login to vm and issue dd cmd
    vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)

    LOG.info("Boosting cpu usage for vm {} using 'dd'".format(vm_id))
    dd_cmd = 'dd if=/dev/zero of=/dev/null &'
    image = GuestImages.DEFAULT_GUEST

    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id, vm_image_name=image, close_ssh=False) as vm_ssh:
        VM_SSHS.append(vm_ssh)
        vm_ssh.exec_cmd(cmd=dd_cmd, fail_ok=False)

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


@mark.usefixtures('check_alarms')
@mark.parametrize(('vcpus', 'min_vcpus'), [
    mark.p1((3, 1)),
    mark.priorities('nightly', 'sx_nightly')((3, 1)),
])
def test_heat_cpu_scale(vcpus, min_vcpus):
    """
    Vcpu auto scale via  Heat template testing:

    Args:
        vcpus (int): Max number of vcpus to use in the flavor
        min_vcpus (Int): min number of vcpus use in  the flavor

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
    return_code, msg = launch_cpu_scaling_stack(vcpus=vcpus, min_vcpus=min_vcpus)

    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)

    stack_name = msg
    # verify VM is created
    LOG.tc_step("Verifying VM is created via heat stack for vcpu scaling")
    vm_name = 'vm_cpu_scale'
    vm_id = nova_helper.get_vm_id_from_name(vm_name=vm_name, strict=False)
    if not vm_id:
        assert "Error:vm was not created by stack"

    # Verify Vcpus
    LOG.tc_step("Check vm vcpus in nova show is as specified in flavor")
    expt_min_cpu =  min_vcpus
    expt_max_cpu = expt_current_cpu = vcpus
    if not wait_for_cpu_to_scale(vm_id, expt_min_cpu, expt_current_cpu, expt_max_cpu):
        assert "Vcpu did not go to max number {} after initial boot".format(expt_max_cpu)

    # wait for scale down to min
    LOG.tc_step("Check vm vcpus gone to min vcpu")
    expt_min_cpu = expt_current_cpu= min_vcpus
    expt_max_cpu = vcpus
    if not wait_for_cpu_to_scale(vm_id, expt_min_cpu, expt_current_cpu, expt_max_cpu):
        assert "Failed to go to min vcpu {} after inital boot".format(min_vcpus)


    # scale up now
    LOG.tc_step("Scaling up vcpu")
    if not scale_up_vcpu(vm_name=vm_name):
        assert "Failed to scale up, expected to see 3 vms in total"

    # check if vcpu has gone up by one
    expt_current_cpu += 1

    if not wait_for_cpu_to_scale(vm_id, expt_min_cpu, expt_current_cpu, expt_max_cpu):
        assert "Failed to reach {} vcpus".format(expt_current_cpu)

    # scale up to maximum

    # delete heat stack
    LOG.tc_step("Deleting heat stack{}".format(stack_name))
    return_code, msg = heat_helper.delete_stack(stack_name=stack_name)
    assert 0 == return_code, "Expected return code {}. Actual return code: {}; details: {}".format(0, return_code, msg)
    # can check vm is deleted

