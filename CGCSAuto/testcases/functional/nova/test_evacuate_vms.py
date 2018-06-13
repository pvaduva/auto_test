import re

from pytest import fixture, skip, mark

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, VMStatus, InstanceTopology
from consts.reasons import SkipStorageBacking, SkipHypervisor

from keywords import vm_helper, host_helper, nova_helper, cinder_helper, system_helper, check_helper
from testfixtures.fixture_resources import ResourceCleanup

from testfixtures.pre_checks_and_configs import check_numa_num
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
def update_quotas(add_admin_role_module):
    LOG.fixture_step("Update instance and volume quota to at least 10 and 20 respectively")
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)


def touch_files_under_vm_disks(vm_id, ephemeral, swap, vm_type, disks):

    expt_len = 1 + int(bool(ephemeral)) + int(bool(swap)) + (1 if 'with_vol' in vm_type else 0)

    LOG.info("\n--------------------------Auto mount non-root disks if any")
    mounts = vm_helper.auto_mount_vm_disks(vm_id=vm_id, disks=disks)
    assert expt_len == len(mounts)

    if bool(swap):
        mounts.remove('none')

    LOG.info("\n--------------------------Create files under vm disks: {}".format(mounts))
    file_paths, content = vm_helper.touch_files(vm_id=vm_id, file_dirs=mounts)
    return file_paths, content


def check_vm_numa_topology(vm_id, numa_nodes, numa_node0, numa_node1):
    """

    Args:
        vm_id:
        numa_nodes (None|int):
        numa_node0 (None|int):
        numa_node1 (None|int):

    Returns:

    """
    LOG.tc_step("Verify cpu info for vm {} via vm-topology.".format(vm_id))
    actual_node_vals = vm_helper.get_vm_host_and_numa_nodes(vm_id)[1]
    if not numa_nodes:
        nodes = 1
    else:
        nodes = numa_nodes

    if nodes == 2 and numa_node0 is None and numa_node1 is None:
        expected_node_vals = [0, 1]
    elif nodes == 1 and numa_node0 is None:
        expected_node_vals = [0]
    else:
        expected_node_vals = [int(val) for val in [numa_node0, numa_node1] if val is not None]

    # Each numa node will have an entry for given instance, thus number of entries should be the same as number of
    # numa nodes for the vm
    assert nodes == len(actual_node_vals)
    assert expected_node_vals == actual_node_vals, \
        "Individual NUMA node value(s) for vm {} is different than numa_node setting in flavor".format(vm_id)


