###
# below testcases is under SysInv Local Storage Test Plan -
# ~/wassp-repos/testmatrices/cgcs/teststrategies/cgcs2.0/us68398_sysinv_local_storage_test_plan.odt
# It specifically cover testcase 40 Local Storage Negative Test (Storage Host → Non-storage Host)
###

from pytest import fixture, mark, skip
import ast

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3
from testfixtures.recover_hosts import HostsToRecover


#creating a storage profile on storage-0 node
#check storage is succesfully create

# apply that profile to compute-0
#verify rejected message
#Can not apply this profile to host
#echo $? is 1


#this test will run only if there is a storage node
#need to add skipif
def storage_node_not_exist():
    return len(system_helper.get_storage_nodes()) == 0


@fixture(scope='module')
def create_storage_profile(request):

    profile_name = 'storage_test_profile'
    host_name = 'storage-0'
    positional_arg = profile_name + ' ' + host_name
    cli.system('storprofile-add', positional_arg)

    storage_profile = {
        'profile_name': profile_name,
        'host_name': host_name
    }

    return storage_profile


def test_storage_profile_on_compute(create_storage_profile):
    # apply that profile to compute-0
    if storage_node_not_exist():
        skip("No storage node exist within lab for automation to continue")
    host_name = 'compute-0'
    profile_name = create_storage_profile['profile_name']
    positional_arg = host_name + ' ' + profile_name

    HostsToRecover.add(host_name)
    host_helper.lock_host(host_name)
    exitcode, output = cli.system('host-apply-storprofile', positional_arg, fail_ok=True,
                                  auth_info=Tenant.ADMIN, rtn_list=True)
    host_helper.unlock_host(host_name)

    assert exitcode == 1 and "Can not apply this profile to host" in output
    #verify rejected message
    #Can not apply this profile to host
    #echo $? is 1


def test_storage_profile_on_controller(create_storage_profile):
    # need to check is it true that you can not lock active controller
    #apply that profile to the standby controller
    #verify rejected message

    if storage_node_not_exist():
        skip("No storage node exist within lab for automation to continue")
    host_name = system_helper.get_standby_controller_name()
    profile_name = create_storage_profile['profile_name']
    positional_arg = host_name + ' ' + profile_name

    HostsToRecover.add(host_name)
    host_helper.lock_host(host_name)
    exitcode, output = cli.system('host-apply-storprofile', positional_arg, fail_ok=True,
                                  auth_info=Tenant.ADMIN, rtn_list=True)
    host_helper.unlock_host(host_name)

    assert exitcode == 1

