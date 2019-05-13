# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
import random
from datetime import datetime, timedelta
from pytest import mark, skip

from utils.tis_log import LOG

from consts.cgcs import GuestImages
from consts.auth import Tenant
from keywords import common, host_helper, ceilometer_helper, network_helper, glance_helper, system_helper, \
    gnocchi_helper


# # Obsolete - replaced by test_measurements_for_metric
# @mark.cpe_sanity
# @mark.sanity
# @mark.sx_nightly
# @mark.parametrize('meter', [
#     'image.size'
# ])
# def _test_statistics_for_one_meter(meter):
#     """
#     Validate statistics for one meter
#
#     """
#     # List with column names
#     headers = ['Count', 'Min', 'Max', 'Avg']
#
#     LOG.tc_step('Get ceilometer statistics table for image.size meter')
#
#     stats_tab = ceilometer_helper.get_statistics_table(meter=meter)
#     assert stats_tab['values'], "No entries found for meter {}".format(meter)
#
#     LOG.tc_step('Check that count, min, max, avg values are larger than zero')
#     for header in headers:
#         header_val = eval(table_parser.get_column(stats_tab, header)[0])
#
#         assert 0 <= header_val, "Value for {} in {} stats table is less than zero".format(header, meter)


def _wait_for_measurements(meter, resource_type, extra_query, start_time, overlap=None, timeout=1860,
                           check_interval=60):
    end_time = time.time() + timeout

    while time.time() < end_time:
        values = gnocchi_helper.get_aggregated_measures(metrics=meter, resource_type=resource_type, start=start_time,
                                                        overlap=overlap, extra_query=extra_query)[1]
        if values:
            return values

        time.sleep(check_interval)


@mark.cpe_sanity
@mark.sanity
@mark.sx_nightly
@mark.parametrize('meter', [
    'image.size'
])
def test_measurements_for_metric(meter):
    """
    Validate statistics for one meter

    """
    LOG.tc_step('Get ceilometer statistics table for image.size meter')

    now = datetime.utcnow()
    start = (now - timedelta(minutes=10))
    start = start.strftime("%Y-%m-%dT%H:%M:%S")
    image_name = GuestImages.DEFAULT_GUEST
    resource_type = 'image'
    extra_query = "name='{}'".format(image_name)
    overlap = None

    code, output = gnocchi_helper.get_aggregated_measures(metrics=meter, resource_type=resource_type, start=start,
                                                          extra_query=extra_query, fail_ok=True)
    if code > 0:
        if "Metrics can't being aggregated" in output:
            # there was another glance image that has the same string in its name
            overlap = '0'
        else:
            assert False, output

    values = output
    if code == 0 and values:
        assert len(values) <= 4, "Incorrect count for {} {} metric via 'openstack metric measures aggregation'".\
            format(image_name, meter)
    else:
        values = _wait_for_measurements(meter=meter, resource_type=resource_type, extra_query=extra_query,
                                        start_time=start, overlap=overlap)
        assert values, "No measurements for image.size for 25+ minutes"

    LOG.tc_step('Check that values are larger than zero')
    for val in values:
        assert 0 <= float(val), "{} {} value in metric measurements table is less than zero".format(image_name, meter)


