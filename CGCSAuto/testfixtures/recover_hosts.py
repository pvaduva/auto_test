from pytest import fixture

from utils import table_parser, cli, exceptions
from consts.timeout import HostTimeout
from keywords import host_helper


@fixture(scope='function', autouse=True)
def hosts_recover_func(request):
    def recover_():
        hosts = HostsToRecover._get_hosts_to_recover(scope='function')
        if hosts:
            HostsToRecover._reset('function')
            HostsToRecover._recover_hosts(hosts)
    request.addfinalizer(recover_)


@fixture(scope='class', autouse=True)
def hosts_recover_class(request):
    def recover_hosts():
        hosts = HostsToRecover._get_hosts_to_recover(scope='class')
        if hosts:
            HostsToRecover._reset('class')
            HostsToRecover._recover_hosts(hosts)
    request.addfinalizer(recover_hosts)


@fixture(scope='module', autouse=True)
def hosts_recover_module(request):
    def recover_hosts():
        hosts = HostsToRecover._get_hosts_to_recover(scope='module')
        if hosts:
            HostsToRecover._reset('module')
            HostsToRecover._recover_hosts(hosts)
    request.addfinalizer(recover_hosts)


class HostsToRecover():
    __hosts_to_recover = {
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
        valid_scope = cls.__hosts_to_recover.keys()
        if scope not in valid_scope:
            raise ValueError("scope has to be one of the following: {}".format(valid_scope))

        if isinstance(hostnames, str):
            hostnames = [hostnames]

        cls.__hosts_to_recover[scope] += hostnames

    @classmethod
    def _reset(cls, scope):
        cls.__hosts_to_recover[scope] = []

    @classmethod
    def _get_hosts_to_recover(cls, scope):
        return cls.__hosts_to_recover[scope]

    @staticmethod
    def _recover_hosts(hostnames):
        hostnames = sorted(hostnames)
        table_ = table_parser.table(cli.system('host-list'))
        table_ = table_parser.filter_table(table_, hostname=hostnames)

        unlocked_hosts = table_parser.get_values(table_, 'hostname', administrative='unlocked')
        locked_hosts = table_parser.get_values(table_, 'hostname', administrative='locked')

        err_msg = []
        if locked_hosts:
            res1 = host_helper.unlock_hosts(hosts=locked_hosts, fail_ok=True)
            for host in res1:
                if res1[host][0] not in [0, 4]:
                    err_msg.append("Not all host(s) unlocked successfully. Detail: {}".format(res1))

        if unlocked_hosts:
            res2 = host_helper._wait_for_hosts_states(unlocked_hosts, timeout=HostTimeout.REBOOT, check_interval=10,
                                                      fail_ok=True, availability=['available', 'degraded'])
            if not res2:
                err_msg.append("Some host(s) from {} are not available.".format(unlocked_hosts))

        assert not err_msg, '\n'.join(err_msg)
