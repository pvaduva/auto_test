import time
from pytest import fixture, skip, mark

from utils.tis_log import LOG
from utils.kpi import kpi_log_parser
from consts.auth import Tenant
from consts.cgcs import VMStatus
from consts.reasons import SkipHypervisor
from consts.kpi_vars import Evacuate
from consts.proj_vars import ProjVar

from keywords import vm_helper, host_helper, nova_helper, cinder_helper, system_helper, network_helper, \
    check_helper, keystone_helper, common
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
def skip_test_if_less_than_two_hosts():
    hypervisors = host_helper.get_up_hypervisors()
    if len(hypervisors) < 2:
        skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    LOG.fixture_step("Update instance and volume quota to at least 10 and 20 respectively")
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)

    return len(hypervisors)


class TestTisGuest:

    @fixture(scope='class')
    def vms_(self, add_admin_role_class):

        LOG.fixture_step("Create a flavor without ephemeral or swap disks")
        flavor_1 = nova_helper.create_flavor('flv_nolocaldisk')[1]
        ResourceCleanup.add('flavor', flavor_1, scope='class')

        LOG.fixture_step("Create a flavor with ephemeral and swap disks")
        flavor_2 = nova_helper.create_flavor('flv_localdisk', ephemeral=1, swap=512)[1]
        ResourceCleanup.add('flavor', flavor_2, scope='class')

        LOG.fixture_step("Boot vm1 from volume with flavor flv_nolocaldisk and wait for it pingable from NatBox")
        vm1_name = "vol_nolocal"
        vm1 = vm_helper.boot_vm(vm1_name, flavor=flavor_1, source='volume', cleanup='class')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm1)

        vm_host = nova_helper.get_vm_host(vm_id=vm1)

        LOG.fixture_step("Boot vm2 from volume with flavor flv_localdisk and wait for it pingable from NatBox")
        vm2_name = "vol_local"
        vm2 = vm_helper.boot_vm(vm2_name, flavor=flavor_2, source='volume', cleanup='class', avail_zone='nova',
                                vm_host=vm_host)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm2)

        LOG.fixture_step("Boot vm3 from image with flavor flv_nolocaldisk and wait for it pingable from NatBox")
        vm3_name = "image_novol"
        vm3 = vm_helper.boot_vm(vm3_name, flavor=flavor_1, source='image', cleanup='class', avail_zone='nova',
                                vm_host=vm_host)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm3)

        LOG.fixture_step("Boot vm4 from image with flavor flv_nolocaldisk and wait for it pingable from NatBox")
        vm4_name = 'image_vol'
        vm4 = vm_helper.boot_vm(vm4_name, flavor_1, source='image', cleanup='class', avail_zone='nova',
                                vm_host=vm_host)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm4)

        LOG.fixture_step("Attach volume to vm4 which was booted from image: {}.".format(vm4))
        vm_helper.attach_vol_to_vm(vm4)

        return [vm1, vm2, vm3, vm4], vm_host

    @mark.trylast
    @mark.sanity
    @mark.cpe_sanity
    def test_evacuate_vms(self, vms_):
        vms, target_host = vms_

        pre_res_sys, pre_msg_sys = system_helper.wait_for_services_enable(timeout=20, fail_ok=True)
        up_hypervisors = host_helper.get_up_hypervisors()
        pre_res_neutron, pre_msg_neutron = network_helper.wait_for_agents_alive(up_hypervisors, timeout=20,
                                                                                fail_ok=True)

        LOG.tc_step("reboot -f on vms host, ensure vms are successfully evacuated and host is recovered after reboot")
        vm_helper.evacuate_vms(host=target_host, vms_to_check=vms, wait_for_host_up=True, ping_vms=True)

        LOG.tc_step("Check rebooted host can still host vm")
        vm_helper.live_migrate_vm(vms[0], destination_host=target_host)
        vm_helper.wait_for_vm_pingable_from_natbox(vms[0])

        LOG.tc_step("Check system services and neutron agents after {} reboot".format(target_host))
        post_res_sys, post_msg_sys = system_helper.wait_for_services_enable(fail_ok=True)
        post_res_neutron, post_msg_neutron = network_helper.wait_for_agents_alive(hosts=up_hypervisors, fail_ok=True)

        assert post_res_sys, "\nPost-evac system services stats: {}\nPre-evac system services stats: {}".\
            format(post_msg_sys, pre_msg_sys)
        assert post_res_neutron, "\nPost evac neutron agents stats: {}\nPre-evac neutron agents stats: {}".\
            format(pre_msg_neutron, post_msg_neutron)


