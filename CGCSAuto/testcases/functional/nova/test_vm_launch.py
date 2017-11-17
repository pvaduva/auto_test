from pytest import mark, skip, fixture

from keywords import cinder_helper, common, storage_helper, host_helper, nova_helper, vm_helper
from consts.kpi_vars import KPI_DATE_FORMAT, VmStartup
from consts.reasons import SkipStorageBacking
from consts.cgcs import FlavorSpec
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
