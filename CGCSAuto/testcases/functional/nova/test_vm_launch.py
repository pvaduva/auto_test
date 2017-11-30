from pytest import mark, skip, fixture

from keywords import cinder_helper, common, storage_helper, host_helper, nova_helper, vm_helper
from consts.kpi_vars import KPI_DATE_FORMAT, VmStartup
from consts.reasons import SkipStorageBacking
from consts.cgcs import FlavorSpec
from consts.auth import Tenant

from utils import table_parser, cli
from utils.kpi import kpi_log_parser
from utils.tis_log import LOG
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def hosts_per_backing():
    hosts = host_helper.get_hosts_per_storage_backing()
    return hosts


@mark.kpi
@mark.parametrize('boot_from', [
    'volume',
    'local_image',
    'local_lvm',
    'remote'
])
def test_kpi_vm_launch(collect_kpi, hosts_per_backing, boot_from):
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

    if boot_from != 'volume':
        if not hosts_per_backing.get(boot_from):
            skip(SkipStorageBacking.NO_HOST_WITH_BACKING.format(boot_from))
        LOG.tc_step("Create a flavor with 2 vcpus, dedicated cpu policy, and {} storage backing".format(boot_from))
        boot_source = 'image'
        flavor = nova_helper.create_flavor(name=boot_from, vcpus=2, storage_backing=boot_from,
                                           check_storage_backing=False)[1]
    else:
        LOG.tc_step("Create a flavor with 2 vcpus, and dedicated cpu policy")
        boot_source = 'volume'
        flavor = nova_helper.create_flavor(vcpus=2)[1]

    ResourceCleanup.add('flavor', flavor)
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    LOG.tc_step("Boot a vm from {} and collect vm startup time".format(boot_from))
    vm_id = vm_helper.boot_vm(name=boot_from, flavor=flavor, source=boot_source, cleanup='function')[1]

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=VmStartup.NAME.format(boot_from),
                              log_path=VmStartup.LOG_PATH, end_pattern=VmStartup.END.format(vm_id),
                              start_pattern=VmStartup.START.format(vm_id), uptime=1)


def check_for_qemu_process(host_ssh):
    return bool(host_ssh.exec_cmd(cmd='ps aux | grep qemu')[1])


def get_compute_free_disk_gb(host):
    free_disk_space = host_helper.get_hypervisor_info(hosts=host, rtn_val='free_disk_gb')[host]
    return free_disk_space


def get_initial_pool_space(host_ssh, excluded_vm):
    all_volume_size = 0.00

    raw_thin_pool_output = host_ssh.exec_sudo_cmd(cmd="lvs --noheadings -o lv_size -S lv_name=nova-local-pool")[1]
    assert raw_thin_pool_output, "thin pool volume not found"
    raw_lvs_output = host_ssh.exec_sudo_cmd(cmd="lvs --noheadings -o lv_name,lv_size -S pool_lv=nova-local-pool | grep -v {}_disk".format(excluded_vm))[1]

    if raw_lvs_output:
        lvs_in_pool = raw_lvs_output.split('\n')

        for lv in lvs_in_pool:
            raw_vm_volume_output = lv.split()[1]
            vm_volume_size = float(raw_vm_volume_output.strip('<g'))
            all_volume_size += vm_volume_size

    return float(raw_thin_pool_output.strip('<g')) - all_volume_size


# TC5080
def test_check_vm_disk_on_lvm_compute():

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
            - Ensure that the "free" space shown for the hypervisor (obtained by running "nova hypervisor-show
            <compute node>" and then checking the "free_disk_gb" field) reflects the space available within the thin pool
            - Delete the instance and ensure that space is returned to the hypervisor

        Test Teardown:
            - Delete created VM if not already done

    """

    lvm_hosts = host_helper.get_hosts_by_storage_aggregate(storage_backing='local_lvm')
    LOG.info("lvm hosts: {}".format(lvm_hosts))
    if not lvm_hosts:
        skip(SkipStorageBacking.NO_HOST_WITH_BACKING.format("local_lvm"))

    LOG.tc_step("Create flavor and boot vm")
    flavor = nova_helper.create_flavor(storage_backing='local_lvm')[1]
    ResourceCleanup.add('flavor', flavor, scope='function')
    vm = vm_helper.boot_vm(source='image', flavor=flavor, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm)
    vm_host = nova_helper.get_vm_host(vm)

    with host_helper.ssh_to_host(vm_host) as compute_ssh:
        LOG.tc_step("Look for qemu process")
        compute_ssh.exec_sudo_cmd(cmd="lvs")
        assert check_for_qemu_process(compute_ssh), "qemu process not found when calling ps"

        LOG.tc_step("Look for pool information")
        thin_pool_size = get_initial_pool_space(compute_ssh, vm)

        vm_vol_name = vm + '_disk'
        raw_vm_volume_output = \
            compute_ssh.exec_sudo_cmd(cmd="lvs --noheadings -o lv_size -S lv_name={}".format(vm_vol_name))[1]
        assert raw_vm_volume_output, "created vm volume not found"
        vm_volume_size = float(raw_vm_volume_output.strip('<g'))

    LOG.tc_step("Calculate compute free disk space and ensure that it reflects thin pool")
    expected_space_left = int(thin_pool_size - vm_volume_size)
    free_disk_space = get_compute_free_disk_gb(vm_host)
    assert expected_space_left - 1 <= free_disk_space <= expected_space_left + 1, 'Hypervisor-show does not reflect space within thin pool'

    LOG.tc_step("Calculate free space following vm deletion (ensure volume space is returned)")
    vm_helper.delete_vms(vm)
    free_disk_space = get_compute_free_disk_gb(vm_host)
    assert int(thin_pool_size) == free_disk_space, 'Space is not properly returned to the hypervisor or hypervisor ' \
                                                   'info does not properly reflect it'