class TestVariousGuests:
    @fixture(scope='class', params=['image', 'volume'])
    def boot_source(self, request):
        return request.param

    @mark.trylast
    @mark.features('guest_os')
    @mark.parametrize('guest_os', [
        'ubuntu_14',
        'ubuntu_16',
        'centos_6',
        'centos_7',
        'opensuse_11',
        'opensuse_12',
        # 'opensuse_13',
        'rhel_6',
        'rhel_7',
        'win_2012',
        'win_2016',
        'ge_edge',
    ])
    def test_evacuate_vm(self, guest_os, boot_source):
        img_id = check_helper.check_fs_sufficient(guest_os=guest_os, boot_source=boot_source)

        source_id = img_id if boot_source == 'image' else None
        LOG.tc_step("Boot a {} VM from {}".format(guest_os, boot_source))
        vm_id = vm_helper.boot_vm(name="{}_{}".format(guest_os, boot_source), source=boot_source, source_id=source_id,
                                  guest_os=guest_os, cleanup='function')[1]

        LOG.tc_step("Wait for VM pingable from NATBox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        vm_host = nova_helper.get_vm_host(vm_id)
        LOG.tc_step("Reboot VM host {}".format(vm_host))
        vm_helper.evacuate_vms(host=vm_host, vms_to_check=vm_id, ping_vms=True)


class TestEvacKPI:
    @fixture()
    def check_alarms(self):
        pass

    @fixture(scope='class')
    def get_hosts(self, skip_test_if_less_than_two_hosts):
        if 'ixia_ports' not in ProjVar.get_var("LAB"):
            skip("this lab is not configured with ixia_ports.")

        hosts = host_helper.get_hosts_in_storage_aggregate()
        if len(hosts) < 2 or len(hosts) > 4:
            skip("Lab not suitable for this test. Too many or too few hosts with local_image backing")

        return hosts

        # router_id = network_helper.get_tenant_router()
        # is_dvr = eval(network_helper.get_router_info(router_id, field='distributed', auth_info=Tenant.ADMIN))
        #
        # def teardown():
        #     if is_dvr:
        #         LOG.fixture_step("Revert router to DVR")
        #         network_helper.update_router_distributed(router_id, distributed=True)
        # request.addfinalizer(teardown)
        #
        # if is_dvr:
        #     LOG.fixture_step("Update router to non-DVR")
        #     network_helper.update_router_distributed(router_id, distributed=False, post_admin_up_on_failure=False)

    @staticmethod
    def _prepare_test(vm1, vm2, get_hosts, with_router):
        """
        VMs:
            VM1: under test (primary tenant)
            VM2: traffic observer
        """

        vm1_host = nova_helper.get_vm_host(vm1)
        vm2_host = nova_helper.get_vm_host(vm2)
        vm1_router = network_helper.get_tenant_router(auth_info=Tenant.get_primary())
        vm2_router = network_helper.get_tenant_router(auth_info=Tenant.get_secondary())
        vm1_router_host = network_helper.get_router_info(router_id=vm1_router, field='wrs-net:host')
        vm2_router_host = network_helper.get_router_info(router_id=vm2_router, field='wrs-net:host')
        targets = list(get_hosts)

        if vm1_router_host == vm2_router_host:
            def _chk_same_router_host():
                vm1_router_host = network_helper.get_router_info(router_id=vm1_router, field='wrs-net:host')
                vm2_router_host = network_helper.get_router_info(router_id=vm2_router, field='wrs-net:host')
                return vm1_router_host == vm2_router_host
            succ, val = common.wait_for_val_from_func(False, 360, 10, _chk_same_router_host)
            assert succ, \
                "two routers are located on the same compute host, cannot run without_router test"

        if not with_router:
            """
            Setup:
                VM1 on COMPUTE-A
                ROUTER1 not on COMPUTE-A
                VM2, ROUTER2 not on COMPUTE-A
            """
            if len(get_hosts) < 3:
                skip("Lab not suitable for without_router, requires at least three hypervisors")

            LOG.tc_step("Ensure VM2, ROUTER2 not on COMPUTE-A, for simplicity, ensure they are on the same compute")
            if vm2_host != vm2_router_host:
                vm_helper.live_migrate_vm(vm_id=vm2, destination_host=vm2_router_host)
                vm2_host = nova_helper.get_vm_host(vm2)
                assert vm2_host == vm2_router_host, "live-migration failed"
            host_observer = vm2_host

            LOG.tc_step("Ensure VM1 and (ROUTER1, VM2, ROUTER2) are on different hosts")
            if vm1_router_host in targets:
                # ensure vm1_router_host is not selected for vm1
                # vm1_router_host can be backed by any type of storage
                targets.remove(vm1_router_host)
            if vm2_host in targets:
                targets.remove(vm2_host)

            if vm1_host in targets:
                host_src_evacuation = vm1_host
            else:
                assert targets, "no suitable compute for vm1, after excluding ROUTER1, VM2, ROUTER2 's hosts"
                host_src_evacuation = targets[0]
                vm_helper.live_migrate_vm(vm_id=vm1, destination_host=host_src_evacuation)
                vm1_host = nova_helper.get_vm_host(vm1)
                assert vm1_host == host_src_evacuation, "live-migration failed"

            # verify setup
            vm1_host = nova_helper.get_vm_host(vm1)
            vm2_host = nova_helper.get_vm_host(vm2)
            vm1_router_host = network_helper.get_router_info(router_id=vm1_router, field='wrs-net:host')
            vm2_router_host = network_helper.get_router_info(router_id=vm2_router, field='wrs-net:host')
            assert vm1_router_host != vm1_host and vm2_host != vm1_host and vm2_router_host != vm1_host, \
                "setup is incorrect"
        else:
            """
            Setup:
                VM1, ROUTER1 on COMPUTE-A
                VM2, ROUTER2 not on COMPUTE-A
            """
            LOG.tc_step("Ensure VM1, ROUTER1 on COMPUTE-A")

            # VM1 must be sitting on ROUTER1's host, thus vm1_router_host must be backed by local_image
            assert vm1_router_host in targets, "vm1_router_host is not backed by local_image"

            if vm1_host != vm1_router_host:
                vm_helper.live_migrate_vm(vm_id=vm1, destination_host=vm1_router_host)
                vm1_host = nova_helper.get_vm_host(vm1)
                assert vm1_host == vm1_router_host, "live-migration failed"
            host_src_evacuation = vm1_host

            LOG.tc_step("Ensure VM2, ROUTER2 not on COMPUTE-A, for simplicity, ensure they are on the same compute")
            targets.remove(host_src_evacuation)
            if vm2_host in targets:
                host_observer = vm2_host
            else:
                assert targets, "no suitable compute for vm2, after excluding COMPUTE-A"
                host_observer = targets[0]
                vm_helper.live_migrate_vm(vm_id=vm2, destination_host=host_observer)
                vm2_host = nova_helper.get_vm_host(vm2)
                assert vm2_host == host_observer, "live-migration failed"

            # verify setup
            vm1_host = nova_helper.get_vm_host(vm1)
            vm2_host = nova_helper.get_vm_host(vm2)
            vm1_router_host = network_helper.get_router_info(router_id=vm1_router, field='wrs-net:host')
            vm2_router_host = network_helper.get_router_info(router_id=vm2_router, field='wrs-net:host')
            assert vm1_host == vm1_router_host and vm2_host != vm1_host and vm2_router_host != vm1_host, \
                "setup is incorrect"

        assert vm1_host == host_src_evacuation and vm2_host == host_observer, "setup is incorrect"
        LOG.info("Evacuate: VM {} on {}, ROUTER on {}".format(vm1, vm1_host, vm1_router_host))
        LOG.info("Observer: VM {} on {}, ROUTER on {}".format(vm2, vm2_host, vm2_router_host))

        return host_src_evacuation, host_observer

    @mark.kpi
    @mark.parametrize('vm_type', [
        'virtio',
        'avp',
        'dpdk'
    ])
    def test_kpi_evacuate(self, vm_type, get_hosts, collect_kpi):
        if not collect_kpi:
            skip("KPI only test. Skip due to kpi collection is not enabled.")
        if not system_helper.is_avs() and vm_type in ('dpdk', 'avp'):
            skip('avp vif unsupported by OVS')

        def operation(vm_id_, host_):
            vm_helper.evacuate_vms(host=host_, vms_to_check=vm_id_, ping_vms=True)

        vm_test, vm_observer = vm_helper.launch_vm_pair(vm_type=vm_type, storage_backing='local_image')

        host_src_evacuation, host_observer = self._prepare_test(
            vm_test, vm_observer, get_hosts.copy(), with_router=True)
        time.sleep(60)
        with_router_kpi = vm_helper.get_traffic_loss_duration_on_operation(
            vm_test, vm_observer, operation, vm_test, host_src_evacuation)
        assert with_router_kpi > 0, "Traffic loss duration is not properly detected"
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Evacuate.NAME.format(vm_type, 'with'),
                                  kpi_val=with_router_kpi/1000, uptime=5)

        host_helper.wait_for_hosts_ready(hosts=host_src_evacuation)

        host_src_evacuation, host_observer = self._prepare_test(
            vm_test, vm_observer, get_hosts.copy(), with_router=False)
        time.sleep(60)
        without_router_kpi = vm_helper.get_traffic_loss_duration_on_operation(
            vm_test, vm_observer, operation, vm_test, host_src_evacuation)
        assert without_router_kpi > 0, "Traffic loss duration is not properly detected"
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Evacuate.NAME.format(vm_type, 'no'),
                                  kpi_val=without_router_kpi/1000, uptime=5)
