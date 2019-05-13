from pytest import fixture, mark, skip

from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper, host_helper, system_test_helper
from consts.auth import Tenant
from consts.proj_vars import ProjVar


@fixture(scope='function')
def check_alarms():
    pass


@fixture(scope='module', autouse=True)
def pre_check(request):
    """
    This is to adjust the quota and to launch the heat stack
    return: code 0/1
    """
    hypervisors = host_helper.get_up_hypervisors()
    if len(hypervisors) < 3:
        skip('System test heat tests require 3+ hypervisors')

    # disable remote cli for these testcases
    remote_cli = ProjVar.get_var('REMOTE_CLI')
    if remote_cli:
        ProjVar.set_var(REMOTE_CLI=False)

        def revert():
            ProjVar.set_var(REMOTE_CLI=remote_cli)
        request.addfinalizer(revert)

    vm_helper.set_quotas(networks=600, ports=1000, volumes=1000, cores=1000, instances=1000, ram=7168000,
                         server_groups=100, server_group_members=1000)
    system_test_helper.launch_lab_setup_tenants_vms()

    def list_status():
        LOG.fixture_step("Listing heat resources and nova migrations")
        stacks = heat_helper.get_stacks(auth_info=Tenant.ADMIN)
        for stack in stacks:
            heat_helper.get_stack_resources(stack=stack, auth_info=Tenant.ADMIN)

        nova_helper.get_migration_list_table()
        # system_test_helper.delete_lab_setup_tenants_vms()
    request.addfinalizer(list_status)


@mark.p1
@mark.parametrize('number_of_hosts_to_lock', [
    1,
    3,
])
def _test_sys_lock_unlock_hosts(number_of_hosts_to_lock):
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    # identify a host with atleast 5 vms

    system_test_helper.sys_lock_unlock_hosts(number_of_hosts_to_lock=number_of_hosts_to_lock)


@mark.p1
@mark.parametrize('number_of_hosts_to_evac', [
    1,
    3,
    5,
])
def _test_sys_evacuate_from_hosts(number_of_hosts_to_evac):
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    system_test_helper.sys_evacuate_from_hosts(number_of_hosts_to_evac=number_of_hosts_to_evac)


def _test_sys_storage_reboot():
    system_test_helper.sys_reboot_storage()


def _test_sys_standby_reboot():
    system_test_helper.sys_reboot_standby()


def _test_sys_controlled_swact():
    system_test_helper.sys_controlled_swact()


def _test_sys_uncontrolled_swact():
    system_test_helper.sys_uncontrolled_swact()


def _test_sys_lock_unlock_standby():
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    # identify a host with atleast 5 vms

    system_test_helper.sys_lock_unlock_standby()


def test_sys_ping_all_vms():
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    # identify a host with atleast 5 vms

    system_test_helper.ping_all_vms_from_nat_box()
