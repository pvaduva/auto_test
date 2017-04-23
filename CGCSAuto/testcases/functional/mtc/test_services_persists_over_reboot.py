import time

from pytest import mark, skip

from utils import table_parser, cli
from utils.tis_log import LOG

from keywords import host_helper, system_helper, common
from testfixtures.recover_hosts import HostsToRecover


@mark.usefixtures('check_alarms')
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

    host = None
    if host_type == 'controller':
        if len(system_helper.get_controllers()) > 1:
            LOG.tc_step("Swact active controller")
            host_helper.swact_host()
            # give it sometime to setting before rebooting
            time.sleep(10)

        host = system_helper.get_active_controller_name()
    elif host_type == 'compute':
        if system_helper.is_small_footprint():
            skip("Not applicable to CPE")
        host = host_helper.get_nova_hosts()[-1]
    elif host_type == 'storage':
        # Make a better function for this
        hosts = host_helper.get_hosts(personality='storage')
        if hosts:
            host = hosts[0]
        else:
            skip(msg="Lab has no storage nodes. Skip rebooting storage node.")
    else:
        raise ValueError("Unknown host type specified. Valid options: controller, compute, storage")

    LOG.tc_step("Reboot a {} node: {}".format(host_type, host))
    HostsToRecover.add(host)
    host_helper.reboot_hosts(host, wait_for_reboot_finish=True)

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
