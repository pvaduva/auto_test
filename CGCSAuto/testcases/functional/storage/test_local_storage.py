import time
import random

from pytest import mark
from pytest import skip
from pytest import fixture

from utils.tis_log import LOG
from keywords import system_helper, host_helper
from utils import cli
from utils.ssh import ControllerClient


def _get_computes_for_local_backing_type(lc_type='image', con_ssh=None):
    hosts_of_type = []
    hosts = host_helper.get_hypervisors(state='up', status='enabled', con_ssh=con_ssh)

    for host in hosts:
        if host_helper.check_host_local_backing_type(host, type=lc_type, con_ssh=con_ssh):
            hosts_of_type.append(host)

    return hosts_of_type


def _less_than_2_hypervisors():
    return len(host_helper.get_hypervisors()) < 2


class TestLocalStorage(object):
    """

    """
    types_local_storage_backing = ('image', 'lvm', 'remote')

    _profiles_created = []
    _computes_locked = []

    @fixture(scope='class', autouse=True)
    def cleanup_local_storage(self, request):
        def cleanup():
            profiles_created = TestLocalStorage._profiles_created
            computes_locked = TestLocalStorage._computes_locked
            try:
                while profiles_created:
                    system_helper.delete_stroage_profile(profile=profiles_created.pop())

                while computes_locked:
                    host_helper.unlock_host(computes_locked.pop())
            finally:
                while computes_locked:
                    host_helper.unlock_host(computes_locked.pop())

        request.addfinalizer(cleanup)

    def apply_storage_profile(self, host, lc_type='image', profile=None, con_ssh=None, fail_ok=False):
        if host_helper.check_host_local_backing_type(host, lc_type, con_ssh=con_ssh):
            msg = 'host already has local-storage backing:{} as expected'.format(lc_type)
            LOG.info(msg)
            return 1, msg

        if host == ControllerClient.get_active_controller():
            # this will happen on a CPE lab
            LOG.info('will swact the current active controller:{}'.format(host))
            host_helper.swact_host()

        LOG.tc_step('Lock the host:{} for applying storage-profile'.format(host))
        rtn_code, msg = host_helper.lock_host(host, con_ssh=con_ssh, fail_ok=False, check_first=True)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.append(host)

        LOG.tc_step('Delete the PV of type:{} on host:{}'.format(lc_type, host))
        pv_uuids = host_helper.get_host_pv_uuid(host, lvg_type='nova-local', con_ssh=con_ssh)
        if len(pv_uuids) <= 0:
            LOG.warn('No pv for lvg type:{} on host:{}'.format(lc_type, host))
        else:
            # THERE IS A Known issue: the following CLI return non-zero, hence skip checking the return code
            # rtn_code, output = cli.system('host-pv-delete {}'.format(pv_uuids[0]),
            _, _ = cli.system('host-pv-delete {}'.format(pv_uuids[0]),
                              ssh_client=con_ssh, fail_ok=True, rtn_list=True)
            # assert 0 == rtn_code

        LOG.tc_step('Delete the lvg "nova-local" on host:{}'.format(host))
        cli.system('host-lvg-delete {} nova-local'.format(host),
                   ssh_client=con_ssh, fail_ok=False, rtn_list=True)

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(profile, host))
        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(host, profile),
                                      fail_ok=fail_ok, rtn_list=True)
        # currently there's a known issue that the CLI host-apply-stoprof returns 1 even it succeeded
        # assert 0 == rtn_code, 'Failed to apply storage-profile:{} to host:{}'.format(prof_name, compute_dest)
        return rtn_code, output

    def create_storage_profile(self, host, lc_type='image'):
        prof_name = 'storprof_{}{}_{}_{}'.format(host[0], host[-1],
                                                 lc_type, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
        prof_uuid = system_helper.create_storage_profile(host, profile_name=prof_name)

        TestLocalStorage._profiles_created.append(prof_uuid)

        return prof_uuid

    def set_local_storage_backing(self, compute, new_type='image'):
        LOG.info('will lock compute:{} in order to change to new lc-type:{}'\
                 .format(compute, new_type))
        rtn_code, msg = host_helper.lock_host(compute, check_first=True)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.append(compute)
        cmd = 'system host-lvg-modify -b {} {} nova-local'.format(new_type, compute)
        _, _ = cli.system(cmd, rtn_list=True, fail_ok=False)

        LOG.info('OK, the lc-type of {} changed to {}'.format(compute, new_type))

        LOG.info('Unlock {} now'.format(compute))

        host_helper.unlock_host(compute)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.remove(compute)

    def setup_local_storage_type_on_lab(self, lc_type='image'):
        LOG.info('Chose one compute to change its lc-backing to expected type: {}'.format(lc_type))

        computes_locked = host_helper.get_hypervisors(state='down', status='disabled')
        if computes_locked:
            compute_to_change = random.choice(computes_locked)
        else:
            #if possible, avoid to pick up the active controller, which only may happen on CPE system
            computes_unlocked = host_helper.get_hypervisors(state='up', status='enabled')
            compute_to_change = random.choice([c for c in computes_unlocked
                                               if c != ControllerClient.get_active_controller()])
        self.set_local_storage_backing(compute_to_change, new_type=lc_type)

        return compute_to_change


    def select_target_compute(self, compute_src='', lc_type='image'):
        compute_dest = ''

        # firstly chose one compute from locked and of different lc-type to apply storage-profile
        computes_locked_diff_type = [c for c in
                           host_helper.get_hypervisors(state='down', status='disabled')
                           if not host_helper.check_host_local_backing_type(c, type=lc_type)]
        if computes_locked_diff_type:
            compute_dest = random.choice(computes_locked_diff_type)
            LOG.info('will apply the storage-profile to locked compute:{}, locked, diff lc-type'.format(compute_dest))
            return compute_dest

        # otherwise chose one compute from unlocked and of different lc-type to apply storage-profile
        computes_unlocked_diff_type = [c for c in
                       host_helper.get_hypervisors(state='up', status='enabled')
                       if not host_helper.check_host_local_backing_type(c, type=lc_type)]
        old_active_controller = ControllerClient.get_active_controller()
        # if computes_unlocked_diff_type:
        if old_active_controller in computes_unlocked_diff_type:
            computes_unlocked_diff_type.remove(old_active_controller)
        if not computes_unlocked_diff_type:
            compute_dest = old_active_controller
            LOG.info('will apply the storage-profile to locked compute:{}, old active-controller, diff-lc'\
                     .format(compute_dest))
            return old_active_controller

        if computes_unlocked_diff_type:
            compute_dest = random.choice(computes_unlocked_diff_type)
            LOG.info('will apply the storage-profile to unlocked compute:{}, unlocked, diff-lc'.format(compute_dest))
            host_helper.lock_host(compute_dest)
            TestLocalStorage._computes_locked.append(compute_dest)
            return compute_dest

        # still can't find a candidate, choose one with the same lc-type
        computes_locked = [c for c in
                           host_helper.get_hypervisors(state='down', status='disabled')
                           if host_helper.check_host_local_backing_type(c, type=lc_type)]
        if computes_locked:
            compute_dest = random.choice(computes_locked)
            LOG.info('will apply the storage-profile to locked compute:{}, locked, same lc-type'\
                     .format(compute_dest))
            return compute_dest

        computes_unlocked = [c for c in
                        host_helper.get_hypervisors(state='up', status='enabled')
                        if host_helper.check_host_local_backing_type(c, type=lc_type)]
        computes_unlocked.remove(old_active_controller)
        if not computes_unlocked:
            compute_dest = old_active_controller
            LOG.info('will apply the storage-profile to locked compute:{}, old active-controller, same lc-type'\
                     .format(compute_dest))
            return old_active_controller

        compute_dest = random.choice(computes_unlocked)
        LOG.info('will apply the storage-profile to unlocked compute:{}, unlocked, same lc-type'.format(compute_dest))
        return compute_dest

    def create_storage_profile_of_type(self, lc_type='image'):
        LOG.info('create a local-storage profile of backing type:{}'.format(lc_type))
        computes_of_lc_type = [h for h in host_helper.get_hypervisors()
                               if host_helper.check_host_local_backing_type(h, lc_type)]

        if not computes_of_lc_type:
            # no computes have expected type of lc-type, modify one of them to the type
            compute_src = self.setup_local_storage_type_on_lab(lc_type=lc_type)
        else:
            active_controller = ControllerClient.get_active_controller()
            if active_controller in  computes_of_lc_type:
                compute_src = active_controller
            else:
                compute_src = random.choice(computes_of_lc_type)
        prof_uuid = self.create_storage_profile(compute_src, lc_type=lc_type)

        return prof_uuid, compute_src

    @mark.skipif(_less_than_2_hypervisors(), reason='Require 2 or more hyperviors to run the testcase')
    @mark.parametrize(
        'local_storage_type',
        ['image', 'lvm'])
    def test_local_storage_operations(self, local_storage_type):
        """
        Args:
            local_storage_type(str): type of local-storage backing, should be image, lvm, remote

        Setup:

        Test Steps:
            1 Create a storage-profile with expected local-storage type
                1) if there are computes/hyperviors with the local-storage type, randomly choose one
                2) otherwise, chose a non-active-controller, change its local-storage backing type to the expected type
            2 Test a negative case: attempt to apply the storage-profile on an unlocked compute/hypervisor
            3 Select one compute/hypervisor to aplly the storage-profile
                1) if there is/are locked compute/computes with different storage-type, then randomly chose one
                2) otherwise randomly select one unlocked with different storage-type
                    (including the current active controller in case of CPE)
                3) otherwise, randomly select one from locked computes
                4) lastly, randomly choose one from the unlocked computes
                (including the current active controller in case of CPE)
            4 Apply the storage-profile onto the selected target compute
                1) if the target compute/hypervisor is also the current active controller, do swact-host
                2) lock the target compute if it's unlocked
                3) delete it's PV attached to the LVG named 'nova-local'
                4) delete it's LVG named 'nova-local'
                5 apply the storage-profile onto the target compute with CLI 'system host-apply-storpofile'

        Teardown:
            1 delete the storage-profile created
            2 unlock the computes/hyperviors locked for testing

        Notes:
                will cover 3 test cases:
                    34.  Local Storage Create/Apply/Delete – Local Image
                    35.  Local Storage Profile Create/Apply/Delete – Local LVM
                    36.  Local Storage Profile Apply (Local Image ↔ Local LVM)
        """
        LOG.tc_step('Create a storage-profile with the expected type of local-storage backing:{}'\
                    .format(local_storage_type))
        prof_uuid, compute_src = self.create_storage_profile_of_type(lc_type=local_storage_type)
        assert prof_uuid, 'Faild to create storage-profile for local-storage-type:{}'\
            .format_map(local_storage_type)
        LOG.info('OK, created {} lc-type from compute:{}'.format(local_storage_type, compute_src))

        LOG.tc_step('NEG: Attempt to apply the storage profile on an unlocked compute, expecting to fail')
        # assuming there's at least one compute up/enabled, which is OK in most cases
        computes_unlocked = host_helper.get_hypervisors(state='up', status='enabled')
        if computes_unlocked:
            compute_unlocked = random.choice(host_helper.get_hypervisors(state='up', status='enabled'))
            rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_unlocked, prof_uuid),
                                      fail_ok=True, rtn_list=True)
            assert 0 != rtn_code, 'Should fail to apply storage-profile:{} to unlocked host:{}' \
                .format(prof_uuid, compute_unlocked)

        LOG.tc_step('Choose another compute to apply the storage-profile'.format(compute_src))
        compute_to_modify = self.select_target_compute(compute_src)
        LOG.info('target compute:{}'.format(compute_to_modify))

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(prof_uuid, compute_to_modify))
        # THERE IS A KNOWN issue currently (20160602), CLI will return non-zero when applying storage-profile
        # so we don not check ther return code

        self.apply_storage_profile(
            compute_to_modify,
            lc_type=local_storage_type, profile=prof_uuid, fail_ok=True)
        # assert 0 == rtn_code, ...

        LOG.tc_step('Check if the changes take effect after unlocking')
        rtn_code = host_helper.unlock_host(compute_to_modify)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.remove(compute_to_modify)

        LOG.tc_step('-Verify the lc type changed to {} on host:{}'
                    .format(local_storage_type, compute_to_modify))
        assert host_helper.check_host_local_backing_type(compute_to_modify, type=local_storage_type), \
            'Local-storage backing failed to change to {} from {}'.format(local_storage_type)

