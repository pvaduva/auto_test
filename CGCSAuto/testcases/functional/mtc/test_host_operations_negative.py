from pytest import fixture, mark

from utils import table_parser, cli
from keywords import host_helper, system_helper
from utils.tis_log import LOG


@mark.sx_sanity
def test_add_host_simplex_negative(simplex_only):
    """
    Test add second controller is rejected on simplex system
    Args:
        simplex_only: skip if non-sx system detected

    Test Steps:
        - On simplex system, check 'system host-add -n controller-1' is rejected

    """
    LOG.tc_step("Check adding second controller is rejected on simplex system")
    code, out = cli.system('host-add', '-n controller-1', fail_ok=True)

    assert 1 == code, "Unexpected exitcode for 'system host-add controller-1': {}".format(code)
    assert 'Adding a host on a simplex system is not allowed' in out, "Unexpected error message: {}".format(out)


def test_delete_host_if_unlock_negative():
    """
    TC1936 Verify that interfaces can't be deleted from an unlocked host

    Test Steps:
        - Choose an unlocked host and one of its interfaces
        - Attempt to delete the interface
        - Verify that the command was rejected

    """
    hosts = system_helper.get_hosts(administrative='unlocked')
    host = hosts[len(hosts) - 1]
    uuid = host_helper.get_host_interfaces(host, field='uuid', if_type='ethernet')[0]
    LOG.tc_step("Attempting to delete interface {} from host {}".format(uuid, host))
    code, out = cli.system('host-if-delete', '{} {}'.format(host, uuid), fail_ok=True)
    LOG.tc_step("Verify that the cli was rejected")
    assert 1 == code, "FAIL: Request to delete if was not rejected. Code: {}".format(code)


@fixture(scope='function')
def lock_(request):
    hosts = system_helper.get_hosts()
    host = hosts[0]
    if hosts[0] == system_helper.get_active_controller_name():
        if not system_helper.is_aio_simplex():
            host = hosts[1]
    host_helper.lock_host(host)

    def unlock_():
        host_helper.unlock_host(host)

    request.addfinalizer(unlock_)
    return host


# Low priority test case that takes too long to test
def _test_modify_non_existing_cpu_negative(lock_):
    """
    TC1940 cpu data can't be modified for a non existing cpu

    Test Steps:
        - Choose a host to lock and find how many phys cores it has
        - Attempt to change the cpu settings for a phys core that doesn't exist
        - Verify that the cli is rejected

    """
    host = lock_
    table_ = host_helper.get_host_cpu_list_table(host)
    cores = set(table_parser.get_column(table_, 'phy_core'))
    fake_proc_num = 2
    while fake_proc_num in cores:
        fake_proc_num += 1
    fake_proc = 'p{}'.format(fake_proc_num)
    map_ = {fake_proc: 1}
    LOG.tc_step("Attempt to modify fake processor {}'s function to vSwitch".format(fake_proc))
    code, out = host_helper.modify_host_cpu(host, 'vSwitch', fail_ok=True, **map_)
    assert 0 != code, "FAIL: Modifying a non existing processor was not rejected"

    hosts = system_helper.get_hosts()
    name = hosts[len(hosts) - 1] + "a"
    while True:
        if name not in hosts:
            break
        name += "a"
    LOG.tc_step("Attempt to modify fake host {}'s processor p0 function to vSwitch".format(name))
    code, out = host_helper.modify_host_cpu(name, 'vSwitch', p0=1, fail_ok=True)
    LOG.tc_step("Verifying that the cli was rejected")
    assert 1 == code, "FAIL: Modifying a cpu on a non-existant host was not rejected"


def test_modify_cpu_unlock_negative():
    """
    TC1942 Verify that cpu data can't be modified on an unlocked host

    Test Steps:
        - Choose an unlocked host
        - Attempt to change host's cpu settings
        - Verify that the command is rejected

    """
    hosts = system_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("Host {} is unlocked. Attempt to change its p0 function to vSwitch".format(host))
        code, out = host_helper.modify_host_cpu(host, 'vswitch', fail_ok=True, p0=0)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: Request to modify cpu settings was not rejected"


