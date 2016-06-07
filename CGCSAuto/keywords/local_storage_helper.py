from utils import cli, table_parser
from utils.tis_log import LOG
from keywords import host_helper


def get_storprof_diskconfig(profile=None, con_ssh=None):
    if not profile:
        return '', 0
    table = table_parser.table(cli.system('storprofile-show {}'.format(profile), ssh_client=con_ssh))
    disk, size = (table_parser.get_value_two_col_table(table, 'diskconfig', strict=True, regex=False)).split(':')

    return disk.strip(), int(size.strip())


def is_storprof_applicable_to(host=None, profile=None, con_ssh=None):
    profile_disk, profile_size = get_storprof_diskconfig(profile=profile, con_ssh=con_ssh)
    if not profile_disk or not profile_size:
        return False

    host_disk_size = get_host_disk_size(host=host, disk=profile_disk, con_ssh=con_ssh)

    return int(host_disk_size) >= profile_size


def get_pv_of_lvg(host=None, lvg_name='nova-local', con_ssh=None):
    if not host:
        return {}

    cmd = 'host-pv-list {}'.format(host)
    table = table_parser.table(cli.system(cmd, ssh_client=con_ssh))
    pv_uuid = table_parser.get_values(table, 'UUID', lvm_vg_name=lvg_name, strict=True)[0]
    lvm_pv_name = table_parser.get_values(table, 'lvm_pv_name', lvm_vg_name=lvg_name, strict=True)[0]
    idisk_uuid = table_parser.get_values(table, 'idisk_uuid', lvm_vg_name=lvg_name, strict=True)[0]
    idisk_device_node = table_parser.get_values(table, 'idisk_device_node', lvm_vg_name=lvg_name, strict=True)[0]

    LOG.info('pv_uuid={}, lvm_pv_name={}, idisk_uuid={}, idisk_device_node={}'\
             .format(pv_uuid, lvm_pv_name, idisk_uuid, idisk_device_node))

    return {'pv_uuid':pv_uuid,
            'lvm_pv_name':lvm_pv_name,
            'idisk_uuid':idisk_uuid,
            'idisk_device_node':idisk_device_node}


def get_host_disk_size(host=None, disk=None, con_ssh=None):
    if not host or not disk:
        return 0

    table = table_parser.table(cli.system('host-disk-show {} {}'.format(host, disk), ssh_client=con_ssh))
    size_mib = table_parser.get_value_two_col_table(table, 'size_mib')

    return size_mib


def get_host_lvg_disk_size(host=None, lvg_name='nova-local', con_ssh=None):
    pv_info = get_pv_of_lvg(host=host, lvg_name=lvg_name, con_ssh=con_ssh)
    if not pv_info:
        return 0

    return get_host_disk_size(host=host, disk=pv_info['idisk_uuid'], con_ssh=con_ssh)
