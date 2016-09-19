# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
import time
from pytest import mark

from utils.tis_log import LOG

from keywords import ceilometer_helper


@mark.sanity
@mark.cpe_sanity
def test_ceilometer_vswitch_port_samples_5_min_record():
    """

    Test Steps:
        - Get resource IDs for last two vswitch.port.transmit.util entries in sample-list

    """
    meter = 'vswitch.port.transmit.util'

    LOG.tc_step("Get resource IDs for last two vswitch.port.transmit.util entries in sample-list")
    # last_two_vswitch_samples_resource_ids = ceilometer_helper.get_samples(limit=2, meter=meter)
    # vswitch_samples_len = len(last_two_vswitch_samples_resource_ids)
    last_two_samples = __wait_for_records(limit=2, meter=meter, query=None, entry_num=2, timeout=60)

    assert 2 == len(last_two_samples), "Number of entries for {} meter is {} instead of 2".format(meter, last_two_samples)

    LOG.tc_step("Verify 10 vswitch.port.transmit.util entries exist in sample-list per resource id")
    for resource_id in last_two_samples:
        query = 'resource={}'.format(resource_id)
        samples = __wait_for_records(limit=30, meter=meter, query=query, entry_num=10, timeout=300)
        assert 10 == len(samples), "Entries for resource {} for {} meter is not 10".format(resource_id, meter)


def __wait_for_records(limit, meter, query, entry_num, timeout):

    end_time = time.time() + timeout
    while time.time() < end_time:
        samples = ceilometer_helper.get_samples(limit=limit, meter=meter, query=query)
        if len(samples) >= entry_num:
            return samples

        time.sleep(30)

    else:
        return samples
