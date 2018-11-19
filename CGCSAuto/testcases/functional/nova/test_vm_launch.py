import time
from pytest import mark, skip, fixture

from keywords import host_helper, nova_helper, vm_helper, network_helper
from consts.kpi_vars import VmStartup, LiveMigrate, ColdMigrate, Rebuild
from consts.reasons import SkipStorageBacking
from consts.cgcs import FlavorSpec
from consts.proj_vars import ProjVar
from consts.auth import Tenant

from utils.kpi import kpi_log_parser
from utils.tis_log import LOG
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def hosts_per_backing(add_admin_role_module):
    hosts = host_helper.get_hosts_per_storage_backing()
    return hosts


@mark.kpi
@mark.parametrize('boot_from', [
    'volume',
    'local_image',
    'remote'
])
def test_kpi_vm_launch_migrate_rebuild(ixia_supported, collect_kpi, hosts_per_backing, boot_from):
    """
    KPI test  - vm startup time.
    Args:
        collect_kpi:
        hosts_per_backing
        boot_from

    Test Steps:
        - Create a flavor with 2 vcpus, dedicated cpu policy and storage backing (if boot-from-image)
        - Launch a vm from specified boot source
        - Collect the vm startup time via event log

    """
    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled.")

    # vm launch KPI
    if boot_from != 'volume':
        storage_backing = boot_from
        hosts = hosts_per_backing.get(boot_from)
        if not hosts:
            skip(SkipStorageBacking.NO_HOST_WITH_BACKING.format(boot_from))

        target_host = hosts[0]
        LOG.tc_step("Clear local storage cache on {}".format(target_host))
        host_helper.clear_local_storage_cache(host=target_host)

        LOG.tc_step("Create a flavor with 2 vcpus, dedicated cpu policy, and {} storage".format(storage_backing))
        boot_source = 'image'
        flavor = nova_helper.create_flavor(name=boot_from, vcpus=2, storage_backing=storage_backing,
                                           check_storage_backing=False)[1]
    else:
        target_host = None
        boot_source = 'volume'
        storage_backing = nova_helper.get_storage_backing_with_max_hosts()[0]
        LOG.tc_step("Create a flavor with 2 vcpus, and dedicated cpu policy and {} storage".format(storage_backing))
        flavor = nova_helper.create_flavor(vcpus=2, storage_backing=storage_backing)[1]

    ResourceCleanup.add('flavor', flavor)
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    host_str = ' on {}'.format(target_host) if target_host else ''
    LOG.tc_step("Boot a vm from {}{} and collect vm startup time".format(boot_from, host_str))

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'virtio'}]

    vm_id = vm_helper.boot_vm(boot_from, flavor=flavor, source=boot_source, nics=nics, cleanup='function')[1]

    code_boot, out_boot = \
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=VmStartup.NAME.format(boot_from),
                                  log_path=VmStartup.LOG_PATH, end_pattern=VmStartup.END.format(vm_id),
                                  start_pattern=VmStartup.START.format(vm_id), uptime=1)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    # Migration KPI
    if ('ixia_ports' in ProjVar.get_var("LAB")) and (len(hosts_per_backing.get(storage_backing)) >= 2):

        LOG.info("Run migrate tests when more than 2 {} hosts available".format(storage_backing))
        LOG.tc_step("Launch an observer vm")

        mgmt_net_observer = network_helper.get_mgmt_net_id(auth_info=Tenant.get_secondary())
        tenant_net_observer = network_helper.get_tenant_net_id(auth_info=Tenant.get_secondary())
        nics_observer = [{'net-id': mgmt_net_observer, 'vif-model': 'virtio'},
                         {'net-id': tenant_net_observer, 'vif-model': 'virtio'},
                         {'net-id': internal_net_id, 'vif-model': 'virtio'}]
        vm_observer = vm_helper.boot_vm('observer', flavor=flavor, source=boot_source,
                                        nics=nics_observer, cleanup='function', auth_info=Tenant.get_secondary())[1]

        vm_helper.wait_for_vm_pingable_from_natbox(vm_observer)
        vm_helper.setup_kernel_routing(vm_observer)
        vm_helper.setup_kernel_routing(vm_id)
        vm_helper.route_vm_pair(vm_observer, vm_id)

        if 'local_lvm' != boot_from:
            # live migration unsupported for boot-from-image vm with local_lvm storage
            LOG.tc_step("Collect live migrate KPI for vm booted from {}".format(boot_from))

            def operation_live(vm_id_):
                code, msg = vm_helper.live_migrate_vm(vm_id=vm_id_)
                assert 0 == code, msg
                vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id_)
                # kernel routing
                vm_helper.ping_between_routed_vms(vm_id, vm_observer, vshell=False)

            time.sleep(30)
            duration = vm_helper.get_traffic_loss_duration_on_operation(vm_id, vm_observer, operation_live, vm_id)
            assert duration > 0, "No traffic loss detected during live migration for {} vm".format(boot_from)
            kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=LiveMigrate.NAME.format(boot_from),
                                      kpi_val=duration, uptime=1, unit='Time(ms)')

            vim_duration = vm_helper.get_live_migrate_duration(vm_id=vm_id)
            kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=LiveMigrate.NOVA_NAME.format(boot_from),
                                      kpi_val=vim_duration, uptime=1, unit='Time(s)')

        LOG.tc_step("Collect cold migrate KPI for vm booted from {}".format(boot_from))

        def operation_cold(vm_id_):
            code, msg = vm_helper.cold_migrate_vm(vm_id=vm_id_)
            assert 0 == code, msg
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id_)
            vm_helper.ping_between_routed_vms(vm_id, vm_observer, vshell=False)

        time.sleep(30)
        duration = vm_helper.get_traffic_loss_duration_on_operation(vm_id, vm_observer, operation_cold, vm_id)
        assert duration > 0, "No traffic loss detected during cold migration for {} vm".format(boot_from)
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=ColdMigrate.NAME.format(boot_from),
                                  kpi_val=duration, uptime=1, unit='Time(ms)')

        vim_duration = vm_helper.get_cold_migrate_duration(vm_id=vm_id)
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=ColdMigrate.NOVA_NAME.format(boot_from),
                                  kpi_val=vim_duration, uptime=1, unit='Time(s)')

    # Rebuild KPI
    if 'volume' != boot_from:
        LOG.info("Run rebuild test for vm booted from image")

        def operation_rebuild(vm_id_):
            code, msg = vm_helper.rebuild_vm(vm_id=vm_id_)
            assert 0 == code, msg
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id_)
            vm_helper.ping_vms_from_vm(vm_id, vm_id, net_types=('data', 'internal'))

        LOG.tc_step("Collect vm rebuild KPI for vm booted from {}".format(boot_from))
        time.sleep(30)
        duration = vm_helper.get_ping_loss_duration_on_operation(vm_id, 300, 0.5, operation_rebuild, vm_id)
        assert duration > 0, "No ping loss detected during rebuild for {} vm".format(boot_from)
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Rebuild.NAME.format(boot_from),
                                  kpi_val=duration, uptime=1, unit='Time(ms)')

    # Check the vm boot result at the end after collecting other KPIs
    assert code_boot == 0, out_boot


