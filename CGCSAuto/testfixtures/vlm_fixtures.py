from pytest import fixture

from keywords import vlm_helper

from utils.tis_log import LOG
from utils.exceptions import VLMError


@fixture(scope='session', autouse=True)
def unreserve_hosts_session(request):
    """
    Module level fixture to delete created resources after each caller testcase.

    Notes: Auto used fixture - import it to a conftest.py file under a feature directory to auto use it on all children
        testcases.

    Examples:
        - see nova/conftest.py for importing
        - see ResourceCleanup.add function usages in nova/test_shared_cpu.py for adding resources to cleanups

    Args:
        request: pytest param present caller test function

    """
    def unreserve():
        __unreserve(scope='session')
    request.addfinalizer(unreserve)


@fixture(scope='module', autouse=True)
def unreserve_hosts_module(request):
    """
    Module level fixture to delete created resources after each caller testcase.

    Notes: Auto used fixture - import it to a conftest.py file under a feature directory to auto use it on all children
        testcases.

    Examples:
        - see nova/conftest.py for importing
        - see ResourceCleanup.add function usages in nova/test_shared_cpu.py for adding resources to cleanups

    Args:
        request: pytest param present caller test function

    """
    def unreserve():
        __unreserve(scope='module')
    request.addfinalizer(unreserve)


def __unreserve(scope):
    hosts_to_unreserve = HostsReserved._get_hosts_reserved(scope)

    LOG.fixture_step("({}) Unreserve hosts: {}".format(scope, hosts_to_unreserve))
    try:
        vlm_helper.unreserve_hosts(hosts=hosts_to_unreserve)
    except VLMError as e:
        LOG.error(e)

    HostsReserved._reset(scope)


class HostsReserved:
    __hosts_reserved_dict = {
        'function': [],
        'class': [],
        'module': [],
        'session': [],
    }

    @classmethod
    def _reset(cls, scope):
        cls.__hosts_reserved_dict[scope] = []

    @classmethod
    def _get_hosts_reserved(cls, scope):
        return cls.__hosts_reserved_dict[scope]

    @classmethod
    def add(cls, hosts, scope='session'):
        """
        Add resource to cleanup list.

        Args:
            hosts (str|list): hostname(s)
            scope (str): one of these: 'function', 'class', 'module', 'session'

        """
        scope = scope.lower()
        valid_scopes = ['function', 'class', 'module', 'session']

        if scope not in valid_scopes:
            raise ValueError("'scope' param value has to be one of the: {}".format(valid_scopes))

        if not isinstance(hosts, (list, tuple)):
            hosts = [hosts]

        for host in hosts:
            cls.__hosts_reserved_dict[scope].append(host)