import time

from pytest import mark

from utils import table_parser, cli
from utils.tis_log import LOG

from keywords import host_helper, system_helper


@mark.parametrize('host_type', [
    mark.sanity('controller'),
    mark.sanity('compute'),
    'storage'
])
def test_system_persist_over_host_reboot(host_type):
    """
    Validate Inventory summary over reboot of one of the controller see if data persists over reboot

    Test Steps:
        - capture Inventory summary for list of hosts on system service-list and neutron agent-list
        - reboot the current Controller-Active
        - Wait for reboot to complete
        - Validate key items from inventory persist over reboot

    """

    LOG.tc_step("Get 'system service-list', 'neutron agent-list', 'system host-list' output before rebooting host.")
    service_list_table_ = table_parser.table(cli.system('service-list'))
    neutron_list_table_ = table_parser.table(cli.neutron('agent-list'))
    host_list_table_ = table_parser.table(cli.system('host-list'))

    if host_type == 'controller':
        LOG.tc_step("Swact active controller")
        host_helper.swact_host()

        host = system_helper.get_active_controller_name()
        # give it sometime to setting before rebooting
        time.sleep(10)

    elif host_type == 'compute':
        host = host_helper.get_nova_hosts()[-1]
    elif host_type == 'storage':
        host = system_helper.get_storage_nodes()[0]
    else:
        raise ValueError("Unknown host type specified. Valid options: controller, compute, storage")

    LOG.tc_step("Reboot a {} node: {}".format(host_type, host))
    host_helper.reboot_hosts(host)

    # sleep 30 seconds for services to settle
    time.sleep(30)

    after_service_list_table_ = table_parser.table(cli.system('service-list'))
    after_neutron_list_table_ = table_parser.table(cli.neutron('agent-list'))
    after_host_list_table = table_parser.table(cli.system('host-list'))

    # check the states is same as before.
    LOG.tc_step("Check 'system service-list' output persist after {} reboot".format(host_type))
    service_list_result = table_parser.compare_tables(service_list_table_, after_service_list_table_)
    assert service_list_result[0] == 0, "system service-list comparison failed: {}".format(service_list_result[1])

    LOG.tc_step("Check 'neutron agent-list' output persist after {} reboot".format(host_type))
    neutron_list_result = table_parser.compare_tables(neutron_list_table_, after_neutron_list_table_)
    assert neutron_list_result[0] == 0, "neutron agent-list comparison failed: {}".format(neutron_list_result[1])

    LOG.tc_step("Check 'system host-list' output persist after {} reboot".format(host_type))
    host_list_result = table_parser.compare_tables(host_list_table_, after_host_list_table)
    assert host_list_result[0] == 0, "system host-list comparison failed: {}".format(host_list_result[1])


