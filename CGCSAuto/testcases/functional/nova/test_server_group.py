import re
from pytest import mark, skip, fixture

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ServerGroupMetadata
from consts.reasons import SkipReason
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module', autouse=True)
def check_system(add_cgcsauto_zone, add_admin_role_module):
    hosts = host_helper.get_hypervisors(state='up', status='enabled')

    is_simplex = system_helper.is_simplex()
    if is_simplex:
        hosts_to_add = hosts
    elif len(hosts) >= 2:
        hosts_to_add = hosts[:2]
    else:
        skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)
        hosts_to_add = []

    LOG.fixture_step("Add hosts to cgcsauto aggregate: {}".format(hosts_to_add))
    nova_helper.add_hosts_to_aggregate('cgcsauto', hosts_to_add)

    def remove_():
        LOG.fixture_step("Remove hosts from cgcsauto aggregate: {}".format(hosts_to_add))
        nova_helper.remove_hosts_from_aggregate('cgcsauto', hosts_to_add)

    return is_simplex, hosts_to_add


@mark.parametrize(('srv_grp_msging_flavor', 'policy', 'group_size', 'best_effort', 'vms_num'), [
    mark.priorities('nightly', 'domain_sanity')((None, 'affinity', 4, None, 2)),
    mark.domain_sanity((None, 'anti_affinity', 3, True, 3)),
    mark.nightly(('srv_grp_msg_true', 'anti_affinity', 4, None, 3)),    # negative res for last vm
])
def test_boot_vms_server_group(srv_grp_msging_flavor, policy, group_size, best_effort, vms_num, check_system):
    """
    Test boot vm with specified server group

    Args:
        srv_grp_msging_flavor (str): server group messaging flavor spec
        policy (str): server group policy to set when creating the group
        group_size (int): group size metadata to set for server group
        best_effort (bool): best effort metadata to set for server group
        vms_num (int): number of vms to boot

    Test Steps:
        - Create a server group with given policy
        - Add given metadata to above server group
        - Boot vm(s) with above server group
        - Verify vm(s) booted successfully and is a member of the server group
        - If server_group_messaging is on, then verify vms can communicate with each other
        - If server group messaging is off, verify server_group_app is not included in vm

    Teardown:
        - Delete created vm
        - Delete created server group

    """
    is_simplex, cgcsauto_hosts = check_system
    if is_simplex and policy == 'anti_affinity' and not best_effort:
        skip("Skip anti_affinity strict for simplex system")

    LOG.tc_step("Create a flavor with server group messaging set to {}".format(srv_grp_msging_flavor))
    flavor_id = nova_helper.create_flavor('srv_grp')[1]
    ResourceCleanup.add('flavor', resource_id=flavor_id)

    srv_grp_msg = False
    if srv_grp_msging_flavor is not None:
        srv_grp_msg = True if 'true' in srv_grp_msging_flavor.lower() else False
        nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.SRV_GRP_MSG: srv_grp_msg})

    LOG.tc_step("Create a server group with policy set to {}".format(policy))
    srv_grp_id = nova_helper.create_server_group(policy=policy)[1]
    ResourceCleanup.add(resource_type='server_group', resource_id=srv_grp_id)

    metadata = {}
    if group_size is not None:
        metadata[ServerGroupMetadata.GROUP_SIZE] = group_size
    if best_effort is not None:
        metadata[ServerGroupMetadata.BEST_EFFORT] = best_effort

    LOG.tc_step("Add server group metadata: {}".format(metadata))
    nova_helper.set_server_group_metadata(srv_grp_id, **metadata)

    vm_hosts = []
    members = []
    failed_num = 0
    if policy == 'anti_affinity' and not best_effort and vms_num > 2:
        failed_num = vms_num - 2
        vms_num = 2

    LOG.tc_step("Boot {} vm(s) with flavor {} in server group {} and ensure they are successfully booted.".
                format(flavor_id, srv_grp_id, vms_num))

    for i in range(vms_num):
        code, vm_id, err, vol = vm_helper.boot_vm(name='srv_grp', flavor=flavor_id, hint={'group': srv_grp_id},
                                                  avail_zone='cgcsauto', fail_ok=True)
        ResourceCleanup.add(resource_type='vm', resource_id=vm_id, del_vm_vols=False)
        ResourceCleanup.add('volume', vol)
        assert 0 == code, "VM is not booted successfully. Details: {}".format(err)

        LOG.tc_step("Check vm {} is in server group {}".format(vm_id, srv_grp_id))
        members = eval(nova_helper.get_server_groups_info(srv_grp_id, header='Members')[0])
        assert vm_id in members, "VM {} is not a member of server group {}".format(vm_id, srv_grp_id)

        vm_hosts.append(nova_helper.get_vm_host(vm_id))

    for i in range(failed_num):
        LOG.tc_step("Boot vm{} in server group {} that's expected to fail".format(i, srv_grp_id))
        code, vm_id, err, vol = vm_helper.boot_vm(name='srv_grp', flavor=flavor_id, hint={'group': srv_grp_id},
                                                  avail_zone='cgcsauto', fail_ok=True)
        nova_helper.get_vm_nova_show_value(vm_id, 'fault')
        assert 1 == code, "Boot vm is not rejected"

    unique_vm_hosts = list(set(vm_hosts))
    if policy == 'affinity' or is_simplex:
        assert 1 == len(unique_vm_hosts)

    else:
        assert len(unique_vm_hosts) >= 2

    assert len(members) == vms_num

    vm_to_ssh = members[0]
    another_vm = members[1]

    vm_helper.wait_for_vm_pingable_from_natbox(vm_to_ssh)
    vm_helper.wait_for_vm_pingable_from_natbox(another_vm)

    LOG.tc_step("Login to a member {} in server group".format(vm_to_ssh))
    with vm_helper.ssh_to_vm_from_natbox(vm_to_ssh) as vm_ssh:
        if srv_grp_msg:

            LOG.tc_step("Ensure server_group_app is included on VM")
            output = vm_ssh.exec_cmd('server_group_app', blob='\r\n\r\n', get_exit_code=False, fail_ok=False,
                                     force_end=True)[1]
            print(output)
            assert 'got server group status response msg: [' in output

            LOG.tc_step("Pause another vm in same server group and ensure current vm receive notification")
            vm_ssh.exec_cmd('server_group_app', blob='\r\n\r\n', get_exit_code=False, fail_ok=False)
            vm_helper.pause_vm(vm_id=another_vm)

            vm_ssh.send()
            for i in range(10):
                code = vm_ssh.expect('\r\n\r\n', fail_ok=True)
                if code < 0:
                    assert False, "No more server group notification received. No pause.end notification found."

                current_output = vm_ssh.cmd_output
                if re.search('{}.*compute.instance.pause.end'.format(another_vm), current_output):
                    vm_ssh.expect('\r\n\r\n', fail_ok=True)
                    break
            else:
                assert False, "No pause.end notification found in past 10 notifications"

        else:
            LOG.tc_step("Ensure server_group_app is not included in VM")
            code, output = vm_ssh.exec_cmd("server_group_app", fail_ok=True)
            assert code > 0
