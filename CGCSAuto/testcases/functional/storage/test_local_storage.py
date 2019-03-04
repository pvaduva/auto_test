import time
import random
import os
import re
import operator

from pytest import mark
from pytest import skip
from pytest import fixture

from consts.cgcs import LocalStorage
from consts.filepaths import WRSROOT_HOME

from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG
from utils import cli
from keywords import common
from testfixtures.recover_hosts import HostsToRecover

from keywords import system_helper, host_helper, local_storage_helper


def _get_computes_for_local_backing_type(ls_type='image', con_ssh=None):
    hosts_of_type = []
    hosts = host_helper.get_up_hypervisors(con_ssh=con_ssh)

    for host in hosts:
        if host_helper.is_host_with_instance_backing(host, storage_type=ls_type, con_ssh=con_ssh):
            hosts_of_type.append(host)

    return hosts_of_type


def min_no_disks_hypervisor():
    hypervisors = host_helper.get_hypervisors(state='up', status='enabled')

    host_disks = [local_storage_helper.get_host_disk_sizes(host=hypervisor) for hypervisor in hypervisors]

    LOG.debug('host_disks={}'.format(host_disks))
    return min([len(hd.keys()) for hd in host_disks])


@fixture(scope='module')
def ensure_multiple_disks():
    if min_no_disks_hypervisor() < 2:
        skip('Every hypervisor must have 2+ hard disks')


@fixture(scope='module')
def ensure_two_hypervisors():
    if len(host_helper.get_hypervisors(state='up', status='enabled')) < 2:
        skip("Less than two up hypervisors on system")


@fixture(scope='module')
def get_target_host():
    host = host_helper.get_up_hypervisors()[0]
    return host