class TestDefaultGuest:

    @fixture(scope='class', autouse=True)
    def skip_test_if_less_than_two_hosts(self):
        if len(host_helper.get_up_hypervisors()) < 2:
            skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    @mark.parametrize('storage_backing', [
        'local_image',
        'local_lvm',
        'remote',
    ])
    def test_evacuate_vms_with_inst_backing(self, storage_backing):
        """
        Test evacuate vms with various vm storage configs and host instance backing configs

        Args:
            storage_backing: storage backing under test
            add_admin_role_class (None): test fixture to add admin role to primary tenant

        Skip conditions:
            - Less than two hosts configured with storage backing under test

        Setups:
            - Add admin role to primary tenant (module)

        Test Steps:
            - Create flv_rootdisk without ephemeral or swap disks, and set storage backing extra spec
            - Create flv_ephemswap with ephemeral AND swap disks, and set storage backing extra spec
            - Boot following vms on same host and wait for them to be pingable from NatBox:
                - Boot vm1 from volume with flavor flv_rootdisk
                - Boot vm2 from volume with flavor flv_localdisk
                - Boot vm3 from image with flavor flv_rootdisk
                - Boot vm4 from image with flavor flv_rootdisk, and attach a volume to it
                - Boot vm5 from image with flavor flv_localdisk
            - sudo reboot -f on vms host
            - Ensure evacuation for all 5 vms are successful (vm host changed, active state, pingable from NatBox)

        Teardown:
            - Delete created vms, volumes, flavors
            - Remove admin role from primary tenant (module)

        """
        hosts = host_helper.get_hosts_in_storage_aggregate(storage_backing=storage_backing)
        if len(hosts) < 2:
            skip(SkipStorageBacking.LESS_THAN_TWO_HOSTS_WITH_BACKING.format(storage_backing))

        target_host = hosts[0]

        LOG.tc_step("Create a flavor without ephemeral or swap disks")
        flavor_1 = nova_helper.create_flavor('flv_rootdisk', storage_backing=storage_backing,
                                             check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor_1, scope='function')

        LOG.tc_step("Create another flavor with ephemeral and swap disks")
        flavor_2 = nova_helper.create_flavor('flv_ephemswap', ephemeral=1, swap=512, storage_backing=storage_backing,
                                             check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor_2, scope='function')

        LOG.tc_step("Boot vm1 from volume with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm1_name = "vol_root"
        vm1 = vm_helper.boot_vm(vm1_name, flavor=flavor_1, source='volume', avail_zone='nova', vm_host=target_host,
                                cleanup='function')[1]

        vms_info = {vm1: {'ephemeral': 0,
                          'swap': 0,
                          'vm_type': 'volume',
                          'disks': vm_helper.get_vm_devices_via_virsh(vm1)}}
        vm_helper.wait_for_vm_pingable_from_natbox(vm1)

        LOG.tc_step("Boot vm2 from volume with flavor flv_localdisk and wait for it pingable from NatBox")
        vm2_name = "vol_ephemswap"
        vm2 = vm_helper.boot_vm(vm2_name, flavor=flavor_2, source='volume', avail_zone='nova', vm_host=target_host,
                                cleanup='function')[1]

        vm_helper.wait_for_vm_pingable_from_natbox(vm2)
        vms_info[vm2] = {'ephemeral': 1,
                         'swap': 512,
                         'vm_type': 'volume',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm2)}

        LOG.tc_step("Boot vm3 from image with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm3_name = "image_root"
        vm3 = vm_helper.boot_vm(vm3_name, flavor=flavor_1, source='image', avail_zone='nova', vm_host=target_host,
                                cleanup='function')[1]

        vm_helper.wait_for_vm_pingable_from_natbox(vm3)
        vms_info[vm3] = {'ephemeral': 0,
                         'swap': 0,
                         'vm_type': 'image',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm3)}

        LOG.tc_step("Boot vm4 from image with flavor flv_rootdisk, attach a volume to it and wait for it "
                    "pingable from NatBox")
        vm4_name = 'image_root_attachvol'
        vm4 = vm_helper.boot_vm(vm4_name, flavor_1, source='image', avail_zone='nova', vm_host=target_host,
                                cleanup='function')[1]

        vol = cinder_helper.create_volume(bootable=False)[1]
        ResourceCleanup.add('volume', vol, scope='function')
        vm_helper.attach_vol_to_vm(vm4, vol_id=vol, mount=False)

        vm_helper.wait_for_vm_pingable_from_natbox(vm4)
        vms_info[vm4] = {'ephemeral': 0,
                         'swap': 0,
                         'vm_type': 'image_with_vol',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm4)}

        LOG.tc_step("Boot vm5 from image with flavor flv_localdisk and wait for it pingable from NatBox")
        vm5_name = 'image_ephemswap'
        vm5 = vm_helper.boot_vm(vm5_name, flavor_2, source='image', avail_zone='nova', vm_host=target_host,
                                cleanup='function')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm5)
        vms_info[vm5] = {'ephemeral': 1,
                         'swap': 512,
                         'vm_type': 'image',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm5)}

        LOG.tc_step("Check all VMs are booted on {}".format(target_host))
        vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=target_host)
        vms = [vm1, vm2, vm3, vm4, vm5]
        assert set(vms) <= set(vms_on_host), "VMs booted on host: {}. Current vms on host: {}".format(vms, vms_on_host)

        for vm_ in vms:
            LOG.tc_step("Touch files under vm disks {}: {}".format(vm_, vms_info[vm_]))
            file_paths, content = touch_files_under_vm_disks(vm_, **vms_info[vm_])
            vms_info[vm_]['file_paths'] = file_paths
            vms_info[vm_]['content'] = content

        LOG.tc_step("Reboot target host {}".format(target_host))
        vm_helper.evacuate_vms(host=target_host, vms_to_check=vms, ping_vms=True)

        LOG.tc_step("Check files after evacuation")
        for vm_ in vms:
            LOG.info("--------------------Check files for vm {}".format(vm_))
            check_helper.check_vm_files(vm_id=vm_, vm_action='evacuate', storage_backing=storage_backing,
                                        prev_host=target_host, **vms_info[vm_])
        vm_helper.ping_vms_from_natbox(vms)

    @fixture(scope='function')
    def check_hosts(self):
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
        if len(hosts) < 2:
            skip("at least two hosts with the same storage backing are required")

        acceptable_hosts = []
        for host in hosts:
            numa_num = len(host_helper.get_host_procs(host))
            if numa_num > 1:
                acceptable_hosts.append(host)
                if len(acceptable_hosts) == 2:
                    break
        else:
            skip("at least two hosts with multiple numa nodes are required")

        target_host = acceptable_hosts[0]
        return target_host

    # TC6500
    def test_evacuate_numa_setting(self, check_hosts):
        """
            Test evacuate vms with various vm numa node settings

            Skip conditions:
                - Less than two hosts with common storage backing with 2 numa nodes

            Setups:
                - Check if there are enough hosts with a common backing and 2 numa nodes to execute test
                - Add admin role to primary tenant (module)

            Test Steps:
                - Create three flavors:
                    - First flavor has a dedicated cpu policy, 1 vcpu set on 1 numa node and the vm's numa_node0 is set
                      to host's numa_node0
                    - Second flavor has a dedicated cpu policy, 1 vcpu set on 1 numa node and the vm's numa_node0 is set
                      to host's numa_node1
                    - Third flavor has a dedicated cpu policy, 2 vcpus split between 2 different numa nodes and the vm's
                      numa_node0 is set to host's numa_node0 and vm's numa_node1 is set to host's numa_node1
                - Boot vms from each flavor on same host and wait for them to be pingable from NatBox
                - Check that the vm's topology is correct
                - sudo reboot -f on vms host
                - Ensure evacuation for all 5 vms are successful (vm host changed, active state, pingable from NatBox)
                - Check that the vm's topology is still correct following the evacuation

            Teardown:
                - Delete created vms, volumes, flavors
                - Remove admin role from primary tenant (module)

            """

        target_host = check_hosts

        LOG.tc_step("Create flavor with 1 vcpu, set on host numa node 0")
        flavor1 = nova_helper.create_flavor('numa_vm', vcpus=1)[1]
        ResourceCleanup.add('flavor', flavor1, scope='function')
        extra_specs1 = {FlavorSpec.CPU_POLICY: 'dedicated',
                        FlavorSpec.NUMA_NODES: 1,
                        FlavorSpec.NUMA_0: 0
                        }
        nova_helper.set_flavor_extra_specs(flavor1, **extra_specs1)

        LOG.tc_step("Create flavor with 1 vcpu, set on host numa node 1")
        flavor2 = nova_helper.create_flavor('numa_vm', vcpus=1)[1]
        ResourceCleanup.add('flavor', flavor2, scope='function')
        extra_specs2 = {FlavorSpec.CPU_POLICY: 'dedicated',
                        FlavorSpec.NUMA_NODES: 1,
                        FlavorSpec.NUMA_0: 1
                        }
        nova_helper.set_flavor_extra_specs(flavor2, **extra_specs2)

        LOG.tc_step("Create flavor with 1 vcpu, set on host numa node 1")
        flavor3 = nova_helper.create_flavor('numa_vm', vcpus=2)[1]
        ResourceCleanup.add('flavor', flavor3, scope='function')
        extra_specs3 = {FlavorSpec.CPU_POLICY: 'dedicated',
                        FlavorSpec.NUMA_NODES: 2,
                        FlavorSpec.NUMA_0: 1,
                        FlavorSpec.NUMA_1: 0
                        }
        nova_helper.set_flavor_extra_specs(flavor3, **extra_specs3)

        LOG.tc_step("Boot vm with cpu on host node 0")
        vm1 = vm_helper.boot_vm(flavor=flavor1, avail_zone='nova', vm_host=target_host, cleanup='function')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm1)
        check_vm_numa_topology(vm1, 1, 0, None)

        LOG.tc_step("Boot vm with cpu on host node 1")
        vm2 = vm_helper.boot_vm(flavor=flavor2, avail_zone='nova', vm_host=target_host, cleanup='function')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm2)
        check_vm_numa_topology(vm2, 1, 1, None)

        LOG.tc_step("Boot vm with cpus on host nodes 0 and 1, (virtual nodes are switched here)")
        vm3 = vm_helper.boot_vm(flavor=flavor3, avail_zone='nova', vm_host=target_host, cleanup='function')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm3)
        check_vm_numa_topology(vm3, 2, 1, 0)

        LOG.tc_step("Check all VMs are booted on {}".format(target_host))
        vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=target_host)
        vms = [vm1, vm2, vm3]
        assert set(vms) <= set(vms_on_host), "VMs booted on host: {}. Current vms on host: {}".format(vms, vms_on_host)

        vm_helper.evacuate_vms(target_host, vms, ping_vms=True)

        check_vm_numa_topology(vm1, 1, 0, None)
        check_vm_numa_topology(vm2, 1, 1, None)
        check_vm_numa_topology(vm3, 2, 1, 0)


