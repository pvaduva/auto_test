from pytest import fixture, mark, skip, raises

import keywords.system_helper
from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from keywords import host_helper, system_helper

_skip = False

@fixture(scope='function')
def check_hosts_availability(request):
    print("wait for previous swact complete")
    #con_ssh = ControllerClient.get_active_controller()
    #if not con_ssh.get_hostname() == 'controller-0':
    #    host_helper.swact_host()

    host_helper._wait_for_openstack_cli_enable()
    host_helper._wait_for_host_states('controller-0', timeout=900, fail_ok=False, task='')
    host_helper._wait_for_host_states('controller-1', timeout=900, fail_ok=False, task='')

    # Restore the host states
    def restore_hosts_availability():
        print("Waiting for swact to complete...")
        host_helper._wait_for_openstack_cli_enable()
        host_helper._wait_for_host_states('controller-0', timeout=900, fail_ok=False, task='')
        host_helper._wait_for_host_states('controller-1', timeout=900, fail_ok=False, task='')

    request.addfinalizer(restore_hosts_availability)

@mark.cpe_sanity
@mark.usefixtures('check_hosts_availability')
@mark.parametrize(('hostname', 'timeout', 'fail_ok'), [
    ('controller-0', 30, False),
    ('controller-1', 30, False),
])
def test_tc4702_swact_host(hostname, timeout, fail_ok):
    LOG.tc_step("swact host")

    con_ssh = ControllerClient.get_active_controller()
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
            host_helper.swact_host(hostname=hostname, swact_start_timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh)

