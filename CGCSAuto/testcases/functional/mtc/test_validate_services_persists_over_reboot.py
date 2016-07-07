from pytest import fixture, mark
from time import sleep

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, glance_helper,system_helper

@mark.sanity
def test_validate_services_persists_over_controller_reboot():
    """
    Validate Inventory summary over reboot of one of the controller see if data persists over reboot

    Args:
        None

    Setup:
        - Standard 4 blade config: 2 controllers + 2 compute
        - Lab booted and configure step complete

    Test Steps:
        - capture Inventory summary for list of hosts on system service-list and neutron agent-list
        - reboot the current Controller-Active
        - Wait for reboot to complete
        - Validate key items from inventory persist over reboot

    Teardown:
        None
    """

    # retrieve states from controller-0
    # retrieve nova service-list
    service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
    neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))
    # retrieve neutron agent list

    # swact so that controller1 become active

    host_helper.swact_host(fail_ok=False)
    active_controller = system_helper.get_active_controller_name()

    # reboot active controller1
    LOG.tc_step("Reboot active controller {}".format(active_controller))
    host_helper.reboot_hosts(active_controller)
    # now original active controller should be active
    # sleep 20 seconds for services to settle
    sleep(30)
    after_service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
    after_neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))

    # retrieve system service-list
    # retrieve neutron agent list
    # check the states is same as before.
    service_list_result = table_parser.compare_tables(service_list_table_, after_service_list_table_)
    neutron_list_result = table_parser.compare_tables(neutron_list_table_, after_neutron_list_table_)

    assert service_list_result[0] == 0, "Service list comparison failed: {}".format(service_list_result[1])
    assert neutron_list_result[0] == 0, "neutron list comparison failed: {}".format(neutron_list_result[1])


@mark.sanity
def test_validate_services_persists_over_compute_reboot():
    """
    Validate Inventory summary over reboot of one of the compute node see if data persists over reboot

    Args:
        None
    Setup:
        - Standard 4 blade config: 2 controllers + 2 compute
        - Lab booted and configure step complete

    Test Steps:
        - capture Inventory summary for list of hosts on system service-list and neutron agent-list
        - reboot a compute node
        - Wait for reboot to complete
        - Validate key items from inventory persist over reboot

    Teardown:
        None
    """

    a_compute_node = host_helper.get_nova_host_with_min_or_max_vms()

    # retrieve neutron agent list
    service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
    neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))

    # reboot compute node
    LOG.tc_step("Reboot compute node {}".format(a_compute_node))
    host_helper.reboot_hosts(a_compute_node)
    # now controller-0 should be active
    # sleep 60 seconds for services to settle
    sleep(60)
    after_service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
    after_neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))

    # retrieve system service-list
    # retrieve neutron agent list
    # check the states is same as before.
    service_list_result = table_parser.compare_tables(service_list_table_, after_service_list_table_)
    neutron_list_result = table_parser.compare_tables(neutron_list_table_, after_neutron_list_table_)

    assert service_list_result[0] == 0, "Service list comparison failed: {}".format(service_list_result[1])
    assert neutron_list_result[0] == 0, "neutron list comparison failed: {}".format(neutron_list_result[1])


@mark.sanity
def test_validate_inventory_summary_persists_over_reboot():
    """
    Validate Inventory summary over reboot of one of the compute node see if data persists over reboot

    Args:
        None
    Setup:
        - Standard 4 blade config: 2 controllers + 2 compute
        - Lab booted and configure step complete

    Test Steps:
        - capture Inventory summary for list of hosts on system host-list
        - reboot the current Controller-Active
        - Wait for reboot to complete
        - Validate key items from inventory persist over reboot

    Teardown:
        None
    """

    # retrieve states from controller-0
    # retrieve nova service-list
    host_list_table_ = table_parser.table(cli.system('host-list', auth_info=Tenant.ADMIN, fail_ok=False))
    # retrieve neutron agent list

    # swact so that controller-1 become active
    host_helper.swact_host(fail_ok=False)
    active_controller = system_helper.get_active_controller_name()

    # reboot active controller-1
    LOG.tc_step("Reboot active controller {}".format(active_controller))
    host_helper.reboot_hosts(active_controller)
    # now original active controller should be active
    # sleep 20 seconds for services to settle
    sleep(30)
    after_host_list_table_ = table_parser.table(cli.system('host-list', auth_info=Tenant.ADMIN, fail_ok=False))

    # retrieve system service-list
    # retrieve neutron agent list
    # check the states is same as before.
    host_list_result = table_parser.compare_tables(host_list_table_, after_host_list_table_)

    assert host_list_result[0] == 0, "Service list comparison failed: {}".format(host_list_result[1])
