import re
import time
import random
from pytest import mark, skip, fixture

from utils.tis_log import LOG
from utils.multi_thread import MThread, Events

from consts.cgcs import FlavorSpec, ServerGroupMetadata
from consts.reasons import SkipHypervisor
from consts.cli_errs import SrvGrpErr
from keywords import nova_helper, vm_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs


@fixture(scope='module')
def setups(no_simplex):
    vm_helper.ensure_vms_quotas(vms_num=10, cores_num=20, vols_num=10)
    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
    if len(hosts) < 2:
        skip("Less than two hosts with in same storage aggregate")

    LOG.fixture_step("Create a flavor with server group messaging enabled")
    flavor_id = nova_helper.create_flavor('srv_grp_msg', storage_backing=storage_backing)[1]
    nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.SRV_GRP_MSG: True})

    LOG.fixture_step("Create affinity and anti-affinity server groups")
    affinity_grp = nova_helper.create_server_group(policy='affinity')[1]
    anti_affinity_grp = nova_helper.create_server_group(policy='anti_affinity')[1]

    if len(hosts) < 3:
        LOG.fixture_step("Turn on best effort flag for anti-affinity group due to less than 3 computes on system")
        nova_helper.set_server_group_metadata(anti_affinity_grp, **{ServerGroupMetadata.BEST_EFFORT: True})

    return hosts, flavor_id, {'affinity': affinity_grp, 'anti_affinity': anti_affinity_grp}


def test_launch_server_group_vms(setups):
    """
    Launch two affinity and two anti-affinity vms and live/cold migrate them

    Test Steps:
        - Launch two affinity vms with best effort = False:
            - 1 boot-from-volume and 1 boot-from-image
        - Launch two anti-affinity vms with best effort=True only if there are more than 2 computes
            - 1 boot-from-volume and 1 boot-from-image

    """
    hosts, flavor_id, server_groups = setups

    boot_sources = ('volume', 'image')
    vms_dict = {}
    for policy, srv_grp_id in server_groups.items():
        vms = []

        for source in boot_sources:
            vm_name = '{}_{}'.format(policy, source)
            vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id, hint={'group': srv_grp_id}, source=source)[1]

            server_group_output = nova_helper.get_vm_nova_show_values(vm_id, ['wrs-sg:server_group'])[0]
            assert srv_grp_id in server_group_output, \
                'Server group info does not appear in nova show for vm {}'.format(vm_id)

            members = nova_helper.get_server_group_info(srv_grp_id, headers='Members')[0]
            LOG.tc_step("Check vm {} is in server group {}".format(vm_id, srv_grp_id))
            assert vm_id in members, "VM {} is not a member of server group {}".format(vm_id, srv_grp_id)

            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
            vms.append(vm_id)

        # initially the anti-affinity vms should go onto diff host since there are at least 2 hosts on system
        check_vm_hosts(vms=vms, policy=policy, best_effort=False)
        vms_dict[policy] = vms

    _check_affinity_vms()
    _check_anti_affinity_vms()


def check_vm_hosts(vms, policy='affinity', best_effort=False):
    vm_hosts = []
    for vm in vms:
        vm_host = nova_helper.get_vm_host(vm_id=vm)
        vm_hosts.append(vm_host)

    vm_hosts = list(set(vm_hosts))
    if policy == 'affinity':
        if best_effort:
            return 1 == len(vm_hosts)
        assert 1 == len(vm_hosts), "VMs in affinity group are not on same host"

    else:
        if best_effort:
            return len(vms) == len(vm_hosts)
        assert len(vms) == len(vm_hosts), "VMs in anti_affinity group are not on different host"

    return vm_hosts


def _check_affinity_vms():
    affinity_vms = nova_helper.get_server_group_info(group_name='grp_affinity', headers='Members')[0]
    vm_host = check_vm_hosts(vms=affinity_vms, policy='affinity')[0]

    for vm_id in affinity_vms:
        vm_helper.wait_for_vm_status(vm_id=vm_id, check_interval=10)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

        res, out = vm_helper.live_migrate_vm(vm_id=vm_id, fail_ok=True)
        assert res in (1, 2, 6), out

        res, out = vm_helper.cold_migrate_vm(vm_id=vm_id, fail_ok=True)
        assert res in (1, 2), out

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    return vm_host, affinity_vms


def _check_anti_affinity_vms():
    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
    best_effort = True if len(hosts) < 3 else False
    anti_affinity_vms = nova_helper.get_server_group_info(group_name='grp_anti_affinity', headers='Members')[0]

    check_vm_hosts(vms=anti_affinity_vms, policy='anti_affinity', best_effort=best_effort)

    vm_hosts = []
    for vm_id in anti_affinity_vms:
        vm_helper.wait_for_vm_status(vm_id=vm_id, check_interval=10)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

        vm_helper.live_migrate_vm(vm_id=vm_id)
        vm_helper.cold_migrate_vm(vm_id=vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

        vm_hosts.append(nova_helper.get_vm_host(vm_id))

    return vm_hosts, anti_affinity_vms
