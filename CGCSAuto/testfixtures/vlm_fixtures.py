from pytest import fixture

from keywords import vlm_helper, system_helper
from testfixtures.fixture_resources import VlmHostsReserved

from utils.tis_log import LOG
from utils.exceptions import VLMError


@fixture(scope='session', autouse=True)
def unreserve_hosts_session(request):
    """
    Unreserve hosts in test session teardown.

    Notes: Auto used fixture - import it to a testcase module or conftest.py file under a feature directory to auto use
        it on all children testcases.

    Examples:
        - see mtc/conftest.py for importing
        - use VlmHostsReserved.add(<host(s)>, <scope>) to add host(s) to unreserve list

    """
    def unreserve():
        __unreserve(scope='session')
    request.addfinalizer(unreserve)


@fixture(scope='module', autouse=True)
def unreserve_hosts_module(request):
    """
    Unreserve hosts in test module teardown.

    Notes: Auto used fixture - import it to a testcase module or conftest.py file under a feature directory to auto use
        it on all children testcases.

    Examples:
        - see mtc/conftest.py for importing
        - use VlmHostsReserved.add(<host(s)>, <scope>) to add host(s) to unreserve list

    Args:
        request: pytest param present caller test function

    """
    def unreserve():
        __unreserve(scope='module')
    request.addfinalizer(unreserve)


def __unreserve(scope):
    hosts_to_unreserve = VlmHostsReserved._get_hosts_reserved(scope)

    if hosts_to_unreserve:
        LOG.fixture_step("({}) Unreserve hosts: {}".format(scope, hosts_to_unreserve))
        try:
            vlm_helper.unreserve_hosts(hosts=hosts_to_unreserve)
        except VLMError as e:
            LOG.error(e)
            VlmHostsReserved._reset(scope)


@fixture(scope='module')
def reserve_unreserve_all_hosts_module():
    """
    Reserve all hosts in module setup and unreserve hosts in module teardown
    """
    __reserve_unreserve_all_hosts(scope='module')


@fixture(scope='session')
def reserve_unreserve_all_hosts_session(unreserve_hosts_session):
    """
    Reserve all hosts in session setup and unreserve hosts in session teardown
    """
    __reserve_unreserve_all_hosts(scope='session')


def __reserve_unreserve_all_hosts(scope):
    hosts = vlm_helper.get_hostnames_from_consts()
    VlmHostsReserved.add(hosts, scope=scope)
    vlm_helper.reserve_hosts(hosts)