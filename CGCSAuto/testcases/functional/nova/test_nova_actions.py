from pytest import mark, skip

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, VMStatus
from consts.reasons import SkipReason

from keywords import vm_helper, nova_helper, glance_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


def id_gen(val):
    if isinstance(val, list):
        return '-'.join(val)


@mark.usefixtures('ubuntu14_image')
@mark.parametrize(('guest_os', 'cpu_pol', 'actions'), [
    mark.priorities('sanity', 'cpe_sanity')(('ubuntu_14', 'dedicated', ['pause', 'unpause'])),
    mark.sanity(('ubuntu_14', 'shared', ['stop', 'start'])),
    mark.sanity(('ubuntu_14', 'dedicated', ['auto_recover'])),
    mark.priorities('sanity', 'cpe_sanity')(('cgcs-guest', 'dedicated', ['suspend', 'resume'])),
], ids=id_gen)
def test_nova_actions(guest_os, cpu_pol, actions):
    if guest_os == 'opensuse_12':
        if not cinder_helper.is_volumes_pool_sufficient(min_size=30):
            skip(SkipReason.SMALL_CINDER_VOLUMES_POOL)

    LOG.tc_step("Create a flavor with 1 vcpu")
    flavor_id = nova_helper.create_flavor(name=cpu_pol, vcpus=1, root_disk=9)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if cpu_pol is not None:
        specs = {FlavorSpec.CPU_POLICY: cpu_pol}
        LOG.tc_step("Add following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    LOG.tc_step("Create a volume from {} image".format(guest_os))
    vol_id = cinder_helper.create_volume(name='vol-' + guest_os, guest_image=guest_os)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot a vm from above flavor and volume")
    vm_id = vm_helper.boot_vm('nova_actions', flavor=flavor_id, source='volume', source_id=vol_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    LOG.tc_step("Wait for VM pingable from NATBOX")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    for action in actions:
        if action == 'auto_recover':
            LOG.tc_step(
                "Set vm to error state and wait for auto recovery complete, then verify ping from base vm over "
                "management and data networks")
            vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action on vm {}: {}".format(vm_id, action))
            vm_helper.perform_action_on_vm(vm_id, action=action)


class TestVariousGuests:

    @mark.usefixtures('ubuntu14_image',
                      'centos6_image', 'centos7_image',
                      'opensuse11_image', 'opensuse12_image',
                      # 'opensuse13_image',
                      'rhel6_image', 'rhel7_image'
    )
    @mark.parametrize(('guest_os', 'cpu_pol', 'boot_source', 'actions'), [
        ('ubuntu_14', 'dedicated', 'image', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        ('centos_6', 'dedicated', 'image', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        ('centos_7', 'dedicated', 'volume', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        # ('opensuse_13', 'dedicated', 'image', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        ('opensuse_11', 'dedicated', 'volume', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        ('opensuse_12', 'dedicated', 'volume', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        ('opensuse_12', 'dedicated', 'image', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        ('rhel_7', 'dedicated', 'volume', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
        ('rhel_6', 'dedicated', 'image', ['pause', 'unpause', 'suspend', 'resume', 'stop', 'start', 'auto_recover']),
    ], ids=id_gen)
    def test_nova_actions_various_guest(self, guest_os, cpu_pol, boot_source, actions):
        if guest_os == 'opensuse_12' and boot_source == 'volume':
            if not cinder_helper.is_volumes_pool_sufficient(min_size=30):
                skip(SkipReason.SMALL_CINDER_VOLUMES_POOL)

        LOG.tc_step("Create a flavor with 1 vcpu")
        flavor_id = nova_helper.create_flavor(name=cpu_pol, vcpus=1, guest_os=guest_os)[1]
        ResourceCleanup.add('flavor', flavor_id)

        if cpu_pol is not None:
            specs = {FlavorSpec.CPU_POLICY: cpu_pol}
            LOG.tc_step("Add following extra specs: {}".format(specs))
            nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

        source_id = None
        if boot_source == 'volume':
            LOG.tc_step("Create a volume from {} image".format(guest_os))
            code, vol_id = cinder_helper.create_volume(name='vol-' + guest_os, guest_image=guest_os, fail_ok=True)
            ResourceCleanup.add('volume', vol_id)

            assert 0 == code, "Issue occurred when creating volume"
            source_id = vol_id

        LOG.tc_step("Boot a {} vm with above flavor from {}".format(guest_os, boot_source))
        vm_id = vm_helper.boot_vm('nova_actions-{}-{}'.format(guest_os, boot_source), flavor=flavor_id,
                                  source=boot_source, source_id=source_id, guest_os=guest_os)[1]
        ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

        LOG.tc_step("Wait for VM pingable from NATBOX")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        for action in actions:
            if action == 'auto_recover':
                LOG.tc_step(
                        "Set vm to error state and wait for auto recovery complete, then verify ping from base vm over "
                        "management and data networks")
                vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
                vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
            else:
                LOG.tc_step("Perform following action on vm {}: {}".format(vm_id, action))
                vm_helper.perform_action_on_vm(vm_id, action=action)
