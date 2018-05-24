
import re
from utils import cli, table_parser
from utils.tis_log import LOG
from xml.etree import ElementTree as ET


from consts.cgcs import LocalStorage


def get_storprof_diskconfig(profile=None, con_ssh=None):
    if not profile:
        return '', 0
    table = table_parser.table(cli.system('storprofile-show {}'.format(profile), ssh_client=con_ssh))

    disk_sizes = {}
    for disk_size in table_parser.get_value_two_col_table(table, 'diskconfig', strict=True, regex=False).split(';'):
        d, s = disk_size.split(': ')
        disk_sizes[d.strip()] = float(s.split('GiB')[0].strip())

    return disk_sizes


def is_storprof_applicable_to(host=None, profile=None, con_ssh=None):
    profile_disk_sizes = get_storprof_diskconfig(profile=profile, con_ssh=con_ssh)

    LOG.info("Profile disk sizes is: {}".format(profile_disk_sizes))

    if not profile_disk_sizes:
        LOG.warn('empty profile disk sizes:{}'.format(profile_disk_sizes))
        return False

    applicable = True
    host_disk_sizes = get_host_disk_sizes(host=host)
    LOG.info("Disk sizes is {} for {}".format(host_disk_sizes, host))
    for disk in profile_disk_sizes.keys():
        if disk not in host_disk_sizes.keys():
            LOG.warn('host does not have disk:{} '.format(host, disk))
            applicable = False
            break
        else:
            profile_disk_size = profile_disk_sizes[disk]
            host_disk_size = host_disk_sizes[disk]
            if host_disk_size < profile_disk_size:
                LOG.info('host disk size:{} is smaller than that of profile'.format(host_disk_size, profile_disk_size))
                applicable = False
                break

    return applicable


def get_pv_of_lvg(host=None, lvg_name='nova-local', con_ssh=None):
    if not host:
        return {}

    cmd = 'host-pv-list {} --nowrap'.format(host)
    table = table_parser.table(cli.system(cmd, ssh_client=con_ssh))
    pv_uuid = table_parser.get_values(table, 'UUID', lvm_vg_name=lvg_name, strict=True)[0]
    lvm_pv_name = table_parser.get_values(table, 'lvm_pv_name', lvm_vg_name=lvg_name, strict=True)[0]
    idisk_uuid = table_parser.get_values(table, 'disk_or_part_uuid', lvm_vg_name=lvg_name, strict=True)[0]
    idisk_device_node = table_parser.get_values(table, 'disk_or_part_device_node', lvm_vg_name=lvg_name, strict=True)[0]
    pv_type = table_parser.get_values(table, 'pv_type', lvm_vg_name=lvg_name, strict=True)[0]

    LOG.debug('pv_uuid={}, lvm_pv_name={}, idisk_uuid={}, idisk_device_node={}, pv_type={}'.
              format(pv_uuid, lvm_pv_name, idisk_uuid, idisk_device_node, pv_type))

    disk_uuid_or_node = idisk_uuid
    if pv_type in ['partition']:
        disk_uuid_or_node = re.sub('\d*$', '', idisk_device_node)

    return {'pv_uuid': pv_uuid,
            'lvm_pv_name': lvm_pv_name,
            'idisk_uuid': disk_uuid_or_node,
            'idisk_device_node': idisk_device_node}


def get_host_disk_sizes(host=None, con_ssh=None):
    if not host:
        return {}

    table = table_parser.table(cli.system('host-disk-list {} --nowrap'.format(host), ssh_client=con_ssh))
    index_device_node = table['headers'].index('device_path')
    index_size_gib = table['headers'].index('size_gib')

    disk_sizes = {}
    for row in table['values']:
        disk_sizes[row[index_device_node].strip()] = float(row[index_size_gib].strip())

    return disk_sizes


def get_host_disks_values(host, rtn_val='size_gib', dev_type=None, serial_id=None, dev_num=None, dev_node=None,
                          size_gib=None, device_path=None, strict=True, con_ssh=None):
    assert host
    filters = {'device_node': dev_node,
               'device_num': dev_num,
               'device_type': dev_type,
               'size_gib': size_gib,
               'serial_id': serial_id,
               'device_path': device_path
               }
    table_ = table_parser.table(cli.system('host-disk-list', '{} --nowrap'.format(host), ssh_client=con_ssh))
    vals = table_parser.get_values(table_, rtn_val, strict=strict, **filters)
    if rtn_val == 'size_gib':
        vals = [float(val) for val in vals]
    elif rtn_val == 'device_num':
        vals = [int(val) for val in vals]

    LOG.info("{} disk {} filtered: {}".format(host, rtn_val, vals))
    return vals


