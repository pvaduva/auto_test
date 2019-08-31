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

from consts.stx import GuestImages
from consts.auth import Tenant
from keywords import common, host_helper, ceilometer_helper, network_helper, glance_helper, system_helper, \
    gnocchi_helper


@fixture(scope='module', autouse=True)
def check_openstack(stx_openstack_required):
    pass


def _wait_for_measurements(meter, resource_type, extra_query, start_time, overlap=None, timeout=1860,
                           check_interval=60):
    end_time = time.time() + timeout

    while time.time() < end_time:
        values = gnocchi_helper.get_aggregated_measures(metrics=meter, resource_type=resource_type, start=start_time,
                                                        overlap=overlap, extra_query=extra_query)[1]
        if values:
            return values

        time.sleep(check_interval)


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
    image_name = GuestImages.DEFAULT['guest']
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
        assert len(values) <= 4, "Incorrect count for {} {} metric via 'openstack metric measures aggregation'". \
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


# Hardcode the parameter even though unused so test name can show the meters tested
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
    # skip('CGTS-10102: Disable TC until US116020 completes')
    time_create = system_helper.get_host_values('controller-1', 'created_at')[0]
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
    images = glance_helper.get_images(field='id')
    resource_ids = gnocchi_helper.get_metrics(metric_name='image.size', field='resource_id')
    assert set(images) <= set(resource_ids)

    # Check meter for vswitch
    LOG.tc_step('Check meters for vswitch')
    resource_ids = gnocchi_helper.get_metrics(metric_name='vswitch.engine.util', fail_ok=True, field='resource_id')
    if system_helper.is_avs():
        hypervisors = host_helper.get_hypervisors()
        assert len(hypervisors) <= len(resource_ids), \
            "Each nova hypervisor should have at least one vSwitch core"
    else:
        assert not resource_ids, "vswitch meters found for STX build"
