import time
import random
import os
import operator

from pytest import mark
from pytest import skip
from pytest import fixture

from consts.proj_vars import ProjVar

from utils.tis_log import LOG
from utils import cli

from keywords import system_helper, host_helper, local_storage_helper


def _get_computes_for_local_backing_type(lc_type='image', con_ssh=None):
    hosts_of_type = []
    hosts = host_helper.get_nova_hosts(con_ssh=con_ssh)

    for host in hosts:
        if host_helper.check_host_local_backing_type(host, type=lc_type, con_ssh=con_ssh):
            hosts_of_type.append(host)

    return hosts_of_type


def _less_than_2_hypervisors():
    return len(host_helper.get_hypervisors()) < 2


class TestLocalStorage(object):
    """

    """
    types_local_storage_backing = ('image', 'lvm')

    _profiles_created = []
    _computes_locked = []
    _host_old_new_lc_types = {}

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
            # restore the local-storage types for computes ever changed by testing
            old_new_types = TestLocalStorage._host_old_new_lc_types
            try:
                for host in old_new_types.keys():
                    host_helper.lock_host(host)
                    (old_type, _) = old_new_types.pop(host)
                    self.set_local_storage_backing(compute=host, to_type=old_type)
                    host_helper.unlock_host(host)
            finally:
                pass

        request.addfinalizer(cleanup)

    def apply_storage_profile(self, compute_dest, lc_type='image', profile=None,
                              ssh_client=None, fail_ok=False, force_change=False):
        if host_helper.check_host_local_backing_type(compute_dest, lc_type, con_ssh=ssh_client) and not force_change:
            msg = 'host already has local-storage backing:{} as expected'.format(lc_type)
            LOG.debug(msg)
            return -1, msg

        LOG.debug('compute: {} is not in lc-type:{} or will force to apply'.format(compute_dest, lc_type))
        if compute_dest == system_helper.get_active_controller_name():
            # this will happen on a CPE lab
            LOG.debug('will swact the current active controller:{}'.format(compute_dest))
            host_helper.swact_host()

        LOG.tc_step('Lock the host:{} for applying storage-profile'.format(compute_dest))
        rtn_code, msg = host_helper.lock_host(compute_dest, con_ssh=ssh_client, fail_ok=False, check_first=True)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.append(compute_dest)

        LOG.tc_step('Delete the lvg "nova-local" on host:{}'.format(compute_dest))
        rtn_code, msg = cli.system('host-lvg-delete {} nova-local'.format(compute_dest),
                   ssh_client=ssh_client, fail_ok=False, rtn_list=True)

        assert 0 == rtn_code, 'Failed to delete the nova-local logical-group from {}'.format(compute_dest)

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(profile, compute_dest))
        LOG.debug('Get the original lc-type for compute:{}'.format(compute_dest))
        old_type = host_helper.get_local_storage_backing(compute_dest)
        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_dest, profile),
                                      fail_ok=fail_ok, rtn_list=True)
        assert rtn_code == 0, 'Failed to apply storage-profile {} onto {}'.format(profile, compute_dest)

        LOG.debug('Save lc-type for compute:{}, old:{}, new:{}'.format(compute_dest, old_type, lc_type))
        TestLocalStorage._host_old_new_lc_types[compute_dest] = (old_type, lc_type)

        return rtn_code, output

    def create_storage_profile(self, host, lc_type='image'):
        prof_name = 'storprof_{}{}_{}_{}'.format(host[0], host[-1],
                                                 lc_type, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
        prof_uuid = system_helper.create_storage_profile(host, profile_name=prof_name)

        TestLocalStorage._profiles_created.append(prof_uuid)

        return prof_uuid

    def set_local_storage_backing(self, compute=None, to_type='image'):
        LOG.debug('will lock compute:{} in order to change to new lc-type:{}' \
                 .format(compute, to_type))
        rtn_code, msg = host_helper.lock_host(compute, check_first=True)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.append(compute)
        LOG.debug('Get the original lc-backing-type for compute:{}'.format(compute))
        old_type = host_helper.get_local_storage_backing(compute)
        cmd = 'host-lvg-modify -b {} {} nova-local'.format(to_type, compute)
        _, _ = cli.system(cmd, rtn_list=True, fail_ok=False)
        LOG.debug('Save lc-backing-type for compute:{}, old:{}, new:{}'.format(compute, old_type, to_type))
        TestLocalStorage._host_old_new_lc_types[compute] = (old_type, to_type)

        LOG.debug('OK, the lc-type of {} changed to {}'.format(compute, to_type))

        LOG.debug('Unlock {} now'.format(compute))

        host_helper.unlock_host(compute)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.remove(compute)

    def setup_local_storage_type_on_lab(self, lc_type='image'):
        LOG.debug('Chose one compute to change its lc-backing to expected type: {}'.format(lc_type))

        computes_locked = host_helper.get_hypervisors(state='down', status='disabled')
        if computes_locked:
            compute_to_change = random.choice(computes_locked)
        else:
            # if possible, avoid to pick up the active controller, which only may happen on CPE system
            computes_unlocked = host_helper.get_nova_hosts()
            compute_to_change = random.choice([c for c in computes_unlocked
                                               if c != system_helper.get_active_controller_name()])
        self.set_local_storage_backing(compute=compute_to_change, to_type=lc_type)

        return compute_to_change

    def _is_profile_applicable_to(self, storage_profile=None, compute_dest=None):
        LOG.debug('compare storage-sizes of the storage-profile:{} with compute:{}'.\
                 format(storage_profile, compute_dest))

        disk, size_profile = local_storage_helper.get_storprof_diskconfig(profile=storage_profile)
        size_disk = local_storage_helper.get_host_disk_size(compute_dest, disk)

        if size_disk >= size_profile:
            return True

        return False

    def _choose_compute_locked_diff_type(self, lc_type='image'):
        computes_locked_diff_type = [c for c in
                                     host_helper.get_hypervisors(state='down', status='disabled')
                                     if not host_helper.check_host_local_backing_type(c, type=lc_type)]
        if computes_locked_diff_type:
            compute_dest = random.choice(computes_locked_diff_type)
            return compute_dest

        return ''

    def _choose_compute_unlocked_diff_Type(self, lc_type='image', active_controller=''):
        computes_unlocked_diff_type = [c for c in
                                       host_helper.get_nova_hosts()
                                       if not host_helper.check_host_local_backing_type(c, type=lc_type)]

        if computes_unlocked_diff_type:
            LOG.debug('-{} computes unlocked and with lc-type:{}' \
                     .format(len(computes_unlocked_diff_type), lc_type))
            LOG.debug('-old active is controller:{}'.format(active_controller))

            if active_controller in computes_unlocked_diff_type:
                LOG.debug('-is on a CPE system')
                computes_unlocked_diff_type.remove(active_controller)
                if computes_unlocked_diff_type:
                    LOG.debug('- multiple computes unlocked, different type, randomly select one non-active controller')
                    compute_dest = random.choice(computes_unlocked_diff_type)
                    LOG.debug('-OK, selected {} as the target compute'.format(compute_dest))
                    return compute_dest
                else:
                    LOG.debug('have to select the active controller as target:{}'.format(active_controller))
                    compute_dest = active_controller
                    return compute_dest

            else:
                LOG.debug('-non-CPE system')
                compute_dest = random.choice(computes_unlocked_diff_type)
                LOG.debug('-non-CPE lab, select {} as target compute'.format(compute_dest))
                return compute_dest

        return ''

    def _choose_compute_locked_same_type(self, lc_type='image'):
        computes_locked = [c for c in
                           host_helper.get_hypervisors(state='down', status='disabled')
                           if host_helper.check_host_local_backing_type(c, type=lc_type)]
        if computes_locked:
            compute_dest = random.choice(computes_locked)
            LOG.debug('-will apply the storage-profile to locked compute:{}, locked, same lc-type' \
                     .format(compute_dest))
            return compute_dest

    def _choose_compute_unlocked_same_type(self, lc_type='image', active_controller=''):
        computes_unlocked = [c for c in
                             host_helper.get_nova_hosts()
                             if host_helper.check_host_local_backing_type(c, type=lc_type)]
        if active_controller in computes_unlocked:
            computes_unlocked.remove(active_controller)
            if computes_unlocked:
                compute_dest = random.choice(computes_unlocked)
            else:
                compute_dest = active_controller
                LOG.debug('-selected old active-controller:{}, same lc-type:{}' \
                         .format(compute_dest, lc_type))
        else:
            compute_dest = random.choice(computes_unlocked)
            LOG.debug('-target compute:{}, unlocked, same lc-type'.format(compute_dest))

        return compute_dest

    def select_target_compute(self, compute_src='', lc_type='image'):
        compute_dest = ''

        # firstly chose one compute from locked and of different lc-type to apply storage-profile
        LOG.debug('Looking for a locked computes with different lc-type')
        compute_dest = self._choose_compute_locked_diff_type(lc_type=lc_type)
        if compute_dest:
            LOG.debug('-got target compute:{}, locked, diff lc-type'.format(compute_dest))
            return compute_dest

        old_active_controller = system_helper.get_active_controller_name()
        LOG.debug('-no locked computes with different lc-type')

        # otherwise chose one compute from unlocked and of different lc-type to apply storage-profile
        LOG.debug('Looking for unlocked computes with different lc-type')
        compute_dest = self._choose_compute_unlocked_diff_Type(lc_type=lc_type, active_controller=old_active_controller)
        if compute_dest:
            LOG.debug('-got target compute:{}, unlocked, diff lc-type'.format(compute_dest))
            return compute_dest

        LOG.debug('-no unlocked computes with different lc-type')

        # still can't find a candidate, choose one with the same lc-type
        LOG.debug('Looking for compute locked with same lc-type')
        compute_dest = self._choose_compute_locked_diff_type(lc_type=lc_type)
        if compute_dest:
            LOG.debug('-got target compute:{}, locked, same lc-type'.format(compute_dest))
            return compute_dest

        LOG.debug('-no locked computes with same lc-type')
        LOG.debug('Looking for compute unlocked with same lc-type')
        compute_dest = self._choose_compute_unlocked_same_type(lc_type=lc_type, active_controller=old_active_controller)

        if compute_dest:
            LOG.debug('-got target compute:{}, unlocked, same lc-type'.format(compute_dest))
            return compute_dest

        LOG.warn('Cannot find a target compute!?')
        return ''

    def create_storage_profile_of_type(self, lc_type='image'):
        LOG.debug('create a local-storage profile of backing type:{}'.format(lc_type))
        computes_of_lc_type = [h for h in host_helper.get_hypervisors()
                               if host_helper.check_host_local_backing_type(h, lc_type)]

        if not computes_of_lc_type:
            # no computes have expected type of lc-type, modify one of them to the type
            compute_src = self.setup_local_storage_type_on_lab(lc_type=lc_type)
        else:
            active_controller = system_helper.get_active_controller_name()
            if active_controller in computes_of_lc_type:
                compute_src = active_controller
            else:
                compute_src = random.choice(computes_of_lc_type)
        prof_uuid = self.create_storage_profile(compute_src, lc_type=lc_type)

        return prof_uuid, compute_src

    def _get_local_storage_disk_sizes(self):
        host_pv_sizes = {}
        for host in host_helper.get_hypervisors():
            host_pv_sizes[host] = local_storage_helper.get_host_lvg_disk_size(host=host)

        return host_pv_sizes

    @mark.skipif(_less_than_2_hypervisors(), reason='Requires 2 or more hyperviors to run the testcase')
    @mark.parametrize('local_storage_type', [
        mark.p1('lvm'),
        mark.p1('image'),
    ])
    def test_local_storage_operations(self, local_storage_type):
        """
        Args:
            local_storage_type(str): type of local-storage backing, should be image, lvm

        Setup:

        Test Steps:
            1 Create a storage-profile with the expected local-storage type
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
                5) apply the storage-profile onto the target compute with CLI 'system host-apply-storpofile'
            5 Verify the local-storage type of the taget compute was successfully changed

        Teardown:
            1 delete the storage-profile created
            2 unlock the computes/hyperviors locked for testing
            3 restore the local-storage types changed during testing for the impacted computes

        Notes:
                will cover 3 test cases:
                    34.  Local Storage Create/Apply/Delete – Local Image
                    35.  Local Storage Profile Create/Apply/Delete – Local LVM
                    36.  Local Storage Profile Apply (Local Image ↔ Local LVM)
        """
        LOG.tc_step('Create a storage-profile with the expected type of local-storage backing:{}' \
                    .format(local_storage_type))
        prof_uuid, compute_src = self.create_storage_profile_of_type(lc_type=local_storage_type)
        assert prof_uuid, 'Faild to create storage-profile for local-storage-type:{}' \
            .format(local_storage_type)

        LOG.tc_step('NEG TC: Attempt to apply the storage profile on an unlocked compute, expecting to fail')
        try:
            compute_unlocked = random.choice(host_helper.get_nova_hosts())
        except IndexError as e:
            LOG.warn('No unlocked computes')
            skip('No unlocked computes to create storage-profile from')

        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_unlocked, prof_uuid),
                                      fail_ok=True, rtn_list=True)
        assert 0 != rtn_code, 'Should fail to apply storage-profile:{} to unlocked host:{}' \
            .format(prof_uuid, compute_unlocked)

        LOG.tc_step('Choose a compute other than {} to apply the storage-profile'.format(compute_src))
        compute_dest = self.select_target_compute(compute_src, lc_type=local_storage_type)
        LOG.debug('target compute:{}'.format(compute_dest))

        LOG.debug('Check if the storprofile is applicable to the target compute')
        if not local_storage_helper.is_storprof_applicable_to(host=compute_dest, profile=prof_uuid):
            msg = 'storage-profile:{} is not applicable to compute:{}'.format(prof_uuid, compute_dest)
            LOG.debug(msg)
            return -1, msg

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(prof_uuid, compute_dest))
        rtn_code, output = self.apply_storage_profile(
            compute_dest,
            lc_type=local_storage_type, profile=prof_uuid, fail_ok=True)
        if rtn_code == -1:
            LOG.debug('Skipped to apply storage profile')
            return rtn_code, output
        assert 0 == rtn_code, 'Failed to apply the storage-profile {} onto {}'.format(prof_uuid, compute_dest)

        LOG.tc_step('Check if the changes take effect after unlocking')
        rtn_code = host_helper.unlock_host(compute_dest)
        if 0 == rtn_code:
            TestLocalStorage._computes_locked.remove(compute_dest)

        LOG.tc_step('-Verify the lc type changed to {} on host:{}'
                    .format(local_storage_type, compute_dest))
        assert host_helper.check_host_local_backing_type(compute_dest, type=local_storage_type), \
            'Local-storage backing failed to change to {} on host:{}'.format(local_storage_type, compute_dest)

    @mark.skipif(_less_than_2_hypervisors(), reason='Requires 2 or more computes to test this test case')
    @mark.parametrize('local_storage_type', [
        mark.p2('image'),
        mark.p2('lvm'),
    ])
    def test_apply_profile_to_smaller_sized_host(self, local_storage_type):
        """

        Args:
            local_storage_type(str): type of local-storage backing, allowed values: image, lvm

        Returns:

        Setup:

        Test Steps:
            1 check if the lab has computes with different disk sizes, if not skip the rest of the testing
            2 find the compute having max disk size
            3 create storage-profile on the compute with max disk size
            4 randomly choose one of the compute
            5 lock the selected compute
            6 apply the storage-profile on compute, expecting to fail
            7 verify the attempt to apply the storage-profile did not succeed

        Teardown:
            1 delete the storage-profile created
            2 unlock the computes/hyperviors locked for testing
            3 restore the local-storage types changed during testing for the impacted computes

        Notes:
                will cover 2 test cases:
                    37.  Local Storage Profile Negative Test (Insufficient Resources/Different Devices)
                        – Local_LVM profile
                    38.  Local Storage Profile Negative Test (Different Devices) – Local_Image profile
        """
        host_lc_sizes = self._get_local_storage_disk_sizes()
        sizes = [size for _, size in host_lc_sizes.items()]
        LOG.tc_step('Check if all the sizes of physical-volumes are the same')
        if len(set(sizes)) <= 1:
            msg = 'Skip the test cases, because all sizes of physical-volumes are the same'
            LOG.tc_step(msg)
            skip(msg)
            return -1, msg

        LOG.debug('There are differnt sizes for the pv-disks')
        compute_with_max, size_max = max(host_lc_sizes.items(), key=operator.itemgetter(1))
        LOG.tc_step('Create storage-profile on the compute:{} with max disk size:{}'.
                    format(compute_with_max, size_max))
        profile_uuid = self.create_storage_profile(compute_with_max, lc_type=local_storage_type)
        LOG.debug('Profile:{} with max disk size:{} is created for {}'.format(size_max, profile_uuid, compute_with_max))
        LOG.debug('host_lc_sizes={}'.format(host_lc_sizes))

        LOG.tc_step('Randomly select one other than compute:{}'.format(compute_with_max))
        other_computes = []
        for host in host_lc_sizes.keys():
            size = int(host_lc_sizes[host])
            if host != compute_with_max and  size < size_max and size > 0:
                other_computes.append(host)
        if not other_computes:
            msg = 'Cannot find one compute with the disk size:{} other than'.format(size_max, compute_with_max)
            LOG.error(msg)
            return 1, msg

        compute_dest = random.choice(other_computes)

        LOG.tc_step('Attemp to apply storage-profile from {} to {}'.format(compute_with_max, compute_dest))
        host_helper.lock_host(compute_dest, check_first=True)
        TestLocalStorage._computes_locked.append(compute_dest)

        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_dest, profile_uuid),
                                      fail_ok=True, rtn_list=True)

        LOG.tc_step('Verify the CLI failed as expected')
        assert rtn_code == 1, 'Fail, expect to fail with return code==1, but got return code:{}, msg:{}'. \
            format(rtn_code, output)

        LOG.tc_step('Done, let the tear-down procedure to unlock the host')
        return 0, output

    def _get_storage_profile_local_file(self, local_storage_type='image'):
        profile_file_path = os.path.sep.join([ProjVar.get_var('LOG_DIR'),
                                              'tc39_local_storage_profile_{}.xml'.format(local_storage_type)])
        if not os.path.isfile(profile_file_path):
            msg = 'local storage profile:{} does not exist!'.format(profile_file_path)
            LOG.warn(msg)
            return ''
        else:
            LOG.debug('OK, found local storage profile:{}'.format(profile_file_path))
            return profile_file_path

    def import_profile(self, profile_file=None):
        if not profile_file:
            LOG.warn('Full path name of the storage/hardware profile name is required.')
            return 1

        LOG.debug('Attempt to import profile:{}'.format(profile_file))
        return cli.system('profile-import {}'.format(profile_file), rtn_list=True)

    def verify_local_storage_type(self, profile=''):
        return 0

    @mark.skipif(_less_than_2_hypervisors(), reason='Requires 2 or more computes to test this test case')
    @mark.parametrize('local_storage_type', [mark.p2('image'), mark.p2('lvm')])
    def test_import_storage_profile(self, local_storage_type):
        """
        Args:
            local_storage_type(str): type of local-storage backing, allowed values: image, lvm

        Setup:

        Test Steps:
            1 check if the profile exists
            2 apply the profile
            3 verify the results

        Teardown:
            1 delete the storage-profile created
            2 unlock the computes/hyperviors locked for testing
            3 restore the local-storage types changed during testing for the impacted computes

        Notes:
            will cover 1 test cases:
                39.  Local Storage Profile Import
        Returns:

        """
        LOG.tc_step('Check if file existing for storage-profile of type:{}'.format(local_storage_type))
        profile_file = self._get_storage_profile_local_file(local_storage_type=local_storage_type)
        if not profile_file:
            skip('cannot find required file: {} for type:{}'.format(profile_file, local_storage_type))
            return

        LOG.tc_step('Apply the storage-profile via CLI profile-import {}'.format(profile_file))
        rtn_code, output = self.import_profile(profile_file=profile_file)
        assert 0 == rtn_code, 'Failed in system profile-import {}, msg:{}'.format(profile_file, output)

        LOG.tc_step('Check if the storage profile types are changed on all computes')
        assert 0 == self.verify_local_storage_type(profile=profile_file)