class TestLocalStorage:
    """test local storage"""

    # DIR_PROFILE_IMPORT_FROM='/home/wrsroot/storage_profiles'

    _cleanup_lists = {
        'profile': [],
        'local_storage_type': []
    }

    @fixture(scope='class', autouse=True, params=['image', 'remote'])
    def setup_local_storage(self, request, get_target_host):
        local_storage = request.param
        host = get_target_host

        def cleanup():

            if not system_helper.is_storage_system():
                skip("This test requires a storage system")

            profiles_created = self._pop_cleanup_list('profile')
            old_new_types = self._pop_cleanup_list('local_storage_type')

            # Add hosts to module level recovery fixture in case of modify or unlock fail in following class level
            # recovery attempt.
            for item in old_new_types:
                HostsToRecover.add(item[0], scope='module')

            exceptions = []
            try:
                LOG.fixture_step("(class) Delete created storage profiles")
                while profiles_created:
                    system_helper.delete_storage_profile(profile=profiles_created.pop())

            except Exception as e:
                LOG.exception(e)
                exceptions.append(e)

            try:
                LOG.fixture_step("(class) Revert local storage backing for {}".format(old_new_types))
                while old_new_types:
                    host_to_revert, old_type, _ = old_new_types.pop()
                    LOG.info("Revert {} local storage to {}".format(host_to_revert, old_type))
                    host_helper.set_host_storage_backing(host=host_to_revert, inst_backing=old_type, unlock=True)

            except Exception as e:
                LOG.exception(e)
                exceptions.append(e)

            assert not exceptions, "Failure occurred. Errors: {}".format(exceptions)
        request.addfinalizer(cleanup)

        origin_lvg = host_helper.get_host_instance_backing(host)
        if origin_lvg != local_storage:
            self._add_to_cleanup_list(to_cleanup=(host, origin_lvg, local_storage), cleanup_type='local_storage_type')
            LOG.fixture_step("(class) Set {} local storage backing to {}".format(host, local_storage))
            self.set_local_storage_backing(host, to_type=local_storage)
        return local_storage, host

    def _add_to_cleanup_list(self, to_cleanup=None, cleanup_type=''):
        cleanups = TestLocalStorage._cleanup_lists
        for list_type in cleanups.keys():
            if cleanup_type == list_type:
                cleanups[list_type].append(to_cleanup)

    def _pop_cleanup_list(self, list_type):
        cleanups = TestLocalStorage._cleanup_lists

        if list_type == 'local_storage_type':
            rtn_list = []
            existing_hosts = []
            for item in cleanups[list_type]:
                hostname = item[0]
                if hostname not in existing_hosts:
                    rtn_list.append(item)
                    existing_hosts.append(hostname)
        else:
            rtn_list = list(set(cleanups[list_type]))

        # reset the list for given type
        TestLocalStorage._cleanup_lists[list_type] = []
        return rtn_list

    def apply_storage_profile(self, compute_dest, ls_type='image', profile=None, force_change=False):
        if host_helper.is_host_with_instance_backing(compute_dest, ls_type) and not force_change:
            msg = 'Host already has local-storage backing:{}. No need to apply profile.'.format(ls_type)
            LOG.info(msg)
            return -1, msg

        LOG.debug('compute: {} is not in local-storage-type:{} or will force to apply'.format(compute_dest, ls_type))
        LOG.debug('get the original local-storage-type for compute:{}'.format(compute_dest))
        old_type = host_helper.get_host_instance_backing(compute_dest)

        LOG.tc_step('Lock the host:{} for applying storage-profile'.format(compute_dest))
        HostsToRecover.add(compute_dest, scope='function')
        host_helper.lock_host(compute_dest, fail_ok=False, check_first=True, swact=True)

        LOG.tc_step('Delete the lvg "nova-local" on host:{}'.format(compute_dest))
        cli.system('host-lvg-delete {} nova-local'.format(compute_dest), fail_ok=False)

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(profile, compute_dest))
        cli.system('host-apply-storprofile {} {}'.format(compute_dest, profile), fail_ok=False)

        self._add_to_cleanup_list(to_cleanup=(compute_dest, old_type, ls_type), cleanup_type='local_storage_type')
        return 0, "Storage profile applied successfully"

    def create_storage_profile(self, host, ls_type='image'):
        prof_name = 'storprof_{}{}_{}_{}'.format(host[0], host[-1],
                                                 ls_type, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
        prof_uuid = system_helper.create_storage_profile(host, profile_name=prof_name)

        self._add_to_cleanup_list(to_cleanup=prof_uuid, cleanup_type='profile')

        return prof_uuid

    def set_local_storage_backing(self, compute, to_type='image'):
        LOG.debug('lock compute:{} in order to change to new local-storage-type:{}'.format(compute, to_type))
        HostsToRecover.add(compute, scope='function')
        host_helper.lock_host(compute, check_first=True, swact=True)

        LOG.debug('get the original local-storage-backing-type for compute:{}'.format(compute))
        old_type = host_helper.get_host_instance_backing(compute)

        LOG.info("Modify {} local storage to {}".format(compute, to_type))
        cmd = 'host-lvg-modify -b {} {} nova-local'.format(to_type, compute)
        cli.system(cmd, fail_ok=False)
        self._add_to_cleanup_list(to_cleanup=(compute, old_type, to_type), cleanup_type='local_storage_type')

        LOG.debug('unlock {} now'.format(compute))
        host_helper.unlock_host(compute)

    def _choose_compute_unlocked_diff_type(self, ls_type='image'):
        computes_unlocked_diff_type = [c for c in
                                       host_helper.get_up_hypervisors()
                                       if not host_helper.is_host_with_instance_backing(c, storage_type=ls_type)]

        if computes_unlocked_diff_type:
            return random.choice(computes_unlocked_diff_type)

        return ''

    def _get_computes_unlocked_same_type(self, ls_type='image'):
        computes_unlocked = [c for c in host_helper.get_up_hypervisors()
                             if host_helper.is_host_with_instance_backing(c, storage_type=ls_type)]

        return computes_unlocked

    def select_target_compute(self, host_exclude='', ls_type='image'):

        old_active_controller = system_helper.get_active_controller_name()

        # otherwise chose one compute from unlocked and of different local-storage-type to apply storage-profile
        LOG.debug('Looking for unlocked computes with different local-storage-type')
        compute_dest = self._choose_compute_unlocked_diff_type(ls_type=ls_type)
        if compute_dest:
            LOG.debug('got target compute:{}, unlocked, diff local-storage-type'.format(compute_dest))
            return compute_dest

        LOG.debug('-no unlocked computes with different local-storage-type')

        LOG.debug('Looking for compute unlocked with same local-storage-type')
        candidates = self._get_computes_unlocked_same_type(ls_type=ls_type)
        if host_exclude and host_exclude in candidates:
            candidates.remove(host_exclude)

        if candidates:
            LOG.debug('got target compute:{}, unlocked, same local-storage-type'.format(compute_dest))
            return candidates[0]

        LOG.warn('Cannot find a target compute!?')
        return ''

    def create_storage_profile_of_type(self, host, ls_type):
        LOG.info('From {} create a local-storage profile of backing type:{}'.format(host, ls_type))
        prof_uuid = self.create_storage_profile(host, ls_type=ls_type)

        return prof_uuid

    def _get_local_storage_disk_sizes(self):
        host_pv_sizes = {}
        for host in host_helper.get_hypervisors():
            host_pv_sizes[host] = local_storage_helper.get_host_lvg_disk_size(host=host, lvg_name='nova-local')

        return host_pv_sizes

    # Obsolete following test due to feature already covered in test_storage_profiles.py.
    def _test_local_storage_operations(self, setup_local_storage, ensure_two_hypervisors, ensure_multiple_disks):
        """
        Args:
            setup_local_storage: test fixture to configure storage backing for selected host
            ensure_two_hypervisors
            ensure_multiple_disks

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
                    35.  Local Storage Profile Create/Apply/Delete – Remote
                    36.  Local Storage Profile Apply (Local Image ↔ Remote)
        """
        local_storage_type, compute_src = setup_local_storage
        LOG.tc_step('Create a storage-profile with the expected type of local-storage backing:{}'
                    .format(local_storage_type))
        prof_uuid = self.create_storage_profile_of_type(host=compute_src, ls_type=local_storage_type)
        assert prof_uuid, 'Faild to create storage-profile for local-storage-type:{}'.format(local_storage_type)

        LOG.tc_step('NEG TC: Attempt to apply the storage profile on an unlocked compute, expecting to fail')
        try:
            compute_unlocked = random.choice(host_helper.get_up_hypervisors())
        except IndexError:
            skip('No unlocked computes to create storage-profile from')

        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_unlocked, prof_uuid),
                                      fail_ok=True, rtn_list=True)
        assert 0 != rtn_code, 'Should fail to apply storage-profile:{} to unlocked host:{}' \
            .format(prof_uuid, compute_unlocked)

        computes_list = system_helper.get_computes()
        computes_list.remove(compute_src)

        found_match = False
        for compute_dest in computes_list:
            LOG.info("Checking compute {} is compatible with {}".format(compute_dest, compute_src))
            if not local_storage_helper.is_storprof_applicable_to(host=compute_dest, profile=prof_uuid):
                msg = 'storage-profile:{} is not applicable to compute:{}'.format(prof_uuid, compute_dest)
                LOG.info(msg)
            else:
                found_match = True
                msg = 'Found compute with applicable hardware: {}'.format(compute_dest)
                LOG.info(msg)
                break

        if not found_match:
            skip("No compute found with matching hardware")

        con_ssh = ControllerClient.get_active_controller()

        # Change storage backing if needed
        if compute_dest in host_helper.get_hosts_in_storage_backing(local_storage_type, con_ssh=con_ssh, up_only=False):
            backends = ['image', 'remote']
            backends.remove(local_storage_type)
            host_helper.modify_host_lvg(compute_dest, inst_backing=backends[0])

        host_helper.lock_host(compute_dest)

        LOG.tc_step('Apply the storage-profile:{} onto host:{}'.format(prof_uuid, compute_dest))
        rtn_code, output = self.apply_storage_profile(compute_dest, ls_type=local_storage_type, profile=prof_uuid)
        assert 0 == rtn_code, 'Failed to apply the storage-profile {} onto {}'.format(prof_uuid, compute_dest)

        LOG.tc_step('Check if the changes take effect after unlocking')
        host_helper.unlock_host(compute_dest)

        LOG.tc_step('Verify the local-storage type changed to {} on host:{}' .format(local_storage_type, compute_dest))
        assert host_helper.is_host_with_instance_backing(compute_dest, storage_type=local_storage_type), \
            'Local-storage backing failed to change to {} on host:{}'.format(local_storage_type, compute_dest)

    # Obsolete following test due to feature already covered in test_storage_profiles.py.
    def _test_apply_profile_to_smaller_sized_host(self, setup_local_storage, ensure_two_hypervisors):
        """

        Args:
            setup_local_storage: test fixture to configure storage backing for selected host
            ensure_two_hypervisors: test fixture to skip tests when less than two hypervisors available

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
                        – Remote profile
                    38.  Local Storage Profile Negative Test (Different Devices) – Local_Image profile
        """
        local_storage_type, compute_src = setup_local_storage

        host_ls_sizes = self._get_local_storage_disk_sizes()
        sizes = [size for _, size in host_ls_sizes.items()]
        LOG.tc_step('Check if all the sizes of physical-volumes are the same')
        if len(set(sizes)) <= 1:
            msg = 'Skip the test cases, because all sizes of physical-volumes are the same'
            skip(msg)

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
            if host != compute_with_max and 0 < size < size_max:
                other_computes.append(host)
        assert other_computes, 'Cannot find one compute with the disk size:{} other than'.\
            format(size_max, compute_with_max)

        compute_dest = random.choice(other_computes)
        LOG.tc_step('Attempt to apply storage-profile from {} to {}'.format(compute_with_max, compute_dest))

        HostsToRecover.add(compute_dest, scope='function')
        host_helper.lock_host(compute_dest, check_first=True, swact=True)

        rtn_code, output = cli.system('host-apply-storprofile {} {}'.format(compute_dest, profile_uuid),
                                      fail_ok=True, rtn_list=True)

        LOG.tc_step('Verify the CLI failed as expected')
        assert rtn_code == 1, 'Fail, expect to fail with return code==1, but got return code:{}, msg:{}'. \
            format(rtn_code, output)

    def get_remote_storprofile_file(self, local_storage_type='image'):
        remote_file = os.path.join(WRSROOT_HOME, '{}_storage_profile_to_import.xml'.format(local_storage_type))

        return remote_file

    def get_local_storprfoile_file(self, local_storage_type='image'):
        file_path = os.path.join(os.path.expanduser('~'), LocalStorage.DIR_PROFILE,
                                 '{}_storage_profile_to_import.xml'.format(local_storage_type))
        if os.path.isfile(file_path):
            return file_path
        return ''

    def import_storprofile_profile(self, profile_file=None):
        rtn_code, msg = cli.system('profile-import {}'.format(profile_file), rtn_list=True)
        LOG.info('rtn:{}, msg:{}'.format(rtn_code, msg))
        return rtn_code, msg

    def existing_storprofile_names(self, existing_storprofiles=None):
        existing_names = [(existing_storprofiles[type_][uuid]['name'], type_)
                          for type_ in existing_storprofiles.keys() for uuid in existing_storprofiles[type_].keys()]
        return existing_names

    def verify_storprofile_existing(self, file_name='', existing_profiles=None):
        existing_names = self.existing_storprofile_names(existing_profiles)

        return file_name in [name for name, type_ in existing_names]

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
                        LOG.error('storprofile {} does not exist but still been rejected to import'.
                                  format(failed_profile_name))
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

    def compare_stor_disks(self, xml_disks, impt_disks):
        for disk in xml_disks:
            dev = disk['node']
            func = disk['volumeFunc']
            size = disk['size']
            impt_size, impt_func = impt_disks[dev]
            if size != impt_size:
                LOG.info('mismatched size for XML:{} vs imported:{} for dev:{}'.format(size, impt_size, dev))
                return False

            if func != impt_func:
                LOG.info('mismatched volume-function for XML:{} vs imported:{} for dev:{}'.format(func, impt_func, dev))
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
            LOG.info('storage-type imported:{} IS NOT "storage"'.format(impt_sprofile['name']))
            return False

        if not self.compare_stor_disks(xml_sprofile['disk'], impt_sprofile['disk_stor_conf']):
            LOG.info('disk setting does not match')

        return True

    def compare_ls_disks(self, xml_disks, imt_disks):
        for kv in xml_disks:
            size = kv['size']
            node = kv['node']
            if size != imt_disks[node]:
                LOG.info('mismatched lvg disk size, in XML:{} vs imported:{} for dev:{}'
                         .format(size, imt_disks[node], node))
                return False
        return True

    def compare_ls_lvginfo(self, xml_lvginfo, imt_lvginfo):
        xmllvg = xml_lvginfo[0]
        for key in xmllvg.keys():
            if xmllvg[key] != imt_lvginfo[key]:
                LOG.info('mismatched lvg setting, in XML:{} vs imported:{}'
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
                                                     post_import_storprofiles['storage']), \
                'Improted storage-profiles MISMATCH XML profile'

        assert 0 == self.compare_local_storage_profile(xml_profiles['localstorageProfile'],
                                                       post_import_storprofiles['localstorage']),\
            'Improted local-storage-profiles MISMATCH XML profile'
        return 0

    def verify_storage_profile_imported(self, profile='', msg_import='', pre_import_storprofiles=None):

        from_xml_profile = local_storage_helper.parse_storprofiles_from_xml(xml_file=profile)

        assert 0 == self.check_warn_msg(msg_import=msg_import, existing_profiles=pre_import_storprofiles),\
            'Incorrect CLI messages'

        assert 0 == self.check_imported_storprofiles(xml_profiles=from_xml_profile),\
            'Imported storage-profiles do not match settings from XML file'

        return 0

    def test_import_storage_profile(self, setup_local_storage):
        """
        Args:
            setup_local_storage(str): type of local-storage backing, allowed values: image, remote

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

        local_storage_type, compute_src = setup_local_storage
        
        if not system_helper.is_storage_system():
            skip("This test requires a storage system")

        LOG.tc_step('Get the name of the profile and check if it is existing')
        local_file = self.get_local_storprfoile_file(local_storage_type=local_storage_type)
        if not local_file:
            msg = 'Cannot find the profile:{}'.format(local_file)
            skip(msg)

        LOG.tc_step('Get list of profile names')
        pre_import_storprofiles = local_storage_helper.get_existing_storprofiles()

        LOG.tc_step('Apply the storage-profile via CLI profile-import {}'.format(local_file))
        remote_file = self.get_remote_storprofile_file(local_storage_type=local_storage_type)
        common.scp_from_localhost_to_active_controller(local_file, remote_file)

        rtn_code, output = self.import_storprofile_profile(profile_file=remote_file)
        assert 0 == rtn_code, 'Failed to import storage-profile'.format(remote_file)

        LOG.tc_step('Check if the storage profile are correctly imported into the system')
        assert 0 == self.verify_storage_profile_imported(profile=local_file, msg_import=output,
                                                         pre_import_storprofiles=pre_import_storprofiles)
