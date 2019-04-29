# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
import time
from pytest import mark

from utils.tis_log import LOG

from keywords import ceilometer_helper


# Obsolete: TODO update
@mark.sanity
@mark.cpe_sanity
@mark.sx_nightly
def _test_ceilometer_vswitch_port_samples():
    """
    Test Steps:
        - Get resource IDs for last two vswitch.port.transmit.util entries in ceilometer sample-list
        - Verify 20 vswitch.port.transmit.util entries exist in sample-list per resource id (wait for up to 5 minute)

    Notes: vswitch samples used to be saved in the in-memory database for last 5 minute records. This has been changed
    in CGTS-5760 to eliminate usage of in-memory db. Now all the historic records for vswitch samples are kept.

    """
    meter = 'vswitch.port.transmit.util'

    LOG.tc_step("Get resource IDs for last two vswitch.port.transmit.util entries in sample-list")
    last_two_samples = __wait_for_records(limit=2, meter=meter, query=None, entry_num=2, timeout=300)

    assert 2 == len(last_two_samples), "Number of entries for {} meter is {} instead of 2".\
        format(meter, last_two_samples)

    LOG.tc_step("Verify vswitch.port.transmit.util entries exist in sample-list per resource id")
    limit = 20
    for resource_id in last_two_samples:
        query = 'resource={}'.format(resource_id)
        samples = __wait_for_records(limit=limit, meter=meter, query=query, entry_num=limit, timeout=limit * 30)
        assert limit == len(samples), "Number of samples for resource {} for {} meter is not {}".format(resource_id,
                                                                                                        meter, limit)


def __wait_for_records(limit, meter, query, entry_num, timeout):

    end_time = time.time() + timeout
    while time.time() < end_time:
        # ceilometer sample cmds are obsolete. Update required.
        samples = ceilometer_helper.get_samples(limit=limit, meter=meter, query=query)
        if len(samples) >= entry_num:
            return samples

        time.sleep(30)

    else:
        return samples
