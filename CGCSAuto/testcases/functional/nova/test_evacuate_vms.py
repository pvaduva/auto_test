import random

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from consts.auth import Tenant
from setup_consts import P1, P2, P3
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper


storage = [
    # storage backing, [ephemeral, swap]
    ('local_image', [0, 0]),
    ('local_image', random.choice([(1, 0), (0, 1), (1, 1)])),
    ('local_lvm', [0, 0]),
    ('local_lvm', random.choice([(1, 0), (0, 1), (1, 1)])),
    ('remote', [0, 0]),
    ('remote', random.choice([(1, 0), (0, 1), (1, 1)])),
]
@fixture(scope='module', params=storage)
def flavor_(request):
    """
    Text fixture to create flavor with specific 'ephemeral', 'swap', and 'storage_backing'
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'local_disk': <0 or 1>,
         'storage': <'local_image', 'local_lvm', or 'remote'>
        }
    """
    storage = request.param[0]
    ephemeral, swap = request.param[1]
    if len(host_helper.get_hosts_by_storage_aggregate(storage_backing=storage)) < 1:
        skip("No host support {} storage backing".format(storage))

    storage_spec = {'aggregate_instance_extra_specs:storage': storage}

    flavor_id = nova_helper.create_flavor(ephemeral=ephemeral, swap=swap)[1]
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **storage_spec)

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor)

    return storage, flavor_id


@fixture(scope='module', params=['volume', 'image', 'image_with_vol'])
def vm_(request, flavor_):
    """
    Test fixture to create vm from volume, image or image_with_vol with given flavor.

    Args:
        request: pytest arg
        flavor_: flavor_ fixture which passes the created flavor based on ephemeral', 'swap', and 'storage_backing'

    Returns: vm dict as following:
        {'id': <vm_id>,
          'boot_source': <image or volume>,
          'image_with_vol': <True or False>,
          'storage': <local_image, local_lvm, or remote>,
          'local_disk': <True or False>,
          }
    """
    vm_type = request.param
    storage_type, flavor_id = flavor_
    source = 'image' if 'image' in vm_type else 'volume'

    # instance_quota = nova_helper.get_quotas('instances')
    # existing_vms = nova_helper.get_vms()
    # new_vms_allowed = instance_quota - len(existing_vms)
    # if new_vms_allowed < 1:
    #    vm_helper.delete_vm(existing_vms[0])

    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=source)[1]
    if vm_type == 'image_with_vol':
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    def delete_vms():
        vm_helper.delete_vm(vm_id=vm_id, delete_volumes=True)
    request.addfinalizer(delete_vms)

    return storage_type, vm_id


class TestEvacuateVM:
    @fixture()
    def unlock_if_locked(self, request):
        self.lock_rtn_code = None
        self.target_host = None

        def unlock():
            if self.lock_rtn_code in [0, 3]:
                host_helper.unlock_host(self.target_host)
        request.addfinalizer(unlock)

    @mark.skipif(len(nova_helper.get_hypervisor_hosts()) < 2, reason="Less than 2 hypervisor hosts on the system")
    @mark.usefixtures('unlock_if_locked')
    def test_evacuate_vm(self, vm_):
        """
        Test evacuate vm with various configs for: vm boot source, has volume attached, has local disk, storage backing

        Precondition:
            computes are pre-configured for specific test scenario. e..g, configure storage backing

        Args:
            vm_ (dict): vm created by vm_ fixture
            revert (bool): whether to revert

        Test Setups:
        - create flavor with specific 'ephemeral', 'swap', and 'storage_backing'
        - boot vm from specific boot source with specific flavor
        - (attach volume to vm in one specific scenario)

        Test Steps:
        - Cold migrate vm created by vm_ fixture
        - Assert cold migration and confirm/revert succeeded

        Skip conditions:
         - Less than two hypervisor hosts on system

        """
        storage, vm_id = vm_

        LOG.tc_step("Calculating expected result...")
        candidate_hosts = host_helper.get_up_hosts_with_storage_backing(storage)
        exp_codes = [0] if len(candidate_hosts) > 1 else [1, 4]

        target_host = nova_helper.get_vm_host(vm_id=vm_id)

        code, msg = host_helper.lock_host(host=target_host, fail_ok=True, check_bf_lock=False)
        self.lock_rtn_code = code
        self.target_host = target_host

        assert code in exp_codes, msg
