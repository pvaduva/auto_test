from pytest import mark, skip, fixture

from keywords import cinder_helper, common, storage_helper, host_helper, nova_helper, vm_helper
from consts.kpi_vars import VolCreate, KPI_DATE_FORMAT, ImageConversion, ImageDownload
from consts.reasons import SkipStorageBacking
from consts.cgcs import FlavorSpec
from utils.kpi import kpi_log_parser
from utils.tis_log import LOG
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def kpi_info(collect_kpi):
    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled.")

    hosts = host_helper.get_hosts_per_storage_backing()
    return collect_kpi, hosts


@mark.kpi
@mark.parametrize('boot_from', [
    'volume',
    'local_image',
    'local_lvm',
    'remote'
])
def test_kpi_vm_launch(kpi_info, boot_from):
    """
    KPI test  - cinder  volume creation
    Args:
        kpi_info:

    Test Steps:
        - Create a 20g cinder volume using default tis guest
        - Collect duration kpi from cinder create cli sent to volume available

    """
    kpi_file, hosts_per_backing = kpi_info
    if boot_from != 'volume':
        LOG.tc_step("Create a flavor with 2 vcpus and dedicated cpu policy")
        if not hosts_per_backing.get(boot_from):
            skip(SkipStorageBacking.NO_HOST_WITH_BACKING.format(boot_from))
        boot_source = boot_from
        flavor = nova_helper.create_flavor(name=boot_from, vcpus=2, storage_backing=boot_from,
                                           check_storage_backing=False)[1]
    else:
        LOG.tc_step("Create a flavor with 2 vcpus, dedicated cpu policy, and {} storage backing".format(boot_from))
        boot_source = 'image'
        flavor = nova_helper.create_flavor(vcpus=2)[1]

    ResourceCleanup.add('flavor', flavor)
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    LOG.tc_step("Boot a vm from {} and collect vm startup time".format(boot_from))
    init_time = common.get_date_in_format(date_format=KPI_DATE_FORMAT)
    vm_id = vm_helper.boot_vm(name=boot_from, flavor=flavor, source=boot_source, cleanup='function')[1]

    # kpi_log_parser.record_kpi(local_kpi_file=kpi_file, kpi_name=.NAME, host=None,
    #                           log_path=ImageDownload.LOG_PATH, end_pattern=ImageDownload.GREP_PATTERN,
    #                           python_pattern=ImageDownload.PYTHON_PATTERN, init_time=init_time, uptime=1)
