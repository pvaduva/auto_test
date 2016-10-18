import time
import random
import os
import re
import operator

from pytest import mark
from pytest import skip
from pytest import fixture

from consts.cgcs import LocalStorage

from utils.tis_log import LOG
from utils import cli
from keywords import common
from testfixtures.recover_hosts import HostsToRecover

from keywords import system_helper, host_helper, local_storage_helper


def _get_computes_for_local_backing_type(ls_type='image', con_ssh=None):
    hosts_of_type = []
    hosts = host_helper.get_nova_hosts(con_ssh=con_ssh)

    for host in hosts:
        if host_helper.check_host_local_backing_type(host, storage_type=ls_type, con_ssh=con_ssh):
            hosts_of_type.append(host)

    return hosts_of_type


def _less_than_2_hypervisors():
    return len(host_helper.get_nova_hosts()) < 2


class TestLocalStorage(object):
    """test local storage"""

    # DIR_PROFILE_IMPORT_FROM='/home/wrsroot/storage_profiles'

    _cleanup_lists = {
        'profile': [],
        'locked': [],
        'local_storage_type':[]
    }

    @fixture(scope='class', autouse=True)
    def cleanup_local_storage(self, request):

        def cleanup():
            profiles_created = self._get_cleanup_list('profile')
            computes_locked = self._get_cleanup_list('locked')
            old_new_types = self._get_cleanup_list('local_storage_type')
            try:
                while profiles_created:
                    system_helper.delete_storage_profile(profile=profiles_created.pop())

                while computes_locked:
                    host_helper.unlock_host(computes_locked.pop())

                while old_new_types:
                    host, old_type, _ = old_new_types.pop()
                    HostsToRecover.add(host, scope='class')
                    host_helper.lock_host(host)
                    cmd = 'host-lvg-modify -b {} {} nova-local'.format(old_type, host)
                    cli.system(cmd, fail_ok=False)
                    host_helper.unlock_host(host)
            finally:
                pass

        request.addfinalizer(cleanup)

    def _add_to_cleanup_list(self, to_cleanup=None, cleanup_type=''):
        cleanups = TestLocalStorage._cleanup_lists
        for list in cleanups.keys():
            if cleanup_type == list:
                cleanups[list].append(to_cleanup)

    def _get_cleanup_list(self, list_type=''):
        cleanups = TestLocalStorage._cleanup_lists
        for list in cleanups.keys():
            if list_type == list:
                return cleanups[list]

    def _remove_from_cleanup_list(self, to_remove=None, list_type=''):
        if not to_remove:
            return
        list = self._get_cleanup_list(list_type=list_type)
        if list:
            list.remove(to_remove)

    def apply_storage_profile(self, compute_dest, ls_type='image', profile=None,
                              ssh_client=None, fail_ok=False, force_change=False):
        if host_helper.check_host_local_backing_type(compute_dest, ls_type, con_ssh=ssh_client) and not force_change:
            msg = 'host already has local-storage backing:{} as expected'.format(ls_type)
            LOG.info(msg)
            return -1, msg

        LOG.debug('compute: {} is not in local-storage-type:{} or will force to apply'.format(compute_dest, ls_type))
        if compute_dest == system_helper.get_active_controller_name():
            # this will happen on a CPE lab
            LOG.debug('will swact the current active controller:{}'.format(compute_dest))
            host_helper.swact_host()

        LOG.debug('get the original local-storage-type for compute:{}'.format(compute_dest))
        old_type = host_helper.get_local_storage_backing(compute_dest)

        LOG.tc_step('Lock the host:{} for applying storage-profile'.format(compute_dest))
        HostsToRecover.add(compute_dest, scope='function')
        rtn_code, msg = host_helper.lock_host(compute_dest, con_ssh=ssh_client, fail_ok=False, check_first=True)
        if 0 == rtn_code:
            self._add_to_cleanup_list(to_cleanup=compute_dest, cleanup_type='locked')

        LOG.tc_step('Delete the lvg "nova-local" on host:{}'.format(compute_dest))
        rtn_code, msg = cli.system('host-lvg-delete {} nova-local'.format(compute_dest),
                   ssh_client=ssh_client, fail_ok=False, rtn_list=True)
        assert 0 == rtn_code, msg

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(profile, compute_dest))
        rtn_code, msg = cli.system('host-apply-storprofile {} {}'.format(compute_dest, profile),
                                      fail_ok=fail_ok, rtn_list=True)
        assert rtn_code == 0, msg

        self._add_to_cleanup_list(to_cleanup=(compute_dest, old_type, ls_type), cleanup_type='local_storage_type')

        return rtn_code, msg

    def create_storage_profile(self, host, ls_type='image'):
        prof_name = 'storprof_{}{}_{}_{}'.format(host[0], host[-1],
                                                 ls_type, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
        prof_uuid = system_helper.create_storage_profile(host, profile_name=prof_name)

        self._add_to_cleanup_list(to_cleanup=prof_uuid, cleanup_type='profile')

        return prof_uuid

    def set_local_storage_backing(self, compute=None, to_type='image'):
        LOG.debug('lock compute:{} in order to change to new local-storage-type:{}'\
                 .format(compute, to_type))
        HostsToRecover.add(compute, scope='function')
        rtn_code, msg = host_helper.lock_host(compute, check_first=True)
        if 0 == rtn_code:
            self._add_to_cleanup_list(to_cleanup=compute, cleanup_type='locked')

        LOG.debug('get the original local-storage-backing-type for compute:{}'.format(compute))
        old_type = host_helper.get_local_storage_backing(compute)

        cmd = 'host-lvg-modify -b {} {} nova-local'.format(to_type, compute)
        rtn_code, msg = cli.system(cmd, rtn_list=True, fail_ok=False)
        assert 0 == rtn_code, msg
        self._add_to_cleanup_list(to_cleanup=(compute, old_type, to_type), cleanup_type='local_storage_type')

        LOG.debug('unlock {} now'.format(compute))
        host_helper.unlock_host(compute)

    def setup_local_storage_type_on_lab(self, ls_type='image'):
        LOG.debug('Chose one compute to change its local-storage-backing to expected type: {}'.format(ls_type))

        computes_locked = host_helper.get_hypervisors(state='down', status='disabled')
        if computes_locked:
            compute_to_change = random.choice(computes_locked)
        else:
            computes_unlocked = host_helper.get_nova_hosts()
            compute_to_change = random.choice([c for c in computes_unlocked
                                               if c != system_helper.get_active_controller_name()])
        self.set_local_storage_backing(compute=compute_to_change, to_type=ls_type)

        return compute_to_change

    def _is_profile_applicable_to(self, storage_profile=None, compute_dest=None):
        LOG.debug('compare storage-sizes of the storage-profile:{} with compute:{}'.\
                 format(storage_profile, compute_dest))

        disk, size_profile = local_storage_helper.get_storprof_diskconfig(profile=storage_profile)
        size_disk = local_storage_helper.get_host_disk_size(compute_dest, disk)

        if size_disk >= size_profile:
            return True

        return False

    def _choose_compute_locked_diff_type(self, ls_type='image'):
        computes_locked_diff_type = [c for c in
                                     host_helper.get_hypervisors(state='down', status='disabled')
                                     if not host_helper.check_host_local_backing_type(c, storage_type=ls_type)]
        if computes_locked_diff_type:
            compute_dest = random.choice(computes_locked_diff_type)
            return compute_dest

        return ''

    def _choose_compute_unlocked_diff_Type(self, ls_type='image', active_controller=''):
        computes_unlocked_diff_type = [c for c in
                                       host_helper.get_nova_hosts()
                                       if not host_helper.check_host_local_backing_type(c, storage_type=ls_type)]

        if computes_unlocked_diff_type:
            LOG.debug('{} computes unlocked and with local-storage-type:{}'\
                      .format(len(computes_unlocked_diff_type), ls_type))
            LOG.debug('old active is controller:{}'.format(active_controller))

            if active_controller in computes_unlocked_diff_type:
                LOG.debug('is on a CPE system')
                computes_unlocked_diff_type.remove(active_controller)
                if computes_unlocked_diff_type:
                    LOG.debug('multiple computes unlocked, different type, randomly select one non-active controller')
                    compute_dest = random.choice(computes_unlocked_diff_type)
                    LOG.debug('OK, selected {} as the target compute'.format(compute_dest))
                    return compute_dest
                else:
                    LOG.debug('have to select the active controller as target:{}'.format(active_controller))
                    compute_dest = active_controller
                    return compute_dest

            else:
                LOG.debug('non-CPE system')
                compute_dest = random.choice(computes_unlocked_diff_type)
                LOG.debug('non-CPE lab, select {} as target compute'.format(compute_dest))
                return compute_dest

        return ''

    def _choose_compute_locked_same_type(self, ls_type='image'):
        computes_locked = [c for c in
                           host_helper.get_hypervisors(state='down', status='disabled')
                           if host_helper.check_host_local_backing_type(c, storage_type=ls_type)]
        if computes_locked:
            compute_dest = random.choice(computes_locked)
            LOG.debug('selected target compute:{}, locked, same local-storage-type' \
                     .format(compute_dest))
            return compute_dest

    def _choose_compute_unlocked_same_type(self, ls_type='image', active_controller=''):
        computes_unlocked = [c for c in
                             host_helper.get_nova_hosts()
                             if host_helper.check_host_local_backing_type(c, storage_type=ls_type)]
        if active_controller in computes_unlocked:
            computes_unlocked.remove(active_controller)
            if computes_unlocked:
                compute_dest = random.choice(computes_unlocked)
            else:
                compute_dest = active_controller
                LOG.debug('-selected old active-controller:{}, same local-storage-type:{}' \
                         .format(compute_dest, ls_type))
        else:
            compute_dest = random.choice(computes_unlocked)
            LOG.debug('-target compute:{}, unlocked, same local-storage-type'.format(compute_dest))

        return compute_dest

    def select_target_compute(self, compute_src='', ls_type='image'):
        compute_dest = ''

        old_active_controller = system_helper.get_active_controller_name()

        # otherwise chose one compute from unlocked and of different local-storage-type to apply storage-profile
        LOG.debug('Looking for unlocked computes with different local-storage-type')
        compute_dest = self._choose_compute_unlocked_diff_Type(ls_type=ls_type, active_controller=old_active_controller)
        if compute_dest:
            LOG.debug('got target compute:{}, unlocked, diff local-storage-type'.format(compute_dest))
            return compute_dest

        LOG.debug('-no unlocked computes with different local-storage-type')

        LOG.debug('Looking for compute unlocked with same local-storage-type')
        compute_dest = self._choose_compute_unlocked_same_type(ls_type=ls_type, active_controller=old_active_controller)

        if compute_dest:
            LOG.debug('got target compute:{}, unlocked, same local-storage-type'.format(compute_dest))
            return compute_dest

        LOG.warn('Cannot find a target compute!?')
        return ''

    def create_storage_profile_of_type(self, ls_type='image'):
        LOG.debug('create a local-storage profile of backing type:{}'.format(ls_type))
        computes_of_ls_type = [h for h in host_helper.get_hypervisors()
                               if host_helper.check_host_local_backing_type(h, ls_type)]

        if not computes_of_ls_type:
            # no computes have expected type of local-storage-type, modify one of them to the type
            compute_src = self.setup_local_storage_type_on_lab(ls_type=ls_type)
        else:
            active_controller = system_helper.get_active_controller_name()
            if active_controller in computes_of_ls_type:
                compute_src = active_controller
            else:
                compute_src = random.choice(computes_of_ls_type)
        prof_uuid = self.create_storage_profile(compute_src, ls_type=ls_type)

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
        prof_uuid, compute_src = self.create_storage_profile_of_type(ls_type=local_storage_type)
        assert prof_uuid, 'Faild to create storage-profile for local-storage-type:{}' \
            .format(local_storage_type)

        LOG.tc_step('NEG TC: Attempt to apply the storage profile on an unlocked compute, expecting to fail')
        try:
            compute_unlocked = random.choice(host_helper.get_nova_hosts())
        except IndexError:
            LOG.warn('No unlocked computes')
            skip('No unlocked computes to create storage-profile from')

        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_unlocked, prof_uuid),
                                      fail_ok=True, rtn_list=True)
        assert 0 != rtn_code, 'Should fail to apply storage-profile:{} to unlocked host:{}' \
            .format(prof_uuid, compute_unlocked)

        LOG.tc_step('Choose a compute other than {} to apply the storage-profile'.format(compute_src))
        compute_dest = self.select_target_compute(compute_src, ls_type=local_storage_type)
        LOG.debug('target compute:{}'.format(compute_dest))

        LOG.debug('Check if the storprofile is applicable to the target compute')
        if not local_storage_helper.is_storprof_applicable_to(host=compute_dest, profile=prof_uuid):
            msg = 'storage-profile:{} is not applicable to compute:{}'.format(prof_uuid, compute_dest)
            LOG.info(msg)
            return -1, msg

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(prof_uuid, compute_dest))
        rtn_code, output = self.apply_storage_profile(
            compute_dest,
            ls_type=local_storage_type, profile=prof_uuid, fail_ok=True)
        if rtn_code == -1:
            LOG.debug('Skipped to apply storage profile')
            return rtn_code, output
        assert 0 == rtn_code, 'Failed to apply the storage-profile {} onto {}'.format(prof_uuid, compute_dest)

        LOG.tc_step('Check if the changes take effect after unlocking')
        rtn_code = host_helper.unlock_host(compute_dest)

        LOG.tc_step('Verify the local-storage type changed to {} on host:{}'
                    .format(local_storage_type, compute_dest))
        assert host_helper.check_host_local_backing_type(compute_dest, storage_type=local_storage_type), \
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
        host_ls_sizes = self._get_local_storage_disk_sizes()
        sizes = [size for _, size in host_ls_sizes.items()]
        LOG.tc_step('Check if all the sizes of physical-volumes are the same')
        if len(set(sizes)) <= 1:
            msg = 'Skip the test cases, because all sizes of physical-volumes are the same'
            LOG.tc_step(msg)
            skip(msg)
            return -1, msg

        LOG.debug('There are differnt sizes for the pv-disks')
        compute_with_max, size_max = max(host_ls_sizes.items(), key=operator.itemgetter(1))
        LOG.tc_step('Create storage-profile on the compute:{} with max disk size:{}'.
                    format(compute_with_max, size_max))
        profile_uuid = self.create_storage_profile(compute_with_max, ls_type=local_storage_type)
        LOG.debug('Profile:{} with max disk size:{} is created for {}'.format(size_max, profile_uuid, compute_with_max))
        LOG.debug('host_ls_sizes={}'.format(host_ls_sizes))

        LOG.tc_step('Randomly select one other than compute:{}'.format(compute_with_max))
        other_computes = []
        for host in host_ls_sizes.keys():
            size = int(host_ls_sizes[host])
            if host != compute_with_max and  size < size_max and size > 0:
                other_computes.append(host)
        if not other_computes:
            msg = 'Cannot find one compute with the disk size:{} other than'.format(size_max, compute_with_max)
            LOG.error(msg)
            return 1, msg

        compute_dest = random.choice(other_computes)

        LOG.tc_step('Attemp to apply storage-profile from {} to {}'.format(compute_with_max, compute_dest))

        HostsToRecover.add(compute_dest, scope='function')
        rtn_code, output = host_helper.lock_host(compute_dest, check_first=True)
        if rtn_code == 0:
            self._add_to_cleanup_list(to_cleanup=compute_dest, cleanup_type='locked')

        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_dest, profile_uuid),
                                      fail_ok=True, rtn_list=True)

        LOG.tc_step('Verify the CLI failed as expected')
        assert rtn_code == 1, 'Fail, expect to fail with return code==1, but got return code:{}, msg:{}'. \
            format(rtn_code, output)

        LOG.tc_step('Done, let the tear-down procedure to unlock the host')
        return 0, output

    def get_remote_storprofile_file(self, local_storage_type='image', local_file=''):
        remote_file = os.path.join('/home/wrsroot',
                         '{}_storage_profile_to_import.xml'.format(local_storage_type))

        return remote_file

    def get_local_storprfoile_file(self, local_storage_type='image'):
        file_path = os.path.join(os.path.expanduser('~'),
                            LocalStorage.DIR_PROFILE,
                         '{}_storage_profile_to_import.xml'.format(local_storage_type))
        if os.path.isfile(file_path):
            return file_path
        return ''

    def import_storprofile_profile(self, profile_file=None):
        rtn_code, msg = cli.system('profile-import {}'.format(profile_file), rtn_list=True)
        LOG.info('rtn:{}, msg:{}'.format(rtn_code, msg))
        return rtn_code, msg

    def existing_storprofile_names(self, existing_storprofiles=None):
        existing_names = [(existing_storprofiles[type][uuid]['name'], type)
                            for type in existing_storprofiles.keys()
                                for uuid in existing_storprofiles[type].keys()]
        return existing_names

    def verify_storprofile_existing(self, file_name='', existing_profiles=None):
        existing_names = self.existing_storprofile_names(existing_profiles)

        return file_name in [name for name, type in existing_names]

    def is_storage_node(self):
        return len(system_helper.get_storage_nodes()) > 0

    def check_warn_msg(self, msg_import='', existing_profiles=None):
        err_msg = re.compile('error: Storage profile can only be imported into a system with Ceph backend')
        warn_msg = re.compile('warning: Local Storage profile (\w+) already exists and is not imported.')


        if 'warn' in msg_import or 'error' in msg_import:
            for line in msg_import.splitlines():
                match = warn_msg.match(line)
                if match:
                    failed_profile_name = match.group(1)
                    if not self.verify_storprofile_existing(file_name=failed_profile_name,
                                                            existing_profiles=existing_profiles):
                        LOG.error('storprofile {} does not exist but still been rejected to import'\
                                  .format(failed_profile_name))
                        return 1
                    else:
                        LOG.info('OK, {} is already existing hence failed to import'.format(failed_profile_name))
                else:
                    match = err_msg.match(line)
                    if match:
                        if self.is_storage_node():
                            LOG.error('storprofile been rejected due to non-storage lab')
                            return 1
                        else:
                            LOG.info('OK, storage-profiles been rejected because of non-storage lab')
        return 0

