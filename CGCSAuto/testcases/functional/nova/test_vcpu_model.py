from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from keywords import nova_helper, vm_helper, host_helper, cinder_helper


@fixture(scope='module', autouse=True)
def flavor_and_volume(request):
    """
    Create basic flavor and volume to be used by test cases as test setup, at the beginning of the test module.
    Delete the created flavor and volume as test teardown, at the end of the test module.
    """
    flavor = nova_helper.create_flavor()[1]
    volume = cinder_helper.create_volume(name='vol-vcpu_model')[1]

    def delete():
        cinder_helper.delete_volumes(volume, check_first=False)
        nova_helper.delete_flavors(flavor)
    request.addfinalizer(delete)

    return flavor, volume

vm_to_del = None   # type: str
@fixture(scope='function', autouse=True)
def delete_vm(request):
    """
    Delete the created vm after each test, without deleting the attached volume which can be used for next test case.
    """
    def del_vm():
        vm_helper.delete_vms(vm_to_del, check_first=False, delete_volumes=False)
    request.addfinalizer(del_vm)


@mark.parametrize('vcpu_model', [
    'Conroe',
    'Penryn',
    'Nehalem',
    'Westmere',
    'SandyBridge',
    'Haswell',
    'Broadwell',
    'Broadwell-noTSX',
])
def test_vm_vcpu_model(flavor_and_volume, vcpu_model):
    """
    Test vcpu model specified in flavor will be applied to vm. In case host does not support specified vcpu model,
    proper error message should be displayed in nova show.

    Args:
        flavor_and_volume (tuple): flavor and volume to create vm from
        vcpu_model (str): vcpu model under test

    Setup:
        - Create a basic flavor and volume (module level)
    Test Steps:
        - Set flavor extra spec to given vcpu model
        - Boot a vm from volume using the flavor
        - Verify vcpu model specified in flavor is used by vm. Or proper error message is included if host does not
            support specified vcpu model.
    Teardown:
        - Delete created vm
        - Delete created volume and flavor (module level)

    """
    flavor_id, volume_id = flavor_and_volume
    LOG.tc_step("Set flavor extra specs to given vcpu model.")
    flavor_spec = FlavorSpec.VCPU_MODEL
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **{flavor_spec: vcpu_model})

    LOG.tc_step("Boot a vm with VCPU Model set to {} in flavor.".format(vcpu_model))
    code, vm, msg = vm_helper.boot_vm(flavor=flavor_id, source='volume', source_id=volume_id, fail_ok=True)
    global vm_to_del
    vm_to_del = vm

    if code == 0:
        host = nova_helper.get_vm_host(vm)
        LOG.tc_step("Check vcpu model successfully applied to vm")
        with host_helper.ssh_to_host(host) as host_ssh:
            code, output = host_ssh.exec_cmd("ps aux | grep -i {}".format(vm))
        assert ' -cpu {} '.format(vcpu_model).lower() in output.lower(), 'cpu_model {} not found for vm {}'.\
            format(vcpu_model, vm)
    else:
        LOG.tc_step("Check vm in error state due to vcpu model unsupported by hosts.")
        assert code == 1, "boot vm cli exit code is not 1. Actual fail reason: {}".format(msg)
        expt_fault = "No valid host was found.*vcpu_model.*required.*"
        res_bool, vals = vm_helper.wait_for_vm_values(vm, 10, regex=True, strict=False, status='ERROR', fault=expt_fault)
        assert res_bool, "VM did not reach expected error state. Actual: {}".format(vals)
