# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
import random
from datetime import datetime, timedelta
from pytest import mark, skip, fixture

from utils.tis_log import LOG
from utils import table_parser

from consts.auth import Tenant
from consts.timeout import SysInvTimeout
from keywords import common, host_helper, ceilometer_helper, network_helper, glance_helper, system_helper


@mark.cpe_sanity
@mark.sanity
@mark.sx_nightly
@mark.parametrize('meter', [
    'image.size'
])
def test_statistics_for_one_meter(meter):
    """
    Validate statistics for one meter

    """
    # List with column names
    headers = ['Count', 'Min', 'Max', 'Avg']

    LOG.tc_step('Get ceilometer statistics table for image.size meter')

    stats_tab = ceilometer_helper.get_statistics_table(meter=meter)
    assert stats_tab['values'], "No entries found for meter {}".format(meter)

    LOG.tc_step('Check that count, min, max, avg values are larger than zero')
    for header in headers:
        header_val = eval(table_parser.get_column(stats_tab, header)[0])

        assert 0 <= header_val, "Value for {} in {} stats table is less than zero".format(header, meter)


def check_event_in_tenant_or_admin(resource_id, event_type):
    for auth_ in (None, Tenant.ADMIN):
        traits = ceilometer_helper.get_events(event_type=event_type, header='traits:value', auth_info=auth_)
        for trait in traits:
            if resource_id in trait:
                LOG.info("Resource found in ceilometer events using auth: {}".format(auth_))
                break
        else:
            continue
        break
    else:
        assert False, "{} event for resource {} was not found under admin or tenant".format(event_type, resource_id)


@mark.sanity
# Hardcode the parameter even though unused so sanity test name can show the meters tested
@mark.parametrize('meters', [
    'router_subnet_image_vswitch'
])
def test_ceilometer_meters_exist(meters):
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
    LOG.tc_step("Check number of 'router.create.end' events is at least the number of existing routers")
    routers = network_helper.get_routers()
    router_id = routers[0]
    check_event_in_tenant_or_admin(resource_id=router_id, event_type='router.create.end')

    # Check meter for subnets
    LOG.tc_step("Check number of 'subnet.create' meters is at least the number of existing subnets")
    subnets = network_helper.get_subnets(name=Tenant.get_primary().get('tenant'), strict=False)
    subnet = random.choice(subnets)
    LOG.info("Subnet to check in ceilometer event list: {}".format(subnet))
    check_event_in_tenant_or_admin(resource_id=subnet, event_type='subnet.create.end')

    # Check meter for image
    LOG.tc_step('Check meters for image')
    images = glance_helper.get_images()
    image_meters_tab = ceilometer_helper.get_meters_table(meter='image.size')
    images_in_meter_list = table_parser.get_column(image_meters_tab, 'Resource ID')

    assert set(images) <= set(images_in_meter_list)

    # Check meter for vswitch
    LOG.tc_step('Check meters for vswitch')
    hypervisors = host_helper.get_hypervisors()
    vswitch_util_meters_tab = ceilometer_helper.get_meters_table(meter='vswitch.engine.util')
    vswitch_engines_meters = table_parser.get_values(vswitch_util_meters_tab, 'Resource ID', Name='vswitch.engine.util')
    if system_helper.is_stx_build():
        assert not vswitch_engines_meters, "vswitch meters found for STX build"
    else:
        assert len(hypervisors) <= len(vswitch_engines_meters), \
            "Each nova hypervisor should have at least one vSwitch core"


@fixture(scope='module', autouse=True)
def reset_retention(request):
    original = system_helper.get_retention_period()
    LOG.debug(original)

    def reset():
        system_helper.set_retention_period(period=original, fail_ok=False)
    request.addfinalizer(reset)


