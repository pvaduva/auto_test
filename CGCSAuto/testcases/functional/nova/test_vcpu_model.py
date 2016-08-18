from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from consts.cli_errs import VCPUSchedulerErr
from keywords import nova_helper, vm_helper, host_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module', autouse=True)
def flavor_and_volume():
    """
    Create basic flavor and volume to be used by test cases as test setup, at the beginning of the test module.
    Delete the created flavor and volume as test teardown, at the end of the test module.
    """
    flavor = nova_helper.create_flavor(name='vcpu_model')[1]
    volume = cinder_helper.create_volume(name='vol-vcpu_model')[1]
    ResourceCleanup.add('volume', volume, scope='module')
    ResourceCleanup.add('flavor', flavor, scope='module')
    return flavor, volume


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
    code, vm, msg, vol = vm_helper.boot_vm(flavor=flavor_id, source='volume', source_id=volume_id, fail_ok=True)
    if vm:
        ResourceCleanup.add('vm', vm, 'function', False)

    if code == 0:
        host = nova_helper.get_vm_host(vm)
        LOG.tc_step("Check vcpu model successfully applied to vm")
        with host_helper.ssh_to_host(host) as host_ssh:
            code, output = host_ssh.exec_cmd("ps aux | grep --color='never' -i {}".format(vm), fail_ok=False)

        if vcpu_model == 'Haswell':
            assert ' -cpu  haswell ' in output.lower() or ' -cpu haswell-notsx ' in output.lower(), \
                'cpu_model Haswell or Haswell-noTSX not found for vm {}'.format(vm)
        else:
            assert ' -cpu {} '.format(vcpu_model).lower() in output.lower(), 'cpu_model {} not found for vm {}'.\
                format(vcpu_model, vm)
    else:
        LOG.tc_step("Check vm in error state due to vcpu model unsupported by hosts.")
        assert 1 == code, "boot vm cli exit code is not 1. Actual fail reason: {}".format(msg)

        expt_fault = VCPUSchedulerErr.CPU_MODEL_UNAVAIL
        res_bool, vals = vm_helper.wait_for_vm_values(vm, 10, regex=True, strict=False, status='ERROR', fault=expt_fault)
        assert res_bool, "VM did not reach expected error state. Actual: {}".format(vals)
