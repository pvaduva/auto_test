# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.



import time
from pytest import fixture, mark
from utils.tis_log import LOG
from utils import table_parser, cli
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper
from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus, EventLogID
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def flavor_(request):
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    return flavor_id


@fixture(scope='module')
def vm_1(request, flavor_):

    vm_name = 'avp_test'
    flavor_id = flavor_

    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id)[1]
    time.sleep(30)

    # Teardown to remove the vm and flavor
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True)

    return vm_id


@fixture(scope='module')
def vm_2(request, flavor_):

    vm_name = 'virtio_test'
    flavor_id = flavor_

    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id)[1]
    time.sleep(30)
    # Teardown to remove the vm and flavor
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True)

    return vm_id


def get_column_value_from_multiple_columns(table, match_header_key,
                                           match_col_value, search_header_key):
    """
    Function for getting column value from multiple columns

    """
    column_value = None
    col_index = None
    match_index = None
    for header_key in table["headers"]:
        if header_key == match_header_key:
            match_index = table["headers"].index(header_key)
    for header_key in table["headers"]:
        if header_key == search_header_key:
            col_index = table["headers"].index(header_key)

    if col_index is not None and match_index is not None:
        for col_value in table['values']:
            if match_col_value == col_value[match_index]:
                column_value = col_value[col_index]
    return column_value

def get_column_value(table, search_value):
    """
    Function for getting column value

    Get value from table with two column
    :table param: parse table with two colums (dictionary)
    :search_value param: value in column for checking
    """
    column_value = None
    for col_value in table['values']:
        if search_value == col_value[0]:
            column_value = col_value[1]
    return column_value


#@mark.cpe_sanity
def test_tc4699_cold_migration_guest_instances(vm_1, vm_2):
    """Method to list a host subfunctions
    """

    test_res = True
    instance_list = [vm_1, vm_2]
    instance_dict = {}

    LOG.tc_step("Verify that all the instances were successfully launched")
    for vm_id in instance_list:
        instance_table = table_parser.table(cli.nova('list --all', auth_info=Tenant.ADMIN))
        vm_name = nova_helper.get_vm_name_from_id(vm_id=vm_id)
        time.sleep(10)
        instance_id = get_column_value_from_multiple_columns(instance_table,
                                                             "Name",
                                                              vm_name,
                                                             'ID')
        LOG.tc_step("Verify the location of each instance %s" % instance_id)
        instance_table = table_parser.table(cli.nova('show %s' % instance_id, auth_info=Tenant.ADMIN))
        hostname = get_column_value(instance_table, "OS-EXT-SRV-ATTR:host")

        # Save the instance location
        instance_dict[vm_name] = hostname

        LOG.tc_step("Cold migrate the instances")
        cli.nova('migrate %s' % instance_id, auth_info=Tenant.ADMIN)

        LOG.tc_step("Wait for the instance state to change")
        time.sleep(30)
        LOG.tc_step("Confirm the instance migration")
        instance_table = table_parser.table(cli.nova('list --all', auth_info=Tenant.ADMIN))
        instance_status = get_column_value_from_multiple_columns(instance_table,
                                                                      "Name",
                                                                      vm_name,
                                                                      'Status')
        if instance_status == 'VERIFY_RESIZE':
            cli.nova('resize-confirm %s' % instance_id, auth_info=Tenant.ADMIN)
        else:
            test_res = False
            break

        time.sleep(20)
        LOG.tc_step("Verify the new location of the instances")
        instance_table = table_parser.table(cli.nova('show %s' % instance_id, auth_info=Tenant.ADMIN))
        hostname = get_column_value(instance_table, "OS-EXT-SRV-ATTR:host")

        # Save the instance location
        if instance_dict[vm_name] == hostname:
            test_res = False
            break

    time.sleep(30)

    LOG.tc_step("Verify that all the instances were successfully migrated")
    instance_table = table_parser.table(cli.nova('list --all', auth_info=Tenant.ADMIN))

    for vm_id in instance_list:
        vm_name = nova_helper.get_vm_name_from_id(vm_id=vm_id)
        instance_status = get_column_value_from_multiple_columns(instance_table,
                                                             "Name",
                                                              vm_name,
                                                             'Status')

        if instance_status != 'ACTIVE':
            test_res = False
            break

    assert(test_res)


