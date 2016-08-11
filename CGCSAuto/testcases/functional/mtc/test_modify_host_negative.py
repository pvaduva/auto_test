from pytest import fixture
from utils import table_parser, cli
from keywords import host_helper, system_helper
from utils.tis_log import LOG


def test_delete_host_if():
    """
    TC1936 Verify that interfaces can't be deleted from an unlocked host

    Test Steps:
        - Choose an unlocked host and one of its interfaces
        - Attempt to delete the interface
        - Verify that the command was rejected

    """
    hosts = host_helper.get_hosts(administrative='unlocked')
    host = hosts[len(hosts) - 1]
    uuid = system_helper.get_host_interfaces_info(host, header='uuid', if_type='ethernet')[0]
    # uuid = table_parser.get_values(table_, 'uuid', type='ethernet')[0]
    LOG.tc_step("Attempting to delete interface {} from host {}".format(uuid, host))
    code, out = cli.system('host-if-delete', '{} {}'.format(host, uuid), fail_ok=True, rtn_list=True)
    LOG.tc_step("Verify that the cli was rejected")
    assert 1 == code, "FAIL: Request to delete if was not rejected. Code: {}".format(code)


@fixture(scope='function')
def lock_(request):
    hosts = host_helper.get_hypervisors()
    host = hosts[0]
    if hosts[0] == system_helper.get_active_controller_name():
        host = hosts[1]
    host_helper.lock_host(host)

    def unlock_():
        host_helper.unlock_host(host, check_hypervisor_up=True)

    request.addfinalizer(unlock_)
    return host


def test_modify_non_existing_cpu(lock_):
    """
    TC1940 cpu data can't be modified for a non existing cpu

    Test Steps:
        - Choose a host to lock and find how many phys cores it has
        - Attempt to change the cpu settings for a phys core that doesn't exist
        - Verify that the cli is rejected

    """
    host = lock_
    table_ = system_helper.get_host_cpu_list(host)
    cores = set(table_parser.get_column(table_, 'phy_core'))
    fake_proc_num = 2
    while fake_proc_num in cores:
        fake_proc_num += 1
    fake_proc = 'p{}'.format(fake_proc_num)
    map_ = {}
    map_[fake_proc] = 1
    LOG.tc_step("Attempt to modify fake processor {}'s function to shared".format(fake_proc))
    code, out = host_helper.modify_host_cpu(host, 'shared', fail_ok=True, **map_)
    assert 0 != code, "FAIL: Modifying a non existing processor was not rejected"

    hosts = host_helper.get_hosts()
    name = hosts[len(hosts) - 1] + "a"
    while True:
        if name not in hosts:
            break
        name += "a"
    LOG.tc_step("Attempt to modify fake host {}'s processor p0 function to shared".format(name))
    code, out = host_helper.modify_host_cpu(name, 'shared', p0=1, fail_ok=True)
    LOG.tc_step("Verifying that the cli was rejected")
    assert 1 == code, "FAIL: Modifying a cpu on a non-existant host was not rejected"


def test_modify_cpu_unlocked_host():
    """
    TC1942 Verify that cpu data can't be modified on an unlocked host

    Test Steps:
        - Choose an unlocked host
        - Attempt to change host's cpu settings
        - Verify that the command is rejected

    """
    hosts = host_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("Host {} is unlocked. Attempt to change its p0 function to vSwitch".format(host))
        code, out = host_helper.modify_host_cpu(host, 'vswitch', fail_ok=True, p0=0)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: Request to modify cpu settings was not rejected"


def test_change_personality():
    """
    TC1943 Verify that a host's personality can't be changed

    Test Steps:
        - For each host attempt to update its personality
        - Verify that each attempt is rejected

    """
    hosts = host_helper.get_hosts()
    for host in hosts:
        personality = host_helper.get_hostshow_value(host, 'personality')
        if personality == 'controller':
            change_to = 'compute'
        else:
            change_to = 'controller'
        LOG.tc_step("Attempting to change {}'s personality to {}".format(host, personality))
        code, out = cli.system('host-update', '{} personality={}'.format(host, change_to), fail_ok=True, rtn_list=True)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: The request to modify {}'s personality was not rejected".format(host)


def test_change_name():
    """
    TC1945 Verify that a host's name can't be changed if it is unlocked

    Test Steps:
        - For each unlocked host attempt to change its name
        - Verify that each attempt is rejected

    """
    hosts = host_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("Attempting to change host {} name to {}1".format(host, host))
        code, out = cli.system('host-update', '{} hostname={}'.format(host, host + "1"), fail_ok=True, rtn_list=True)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: The request to modify {}'s name was not rejected".format(host)


def test_reset_host():
    """
    TC1946 Verify that an unlocked host can't be reset

    Test Steps:
        - Attempt to reset each unlocked host
        - Verify that each attempt was rejected

    """
    hosts = host_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("{} is unlocked. Attempting to reset it".format(host))
        code, out = cli.system('host-reset', '{} '.format(host), fail_ok=True, rtn_list=True)
        LOG.tc_step("Verifying that the cli was rejected")

        assert 1 == code, "FAIL: The request to reset {} was not rejected".format(host)


def test_unlock_unlocked_host():
    """
    TC1947 Verify that you can't unlock an unlocked host

    Test Steps:
        - Attempt to unlock each unlocked host
        - Verify that each attempt is rejected

    """
    hosts = host_helper.get_hosts(administrative='unlocked')
    for host in hosts:
        LOG.tc_step("{} is already unlocked. Attempting to unlock it".format(host))
        code, out = cli.system('host-unlock', host, fail_ok=True, rtn_list=True)
        LOG.tc_step("Verifying that the cli was rejected")
        assert 1 == code, "FAIL: The request to reset {} was not rejected".format(host)


def test_lock_locked_host(lock_):
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
