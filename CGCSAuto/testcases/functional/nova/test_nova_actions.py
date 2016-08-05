from pytest import mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, VMStatus

from keywords import vm_helper, nova_helper, glance_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


def id_gen(val):
    if isinstance(val, list):
        return '-'.join(val)


@mark.sanity
@mark.parametrize(('guest_os', 'cpu_pol', 'actions'), [
    mark.cpe_sanity('ubuntu', 'dedicated', ['pause', 'unpause']),
    ('ubuntu', 'shared', ['stop', 'start']),
    ('ubuntu', 'dedicated', ['auto_recover']),
    mark.cpe_sanity('cgcs-guest', 'dedicated', ['suspend', 'resume']),
    ('cgcs-guest', 'shared', ['auto_recover']),
], ids=id_gen)
def test_nova_actions(guest_os, cpu_pol, actions, ubuntu_image):
    LOG.tc_step("Create a flavor with 1 vcpu")
    flavor_id = nova_helper.create_flavor(name=cpu_pol, vcpus=1, root_disk=9)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if cpu_pol is not None:
        specs = {FlavorSpec.CPU_POLICY: cpu_pol}
        LOG.tc_step("Add following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    LOG.tc_step("Create a volume from {} image".format(guest_os))
    if guest_os == 'ubuntu':
        image_id = ubuntu_image
    else:
        image_id = glance_helper.get_image_id_from_name('cgcs-guest')
    vol_id = cinder_helper.create_volume(name='vol-' + guest_os, image_id=image_id, size=9)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot a vm from above flavor and volume")
    vm_id = vm_helper.boot_vm('nova_actions', flavor=flavor_id, source='volume', source_id=vol_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    if actions[0] == 'auto_recover':
        LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from base vm over "
                    "management and data networks")
        vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
        vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
    else:
        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_id, actions))
        for action in actions:
            vm_helper.perform_action_on_vm(vm_id, action=action)
