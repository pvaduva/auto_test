from pytest import mark, skip, fixture

from keywords import nova_helper
from setup_consts import P1, P2
from utils.tis_log import LOG
from utils import exceptions

_skip = True

# @mark.skipif(_skip, reason='test skip if')
# @mark.usefixtures('check_alarms')
@mark.parametrize(('param1', 'param2', 'param3'), [
    P1(('val1', 1, True)),
    P2(('val2', 2, False)),
    P2(('val2', 2, True)),
])
def test_dummy1(param1, param2, param3):
    LOG.tc_step("test dummy 1 step~~ \nparam1: {}, param2:{}".format(param1, param2))
    res = nova_helper.get_all_vms()
    if not param3:
        skip("param3 is : {}".format(param3))
    LOG.info("All VMs: {}".format(res))

    if param2 == 1:
        raise Exception("test failure with exception")

    assert 0, 'dummy test failed ~~~~~~'

@mark.usefixtures('check_alarms')
def test_dummy2():
    LOG.tc_step("test dummy 2 step~~")
    pass


def test_fooo1():
    assert False, '1\n2\3\n4\n5\n6\n7\n8\n9\n10\n11'

def test_fooo2(foo_setup_fail):
    pass

def test_fooo3(foo_teardown_fail):
    #
    #

    error = """
test: tempest.api.compute.servers.test_create_server.ServersTestJSON.test_host_name_is_same_as_server_name[id-ac1ad47f-984b-4441-9274-c9079b7a0666]
test: tempest.api.compute.servers.test_create_server.ServersTestJSON.test_verify_created_server_vcpus[id-cbc0f52f-05aa-492b-bdc1-84b575ca294b]
test: tempest.api.compute.servers.test_create_server.ServersTestManualDisk.test_host_name_is_same_as_server_name[id-ac1ad47f-984b-4441-9274-c9079b7a0666]
test: tempest.api.compute.servers.test_create_server.ServersTestManualDisk.test_verify_created_server_vcpus[id-cbc0f52f-05aa-492b-bdc1-84b575ca294b]
test: tempest.api.compute.servers.test_server_actions.ServerActionsTestJSON.test_reboot_server_hard[id-2cb1baf6-ac8d-4429-bf0d-ba8a0ba53e32,smoke]
test: tempest.api.compute.servers.test_server_actions.ServerActionsTestJSON.test_rebuild_server[id-aaa6cdf3-55a7-461a-add9-1c8596b9a07c]
test: tempest.api.compute.volumes.test_attach_volume.AttachVolumeTestJSON.test_attach_detach_volume[id-52e9045a-e90d-4c0d-9087-79d657faffff]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers[id-3499406a-ae53-4f8c-b43a-133d4dc6fe3f,smoke]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_end_marker[id-5ca164e4-7bde-43fa-bafb-913b53b9e786]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_format_json[id-1c7efa35-e8a2-4b0b-b5ff-862c7fd83704]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_limit[id-5cfa4ab2-4373-48dd-a41f-a532b12b08b2]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_limit_and_end_marker[id-888a3f0e-7214-4806-8e50-5e0c9a69bb5e]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_limit_and_marker[id-f7064ae8-dbcc-48da-b594-82feef6ea5af]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_limit_and_marker_and_end_marker[id-8cf98d9c-e3a0-4e44-971b-c87656fdddbd]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_marker[id-638f876d-6a43-482a-bbb3-0840bca101c6]
test: tempest.api.object_storage.test_account_services.AccountTest.test_list_containers_with_marker_and_end_marker[id-ac8502c2-d4e4-4f68-85a6-40befea2ef5e]
test: tempest.api.object_storage.test_container_acl.ObjectTestACLs.test_read_object_with_rights[id-a3270f3f-7640-4944-8448-c7ea783ea5b6]
test: tempest.api.object_storage.test_container_acl.ObjectTestACLs.test_write_object_with_rights[id-aa58bfa5-40d9-4bc3-82b4-d07f4a9e392a]
"""
    raise exceptions.RefStackError(error)

def test_fooo4(foo_teardown_fail):
    assert 0, "test fun fail"

@fixture(scope='function')
def foo_setup_fail():
    raise ValueError("setup fail")


@fixture(scope='function')
def foo_teardown_fail(request):
    def teardown():
        raise IndexError('teardown fail')
    request.addfinalizer(teardown)

