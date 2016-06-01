import time
import random

from pytest import mark
from pytest import skip
from pytest import fixture

from utils.tis_log import LOG
from keywords import system_helper, host_helper


def _get_computes_for_local_backing_type(type='image', con_ssh=None):
    hosts_of_type = []
    hosts = host_helper.get_hypervisors(state='up', status='enabled', con_ssh=con_ssh)
    for host in hosts:
        if host_helper.check_host_local_backing_type(host, type=type, con_ssh=con_ssh):
            hosts_of_type.append(host)

    return hosts_of_type


def _is_host_locked(host, con_ssh=None):
    return 'locked' == host_helper.get_hostshow_value(host, 'administrative', con_ssh=con_ssh)


def _is_host_unlocked(host, con_ssh=None):
    return 'unlocked' == host_helper.get_hostshow_value(host, 'administrative', con_ssh=con_ssh)


def _less_than_2_hypervisors():
    return len(host_helper.get_hypervisors()) < 2


class TestLocalStorage(object):
    """

    """
    _computes_locked = []
    _profiles = []

    @fixture(scope='class', autouse=True)
    def cleanup_local_storage(self, request):
        #self._computes_locked = []
        #self._profiles = []

        def cleanup():
            try:
                while self._profiles:
                    system_helper.delete_stroage_profile(self._profiles.pop())

                while self._computes_locked:
                    host_helper.unlock_host(self._computes_locked.pop())
            finally:
                while self._computes_locked:
                    host_helper.unlock_host(self._computes_locked.pop())
        request.addfinalizer(cleanup)


    @mark.skipif(_less_than_2_hypervisors(), reason='Require 2 or more hyperviors to run the testcase')
    @mark.parametrize(
        'local_storage_type',
        ['image', 'lvm'])
    def test_local_image_operations(self, local_storage_type):
        """
        Args:

        Test Steps:

        Teardown:

        Notes:
                will cover 2 test cases:
                    34.  Local Storage Create/Apply/Delete – Local Image
                    35.  Local Storage Profile Create/Apply/Delete – Local LVM
        """
        LOG.tc_step('Create storage-profile from one compute with the expected backing:{}'.format(local_storage_type))

        computes = _get_computes_for_local_backing_type(type=local_storage_type)
        if len(computes) < 1:
            # skip the test because no compute with the expected local storage backing type existing
            msg = 'SKIP: no hypervisor with local storage type:{}'.format(local_storage_type)
            LOG.tc_step(msg)
            skip(msg)
            return

        active_controller = system_helper.get_active_controller_name()
        # select the compute from which a storage-profile to be created for
        if active_controller in computes:
            # must be a CPE lab, in which controllers are also computes
            # chose the active controller
            compute_src = active_controller
        else:
            compute_src = random.choice(computes)

        LOG.tc_step('Create storage profile for host:{}'.format(compute_src))
        prof_name = 'storprof_{}'.format(time.strftime('%Y%m%d_%H%M%S', time.localtime()))
        prof_uuid = system_helper.create_storage_profile(compute_src, profile_name=prof_name)

        self._profiles.append(prof_uuid)

        LOG.tc_step('Attempt to apply the storage profile on an unlocked compute, expecting to fail')
        computes_unlocked = [c for c in host_helper.get_hypervisors(state='up', status='enabled') if c != compute_src]
        if len(computes_unlocked) < 1:
            # skip the test because no OTHER enabled compute
            msg = 'SKIP: no OTHER compute enabled to test'
            LOG.tc_step(msg)
            skip(msg)
            return
        compute_unlocked = random.choice(computes_unlocked)

        LOG.tc_step('Attempting to apply the storage profile {} on an unlocked compute {}'
                    .format(prof_name, compute_unlocked))
        rtn_code, output = system_helper.apply_storage_profile(compute_unlocked, profile=prof_uuid, fail_ok=True)
        assert 1 == rtn_code, 'Expected failure in applying storage profile on unlocked host:{}, but succeeded'\
            .format(compute_unlocked)

        LOG.tc_step('Lock the compute:{} in order to applly storage-profile:{}'.format(compute_unlocked, prof_name))
        compute_dest = compute_unlocked
        rtn_code, msg = host_helper.lock_host(compute_dest, check_first=True)
        assert 0 == rtn_code, 'Failed to lock host:{}, msg:{}'.format(compute_dest, msg)
        self._computes_locked.append(compute_dest)

        LOG.tc_step('Applying the storage profile on the host')
        rtn_code, output = system_helper.apply_storage_profile(compute_dest, prof_uuid, fail_ok=True)
        assert 0 == rtn_code, 'Failed to apply storage-profile:{} to host:{}'.format(prof_name, compute_dest)

        LOG.tc_step('Unlock the host and check the type of local image backing on it')
        host_helper.unlock_host(compute_dest)
        self._computes_locked.remove(compute_dest)

        LOG.tc_step('Check the type of storage on compute:{}'.format(compute_dest))
        actual_storage_types = host_helper.get_local_storage_backing(compute_dest)

        assert local_storage_type in actual_storage_types, \
            'Local storage type on {} is not set to {} as expected'.format(compute_dest, local_storage_type)



