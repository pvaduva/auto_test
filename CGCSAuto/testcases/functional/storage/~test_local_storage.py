import os
import re
from xml.etree import ElementTree

from pytest import skip, fixture

from consts.cgcs import LocalStorage
from consts.auth import Tenant
from consts.filepaths import SYSADMIN_HOME

from utils import cli, table_parser
from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover

from keywords import system_helper, host_helper, storage_helper, common


@fixture(scope='module')
def get_target_host():
    host = host_helper.get_up_hypervisors()[0]
    return host


def _get_storage_profile_type(table_):
    headers = table_['headers']
    if 'logical volume group config' in headers:
        return 'localstorage'
    elif 'stor config' in headers:
        return 'storage'


def get_dict_from_table(table, key_col=None):

    results = {}
    headers = table['headers']
    index_key = 0
    try:
        index_key = headers.index(key_col)
    except ValueError:
        pass

    num_cols = len(headers)
    for row in table['values']:
        results[row[index_key].strip()] \
            = {headers[i]: row[i].strip() for i in range(num_cols) if i != index_key}

    return headers[index_key], results


def _get_storprofile_settings(table):
    key_header, results = get_dict_from_table(table, key_col='uuid')

    settings = {}
    for uuid, record in results.items():
        dev_confs = {}
        dev_info = record['disk config'].split(';')
        stor_info = record['stor config'].split(';')
        for i in range(len(dev_info)):
            try:
                dev, size = dev_info[i].split(':')
                stor = stor_info[i]
                if dev.strip():
                    dev_confs[dev.strip()] = [size.strip(), stor.strip()]
            except IndexError:
                pass

        profname = record['profilename']
        settings[uuid] = {'name':profname,
                          'storage_type': 'storage',
                          'disk_stor_conf':dev_confs}

    # LOG.info('inuse storpofile:{}'.format(settings))

    return settings


def _get_local_storageprofle_details(name_id=None):
    if not name_id:
        return {}

    table = table_parser.table(cli.system('storprofile-show {}'.format(name_id))[1])

    lvgsetting = {}

    # FIXME: should be 'profile name', CGTS-4432
    profile_name_header = 'hostname'
    name = table_parser.get_value_two_col_table(table, profile_name_header)
    lvgsetting['name'] = name

    diskconfig = table_parser.get_value_two_col_table(table, 'diskconfig')
    disks = dict([kv.split(':') for kv in diskconfig.split(';')])
    disks = [{k:v} for k,v in disks.items()]
    lvgsetting.update({'disk': disks})

    # pvconfig = table_parser.get_value_two_col_table(table, 'physical volume config')

    lvgconfig = table_parser.get_value_two_col_table(table, 'logical volume group config')
    lvgname = lvgconfig.split(',')[0].strip()
    lvgsetting = {'lvm_vg_name': lvgname}

    lvgbackings = dict([kv.split(':') for kv in lvgconfig.split(',')[1].split(';')])
    lvgsetting.update({k.strip(): v.strip() for k,v in lvgbackings.items()})
    # from xml
    #  'localstorageProfile':
    #      {'lvg': [
    #          {'lvm_vg_name': 'nova-local',
    #           'concurrent_disk_operations': '2',
    #           'instance_backing': 'image'}],
    #          'name': 'with_ceph_image_local_storage_backed',
    #          'disk': [{'size': '228936', 'node': '/dev/sdb'
    #          }]
    #      }
    #  }

    return lvgsetting


def _get_local_storprofile_settings(table):
    key_header, results = get_dict_from_table(table, key_col='uuid')

    settings = {}
    for uuid, record in results.items():
        profname = record['profilename']
        disks = dict([x.split(':') for x in record['disk config'].split(';')])
        disks = {key.strip(): value.strip() for key, value in disks.items()}
        pvs = dict([x.split(':') for x in record['physical volume config'].split(',')])
        pvs = {key.strip():value.strip() for key, value in pvs.items()}
        lvgnm, lvginfo = record['logical volume group config'].split(',')
        lvg = dict([x.split(':') for x in lvginfo.split(';')])
        lvg = {key.strip(): value.strip() for key, value in lvg.items()}

        setting = {}
        setting['name'] = profname
        setting['disk'] = disks
        lvg['lvm_vg_name'] = lvgnm
        setting['lvg'] = lvg

        settings[uuid] = setting

    # LOG.info('inuse local storpofile:{}'.format(settings))


    return settings


def get_storprofiles(con_ssh=None, auth_info=Tenant.get('admin_platform')):
    tables = table_parser.tables(cli.system('storprofile-list --nowrap', ssh_client=con_ssh, auth_info=auth_info)[1])

    cur_profile_settings = {}

    for table in tables:
        stor_type = _get_storage_profile_type(table)
        if stor_type:
            cur_profile_settings[stor_type] = _get_storprofile_settings(table)

    return cur_profile_settings


