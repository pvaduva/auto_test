import time
import random

from pytest import mark

from utils.tis_log import LOG
from keywords import system_helper, host_helper


def _get_hosts_for_local_backing_type(type='image', con_ssh=None):
    hosts_of_type = []
    hosts = host_helper.get_hypervisors(state='up', status='enabled', con_ssh=con_ssh)
    for host in hosts:
        if system_helper.check_host_local_backing_type(host, type=type, con_ssh=con_ssh):
            hosts_of_type.append(host)

    return hosts_of_type


def _is_host_locked(host, con_ssh=None):
    return 'locked' == host_helper.get_hostshow_value(host, 'administrative', con_ssh=con_ssh)


def _is_host_unlocked(host, con_ssh=None):
    return 'unlocked' == host_helper.get_hostshow_value(host, 'administrative', con_ssh=con_ssh)


def _pick_one_unlocked_host(hosts):
    unlocked = (h for h in hosts if _is_host_unlocked(h))
    return random.choice(unlocked)


@mark.skipif(not system_helper.has_local_image_backing(), reason='Lab is not configured with local image backing')
def test_local_image_operations():
    """
    Args:

    Test Steps:

    Teardown:

    """
    LOG.tc_step('Randomly pick one of the hypervisors with local image backing to test with')

    # the skip condition guarantees there's at least one host with local image backend
    hosts_image_backing = _get_hosts_for_local_backing_type(type='image')
    host_under_test = random.choice(hosts_image_backing)

    LOG.tc_step('Create storage profile for host:{}'.format(host_under_test))
    prof_name = 'strprf_{}_{}'.format(host_under_test, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
    prof_uuid = system_helper.create_storage_profile(host_under_test, profile_name=prof_name)

    LOG.tc_step('Attempt to apply the storage profile on an unlocked host, expecting to fail')
    unlocked_host = _pick_one_unlocked_host(hosts_image_backing)
    rtn_code, output = system_helper.apply_storage_profile(unlocked_host, profile=prof_uuid, fail_ok=True)
    assert 1 == rtn_code, 'Expected failure in applying storage profile on unlocked host:{}, but succeeded'\
        .format(unlocked_host)

    LOG.tc_step('Lock the host:{}'.format(unlocked_host))
    rtn_code = host_helper.lock_host(unlocked_host, check_first=True)
    assert 0 == rtn_code, 'Failed to lock host:{}'.format(unlocked_host)

    locked_host = unlocked_host
    LOG.tc_step('Applying the storage profile on the host')
    rtn_code, output = system_helper.apply_storage_profile(locked_host, prof_uuid, fail_ok=True)
    assert 0 == rtn_code, 'Failed to apply storage-profile:{} to host:{}'.format(prof_uuid, locked_host)

