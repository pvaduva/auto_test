import time
from pytest import fixture, skip, mark

from utils.tis_log import LOG
from utils.kpi import kpi_log_parser
from consts.auth import Tenant
from consts.cgcs import VMStatus
from consts.reasons import SkipHypervisor
from consts.kpi_vars import Evacuate

from keywords import vm_helper, host_helper, nova_helper, cinder_helper, system_helper, network_helper, \
    check_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
def skip_test_if_less_than_two_hosts():
    if len(host_helper.get_up_hypervisors()) < 2:
        skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    LOG.fixture_step("Update instance and volume quota to at least 10 and 20 respectively")
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)


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
        HostsToRecover.add(vm_host, scope='function')
        host_helper.reboot_hosts(vm_host, wait_for_reboot_finish=False)

        LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
        vm_helper.wait_for_vm_values(vm_id, fail_ok=True, timeout=120, status=[VMStatus.ERROR, VMStatus.REBUILD])

        LOG.tc_step("Check vms are in Active state and moved to other host after host reboot")
        vm_helper.wait_for_vm_values(vm_id, timeout=300, fail_ok=False, status=[VMStatus.ACTIVE])

        post_vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host != post_vm_host, "VM host did not change upon host reboot even though VM is in Active state."

        LOG.tc_step("Check VM still pingable from Natbox after evacuated to other host")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


class TestEvacKPI:

    @fixture()
    def check_alarms(self):
        pass

    @fixture(scope='class')
    def get_hosts(self, add_admin_role_class, request):
        hosts = host_helper.get_hosts_by_storage_aggregate()
        if len(hosts) < 2 or len(hosts) > 4:
            skip("Lab not suitable for this test. Too many or too few hosts with local_image backing")

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

        hosts_to_lock = hosts[2:]
        for host in hosts_to_lock:
            HostsToRecover.add(host, scope='class')
            host_helper.lock_host(host=host)

        return hosts[:2]

    @mark.kpi
    @mark.parametrize('vm_type', [
        'virtio',
        'avp',
        'dpdk'
    ])
    def test_kpi_evacuate(self, get_hosts, vm_type, collect_kpi):
        if not collect_kpi:
            skip("KPI only test. Skip due to kpi collection is not enabled.")

        router_host = network_helper.get_router_info(field='wrs-net:host')
        target_host = get_hosts[0] if router_host == get_hosts[1] else get_hosts[1]

        LOG.tc_step("Launch a {} vm on host that is different than router host".format(vm_type))
        vms, nics = vm_helper.launch_vms(vm_type=vm_type, count=1, ping_vms=True, avail_zone='nova',
                                         target_host=target_host)
        vm_id = vms[0]

        vm_host = nova_helper.get_vm_host(vm_id=vm_id)
        router_host = network_helper.get_router_info(field='wrs-net:host')
        assert target_host == vm_host, "VM is not launched on target host"
        assert target_host != router_host, "Router is on same host with vm"

        def operation(vm_id_, host_, post_host_):
            vm_helper.evacuate_vms(host=host_, vms_to_check=vm_id_, ping_vms=True, post_host=post_host_)

        LOG.tc_step("Get {} vm ping loss duration on evacuation while router is not on failed host".format(vm_type))
        no_router_kpi = vm_helper.get_ping_loss_duration_on_operation(vm_id, 600, 0.5, operation, vm_id, target_host,
                                                                      router_host)
        assert no_router_kpi > 0, "Ping loss duration is not properly detected"
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Evacuate.NAME.format(vm_type, 'no'),
                                  kpi_val=no_router_kpi/1000, uptime=5)

        host_helper.wait_for_hosts_ready(hosts=target_host)
        time.sleep(60)

        LOG.tc_step("Get {} vm ping loss duration on evacuation while router is on same host")
        router_host = network_helper.get_router_info(field='wrs-net:host')
        vm_host = nova_helper.get_vm_host(vm_id=vm_id)
        assert router_host == vm_host, "VM is not on same host as router after first evacuation"
        with_router_kpi = vm_helper.get_ping_loss_duration_on_operation(vm_id, 600, 0.5, operation, vm_id, router_host,
                                                                        target_host)
        assert with_router_kpi > 0, "Ping loss duration is not properly detected"
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Evacuate.NAME.format(vm_type, 'with'),
                                  kpi_val=with_router_kpi/1000, uptime=5)
