from pytest import mark, skip

from keywords import cinder_helper, common, storage_helper, glance_helper
from consts.kpi_vars import VolCreate, KPI_DATE_FORMAT, ImageConversion, ImageDownload
from utils.kpi import kpi_log_parser
from utils.tis_log import LOG


@mark.kpi
def test_kpi_cinder_volume_creation(collect_kpi):
    """
    KPI test  - cinder  volume creation
    Args:
        collect_kpi:

    Test Steps:
        - Create a 20g cinder volume using default tis guest
        - Collect duration kpi from cinder create cli sent to volume available

    """
    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled.")

    LOG.tc_step("Create a 20g volume from default tis guest and collect image download rate, "
                "image conversion rate, and total volume creation time")
    # init_time = common.get_date_in_format(date_format=KPI_DATE_FORMAT)
    image = glance_helper.get_guest_image(guest_os='tis-centos-guest-qcow2', cleanup='function')

    vol_id = cinder_helper.create_volume(name='20g', source_id=image, size=20,
                                         cleanup='function')[1]
    vol_updated = cinder_helper.get_volume_show_values(vol_id, 'updated_at')[0].split('.')[0]

    # Logs no longer available for image downloading and conversion.
    # code_download, out_download = \
    #     kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=ImageDownload.NAME,
    #                               host=None,
    #                               log_path=ImageDownload.LOG_PATH,
    #                               end_pattern=ImageDownload.GREP_PATTERN,
    #                               python_pattern=ImageDownload.PYTHON_PATTERN,
    #                               init_time=init_time, uptime=1,
    #                               unit=ImageDownload.UNIT)
    # code_conv, out_conv = \
    #     kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=ImageConversion.NAME,
    #                               host=None,
    #                               log_path=ImageConversion.LOG_PATH,
    #                               end_pattern=ImageConversion.GREP_PATTERN,
    #                               python_pattern=ImageConversion.PYTHON_PATTERN,
    #                               init_time=init_time, uptime=1,
    #                               unit=ImageConversion.UNIT)
    code_create, out_create = \
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=VolCreate.NAME, host=None,
                                  log_path=VolCreate.LOG_PATH, end_pattern=vol_updated,
                                  start_pattern=VolCreate.START, uptime=1)
    #
    # assert code_download == 0, out_download
    # assert code_conv == 0, out_conv
    assert code_create == 0, out_create
