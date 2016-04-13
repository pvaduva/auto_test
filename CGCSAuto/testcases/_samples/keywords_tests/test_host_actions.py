from pytest import fixture, mark, skip, raises

import keywords.system_helper
from utils import exceptions
from utils.tis_log import LOG
from keywords import host_helper, system_helper

_skip = False


@mark.skipif(_skip, reason='test skip if')
# @mark.usefixtures('check_alarms')
@mark.parametrize(('hostname', 'timeout', 'fail_ok'), [
    ('controller-0', 30, False),
    ('controller-0', 30, False),
    ('controller-1', 30, False),
    (None, 1, True),
    (None, 30, True),
    (None, 1, False),
    (None, 30, False),
])
def test_swact_host(hostname, timeout, fail_ok):
    LOG.tc_step("wait for previous swact complete")
    host_helper._wait_for_openstack_cli_enable()
    host_helper._wait_for_host_states('controller-0', timeout=60, fail_ok=False, task='')
    host_helper._wait_for_host_states('controller-1', timeout=60, fail_ok=False, task='')

    LOG.tc_step("swact host")

    if fail_ok:
        code, msg = host_helper.swact_host(hostname=hostname, swact_start_timeout=timeout, fail_ok=fail_ok)
        if timeout == 1:
            assert code == 3
            host_helper._wait_for_swact_complete(hostname, fail_ok=False)
        else:
            assert code in [-1, 0, 1, 2]

    else:
        if timeout == 1:
            with raises(exceptions.HostPostCheckFailed):
                host_helper.swact_host(hostname=hostname, swact_start_timeout=1, fail_ok=fail_ok)
            host_helper._wait_for_swact_complete(hostname, fail_ok=False)
        else:
            host_helper.swact_host(hostname=hostname, swact_start_timeout=timeout, fail_ok=fail_ok)


@mark.parametrize(('hostname', 'force'), [
    ('storage-1', False),
    ('compute-0', False),
    ('controller-0', False),
    ('controller-1', False),
    # ('controller-1', True),
    # ('controller-0', True),
    # ('compute-0', True)
])
def test_lock_host(hostname, force):
    if not keywords.system_helper.host_exists(hostname):
        skip("{} does not exist".format(hostname))

    expts = [-1, 0]
    if hostname == system_helper.get_active_controller_name():
        expts = [1]

    rtn_code, msg = host_helper.lock_host(hostname, fail_ok=True, force=force)

    assert rtn_code in expts


@mark.parametrize('hostname', [
    'storage-1',
    'compute-0',
    'controller-0',
    'controller-1',
])
def test_unlock_host(hostname):
    if not keywords.system_helper.host_exists(hostname):
        skip("{} does not exist".format(hostname))

    host_helper.unlock_host(hostname)

@mark.usefixtures('check_alarms')
@mark.parametrize('hostnames', [
    ['compute-0'],
    'standby_controller',
    ['storage-0', 'standby_controller', 'compute-0'],
    ['active_controller', 'compute-1'],
    'active_controller',
    ['controller-0', 'controller-1']
])
def test_reboot_hosts(hostnames):
    LOG.tc_step("Processing hostnames provided...")
    system_hosts = system_helper.get_hostnames()

    is_str = False
    if isinstance(hostnames, str):
        is_str = True
        hostnames = [hostnames]

    tmp_hosts = hostnames
    for host in tmp_hosts:
        if host == 'active_controller':
            hostnames.remove(host)
            host = system_helper.get_active_controller_name()
            hostnames.append(host)
        elif host == 'standby_controller':
            hostnames.remove(host)
            host = system_helper.get_standby_controller_name()
            hostnames.append(host)
        if host not in system_hosts:
            skip("Host(s) not found in system. Host(s) requested: {}."
                 "Hosts in system: {}".format(hostnames, system_hosts))

    if is_str:
        hostnames = hostnames[0]

    LOG.tc_step("Rebooting following host(s): {}".format(hostnames))
    results = host_helper.reboot_hosts(hostnames)
    LOG.tc_step("Results: {}".format(results))
    assert results[0] == 0


def test_get_active_con():
    active = system_helper.get_active_controller_name()
    standby = system_helper.get_standby_controller_name()

    LOG.tc_step("Active: {}; Standby: {}".format(active, standby))
    assert 'controller-' in active