def check_for_qemu_process(host_ssh):
    return bool(host_ssh.exec_cmd(cmd='ps aux | grep qemu')[1])


def get_compute_free_disk_gb(host):
    free_disk_space = host_helper.get_hypervisor_info(hosts=host, rtn_val='free_disk_gb')[host]
    return free_disk_space


def get_initial_pool_space(host_ssh, excluded_vm):
    all_volume_size = 0.00

    raw_thin_pool_output = host_ssh.exec_sudo_cmd(
            cmd="lvs --units g --noheadings -o lv_size -S lv_name=nova-local-pool")[1]
    assert raw_thin_pool_output, "thin pool volume not found"
    raw_lvs_output = host_ssh.exec_sudo_cmd(
            "lvs --units g --noheadings -o lv_name,lv_size -S pool_lv=nova-local-pool | grep -v {}_disk".
            format(excluded_vm))[1]

    if raw_lvs_output:
        lvs_in_pool = raw_lvs_output.split('\n')

        for lv in lvs_in_pool:
            raw_vm_volume_output = lv.split()[1]
            vm_volume_size = float(raw_vm_volume_output.strip('<g'))
            all_volume_size += vm_volume_size

    return float(raw_thin_pool_output.strip('<g')) - all_volume_size


# TC5080
# DO NOT RUN - DOES NOT APPLY ANYMORE
@mark.parametrize('storage', ['local_lvm'])
def _test_check_vm_disk_on_compute(storage, hosts_per_backing):

    """
        Tests that existence of volumes are properly reported for lvm-backed vms.

        Skip:
            - Skip if no lvm-configured compute nodes available

        Test steps:
            - Create a flavor for a lvm-backed vms and boot vm out of that flavor
            - SSH onto the node hosting the VM and do the following:
                - Run ps aux and confirm that there is a qemu process
                - Run sudo lvs and confirm the existence of a thin pool
                - Run sudo lvs and confirm the existence of a volume for the vm
            - Ensure that the "free" space shown for the hypervisor (obtained by running
                "nova hypervisor-show <compute node>" and then checking the "free_disk_gb" field)
                reflects the space available within the thin pool
            - Delete the instance and ensure that space is returned to the hypervisor

        Test Teardown:
            - Delete created VM if not already done

    """

    hosts_with_backing = hosts_per_backing.get(storage, [])
    if not hosts_with_backing:
        skip(SkipStorageBacking.NO_HOST_WITH_BACKING.format(storage))

    LOG.tc_step("Create flavor and boot vm")
    flavor = nova_helper.create_flavor(storage_backing=storage, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor, scope='function')
    vm = vm_helper.boot_vm(source='image', flavor=flavor, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm)
    vm_host = nova_helper.get_vm_host(vm)

    with host_helper.ssh_to_host(vm_host) as compute_ssh:
        LOG.tc_step("Look for qemu process")
        compute_ssh.exec_sudo_cmd(cmd="lvs --units g")
        assert check_for_qemu_process(compute_ssh), "qemu process not found when calling ps"

        LOG.tc_step("Look for pool information")
        thin_pool_size = get_initial_pool_space(compute_ssh, vm)

        vm_vol_name = vm + '_disk'
        raw_vm_volume_output = \
            compute_ssh.exec_sudo_cmd(cmd="lvs --units g --noheadings -o lv_size -S lv_name={}".format(vm_vol_name))[1]
        assert raw_vm_volume_output, "created vm volume not found"
        vm_volume_size = float(raw_vm_volume_output.strip('<g'))

    LOG.tc_step("Calculate compute free disk space and ensure that it reflects thin pool")
    expected_space_left = int(thin_pool_size - vm_volume_size)
    free_disk_space = get_compute_free_disk_gb(vm_host)
    assert expected_space_left - 1 <= free_disk_space <= expected_space_left + 1, \
        'Hypervisor-show does not reflect space within thin pool'

    LOG.tc_step("Calculate free space following vm deletion (ensure volume space is returned)")
    vm_helper.delete_vms(vm)
    free_disk_space = get_compute_free_disk_gb(vm_host)
    assert int(thin_pool_size) == free_disk_space, \
        'Space is not properly returned to the hypervisor or hypervisor info does not properly reflect it'
