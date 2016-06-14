from pytest import mark

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ServerGroupMetadata
from keywords import nova_helper, vm_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('srv_grp_msging_flavor', 'policy', 'group_size', 'best_effort', 'vms_num'), [
    mark.p1((None, 'affinity', 4, None, 1)),
    mark.p1((None, 'anti-affinity', 3, True, 1)),
    mark.p2((True, 'anti-affinity', 2, None, 2)),
])
def test_boot_vms_server_group(srv_grp_msging_flavor, policy, group_size, best_effort, vms_num):
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

    Teardown:
        - Delete created vm
        - Delete created server group

    """
    LOG.tc_step("Create a flavor with server group messaging set to {}".format(srv_grp_msging_flavor))
    flavor_id = nova_helper.create_flavor('srv_grp')[1]
    ResourceCleanup.add('flavor', resource_id=flavor_id)
    if srv_grp_msging_flavor is not None:
        nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.SRV_GRP_MSG: srv_grp_msging_flavor})

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

    LOG.tc_step("Boot {} vm(s) with above flavor in above server group.".format(vms_num))
    for i in range(vms_num):
        vm_id = vm_helper.boot_vm(name='srv_grp', flavor=flavor_id, hint={'group': srv_grp_id})[1]
        ResourceCleanup.add(resource_type='vm', resource_id=vm_id)

        LOG.tc_step("Check vm {} is in server group {}".format(vm_id, srv_grp_id))
        members = eval(nova_helper.get_server_groups_info(srv_grp_id, header='Members')[0])
        assert vm_id in members, "VM {} is not a member of server group {}".format(vm_id, srv_grp_id)