# ls xml_sps:
# {'lvg':
#      [
#          {'instance_backing': 'image',
#           'lvm_vg_name': 'nova-local',
#           'concurrent_disk_operations': '2'
#           }
#      ],
#  'disk': [{'size': '228936', 'node': '/dev/sdb'}],
#  'name': 'with_ceph_image_local_storage_backed'
# }


# ls post_import_sps:
# {'9bba4db3-9b06-4fb0-a53d-c00fb7a00207':
#      {'lvg':
#           {'instance_backing': 'image', 'lvm_vg_name': 'nova-local', 'concurrent_disk_operations': '2'},
#       'disk': {'/dev/sdb': 228936},
#       'name': 'with_ceph_image_local_storage_backed'
#       }
# }

# storage-profiles from XML:/home/mhuang1/storage_profiles/image_storage_profile_to_import.xml
# {'localstorageProfile':
#     {'name': 'with_ceph_image_local_storage_backed',
#      'disk': [{'node': '/dev/sdb', 'size': '228936'}],
#      'lvg':
#         [{'lvm_vg_name': 'nova-local', 'concurrent_disk_operations': '2', 'instance_backing': 'image'}]
#     },
#  'storageProfile':
#     {'name': 'ceph_st
#      'disk': [
#         {'node': '/dev/sdb', 'volumeFunc': 'osd', 'size': '228936'},
#         {'node': '/dev/sdc', 'volumeFunc': 'osd', 'size': '228936'}
#         ]
#     }
# }