def test_ceilometer_retention_period():
    """
    TC1996
    Verify that the retention period can be changed to specified values

    Test Steps:
        - Change the retention period to different values
        - Verify that the retention period changed correctly
        - Attempt to change to invalid values
        - Verify that the changes were rejected

    Teardown:
        - reset     ('module')
    """
    times = [31536000, 604800, 3600, 86400]
    for interval in times:
        LOG.tc_step("changing retention period to: {}".format(interval))
        system_helper.set_retention_period(period=interval)

    times = [3500, 32000000]
    for interval in times:
        LOG.tc_step("changing retention period to: {}".format(interval))
        res, out = system_helper.set_retention_period(period=interval, fail_ok=True)
        ret_per = system_helper.get_retention_period()
        assert interval != int(ret_per) and 0 != res, "FAIL: the retention period was changed"


def test_ceilometer_retention_sample():
    """
    TC1998
    Check that a sample can't be removed until after retention period

    Test Steps:
        - Change retention period to 3600 (minimum allowed)
        - Get a resource ID
        - Create a fake sample
        - Trigger /usr/bin/ceilometer-expirer and verify that fake sample is still in the list
        - Wait for retention period (1 hour)
        - Trigger the expirer again and verify that fake sample is not in the list

    Teardown:
        - reset     ('module')
    """
    LOG.tc_step("Set retention period to 3600 seconds")
    system_helper.set_retention_period(period=3600)

    LOG.tc_step("Choosing a resource")
    out = ceilometer_helper.get_resources(header='Resource ID')
    res_id = out[0]

    # create fake timestamp
    curr_time = datetime.utcnow()
    curr_secs = curr_time.timestamp()
    new_time = datetime.fromtimestamp(curr_secs - 3540)
    new_time = str(new_time).replace(' ', 'T')
    LOG.info("\nNow: {}\n59 min ago: {}".format(curr_time, new_time))

    LOG.tc_step("Creating fake sample")

    args = {'meter-name': 'fake_sample', 'meter-type': 'gauge', 'meter-unit': 'percent',
            'sample-volume': 10, 'timestamp': new_time}
    ceilometer_helper.create_sample(resource_id=res_id, field='timestamp', auth_info=Tenant.ADMIN, **args)

    pre_expirer_samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
    count = 0
    while count < 5:
        if not pre_expirer_samples:
            LOG.tc_step("CREATE SAMPLE FAILED!!!! TRY AGAIN!")
            # create fake timestamp
            curr_time = datetime.utcnow()
            curr_secs = curr_time.timestamp()
            new_time = datetime.fromtimestamp(curr_secs - 3540)
            new_time = str(new_time).replace(' ', 'T')
            args = {'meter-name': 'fake_sample', 'meter-type': 'gauge', 'meter-unit': 'percent',
                    'sample-volume': 10, 'timestamp': new_time}
            LOG.info("\nnow: {}\n59 min ago{}".format(curr_time, new_time))
            ceilometer_helper.create_sample(resource_id=res_id, field='timestamp', auth_info=Tenant.ADMIN, **args)
            fake_sample = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
            if fake_sample:
                break
            else:
                count += 1
        else:
            break

    # pre_samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
    # assert pre_samples, "Created fake_sample is not listed"

    wait_time = SysInvTimeout.RETENTION_PERIOD_SAVED

    LOG.info("Waiting {} seconds for retention period change".format(wait_time))
    time.sleep(wait_time)
    LOG.tc_step("Ensuring the sample is listed")

    pre_expirer_samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
    assert pre_expirer_samples, "fake_sample is not listed after sleep for {} seconds".format(wait_time)

    ceilometer_helper.delete_samples()
    # sample-create uses meter-name for the name of the sample.
    # sample-list uses meter to specify the name to search for.
    # probably will have to change at least one of them when they become consistent.
    samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
    assert 1 == len(samples), "FAIL: The sample is not in the list. Number of samples: {}. Expected: 1"\
                              .format(len(samples))

    if 65 - wait_time > 0:
        LOG.info("Waiting for retention period to end.")
        time.sleep(65 - wait_time)

    ceilometer_helper.delete_samples()

    LOG.tc_step("Ensuring the sample isn't listed anymore")
    ceilometer_helper.wait_for_sample_expire(meter='fake_sample', fail_ok=False)