def test_change_personality_unlock_negative():
    """
    TC1943 Verify that a host's personality can't be changed

    Test Steps:
        - For each host attempt to update its personality
        - Verify that each attempt is rejected

    """
    hosts = system_helper.get_hosts()
    for host in hosts:
        personality = system_helper.get_host_values(host, 'personality')[0]
        if personality == 'controller':
            change_to = 'worker'
        else:
            change_to = 'controller'
        LOG.tc_step("Attempting to change {}'s personality to {}".format(host, personality))
        code, out = cli.system('host-update', '{} personality={}'.format(host, change_to), fail_ok=True)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: The request to modify {}'s personality was not rejected".format(host)


def test_change_name_unlock_negative():
    """
    TC1945 Verify that a host's name can't be changed if it is unlocked

    Test Steps:
        - For each unlocked host attempt to change its name
        - Verify that each attempt is rejected

    """
    hosts = system_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("Attempting to change host {} name to {}1".format(host, host))
        code, out = cli.system('host-update', '{} hostname={}'.format(host, host + "1"), fail_ok=True)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: The request to modify {}'s name was not rejected".format(host)


def test_reset_host_unlock_negative():
    """
    TC1946 Verify that an unlocked host can't be reset

    Test Steps:
        - Attempt to reset each unlocked host
        - Verify that each attempt was rejected

    """
    hosts = system_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("{} is unlocked. Attempting to reset it".format(host))
        code, out = cli.system('host-reset', '{} '.format(host), fail_ok=True)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: The request to reset {} was not rejected".format(host)


################
#  Lock Unlock #
################

def test_unlock_unlocked_host_negative():
    """
    TC1947 Verify that you can't unlock an unlocked host

    Test Steps:
        - Attempt to unlock each unlocked host
        - Verify that each attempt is rejected

    """
    hosts = system_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("{} is already unlocked. Attempting to unlock it".format(host))
        code, out = cli.system('host-unlock', host, fail_ok=True)
        LOG.tc_step("Verifying that the cli was rejected")
        assert 1 == code, "FAIL: The request to reset {} was not rejected".format(host)


# Low priority test that takes too long to execute
def _test_lock_locked_host_negative(lock_):
    """
    TC1948 Verify that you can't lock an already locked host

    Setup:
        - Lock a host

    Test Steps:
        - Attempt to lock the host that was already locked
        - Verify that the command was rejected

    """
    host = lock_
    LOG.tc_step("{} is already locked. Attempting to lock it".format(host))
    code, out = host_helper.lock_host(host, check_first=False, fail_ok=True)
    LOG.tc_step("Verifying that the cli was rejected")
    assert 1 == code, "FAIL: {} was already locked. Attempt to lock it again was not rejected".format(host)


################
#  Host Delete #
################

@mark.domain_sanity
def test_delete_unlocked_node_negative():
    """
    Attempts to delete each unlocked node.
    Fails if one unlocked node does get deleted.

    Test Steps:
        - Creates a list of every unlocked host
        - Iterate through each host and attempt to delete it
        - Verify that each host rejected the delete request

    """

    hosts = system_helper.get_hosts(administrative='unlocked')

    deleted_nodes = []

    for node in hosts:
        LOG.tc_step("attempting to delete {}".format(node))
        LOG.info("{} state: {}".format(node, system_helper.get_host_values(node, fields='administrative')[0]))
        res, out = cli.system('host-delete', node, fail_ok=True)

        LOG.tc_step("Delete request - result: {}\tout: {}".format(res, out))

        assert 1 == res, "FAIL: The delete request for {} was not rejected".format(node)

        LOG.tc_step("Confirming that the node was not deleted")
        res, out = cli.system('host-show', node, fail_ok=True)

        if 'host not found' in out or res != 0:
            # the node was deleted even though it said it wasn't
            LOG.tc_step("{} was deleted.".format(node))
            deleted_nodes.append(node)

    assert not deleted_nodes, "Fail: Delete request for the following node(s) " \
                              "{} was accepted.".format(deleted_nodes)


def test_delete_nonexisting_host_negative():
    """
    TC1933
    Verfiy that cli rejects attempts to delete a non-existent node

    Test Steps:
        - Attempt to delete a non-existing host
        - Verify that the command is rejected

    """
    nodes = system_helper.get_hosts()
    name = nodes[len(nodes) - 1] + "a"
    while True:
        if name not in nodes:
            break
        name += "a"
    LOG.tc_step("Attempt to delete {}".format(name))
    code, out = cli.system('host-delete', name, fail_ok=True)
    assert 1 == code, "FAIL: Attempting to delete non-existent {} was not rejected".format(name)
