###
# below testcases is under SysInv Local Storage Test Plan -
# ~/wassp-repos/testmatrices/cgcs/teststrategies/cgcs2.0/us68398_sysinv_local_storage_test_plan.odt
# It specifically cover testcase 40 Local Storage Negative Test (Storage Host → Non-storage Host)
###

from pytest import fixture, skip, mark

from consts.auth import Tenant
from keywords import host_helper, system_helper, local_storage_helper
from testfixtures.recover_hosts import HostsToRecover
from utils import cli


# creating a storage profile on storage-0 node
# check storage is succesfully create

# apply that profile to compute-0
# verify rejected message
# Can not apply this profile to host
# echo $? is 1


# this test will run only if there is a storage node

def storage_node_not_exist():
    return len(system_helper.get_storage_nodes()) == 0


@fixture(scope='module')
def create_storage_profile(request):
    if storage_node_not_exist():
        skip("No storage node exist within lab for automation to continue")

    profile_name = 'storage_test_profile'
    host_name = 'storage-0'
    system_helper.create_storage_profile(host_name, profile_name=profile_name)
    disks_num = len(local_storage_helper.get_host_disks_values(host_name, 'device_node'))

    storage_profile = {
        'profile_name': profile_name,
        'hostname': host_name,
        'disk_num': disks_num
    }

    def teardown():
        system_helper.delete_storage_profile(profile_name)

    request.addfinalizer(teardown)

    return storage_profile


@mark.p3
@mark.parametrize('personality', [
    'compute',
    'controller'
])
def test_apply_storage_profile_negative(create_storage_profile, personality):

    if personality == 'controller':
        host_name = system_helper.get_standby_controller_name()
        assert host_name, "No standby controller available on system"
    else:
        host_name = host_helper.get_up_hypervisors()[0]

    profile_name = create_storage_profile['profile_name']
    origin_disk_num = create_storage_profile['disk_num']
    disks_num = len(local_storage_helper.get_host_disks_values(host_name, 'device_node'))

    expt_err = 'profile has more disks than host does' if disks_num < origin_disk_num -1 \
        else "Please check if host's disks match profile criteria"
    expt_err_list = ["Please check if host's disks match profile criteria",
                     "Failed to create storage function. Host personality must be 'storage'",
                     ]
    if disks_num < origin_disk_num -1:
        expt_err_list.append("profile has more disks than host does")

    positional_arg = host_name + ' ' + profile_name

    HostsToRecover.add(host_name)
    host_helper.lock_host(host_name, swact=True)
    exitcode, output = cli.system('host-apply-storprofile', positional_arg, fail_ok=True,
                                  auth_info=Tenant.ADMIN, rtn_list=True)
    host_helper.unlock_host(host_name)

    #assert exitcode == 1 and expt_err in output
    assert exitcode == 1 and any(expt in  output for expt in expt_err_list)