# storage-profiles from lab
# {'storage':
#     {'a716a4b3-7dba-4a82-8ac4-854bef593c25':
#         {'name': 'ceph_storage_profile',
#          'storage_type': 'storage',
#          'disk_stor_conf':
#             {'/dev/sdb': [228936, 'osd'],
#              '/dev/sdc': [228936, 'osd']
#             }
#         }
#     },
#  'localstorage':
#     {
#     }
# }
    def compare_stor_disks(self, xml_disks, impt_disks):
        for disk in xml_disks:
            dev = disk['node']
            func = disk['volumeFunc']
            size = disk['size']
            impt_size, impt_func = impt_disks[dev]
            if  size != impt_size:
                LOG.info('mismatched size for XML:{} vs imported:{} for dev:{}'\
                         .format(size, impt_size, dev))
                return False

            if func != impt_func:
                LOG.info('mismatched volume-function for XML:{} vs imported:{} for dev:{}'\
                         .format(func, impt_func, dev))
                return False
        return True

    def get_impt_prof_by_name(self, name, impt_setting):
        for uuid in impt_setting.keys():
            if 'name' in impt_setting[uuid] and name == impt_setting[uuid]['name']:
                return impt_setting[uuid]
        LOG.warn('Failed to find imported storage-profile with name:{}'.format(name))
        return {}

    def compare_storage_profile(self, xml_setting, impt_setting):
        for sprof in xml_setting:
            name = sprof['name']
            sprof_impt = self.get_impt_prof_by_name(name, impt_setting)
            if not sprof_impt:
                LOG.warn('NONE profile imported EISTS for profile from XML {}'.format(name))
                return 1

            if not self.compare_single_storage_profile(sprof, sprof_impt):
                LOG.warn('profile imported does not match profile from XML')
                return 1
        return 0

    def compare_single_storage_profile(self, xml_sprofile, impt_sprofile):

        if impt_sprofile['storage_type'] != 'storage':
            LOG.info('storage-type imported:{} IS NOT "storage"'\
                     .format(impt_sprofile['name']))
            return False

        if not self.compare_stor_disks(xml_sprofile['disk'], impt_sprofile['disk_stor_conf']):
            LOG.info('disk setting does not match')

        return True

    def compare_ls_disks(self, xml_disks, imt_disks):
        for kv in xml_disks:
            size = kv['size']
            node = kv['node']
            if size != imt_disks[node]:
                LOG.info('mismatched lvg disk size, in XML:{} vs imported:{} for dev:{}'\
                         .format(size, imt_disks[node], node))
                return False
        return True

    def compare_ls_lvginfo(self, xml_lvginfo, imt_lvginfo):
        xmllvg = xml_lvginfo[0]
        for key in xmllvg.keys():
            if xmllvg[key] != imt_lvginfo[key]:
                LOG.info('mismatched lvg setting, in XML:{} vs imported:{}'\
                         .format(xmllvg[key], imt_lvginfo[key]))
                return False

        return True

    def get_impt_lsprof_by_name(self, name, impt_lsprf):
        for uuid in impt_lsprf.keys():
            if 'name' in impt_lsprf[uuid] and name == impt_lsprf[uuid]['name']:
                return impt_lsprf[uuid]

        LOG.error('No imported local-storage profile found with name {}'.format(name))
        assert 0
        return {}

    def compare_single_local_storprof(self, xmlprof, imptprof):
        if not self.compare_ls_disks(xmlprof['disk'], imptprof['disk']):
            LOG.error('disk setting MISMATCH for local-storage profile:{}'.format(xmlprof['name']))
            return False

        if not self.compare_ls_lvginfo(xmlprof['lvg'], imptprof['lvg']):
            LOG.error('lvg setting MISMATCH for local-storage profile:{}'.format(xmlprof['name']))
            return False

        return True

    def compare_local_storage_profile(self, xml_lsprf, pstimt_lsprf):
        for xmlprof in xml_lsprf:
            name = xmlprof['name']
            impt_prof = self.get_impt_lsprof_by_name(name, pstimt_lsprf)
            if not impt_prof or not self.compare_single_local_storprof(xmlprof, impt_prof):
                LOG.error('local storage profile mismatch between imported and from XML:{}'.format(name))
                return 1
        return 0

    def check_imported_storprofiles(self, xml_profiles=None):
        post_import_storprofiles = local_storage_helper.get_existing_storprofiles()

        if self.is_storage_node():
            assert 0 == self.compare_storage_profile(xml_profiles['storageProfile'],
                                                     post_import_storprofiles['storage']),\
                    'Improted storage-profiles MISMATCH XML profile'

        assert 0 == self.compare_local_storage_profile(xml_profiles['localstorageProfile'],
                                                       post_import_storprofiles['localstorage']),\
                    'Improted local-storage-profiles MISMATCH XML profile'
        return 0

    def verify_storage_profile_imported(self, profile='',
                                        rtn_import=0, msg_import='', pre_import_storprofiles=None):

        from_xml_profile = local_storage_helper.parse_storprofiles_from_xml(xml_file=profile)

        assert 0 == self.check_warn_msg(msg_import=msg_import, existing_profiles=pre_import_storprofiles),\
                        'Incorrect CLI messages'

        assert 0 == self.check_imported_storprofiles(xml_profiles=from_xml_profile),\
                        'Imported storage-profiles do not match settings from XML file'

        return 0

    @mark.known_issue('CGTS-4432')
    @mark.parametrize('local_storage_type', [
        mark.p2('image'),
        mark.p2('lvm'),
    ])
    def test_import_storage_profile(self, local_storage_type):
        """
        Args:
            local_storage_type(str): type of local-storage backing, allowed values: image, lvm

        Setup:

        Test Steps:
            1 check if the storage-profile exists, skip if not
            2 get list of profile names current existing in the system
            3 import the storage-profile
            4 check the storage-profile actually created matching with those in the profile:
                1) profilename
                2) disk configuration
                3) physical volume config
                4) local volume group config

        Teardown:

        Notes:
            will cover 1 test cases:
                39.  Local Storage Profile Import
        Returns:

        """
        LOG.tc_step('Get the name of the profile and check if it is existing')
        local_file = self.get_local_storprfoile_file(local_storage_type=local_storage_type)
        if not local_file:
            msg = 'Cannot find the profile:{}'.format(local_file)
            LOG.tc_step(msg)
            skip(msg)
            return -1

        LOG.tc_step('Get list of profile names')
        pre_import_storprofiles = local_storage_helper.get_existing_storprofiles()

        LOG.tc_step('Apply the storage-profile via CLI profile-import {}'.format(local_file))
        remote_file = self.get_remote_storprofile_file(local_storage_type=local_storage_type)
        common.scp_to_active_controller(local_file, remote_file)

        rtn_code, output = self.import_storprofile_profile(profile_file=remote_file)
        assert 0 == rtn_code, 'Failed to import storage-profile'.format(remote_file)

        LOG.tc_step('Check if the storage profile are correctly imported into the system')
        assert 0 == self.verify_storage_profile_imported(profile=local_file,
                                                         rtn_import=rtn_code, msg_import=output,
                                                         pre_import_storprofiles=pre_import_storprofiles)

        return 0