class TestOneHostAvail:
    @fixture(scope='class')
    def get_zone(self, request, add_cgcsauto_zone):
        if system_helper.is_simplex():
            zone = 'nova'
            return zone

        zone = 'cgcsauto'
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
        host = hosts[0]
        LOG.fixture_step('Select host {} with backing {}'.format(host, storage_backing))
        nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=[host])

        def remove_hosts_from_zone():
            nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
        request.addfinalizer(remove_hosts_from_zone)
        return zone

    @mark.sx_sanity
    def test_reboot_only_host(self, get_zone):
        zone = get_zone

        LOG.tc_step("Launch 5 vms in {} zone".format(zone))
        vms = vm_helper.boot_vms_various_types(avail_zone=zone, cleanup='function')
        target_host = nova_helper.get_vm_host(vm_id=vms[0])
        for vm in vms[1:]:
            vm_host = nova_helper.get_vm_host(vm)
            assert target_host == vm_host, "VMs are not booted on same host"

        LOG.tc_step("Reboot -f from target host {}".format(target_host))
        HostsToRecover.add(target_host)
        host_helper.reboot_hosts(target_host)

        LOG.tc_step("Check vms are in Active state after host come back up")
        res, active_vms, inactive_vms = vm_helper.wait_for_vms_values(vms=vms, values=VMStatus.ACTIVE, timeout=600)

        vms_host_err = []
        for vm in vms:
            if nova_helper.get_vm_host(vm) != target_host:
                vms_host_err.append(vm)

        assert not vms_host_err, "Following VMs are not on the same host {}: {}\nVMs did not reach Active state: {}". \
            format(target_host, vms_host_err, inactive_vms)

        assert not inactive_vms, "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)

        LOG.tc_step("Check VMs are pingable from NatBox after evacuation")
        vm_helper.wait_for_vm_pingable_from_natbox(vms)
