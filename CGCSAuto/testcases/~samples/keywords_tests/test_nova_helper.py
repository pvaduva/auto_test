from pytest import fixture, mark

from keywords import vm_helper, nova_helper, host_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def add_host_to_zone(request, add_cgcsauto_zone, add_admin_role_module):
    nova_zone_hosts = host_helper.get_nova_hosts(zone='nova')
    host_to_add = nova_zone_hosts[0]
    nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=host_to_add)

    def remove_host_from_zone():
        nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
    request.addfinalizer(remove_host_from_zone)

    return host_to_add


def test_boot_vm_on_host(add_host_to_zone):
    target_host = add_host_to_zone

    vm_id = vm_helper.boot_vm(name='cgcsauto_zone', avail_zone='cgcsauto', vm_host=target_host, cleanup='function')[1]

    assert target_host == nova_helper.get_vm_host(vm_id=vm_id)

    res, msg = vm_helper.cold_migrate_vm(vm_id=vm_id, fail_ok=True)

    assert 1 == res, "Expect cold migration reject due to no other host in cgcsauto zone, actual result: {}".format(msg)