def check_event_in_tenant_or_admin(resource_id, event_type):
    for auth_ in (None, Tenant.get('admin')):
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
    1. Check via 'openstack metric list' or 'ceilometer event-list'
    2. Check meters for router, subnet, image, and vswitch exists
    """
    skip('CGTS-10102: Disable TC until US116020 completes')
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
    images = glance_helper.get_images(rtn_val='id')
    resource_ids = gnocchi_helper.get_metrics(metric_name='image.size', rtn_val='resource_id')
    assert set(images) <= set(resource_ids)

    # Check meter for vswitch
    LOG.tc_step('Check meters for vswitch')
    resource_ids = gnocchi_helper.get_metrics(metric_name='vswitch.engine.util', fail_ok=True, rtn_val='resource_id')
    if system_helper.is_avs():
        hypervisors = host_helper.get_hypervisors()
        assert len(hypervisors) <= len(resource_ids), \
            "Each nova hypervisor should have at least one vSwitch core"
    else:
        assert not resource_ids, "vswitch meters found for STX build"


# # Obsolete: Ceilometer retention period test obsoleted. No equivalent in gnocchi
# @fixture(scope='module', autouse=True)
# def reset_retention(request):
#     original = system_helper.get_retention_period()
#     LOG.debug(original)
#
#     def reset():
#         system_helper.set_retention_period(period=original, fail_ok=False)
#     request.addfinalizer(reset)
#
#
# def _test_ceilometer_retention_period():
#     """
#     TC1996
#     Verify that the retention period can be changed to specified values
#
#     Test Steps:
#         - Change the retention period to different values
#         - Verify that the retention period changed correctly
#         - Attempt to change to invalid values
#         - Verify that the changes were rejected
#
#     Teardown:
#         - reset     ('module')
#     """
#     times = [31536000, 604800, 3600, 86400]
#     for interval in times:
#         LOG.tc_step("changing retention period to: {}".format(interval))
#         system_helper.set_retention_period(period=interval)
#
#     times = [3500, 32000000]
#     for interval in times:
#         LOG.tc_step("changing retention period to: {}".format(interval))
#         res, out = system_helper.set_retention_period(period=interval, fail_ok=True)
#         ret_per = system_helper.get_retention_period()
#         assert interval != int(ret_per) and 0 != res, "FAIL: the retention period was changed"
#
#
# def _test_ceilometer_retention_sample():
#     """
#     TC1998
#     Check that a sample can't be removed until after retention period
#
#     Test Steps:
#         - Change retention period to 3600 (minimum allowed)
#         - Get a resource ID
#         - Create a fake sample
#         - Trigger /usr/bin/ceilometer-expirer and verify that fake sample is still in the list
#         - Wait for retention period (1 hour)
#         - Trigger the expirer again and verify that fake sample is not in the list
#
#     Teardown:
#         - reset     ('module')
#     """
#     LOG.tc_step("Set retention period to 3600 seconds")
#     system_helper.set_retention_period(period=3600)
#
#     LOG.tc_step("Choosing a resource")
#     out = ceilometer_helper.get_resources(header='Resource ID')
#     res_id = out[0]
#
#     # create fake timestamp
#     curr_time = datetime.utcnow()
#     curr_secs = curr_time.timestamp()
#     new_time = datetime.fromtimestamp(curr_secs - 3540)
#     new_time = str(new_time).replace(' ', 'T')
#     LOG.info("\nNow: {}\n59 min ago: {}".format(curr_time, new_time))
#
#     LOG.tc_step("Creating fake sample")
#
#     args = {'meter-name': 'fake_sample', 'meter-type': 'gauge', 'meter-unit': 'percent',
#             'sample-volume': 10, 'timestamp': new_time}
#     ceilometer_helper.create_sample(resource_id=res_id, field='timestamp', auth_info=Tenant.get('admin'), **args)
#
#     pre_expirer_samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
#     count = 0
#     while count < 5:
#         if not pre_expirer_samples:
#             LOG.tc_step("CREATE SAMPLE FAILED!!!! TRY AGAIN!")
#             # create fake timestamp
#             curr_time = datetime.utcnow()
#             curr_secs = curr_time.timestamp()
#             new_time = datetime.fromtimestamp(curr_secs - 3540)
#             new_time = str(new_time).replace(' ', 'T')
#             args = {'meter-name': 'fake_sample', 'meter-type': 'gauge', 'meter-unit': 'percent',
#                     'sample-volume': 10, 'timestamp': new_time}
#             LOG.info("\nnow: {}\n59 min ago{}".format(curr_time, new_time))
#             ceilometer_helper.create_sample(resource_id=res_id, field='timestamp', auth_info=Tenant.get('admin'), **args)
#             fake_sample = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
#             if fake_sample:
#                 break
#             else:
#                 count += 1
#         else:
#             break
#
#     # pre_samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
#     # assert pre_samples, "Created fake_sample is not listed"
#
#     wait_time = SysInvTimeout.RETENTION_PERIOD_SAVED
#
#     LOG.info("Waiting {} seconds for retention period change".format(wait_time))
#     time.sleep(wait_time)
#     LOG.tc_step("Ensuring the sample is listed")
#
#     pre_expirer_samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
#     assert pre_expirer_samples, "fake_sample is not listed after sleep for {} seconds".format(wait_time)
#
#     ceilometer_helper.delete_samples()
#     # sample-create uses meter-name for the name of the sample.
#     # sample-list uses meter to specify the name to search for.
#     # probably will have to change at least one of them when they become consistent.
#     samples = ceilometer_helper.get_samples(header='Name', meter='fake_sample')
#     assert 1 == len(samples), "FAIL: The sample is not in the list. Number of samples: {}. Expected: 1"\
#                               .format(len(samples))
#
#     if 65 - wait_time > 0:
#         LOG.info("Waiting for retention period to end.")
#         time.sleep(65 - wait_time)
#
#     ceilometer_helper.delete_samples()
#
#     LOG.tc_step("Ensuring the sample isn't listed anymore")
#     ceilometer_helper.wait_for_sample_expire(meter='fake_sample', fail_ok=False)
