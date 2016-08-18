# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from datetime import datetime, timedelta
from pytest import mark, skip

from utils.tis_log import LOG
from utils import table_parser

from consts.auth import Tenant
from keywords import common, host_helper, ceilometer_helper, network_helper, glance_helper


@mark.cpe_sanity
@mark.sanity
def test_tc402_validate_statistics_for_one_meter():
    """
    Validate statistics for one meter

    """
    # List with column names
    headers = ['Count', 'Min', 'Max', 'Avg']

    LOG.tc_step('Get ceilometer statistics table for image.size meter')
    # Verify that all the instances were successfully launched
    stats_tab = ceilometer_helper.get_statistics_table(meter='image.size')

    LOG.tc_step('Check that count, min, max, avg values are larger than zero')
    for header in headers:
        header_val = eval(table_parser.get_column(stats_tab, header)[0])

        assert 0 < header_val, "Value for {} in image.size stats table is not larger than zero".format(header)


@mark.sanity
def test_401_validate_ceilometer_meters_exist():
    """
    Validate ceilometer meters exist
    Verification Steps:
    1. Get ceilometer meter-list
    2. Check meters for router, subnet, image, and vswitch exists
    """

    time_create = host_helper.get_hostshow_value('controller-1', 'created_at')
    current_isotime = datetime.utcnow().isoformat(sep='T')

    if common.get_timedelta_for_isotimes(time_create, current_isotime) > timedelta(hours=24):
        skip("Over a day since install. Meters no longer exist.")

    # Check meter for routers
    LOG.tc_step("Check number of router.create meters is at least the number of existing routers")
    routers = network_helper.get_routers(auth_info=Tenant.ADMIN)
    router_create_meter_table = ceilometer_helper.get_meters_table(meter='router.create')
    created_routers_in_meters = table_parser.get_column(router_create_meter_table, 'Resource ID')

    assert set(routers) <= set(created_routers_in_meters), "router.create meters do not exist for all existing routers"

    # Check meter for subnets
    LOG.tc_step("Check number of subnet.create meters is at least the number of existing subnets")
    subnets = network_helper.get_subnets(auth_info=Tenant.ADMIN)
    subnet_create_meter_table = ceilometer_helper.get_meters_table(meter='subnet.create')
    created_subnets_in_meters = table_parser.get_column(subnet_create_meter_table, 'Resource ID')

    assert set(subnets) <= set(created_subnets_in_meters), "subnet.create meters do not exist for all existing subnets"

    # Check meter for image
    LOG.tc_step('Check meters for image')
    images = glance_helper.get_images()
    image_meters_tab = ceilometer_helper.get_meters_table(meter='image.upload')
    images_in_meter_list = table_parser.get_column(image_meters_tab, 'Resource ID')

    assert set(images) <= set(images_in_meter_list)

    # Check meter for vswitch
    LOG.tc_step('Check meters for vswitch')
    hypervisors = host_helper.get_hypervisors()
    vswitch_util_meters_tab = ceilometer_helper.get_meters_table(meter='vswitch.engine.util')
    vswitch_engines_meters = table_parser.get_values(vswitch_util_meters_tab, 'Resource ID', Name='vswitch.engine.util')

    assert len(hypervisors) <= len(vswitch_engines_meters), "Each nova hypervisor should have at least one vSwitch core"