def parse_storprofiles_from_xml(xml_file=None):
    """

    Args:
        xml_file:

    Returns:
        example result:
            {'storageProfile':[
                 {'disk':
                      [{'node': '/dev/sdb', 'volumeFunc': 'osd', 'size': '228936'},
                       {'node': '/dev/sdc', 'volumeFunc': 'osd', 'size': '228936'}],
                  'name': 'ceph_storage_profile'
                  }],
             'localstorageProfile':
                 {'lvg':
                      [{'lvm_vg_name': 'nova-local', 'concurrent_disk_operations': '2', 'instance_backing': 'image'}],
                  'disk': [{'node': '/dev/sdb', 'size': '228936'}],
                  'name': 'with_ceph_image_local_storage_backed'}
             }

    """
    if not xml_file:
        return {}

    storprofile = {}
    expected_types = ['storageProfile', 'localstorageProfile']
    for type in expected_types:
        storprofile.setdefault(type, [])

    root = ElementTree.parse(xml_file).getroot()

    for child in root:
        if child.tag not in expected_types:
            continue

        values = child.attrib
        for grandchild in child:
            if grandchild.tag in values:
                values[grandchild.tag].append(grandchild.attrib)
            else:
                values[grandchild.tag] = [grandchild.attrib]

        if child.tag in storprofile:
            LOG.warn('{} already exists!'.format(child.tag))
            storprofile[child.tag].append(values)
        else:
            storprofile[child.tag] = [values]

    return storprofile


class TestLocalStorage:
    """test local storage"""

    # DIR_PROFILE_IMPORT_FROM='/home/sysadmin/storage_profiles'

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
                    storage_helper.delete_storage_profile(profile=profiles_created.pop())

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
            host_helper.set_host_storage_backing(host, inst_backing=local_storage, check_first=False)

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

    def get_remote_storprofile_file(self, local_storage_type='image'):
        remote_file = os.path.join(SYSADMIN_HOME, '{}_storage_profile_to_import.xml'.format(local_storage_type))

        return remote_file

    def get_local_storprfoile_file(self, local_storage_type='image'):
        file_path = os.path.join(os.path.expanduser('~'), LocalStorage.DIR_PROFILE,
                                 '{}_storage_profile_to_import.xml'.format(local_storage_type))
        if os.path.isfile(file_path):
            return file_path
        return ''

    def import_storprofile_profile(self, profile_file=None):
        rtn_code, msg = cli.system('profile-import {}'.format(profile_file))
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

    def verify_storage_profile_imported(self, profile='', msg_import='', pre_import_storprofiles=None):

        from_xml_profile = parse_storprofiles_from_xml(xml_file=profile)

        assert 0 == self.check_warn_msg(msg_import=msg_import, existing_profiles=pre_import_storprofiles),\
            'Incorrect CLI messages'

        post_import_storprofiles = get_storprofiles()

        if self.is_storage_node():
            assert 0 == self.compare_storage_profile(from_xml_profile['storageProfile'],
                                                     post_import_storprofiles['storage']), \
                'Improted storage-profiles MISMATCH XML profile'

        impt_prof = None
        pstimt_lsprf = post_import_storprofiles['localstorage']
        for xmlprof in from_xml_profile['localstorageProfile']:
            name = xmlprof['name']
            for uuid in pstimt_lsprf.keys():
                if 'name' in pstimt_lsprf[uuid] and name == pstimt_lsprf[uuid]['name']:
                    impt_prof = pstimt_lsprf[uuid]

            assert impt_prof, 'No imported local-storage profile found with name {}'.format(name)
            assert self.compare_ls_disks(xmlprof['disk'], impt_prof['disk']), \
                'disk setting MISMATCH for local-storage profile:{}'.format(xmlprof['name'])

            assert self.compare_ls_lvginfo(xmlprof['lvg'], impt_prof['lvg']), \
                'lvg setting MISMATCH for local-storage profile:{}'.format(xmlprof['name'])

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
        pre_import_storprofiles = get_storprofiles()

        LOG.tc_step('Apply the storage-profile via CLI profile-import {}'.format(local_file))
        remote_file = self.get_remote_storprofile_file(local_storage_type=local_storage_type)
        common.scp_from_localhost_to_active_controller(local_file, remote_file)

        rtn_code, output = self.import_storprofile_profile(profile_file=remote_file)
        assert 0 == rtn_code, 'Failed to import storage-profile'.format(remote_file)

        LOG.tc_step('Check if the storage profile are correctly imported into the system')
        assert 0 == self.verify_storage_profile_imported(profile=local_file, msg_import=output,
                                                         pre_import_storprofiles=pre_import_storprofiles)
