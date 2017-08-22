import time
from pytest import fixture, skip, mark

from utils.tis_log import LOG

from keywords import vm_helper, host_helper, nova_helper, cinder_helper
from testfixtures.recover_hosts import HostsToRecover
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module, unreserve_hosts_module


@fixture()
def add_hosts_to_zone(request, add_admin_role_class, add_cgcsauto_zone, reserve_unreserve_all_hosts_module):
    storage_backing, target_hosts = nova_helper.get_storage_backing_with_max_hosts()
    if len(target_hosts) < 2:
        skip("Less than two up hosts have same storage backing")

    LOG.fixture_step("Update instance and volume quota to at least 10 and 20 respectively")
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)

    hosts_to_add = target_hosts[:2]
    nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=hosts_to_add)

    def remove_hosts_from_zone():
        nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
    request.addfinalizer(remove_hosts_from_zone)

    return storage_backing, hosts_to_add


def test_evacuate_vms_stress(add_hosts_to_zone):
    """
    Test evacuate vms with various vm storage configs and host instance backing configs

    Args:
        storage_backing: storage backing under test
        add_admin_role_class (None): test fixture to add admin role to primary tenant

    Skip conditions:
        - Less than two hosts configured with storage backing under test

    Setups:
        - Add admin role to primary tenant (module)

    Test Steps:
        - Create flv_rootdisk without ephemeral or swap disks, and set storage backing extra spec
        - Create flv_ephemswap with ephemeral AND swap disks, and set storage backing extra spec
        - Boot following vms on same host and wait for them to be pingable from NatBox:
            - Boot vm1 from volume with flavor flv_rootdisk
            - Boot vm2 from volume with flavor flv_localdisk
            - Boot vm3 from image with flavor flv_rootdisk
            - Boot vm4 from image with flavor flv_rootdisk, and attach a volume to it
            - Boot vm5 from image with flavor flv_localdisk
        - power-off host from vlm
        - Ensure evacuation for all 5 vms are successful (vm host changed, active state, pingable from NatBox)
        - Repeat above evacuation steps

    Teardown:
        - Delete created vms, volumes, flavors
        - Remove admin role from primary tenant (module)

    """
    storage_backing, hosts = add_hosts_to_zone
    zone = 'cgcsauto'

    HostsToRecover.add(hosts)

    initial_host = hosts[0]

    vms = vm_helper.boot_vms_various_types(storage_backing=storage_backing, target_host=initial_host, avail_zone=zone)

    target_host = initial_host

    for i in range(100):
        post_host = hosts[0] if target_host != hosts[0] else hosts[1]
        LOG.info("===============Iteration {}============".format(i+1))
        vm_helper.evacuate_vms(target_host, vms, wait_for_host_up=True, post_host=post_host, timeout=720, vlm=True)

        target_host = post_host
        LOG.info("Rest for 120 seconds before next evacuation")
        time.sleep(120)