# @mark.sanity
# def test_validate_services_persists_over_controller_reboot():
#     """
#     Validate Inventory summary over reboot of one of the controller see if data persists over reboot
#
#     Args:
#         None
#
#     Setup:
#         - Standard 4 blade config: 2 controllers + 2 compute
#         - Lab booted and configure step complete
#
#     Test Steps:
#         - capture Inventory summary for list of hosts on system service-list and neutron agent-list
#         - reboot the current Controller-Active
#         - Wait for reboot to complete
#         - Validate key items from inventory persist over reboot
#
#     Teardown:
#         None
#     """
#
#     # retrieve states from controller-0
#     # retrieve nova service-list
#     service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
#     neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))
#
#     # retrieve neutron agent list
#
#     # swact so that controller1 become active
#
#     host_helper.swact_host(fail_ok=False)
#     active_controller = system_helper.get_active_controller_name()
#
#     # reboot active controller1
#     LOG.tc_step("Reboot active controller {}".format(active_controller))
#     host_helper.reboot_hosts(active_controller)
#     # now original active controller should be active
#     # sleep 20 seconds for services to settle
#     sleep(30)
#     after_service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
#     after_neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))
#
#     # retrieve system service-list
#     # retrieve neutron agent list
#     # check the states is same as before.
#     service_list_result = table_parser.compare_tables(service_list_table_, after_service_list_table_)
#     neutron_list_result = table_parser.compare_tables(neutron_list_table_, after_neutron_list_table_)
#
#     assert service_list_result[0] == 0, "Service list comparison failed: {}".format(service_list_result[1])
#     assert neutron_list_result[0] == 0, "neutron list comparison failed: {}".format(neutron_list_result[1])
#
#
# @mark.sanity
# def test_validate_services_persists_over_compute_reboot():
#     """
#     Validate Inventory summary over reboot of one of the compute node see if data persists over reboot
#
#     Args:
#         None
#     Setup:
#         - Standard 4 blade config: 2 controllers + 2 compute
#         - Lab booted and configure step complete
#
#     Test Steps:
#         - capture Inventory summary for list of hosts on system service-list and neutron agent-list
#         - reboot a compute node
#         - Wait for reboot to complete
#         - Validate key items from inventory persist over reboot
#
#     Teardown:
#         None
#     """
#
#     a_compute_node = host_helper.get_nova_host_with_min_or_max_vms()
#
#     # retrieve neutron agent list
#     service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
#     neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))
#
#     # reboot compute node
#     LOG.tc_step("Reboot compute node {}".format(a_compute_node))
#     host_helper.reboot_hosts(a_compute_node)
#     # now controller-0 should be active
#     # sleep 60 seconds for services to settle
#     sleep(60)
#     after_service_list_table_ = table_parser.table(cli.system('service-list', auth_info=Tenant.ADMIN, fail_ok=False))
#     after_neutron_list_table_ = table_parser.table(cli.neutron('agent-list', auth_info=Tenant.ADMIN, fail_ok=False))
#
#     # retrieve system service-list
#     # retrieve neutron agent list
#     # check the states is same as before.
#     service_list_result = table_parser.compare_tables(service_list_table_, after_service_list_table_)
#     neutron_list_result = table_parser.compare_tables(neutron_list_table_, after_neutron_list_table_)
#
#     assert service_list_result[0] == 0, "Service list comparison failed: {}".format(service_list_result[1])
#     assert neutron_list_result[0] == 0, "neutron list comparison failed: {}".format(neutron_list_result[1])
#
#
#
# @mark.sanity
# def test_validate_inventory_summary_persists_over_reboot():
#     """
#     Validate Inventory summary over reboot of one of the compute node see if data persists over reboot
#
#     Args:
#         None
#     Setup:
#         - Standard 4 blade config: 2 controllers + 2 compute
#         - Lab booted and configure step complete
#
#     Test Steps:
#         - capture Inventory summary for list of hosts on system host-list
#         - reboot the current Controller-Active
#         - Wait for reboot to complete
#         - Validate key items from inventory persist over reboot
#
#     Teardown:
#         None
#     """
#
#     # retrieve states from controller-0
#     # retrieve nova service-list
#     host_list_table_ = table_parser.table(cli.system('host-list', auth_info=Tenant.ADMIN, fail_ok=False))
#     # retrieve neutron agent list
#
#     # swact so that controller-1 become active
#     host_helper.swact_host(fail_ok=False)
#     active_controller = system_helper.get_active_controller_name()
#
#     # reboot active controller-1
#     LOG.tc_step("Reboot active controller {}".format(active_controller))
#     host_helper.reboot_hosts(active_controller)
#     # now original active controller should be active
#     # sleep 20 seconds for services to settle
#     sleep(30)
#     after_host_list_table_ = table_parser.table(cli.system('host-list', auth_info=Tenant.ADMIN, fail_ok=False))
#
#     # retrieve system service-list
#     # retrieve neutron agent list
#     # check the states is same as before.
#     host_list_result = table_parser.compare_tables(host_list_table_, after_host_list_table_)
#
#     assert host_list_result[0] == 0, "Service list comparison failed: {}".format(host_list_result[1])
