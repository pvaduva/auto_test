from pytest import fixture

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from consts.timeout import HostTimeout
from keywords import host_helper


@fixture(scope='function', autouse=True)
def hosts_recover_func(request):
    def recover_():
        hosts = HostsToRecover._get_hosts_to_recover(scope='function')
        if hosts:
            HostsToRecover._reset('function')
            HostsToRecover._recover_hosts(hosts, 'function')
    request.addfinalizer(recover_)


@fixture(scope='class', autouse=True)
def hosts_recover_class(request):
    def recover_hosts():
        hosts = HostsToRecover._get_hosts_to_recover(scope='class')
        if hosts:
            HostsToRecover._reset('class')
            HostsToRecover._recover_hosts(hosts, 'class')
    request.addfinalizer(recover_hosts)


@fixture(scope='module', autouse=True)
def hosts_recover_module(request):
    def recover_hosts():
        hosts = HostsToRecover._get_hosts_to_recover(scope='module')
        if hosts:
            HostsToRecover._reset('module')
            HostsToRecover._recover_hosts(hosts, 'module')
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
    def _recover_hosts(hostnames, scope):
        hostnames = sorted(set(hostnames))
        table_ = table_parser.table(cli.system('host-list'))
        table_ = table_parser.filter_table(table_, hostname=hostnames)

        unlocked_hosts = table_parser.get_values(table_, 'hostname', administrative='unlocked')
        locked_hosts = table_parser.get_values(table_, 'hostname', administrative='locked')

        err_msg = []
        if locked_hosts:
            LOG.fixture_step("({}) Unlock hosts: {}".format(scope, locked_hosts))
            res1 = host_helper.unlock_hosts(hosts=locked_hosts, fail_ok=True)
            for host in res1:
                if res1[host][0] not in [0, 4]:
                    err_msg.append("Not all host(s) unlocked successfully. Detail: {}".format(res1))

        if unlocked_hosts:
            LOG.fixture_step("({}) Wait for hosts to becomes available or degraded: {}".format(scope, unlocked_hosts))
            res2 = host_helper._wait_for_hosts_states(unlocked_hosts, timeout=HostTimeout.REBOOT, check_interval=10,
                                                      fail_ok=True, availability=['available', 'degraded'])
            if not res2:
                err_msg.append("Some host(s) from {} are not available.".format(unlocked_hosts))

        hypervisors = host_helper.get_hypervisors()
        hypervisors_recovered = list(set(hypervisors) & set(hostnames))
        if hypervisors_recovered:
            LOG.fixture_step("({}) Wait for unlocked hypervisors up: {}".format(scope, hypervisors_recovered))
            res, down_hosts = host_helper.wait_for_hypervisors_up(hypervisors_recovered, fail_ok=True)
            if not res:
                err_msg.append("Host(s) {} are not up in hypervisor-list".format(down_hosts))

        assert not err_msg, '\n'.join(err_msg)