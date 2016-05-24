from pytest import fixture

from utils import table_parser, cli
from consts.timeout import HostTimeout
from keywords import host_helper


@fixture(scope='function')
def hosts_recover_func(request):
    def wait():
        hosts = HostsToWait._get_hosts_to_wait(scope='function')
        if hosts:
            HostsToWait._reset('function')
            HostsToWait._wait(hosts)
    request.addfinalizer(wait)


@fixture(scope='class')
def hosts_recover_class(request):
    def wait():
        hosts = HostsToWait._get_hosts_to_wait(scope='class')
        if hosts:
            HostsToWait._reset('class')
            HostsToWait._wait(hosts)
    request.addfinalizer(wait)


@fixture(scope='function')
def hosts_recover_module(request):
    def wait():
        hosts = HostsToWait._get_hosts_to_wait(scope='module')
        if hosts:
            HostsToWait._reset('module')
            HostsToWait._wait(hosts)
    request.addfinalizer(wait)


class HostsToWait():
    __hosts_to_wait = {
        'function': [],
        'class': [],
        'module': [],
    }

    @classmethod
    def add(cls, hostnames, scope='function'):
        """
        Add host(s) to recover list. Will wait for host(s) to recover as test teardown.

        Args:
            hostnames (str|list):

        """
        valid_scope = cls.__hosts_to_wait.keys()
        if not scope in valid_scope:
            raise ValueError("scope has to be one of the following: {}".format(valid_scope))

        if isinstance(hostnames, str):
            hostnames = [hostnames]

        cls.__hosts_to_wait[scope] += hostnames

    @classmethod
    def _reset(cls, scope):
        cls.__hosts_to_wait[scope] = []

    @classmethod
    def _get_hosts_to_wait(cls, scope):
        return cls.__hosts_to_wait[scope]


    @staticmethod
    def _wait(hostnames):
        hostnames = sorted(hostnames)
        table_ = table_parser.table(cli.system('host-list'))
        table_ = table_parser.filter_table(table_, hostname=hostnames)

        unlocked_hosts = table_parser.get_values(table_, 'hostname', administrative='unlocked')
        locked_hosts = table_parser.get_values(table_, 'hostname', administrative='locked')

        host_helper._wait_for_hosts_states(locked_hosts, timeout=HostTimeout.REBOOT, check_interval=10, duration=8,
                                           fail_ok=False, availability=['online'])
        host_helper._wait_for_hosts_states(unlocked_hosts, timeout=HostTimeout.REBOOT, check_interval=10,
                                           fail_ok=False, availability=['available', 'degraded'])

