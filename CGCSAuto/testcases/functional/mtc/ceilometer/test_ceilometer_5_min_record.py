# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from pytest import mark

from utils.tis_log import LOG

from keywords import ceilometer_helper


@mark.sanity
def test_ceilometer_5_min_record():
    meter = 'vswitch.port.transmit.util'

    LOG.tc_step("Get resource IDs for last two vswitch.port.transmit.util entries in sample-list")
    last_two_vswitch_samples_resource_ids = ceilometer_helper.get_samples(limit=2, meter=meter)

    vswitch_samples_len = len(last_two_vswitch_samples_resource_ids)

    assert 2 == vswitch_samples_len, "Number of entries for {} meter is {} instead of 2".format(meter,
                                                                                                vswitch_samples_len)

    LOG.tc_step("Verify 10 vswitch.port.transmit.util entries exist in sample-list per resource id")
    for resource_id in last_two_vswitch_samples_resource_ids:
        samples_per_resource = ceilometer_helper.get_samples(meter=meter, query='resource={}'.format(resource_id))

        assert 10 == len(samples_per_resource), "Entries per resource id for vswitch.port.transmit.util meter is not 10"
