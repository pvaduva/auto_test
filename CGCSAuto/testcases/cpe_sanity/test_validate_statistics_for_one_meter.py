# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from pytest import mark

from utils import table_parser
from utils.tis_log import LOG

from keywords import ceilometer_helper


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