def get_host_disk_size(host=None, disk=None, con_ssh=None):
    if not host or not disk:
        return 0

    table = table_parser.table(cli.system('host-disk-show {} {}'.format(host, disk), ssh_client=con_ssh))
    size_gib = table_parser.get_value_two_col_table(table, 'size_gib')
    if not size_gib:
        return 0

    return float(size_gib)


def get_host_lvg_disk_size(host=None, lvg_name='nova-local', con_ssh=None):
    pv_info = get_pv_of_lvg(host=host, lvg_name=lvg_name, con_ssh=con_ssh)
    if not pv_info:
        return 0

    return get_host_disk_size(host=host, disk=pv_info['idisk_uuid'], con_ssh=con_ssh)


def get_profnms_from_storage_profile(profile_in_xml=None):
    tree = ET.parse(profile_in_xml)

    known_profile_types = LocalStorage.TYPE_STORAGE_PROFILE
    profile_name_types = []
    for elem in tree.getroot():
        if elem.tag in known_profile_types:
            profile_name_types.append((elem.attrib['name'], elem.tag))
    return profile_name_types


def _check_storprof_type(headers_actual, expected_type='storage'):
    headers_storage_type = ['uuid', 'profilename', 'disk config', 'stor config']
    headers_localstorage_type = ['uuid', 'profilename', 'disk config',
                                 'physical volume config', 'logical volume group config']

    if expected_type == 'storage':
        return headers_storage_type == headers_actual
    elif expected_type == 'localstorage':
        return headers_localstorage_type == headers_actual

    return False


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

    table = table_parser.table(cli.system('storprofile-show {}'.format(name_id)))

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


def _get_local_storprofile_settings_todo(table):
    key_header, results = get_dict_from_table(table, key_col='uuid')

    local_profiles = []
    for uuid, _ in results.items():
        local_profiles.append(_get_local_storageprofle_details(uuid))

    return local_profiles


def _get_local_storprofile_settings(table):
    key_header, results = get_dict_from_table(table, key_col='uuid')

    settings = {}
    for uuid, record in results.items():
        profname = record['profilename']
        disks = dict([x.split(':') for x in record['disk config'].split(';')])
        disks = {key.strip():value.strip() for key, value in disks.items()}
        pvs = dict([x.split(':') for x in record['physical volume config'].split(',')])
        pvs = {key.strip():value.strip() for key, value in pvs.items()}
        lvgnm, lvginfo = record['logical volume group config'].split(',')
        lvg = dict([x.split(':') for x in lvginfo.split(';')])
        lvg = {key.strip():value.strip() for key, value in lvg.items()}

        setting = {}
        setting['name'] = profname
        setting['disk'] = disks
        lvg['lvm_vg_name'] = lvgnm
        setting['lvg'] = lvg

        settings[uuid] = setting

    # LOG.info('inuse local storpofile:{}'.format(settings))


    return settings


def get_inuse_storporfile_names(con_ssh=None):
    tables = table_parser.tables(cli.system('storprofile-list --nowrap', ssh_client=con_ssh))
    names = []
    for table in tables:
        names.extend(table_parser.get_values(table, 'profilename'))

    # LOG.debug('exisitng storage-profile names:{}'.format(names))


def get_existing_storprofiles(con_ssh=None):
    tables = table_parser.tables(cli.system('storprofile-list --nowrap', ssh_client=con_ssh))

    cur_profile_settings = {}

    for table in tables:
        headers = table['headers']
        if _check_storprof_type(headers, expected_type='storage'):
            cur_profile_settings['storage'] = _get_storprofile_settings(table)

        elif _check_storprof_type(headers, expected_type='localstorage'):
            cur_profile_settings['localstorage'] = _get_local_storprofile_settings(table)

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

    root = ET.parse(xml_file).getroot()

    for child in root:
        if child.tag not in expected_types:
            continue

        # if child.tag in storprofile:
        #     LOG.warn('{} already exists!'.format(child.tag))
        #     storprofile[child.tag].append(child.attrib)
        # else:
        #     storprofile[child.tag] = [child.attrib]
        #
        values = child.attrib
        for grandchild in child:
            if grandchild.tag in values:
                values[grandchild.tag].append(grandchild.attrib)
            else:
                values[grandchild.tag] = [grandchild.attrib]
        # storprofile[child.tag] = values

        if child.tag in storprofile:
            LOG.warn('{} already exists!'.format(child.tag))
            storprofile[child.tag].append(values)
        else:
            storprofile[child.tag] = [values]


    # LOG.info('xml storage-profile:{}'.format(storprofile))
    return storprofile