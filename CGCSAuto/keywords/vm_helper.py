import random
import re
import time
import copy
import math
from contextlib import contextmanager

from pexpect import TIMEOUT as ExpectTimeout

from utils import exceptions, cli, table_parser, multi_thread
from utils.ssh import NATBoxClient, VMSSHClient, ControllerClient, Prompt
from utils.tis_log import LOG

from consts.auth import Tenant, SvcCgcsAuto
from consts.cgcs import VMStatus, UUID, BOOT_FROM_VOLUME, NovaCLIOutput, EXT_IP, InstanceTopology, VifMapping, \
    VMNetworkStr, EventLogID, GuestImages, Networks, FlavorSpec
from consts.filepaths import TiSPath, VMPath, UserData, TestServerPath
from consts.proj_vars import ProjVar
from consts.timeout import VMTimeout, CMDTimeout

from keywords import network_helper, nova_helper, cinder_helper, host_helper, glance_helper, common, system_helper, \
    keystone_helper, vlm_helper, storage_helper
from testfixtures.recover_hosts import HostsToRecover
from testfixtures.fixture_resources import ResourceCleanup


def _set_vm_meta(vm_id, action, meta_data, check_after_set=False, con_ssh=None, fail_ok=False):
    """

    Args:
        vm_id:
        action:
        meta_data:
        check_after_set:
        con_ssh:
        fail_ok:

    Returns:

    """
    if action not in ['set', 'delete']:
        return 1, ''

    if action == 'set':
        args = ' '.join(['"{}"="{}"'.format(k, v) for k, v in meta_data.items()])

    elif action == 'delete':
        args = ' '.join(['"{}"'.format(k) for k in meta_data])

    else:
        LOG.warn('Unknown meta data operation:{}'.format(action))
        return 0, ''

    meta_data_names = list(meta_data.keys())
    command = 'meta {} {}'.format(vm_id, action)

    code, output = cli.nova(command, positional_args=args, fail_ok=fail_ok, rtn_list=True)

    assert 0 == code or fail_ok, \
        'Failed to set meta data to VM:{}, meta data:"{}", output:{}\n'.format(vm_id, meta_data, output)

    if not check_after_set:
        return code, output

    if 0 != code:
        return code, output

    meta_data_set = get_vm_meta_data(vm_id, meta_data_names=meta_data_names, con_ssh=con_ssh, fail_ok=fail_ok)

    if action == 'set':
        all_set = all(k in meta_data_set for k in meta_data)
        all_equal = all_set and \
                    all(v == meta_data_set[k] or int(v) == int(meta_data_set[k]) for k, v in meta_data.items())
        if all_set and all_equal:
            return 0, meta_data_set

        msg = 'Failed to SET meta data, expected:{} actual:{}'.format(meta_data, meta_data_set)

    else:
        if all(k not in meta_data_set for k in meta_data_names):
            return 0, meta_data_set

        msg = 'Failed to DELETE meta data, actual:{}'.format(meta_data_set)

    assert fail_ok, msg
    return 1, output


def get_vm_meta_data(vm_id, meta_data_names=None, con_ssh=None, fail_ok=False):
    if not meta_data_names:
        return {}

    table_ = table_parser.table(cli.nova('show {}'.format(vm_id), ssh_client=con_ssh, fail_ok=False))
    meta_data_set = eval(table_parser.get_value_two_col_table(table_, 'metadata'))

    not_found = [k for k in meta_data_names if k not in meta_data_set]
    if not_found:
        msg = 'No meta data found for keys:{}, found meta datas:{}'.format(not_found, meta_data_set)
        LOG.warn(msg)
        assert fail_ok, msg

    return {k: meta_data_set[k] for k in meta_data_names if k in meta_data_set}


def set_vm_meta_data(vm_id, meta_data, check_after_set=False, con_ssh=None, fail_ok=False):
    return _set_vm_meta(vm_id, 'set', meta_data, check_after_set=check_after_set, con_ssh=con_ssh, fail_ok=fail_ok)


def delete_vm_meta_data(vm_id, meta_data_names, check_after_set=False, con_ssh=None, fail_ok=False):
    meta_data = {k: None for k in meta_data_names}
    return _set_vm_meta(vm_id, 'delete', meta_data, check_after_set=check_after_set, con_ssh=con_ssh, fail_ok=fail_ok)


def get_any_vms(count=None, con_ssh=None, auth_info=None, all_tenants=False, rtn_new=False):
    """
    Get a list of ids of any active vms.

    Args:
        count (int): number of vms ids to return. If None, all vms for specific tenant will be returned. If num of
        existing vm is less than count additional vm will be created to match the count
        con_ssh (SSHClient):
        auth_info (dict):
        all_tenants (bool): whether to get any vms from all tenants or just admin tenant if auth_info is set to Admin
        rtn_new (bool): whether to return an extra list containing only the newly created vms

    Returns (list):
        vms(list)  # rtn_new=False
        [vms(list), new_vms(list)] # rtn_new=True

    """
    vms = nova_helper.get_vms(con_ssh=con_ssh, auth_info=auth_info, all_vms=all_tenants, Status='ACTIVE')
    if count is None:
        if rtn_new:
            vms = [vms, []]
        return vms
    diff = count - len(vms)
    if diff <= 0:
        vms = random.sample(vms, count)
        if rtn_new:
            vms = [vms, []]
        return vms

    new_vms = []
    for i in range(diff):
        new_vm = boot_vm(con_ssh=con_ssh, auth_info=auth_info)[1]
        vms.append(new_vm)
        new_vms.append(new_vm)

    if rtn_new:
        vms = [vms, new_vms]
    return vms


def wait_for_vol_attach(vm_id, vol_id, timeout=VMTimeout.VOL_ATTACH, con_ssh=None, auth_info=None):
    end_time = time.time() + timeout
    while time.time() < end_time:
        vols_attached = nova_helper.get_vm_volumes(vm_id=vm_id, con_ssh=con_ssh, auth_info=auth_info)
        if vol_id in vols_attached:
            break
        time.sleep(3)
    else:
        LOG.warning("Volume {} is not shown in nova show {} in {} seconds".format(vol_id, vm_id, timeout))
        return False

    return cinder_helper._wait_for_volume_status(vol_id, status='in-use', timeout=timeout,
                                                  con_ssh=con_ssh, auth_info=auth_info)


def attach_vol_to_vm(vm_id, vol_id=None, con_ssh=None, auth_info=None, mount=True, del_vol=None):
    if vol_id is None:
        vols = cinder_helper.get_volumes(auth_info=auth_info, con_ssh=con_ssh, status='available')
        if vols:
            vol_id = random.choice(vols)
        else:
            vol_id = cinder_helper.create_volume(auth_info=auth_info, con_ssh=con_ssh)[1]
            if del_vol:
                ResourceCleanup.add('volume', vol_id, scope=del_vol)

    LOG.info("Attaching volume {} to vm {}".format(vol_id, vm_id))
    cli.nova('volume-attach', ' '.join([vm_id, vol_id]))

    if not wait_for_vol_attach(vm_id=vm_id, vol_id=vol_id, con_ssh=con_ssh, auth_info=auth_info):
        raise exceptions.VMPostCheckFailed("Volume {} is not attached to vm {} within {} seconds".
                                           format(vol_id, vm_id, VMTimeout.VOL_ATTACH))

    if mount:
        LOG.info("Volume {} is attached to vm {}".format(vol_id, vm_id))
        LOG.info("Checking if the attached Volume {} is not auto mounted".format(vol_id))
        guest = nova_helper.get_vm_image_name(vm_id)
        if guest and 'cgcs_guest' not in guest:
            LOG.info("Attached Volume {} need to be mounted on vm {}".format(vol_id, vm_id))
            attachment_info = cinder_helper.get_volume_attachments(vol_id, vm_id=vm_id)
            if attachment_info:
                attached_device_name = attachment_info[0]['device']
                device = attached_device_name.split('/')[-1]
                LOG.info("Volume {} is attached to VM {} as {}".format(vol_id, vm_id, attached_device_name))
                if not mount_attached_volume(vm_id, device, vm_image_name=guest):
                    LOG.info("Failed to mount the attached Volume {} on VM {} filesystem".format(vol_id, vm_id))
                return

            # for pike cinderclient: there is no 'attachments' field, so have to
            # get attachments from 2 tables.
            attachment_ids = cinder_helper.get_volume_attachment_ids(vol_id, vm_id=vm_id)
            if attachment_ids:
                att_show_table = table_parser.table(
                    cli.cinder('--os-volume-api-version 3.27 attachment-show',
                               attachment_ids[0],
                               auth_info=Tenant.ADMIN))
                attached_device_name = table_parser.get_value_two_col_table(
                    att_show_table, 'device')
                device = attached_device_name.split('/')[-1]
                LOG.info("Volume {} is attached to VM {} as {}".format(
                    vol_id, vm_id, attached_device_name))
                if not mount_attached_volume(vm_id, device, vm_image_name=guest):
                    LOG.info("Failed to mount the attached Volume {} "
                             "on VM {} filesystem".format(vol_id, vm_id))


def is_attached_volume_mounted(vm_id, rootfs, vm_image_name=None, vm_ssh=None):
    """
    Checks if an attached volume is mounted in VM
    Args:
        vm_id (str): - the vm uuid where the volume is attached to
        rootfs (str) - the device name of the attached volume like vda, vdb, vdc, ....
        vm_image_name (str): - the  guest image the vm is booted with
        vm_ssh (VMSSHClient): ssh client session to vm
    Returns: bool

    """

    #wait_for_vm_pingable_from_natbox(vm_id)
    if vm_image_name is None:
        vm_image_name = nova_helper.get_vm_image_name(vm_id)

    cmd = "mount | grep {} |  wc -l".format(rootfs)
    mounted_msg = "Filesystem /dev/{} is mounted: {}".format(rootfs, vm_id)
    not_mount_msg = "Filesystem /dev/{} is not mounted: {}".format(rootfs, vm_id)
    if vm_ssh:
        cmd_output = vm_ssh.exec_sudo_cmd(cmd)[1]
        if cmd_output != '0':
            LOG.info(mounted_msg)
            return True
        LOG.info(not_mount_msg)
        return False

    with ssh_to_vm_from_natbox(vm_id, vm_image_name=vm_image_name) as vm_ssh:

        cmd_output = vm_ssh.exec_sudo_cmd(cmd)[1]
        if cmd_output != '0':
            LOG.info(mounted_msg)
            return True
        LOG.info(not_mount_msg)
        return False


def mount_attached_volume(vm_id, rootfs, vm_image_name=None):
    """
    Mounts an attached volume on VM
    Args:
        vm_id (str): - the vm uuid where the volume is attached to
        rootfs (str) - the device name of the attached volume like vda, vdb, vdc, ....
        vm_image_name (str): - the  guest image the vm is booted with

    Returns: bool

    """
    wait_for_vm_pingable_from_natbox(vm_id)
    if vm_image_name is None:
        vm_image_name = nova_helper.get_vm_image_name(vm_id)

    with ssh_to_vm_from_natbox(vm_id, vm_image_name=vm_image_name) as vm_ssh:

        if not is_attached_volume_mounted(vm_id, rootfs, vm_image_name=vm_image_name, vm_ssh=vm_ssh):
            LOG.info("Creating ext4 file system on /dev/{} ".format(rootfs))
            cmd = "mkfs -t ext4 /dev/{}".format(rootfs)
            rc, output = vm_ssh.exec_cmd(cmd)
            if rc != 0:
                msg = "Failed to create filesystem on /dev/{}: {}".format(rootfs, output)
                LOG.warning(msg)
                return False
            LOG.info("Mounting /dev/{} to /mnt/volume".format(rootfs))
            cmd = "test -e /mnt/volume"
            rc, output = vm_ssh.exec_cmd(cmd)
            mount_cmd = ''
            if rc == 1:
                mount_cmd += "mkdir -p /mnt/volume; mount /dev/{} /mnt/volume".format(rootfs)
            else:
                mount_cmd += "mount /dev/{} /mnt/volume".format(rootfs)

            rc, output = vm_ssh.exec_cmd(mount_cmd)
            if rc != 0:
                msg = "Failed to mount /dev/{}: {}".format(rootfs, output)
                LOG.warning(msg)
                return False

            LOG.info("Adding /dev/{} mounting point in /etc/fstab".format(rootfs))
            cmd = "echo \"/dev/{} /mnt/volume ext4  defaults 0 0\" >> /etc/fstab".format(rootfs)

            rc, output = vm_ssh.exec_cmd(cmd)
            if rc != 0:
                msg = "Failed to add /dev/{} mount point to /etc/fstab: {}".format(rootfs, output)
                LOG.warning(msg)

            LOG.info("/dev/{} is mounted to /mnt/volume".format(rootfs))
            return True
        else:
            LOG.info("/dev/{} is already mounted to /mnt/volume".format(rootfs))
            return True


def get_vm_devices_via_virsh(vm_id, con_ssh=None):
    """
    Get vm disks in dict format via 'virsh domblklist <instance_name>'
    Args:
        vm_id (str):
        con_ssh:

    Returns (dict): vm disks per type.
    Examples:
    {'root_img': {'vda': '/dev/nova-local/a746beb9-08e4-4b08-af2a-000c8ca72851_disk'},
     'attached_vol': {'vdb': '/dev/disk/by-path/ip-192.168.205.106:3260-iscsi-iqn.2010-10.org.openstack:volume-...'},
     'swap': {},
     'eph': {}}

    """
    vm_host = nova_helper.get_vm_host(vm_id=vm_id, con_ssh=con_ssh)
    inst_name = nova_helper.get_vm_instance_name(vm_id=vm_id,  con_ssh=con_ssh)

    with host_helper.ssh_to_host(vm_host, con_ssh=con_ssh) as host_ssh:
        output = host_ssh.exec_sudo_cmd('virsh domblklist {}'.format(inst_name), fail_ok=False)[1]
        disk_lines = output.split('-------------------------------\n', 1)[-1].splitlines()

        disks = {}
        root_line = disk_lines.pop(0)
        root_dev, root_source = root_line.split()
        if re.search('openstack:volume|cinder-volumes', root_source):
            disk_type = 'root_vol'
        else:
            disk_type = 'root_img'
        disks[disk_type] = {root_dev: root_source}
        LOG.info("Root disk: {}".format(disks))

        disks.update({'eph': {}, 'swap': {}, 'attached_vol': {}})
        for line in disk_lines:
            dev, source = line.split()
            if re.search('disk.swap', source):
                disk_type = 'swap'
            elif re.search('openstack:volume', source):
                disk_type = 'attached_vol'
            elif re.search('disk.eph|disk.local', source):
                disk_type = 'eph'
            else:
                raise exceptions.CommonError("Unknown disk in virsh: {}. Automation update required.".format(line))
            disks[disk_type][dev] = source

    LOG.info("disks for vm {}: {}".format(vm_id, disks))
    return disks


def get_vm_boot_volume_via_virsh(vm_id, con_ssh=None):
    """
    Get cinder volume id where the vm is booted from via virsh cmd.
    Args:
        vm_id (str):
        con_ssh (SSHClient):

    Returns (str|None): vol_id or None if vm is not booted from cinder volume

    """
    disks = get_vm_devices_via_virsh(vm_id=vm_id, con_ssh=con_ssh)
    root_vol = disks.get('root_vol', {})
    if not root_vol:
        LOG.info("VM is not booted from volume. Return None")
        return

    root_vol = list(root_vol.values())[0]
    root_vol = re.findall('openstack:volume-(.*)-lun', root_vol)[0]
    LOG.info("vm {} is booted from cinder volume {}".format(vm_id, root_vol))
    return root_vol


def auto_mount_vm_devices(vm_id, devices, guest_os=None, check_first=True, vm_ssh=None):
    """
    Mount and auto mount devices on vm
    Args:
        vm_id (str): - the vm uuid where the volume is attached to
        devices (str|list) - the device name(s). such as vdc or [vda, vdb]
        guest_os (str): - the guest image the vm is booted with. such as tis-centos-guest
        check_first (bool): where to check if the device is already mounted and auto mounted before mount and automount
        vm_ssh (VMSSHClient):
    """
    if isinstance(devices, str):
        devices = [devices]

    def _auto_mount(vm_ssh_):
        _mounts = []
        for disk in devices:
            fs = '/dev/{}'.format(disk)
            mount_on, fs_type = storage_helper.mount_partition(ssh_client=vm_ssh_, disk=disk, partition=fs)
            storage_helper.auto_mount_fs(ssh_client=vm_ssh_, fs=fs, mount_on=mount_on, fs_type=fs_type,
                                         check_first=check_first)
            _mounts.append(mount_on)
        return _mounts

    if vm_ssh:
        mounts = _auto_mount(vm_ssh_=vm_ssh)
    else:
        with ssh_to_vm_from_natbox(vm_id, vm_image_name=guest_os) as vm_ssh:
            mounts = _auto_mount(vm_ssh_=vm_ssh)

    return mounts


def touch_files(vm_id, file_dirs, file_name=None, content=None, guest_os=None):
    """
    touch files from vm in specified dirs,and adds same content to all touched files.
    Args:
        vm_id (str):
        file_dirs (list): e.g., ['/', '/mnt/vdb']
        file_name (str|None): defaults to 'test_file.txt' if set to None
        content (str|None): defaults to "I'm a test file" if set to None
        guest_os (str|None): default guest assumed to set to None

    Returns (tuple): (<file_paths_for_touched_files>, <file_content>)

    """
    if not file_name:
        file_name = 'test_file.txt'
    if not content:
        content = "I'm a test file"

    if isinstance(file_dirs, str):
        file_dirs = [file_dirs]
    file_paths = []
    with ssh_to_vm_from_natbox(vm_id=vm_id, vm_image_name=guest_os) as vm_ssh:
        for file_dir in file_dirs:
            file_path = "{}/{}".format(file_dir, file_name)
            file_path = file_path.replace('//', '/')
            vm_ssh.exec_sudo_cmd('mkdir -p {}; touch {}'.format(file_dir, file_path), fail_ok=False)
            time.sleep(3)
            vm_ssh.exec_sudo_cmd('echo "{}" >> {}'.format(content, file_path), fail_ok=False)
            output = vm_ssh.exec_sudo_cmd('cat {}'.format(file_path), fail_ok=False)[1]
            # TO DELETE: Debugging purpose only
            vm_ssh.exec_sudo_cmd('mount | grep vd')
            assert content in output, "Expected content {} is not in {}. Actual content: {}".\
                format(content, file_path, output)
            file_paths.append(file_path)

        vm_ssh.exec_sudo_cmd('sync')
    return file_paths, content


def auto_mount_vm_disks(vm_id, disks=None, guest_os=None):
    """
    Auto mount non-root vm disks and return all the mount points including root dir
    Args:
        vm_id (str):
        disks (dict|None): disks returned by  get_vm_devices_via_virsh()
        guest_os (str|None): when None, default guest is assumed.

    Returns (list): list of mount points. e.g., ['/', '/mnt/vdb']

    """
    if not disks:
        disks_to_check = get_vm_devices_via_virsh(vm_id=vm_id)
    else:
        disks_to_check = copy.deepcopy(disks)

    root_disk = disks_to_check.pop('root_vol', {})
    if not root_disk:
        disks_to_check.pop('root_img')

    # add root dir
    mounted_on = ['/']
    devs_to_mount = []
    for val in disks_to_check.values():
        devs_to_mount += list(val.keys())

    LOG.info("Devices to mount: {}".format(devs_to_mount))
    if devs_to_mount:
        mounted_on += auto_mount_vm_devices(vm_id=vm_id, devices=devs_to_mount, guest_os=guest_os)
    else:
        LOG.info("No non-root disks to mount for vm {}".format(vm_id))

    return mounted_on


def boot_vm(name=None, flavor=None, source=None, source_id=None, min_count=None, nics=None, hint=None,
            max_count=None, key_name=None, swap=None, ephemeral=None, user_data=None, block_device=None,
            block_device_mapping=None,  vm_host=None, avail_zone=None, file=None, config_drive=False, meta=None,
            fail_ok=False, auth_info=None, con_ssh=None, reuse_vol=False, guest_os='', poll=True, cleanup=None):
    """
    Boot a vm with given parameters
    Args:
        name (str):
        flavor (str):
        source (str): 'image', 'volume', or 'snapshot'
        source_id (str): id of the specified source. such as volume_id, image_id, or snapshot_id
        min_count (int):
        max_count (int):
        key_name (str):
        swap (int|None):
        ephemeral (int):
        user_data (str|list):
        vm_host (str): which host to place the vm
        avail_zone (str): availability zone for vm host, Possible values: 'nova', 'cgcsauto', etc
        block_device:
        block_device_mapping (str):  Block device mapping in the format '<dev-name>=<id>:<type>:<size(GB)>:<delete-on-
                                terminate>'.
        auth_info (dict):
        con_ssh (SSHClient):
        nics (list): nics to be created for the vm
            each nic: <net-id=net-uuid,net-name=network-name,v4-fixed-ip=ip-addr,v6-fixed-ip=ip-addr,
                        port-id=port-uuid,vif-model=model>,vif-pci-address=pci-address>
            Examples: [{'net-id': <net_id1>, 'vif-model': <vif1>}, {'net-id': <net_id2>, 'vif-model': <vif2>}, ...]
            Notes: valid vif-models:
                virtio, avp, e1000, pci-passthrough, pci-sriov, rtl8139, ne2k_pci, pcnet

        hint (dict): key/value pair(s) sent to scheduler for custom use. such as group=<server_group_id>
        file (str): <dst-path=src-path> To store files from local <src-path> to <dst-path> on the new server.
        config_drive (bool): To enable config drive.
        meta (dict): key/value pairs for vm meta data. e.g., {'sw:wrs:recovery_priority': 1, ...}
        fail_ok (bool):
        reuse_vol (bool): whether or not to reuse the existing volume
        guest_os (str): Valid values: 'cgcs-guest', 'ubuntu_14', 'centos_6', 'centos_7', etc
        poll (bool):
        cleanup (str|None): valid values: 'module', 'session', 'function', 'class', vm (and volume) will be deleted as
            part of teardown

    Returns (tuple): (rtn_code(int), new_vm_id_if_any(str), message(str), new_vol_id_if_any(str))
        (0, vm_id, 'VM is booted successfully', <new_vol_id>)   # vm is created successfully and in Active state.
        (1, vm_id, <stderr>, <new_vol_id_if_any>)      # boot vm cli command failed, but vm is still booted
        (2, vm_id, "VM building is not 100% complete.", <new_vol_id>)   # boot vm cli accepted, but vm building is not
            100% completed. Only applicable when poll=True
        (3, vm_id, "VM <uuid> did not reach ACTIVE state within <seconds>. VM status: <status>", <new_vol_id>)
            # vm is not in Active state after created.
        (4, '', <stderr>, <new_vol_id>): create vm cli command failed, vm is not booted

    """
    if cleanup is not None:
        if cleanup not in ['module', 'session', 'function', 'class']:
            raise ValueError("Invalid scope provided. Choose from: 'module', 'session', 'function', 'class', None")

    LOG.info("Processing boot_vm args...")
    # Handle mandatory arg - name
    tenant = common.get_tenant_name(auth_info=auth_info)
    if name is None:
        name = 'vm'
    name = "{}-{}".format(tenant, name)

    name = common.get_unique_name(name, resource_type='vm')

    # Handle mandatory arg - flavor
    if flavor is None:
        flavor = nova_helper.get_basic_flavor(auth_info=auth_info, con_ssh=con_ssh, guest_os=guest_os)

    if guest_os == 'vxworks':
        LOG.tc_step("Add HPET Timer extra spec to flavor")
        extra_specs = {FlavorSpec.HPET_TIMER: 'True'}
        nova_helper.set_flavor_extra_specs(flavor=flavor, **extra_specs)

    # Handle mandatory arg - nics
    if not nics:
        vif_model = 'virtio'
        if guest_os == 'vxworks':
            vif_model = 'e1000'
        mgmt_net_id = network_helper.get_mgmt_net_id(auth_info=auth_info, con_ssh=con_ssh)
        if not mgmt_net_id:
            raise exceptions.NeutronError("Cannot find management network")
        nics = [{'net-id': mgmt_net_id, 'vif-model': vif_model}]

        if 'edge' not in guest_os and 'vxworks' not in guest_os:
            tenant_net_id = network_helper.get_tenant_net_id(auth_info=auth_info, con_ssh=con_ssh)
            # tenant_vif = random.choice(['virtio', 'avp'])
            if tenant_net_id:
                nics.append({'net-id': tenant_net_id, 'vif-model': 'virtio'})
    
    if isinstance(nics, dict):
        nics = [nics]

    possible_keys = ['net-id', 'v4-fixed-ip', 'v6-fixed-ip', 'port-id', 'vif-model', 'vif-pci-address']
    nics_args_list = []

    for nic in nics:
        nic_args_list = []

        for key, val in nic.items():
            key = key.strip().lower()
            val = val.strip().lower()
            if key not in possible_keys:
                raise ValueError("{} is not a valid option. Valid options: {}".format(key, possible_keys))
            nic_arg_val = '='.join([key, val])
            nic_args_list.append(nic_arg_val)

        nic_args = '--nic ' + ','.join(nic_args_list)
        nics_args_list.append(nic_args)

    nics_args = ' '.join(nics_args_list)

    # Handle mandatory arg - boot source id
    volume_id = image = snapshot_id = None
    if source is None:
        if min_count is None and max_count is None:
            source = 'volume'
        else:
            source = 'image'

    new_vol = ''
    if source.lower() == 'volume':
        if source_id:
            volume_id = source_id
        else:
            vol_name = 'vol-' + name
            if reuse_vol:
                is_new, volume_id = cinder_helper.get_any_volume(new_name=vol_name, auth_info=auth_info,
                                                                 con_ssh=con_ssh)
                if is_new:
                    new_vol = volume_id
            else:
                new_vol = volume_id = cinder_helper.create_volume(name=vol_name, auth_info=auth_info, con_ssh=con_ssh,
                                                                  guest_image=guest_os, rtn_exist=False)[1]

    elif source.lower() == 'image':
        img_name = guest_os if guest_os else GuestImages.DEFAULT_GUEST
        image = source_id if source_id else glance_helper.get_image_id_from_name(img_name, strict=True, fail_ok=False)

    elif source.lower() == 'snapshot':
        if not snapshot_id:
            snapshot_id = cinder_helper.get_snapshot_id(auth_info=auth_info, con_ssh=con_ssh)
            if not snapshot_id:
                raise ValueError("snapshot id is required to boot vm; however no snapshot exists on the system.")

    # Handle mandatory arg - key_name
    key_name = key_name if key_name is not None else get_any_keypair(auth_info=auth_info, con_ssh=con_ssh)

    if hint:
        hint = ','.join(["{}={}".format(key, hint[key]) for key in hint])

    host_str = ':{}'.format(vm_host) if vm_host else ''
    host_zone = '{}{}'.format(avail_zone, host_str) if avail_zone else None

    if user_data is None and guest_os and not re.search(GuestImages.TIS_GUEST_PATTERN, guest_os):
        # create userdata cloud init file to run right after vm initialization to get ip on interfaces other than eth0.
        user_data = _create_cloud_init_if_conf(guest_os, nics_num=len(nics))

    # create cmd
    optional_args_dict = {'--flavor': flavor,
                          '--image': image,
                          '--boot-volume': volume_id,
                          '--snapshot': snapshot_id,
                          '--min-count': str(min_count) if min_count is not None else None,
                          '--max-count': str(max_count) if max_count is not None else None,
                          '--key-name': key_name,
                          '--swap': swap,
                          '--user-data': user_data,
                          '--ephemeral': ephemeral,
                          '--block-device': block_device,
                          '--hint': hint,
                          '--availability-zone': host_zone,
                          '--file': file,
                          '--config-drive': str(config_drive) if config_drive else None,
                          }

    args_ = ' '.join([__compose_args(optional_args_dict), nics_args, name])

    if meta:
        meta_args = [' --meta {}={}'.format(key_, val_) for key_, val_ in meta.items()]
        args_ += ''.join(meta_args)
    
    if poll:
        args_ += ' --poll'

    if not (min_count is None and max_count is None):
        name_str = name + '-'
        pre_boot_vms = nova_helper.get_vms(auth_info=auth_info, con_ssh=con_ssh, strict=False, name=name_str)

    if cleanup and new_vol:
        ResourceCleanup.add('volume', new_vol, scope=cleanup)

    LOG.info("Booting VM {}...".format(name))
    LOG.info("nova boot {}".format(args_))
    exitcode, output = cli.nova('boot', positional_args=args_, ssh_client=con_ssh,
                                fail_ok=True, rtn_list=True, timeout=VMTimeout.BOOT_VM, auth_info=auth_info)

    tmout = VMTimeout.STATUS_CHANGE
    if min_count is None and max_count is None:
        table_ = table_parser.table(output)
        vm_id = table_parser.get_value_two_col_table(table_, 'id')
        if cleanup and vm_id:
            ResourceCleanup.add('vm', vm_id, scope=cleanup, del_vm_vols=False)

        if exitcode == 1:
            if not fail_ok:
                raise exceptions.VMOperationFailed(output)

            if vm_id:
                return 1, vm_id, output, new_vol       # vm_id = '' if cli is rejected without vm created
            return 4, '', output, new_vol     # new_vol = '' if no new volume created. Pass this to test for proper teardown

        LOG.info("Post action check...")
        if poll and "100% complete" not in output:
            message = "VM building is not 100% complete."
            if fail_ok:
                LOG.warning(message)
                return 2, vm_id, "VM building is not 100% complete.", new_vol
            else:
                raise exceptions.VMOperationFailed(message)

        if not _wait_for_vm_status(vm_id=vm_id, status=VMStatus.ACTIVE, timeout=tmout, con_ssh=con_ssh,
                                   auth_info=auth_info, fail_ok=True):
            vm_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh,
                                                           auth_info=auth_info)
            message = "VM {} did not reach ACTIVE state within {}. VM status: {}".format(vm_id, tmout, vm_status)
            if fail_ok:
                LOG.warning(message)
                return 3, vm_id, message, new_vol
            else:
                raise exceptions.VMPostCheckFailed(message)

        LOG.info("VM {} is booted successfully.".format(vm_id))
        return 0, vm_id, 'VM is booted successfully', new_vol

    else:
        name_str = name + '-'
        post_boot_vms = nova_helper.get_vms(auth_info=auth_info, con_ssh=con_ssh, strict=False, name=name_str)
        # tables_ = table_parser.tables(output)
        # vm_ids = []
        # for tab_ in tables_:
        #     vm_id = table_parser.get_value_two_col_table(tab_, 'id')
        #     if vm_id:
        #         vm_ids.append(vm_id)

        vm_ids = list(set(post_boot_vms) - set(pre_boot_vms))
        if cleanup and vm_ids:
            ResourceCleanup.add('vm', vm_ids, scope=cleanup, del_vm_vols=False)

        if exitcode == 1:
            return 1, vm_ids, output

        result, vms_in_state, vms_failed_to_reach_state = wait_for_vms_values(vm_ids, fail_ok=True, timeout=tmout,
                                                                              con_ssh=con_ssh, auth_info=auth_info)
        if not result:
            msg = "VMs failed to reach ACTIVE state: {}".format(vms_failed_to_reach_state)
            if fail_ok:
                LOG.warning(msg=msg)
                return 3, vm_ids, msg

        LOG.info("VMs booted successfully: {}".format(vm_ids))
        return 0, vm_ids, "VMs are booted successfully"


def wait_for_vm_pingable_from_natbox(vm_id, timeout=180, fail_ok=False, con_ssh=None, use_fip=False, wait_login=True):
    """
    Wait for ping vm from natbox succeeds.

    Args:
        vm_id (str): id of the vm to ping
        timeout (int): max retry time for pinging vm
        fail_ok (bool): whether to raise exception if vm cannot be ping'd successfully from natbox within timeout
        con_ssh (SSHClient): TiS server ssh handle
        use_fip (bool): whether or not to ping floating ip only if any

    Returns (bool): True if ping vm succeeded, False otherwise.

    """
    ping_end_time = time.time() + timeout
    while time.time() < ping_end_time:
        if ping_vms_from_natbox(vm_ids=vm_id, fail_ok=True, con_ssh=con_ssh, num_pings=3, use_fip=use_fip)[0]:
            # give it sometime to settle after vm booted and became pingable
            time.sleep(3)
            return True
    else:
        msg = "Ping from NatBox to vm {} failed for {} seconds.".format(vm_id, timeout)
        if fail_ok:
            LOG.warning(msg)
            return False
        else:
            f_path = '{}/{}'.format(ProjVar.get_var('PING_FAILURE_DIR'), ProjVar.get_var('TEST_NAME'))
            common.write_to_file(f_path, "=================={}===============\n".format(msg))
            ProjVar.set_var(PING_FAILURE=True)
            get_console_logs(vm_ids=vm_id, sep_file=f_path)
            network_helper.collect_networking_info(vms=vm_id, sep_file=f_path)
            raise exceptions.VMNetworkError(msg)


def __compose_args(optional_args_dict):
    args = []
    for key, val in optional_args_dict.items():
        if val is not None:
            arg = key + ' ' + val
            args.append(arg)
    return ' '.join(args)


def get_any_keypair(auth_info=None, con_ssh=None):
    """
    Get keypair for specific tenant.

    Args:
        auth_info (dict): If None, default tenant will be used.
        con_ssh (SSHClient):

    Returns (str): key name

    """
    if auth_info is None:
        auth_info = Tenant.get_primary()
    tenant = auth_info['tenant']
    table_keypairs = table_parser.table(cli.nova('keypair-list', ssh_client=con_ssh, auth_info=auth_info))
    key_name = 'keypair-' + tenant

    if key_name in table_parser.get_column(table_keypairs, 'Name'):
        LOG.debug("{} already exists. Return existing key.".format(key_name))
    else:
        args_ = '--pub-key /home/wrsroot/.ssh/id_rsa.pub keypair-' + tenant
        table_ = table_parser.table(cli.nova('keypair-add', args_, auth_info=auth_info, ssh_client=con_ssh))
        if key_name not in table_parser.get_column(table_, 'Name'):
            raise exceptions.CLIRejected("Failed to add {}".format(key_name))
        LOG.info("Keypair {} added.".format(key_name))
    return key_name


def get_vm_apps_limit(vm_type='avp', con_ssh=None):
    # TODO: remove ssh after copying all scripts to con1 added to installer
    with host_helper.ssh_to_host('controller-0', con_ssh=con_ssh) as host_ssh:
        vm_limit = host_ssh.exec_cmd("grep --color='never' -r {} lab_setup.conf | cut -d = -f2".
                                     format(VifMapping.VIF_MAP[vm_type]))[1]
    vm_limit = vm_limit.split(sep='|')[0]
    vm_limit = re.findall('(\d+)', vm_limit)

    return int(vm_limit[0]) if vm_limit else 0


def launch_vms_via_script(vm_type='avp', num_vms=1, launch_timeout=120, tenant_name=None, con_ssh=None):
    """
    Launch VM(s) using script(s) generated by lab_setup.

    Note, we'll have to switch to
    controller-0, since that's where the scripts are.

    Args:
        tenant_name (str) - name of tenant to launch VMs as, e.g. tenant1, tenant2.
            If not specified, the primary tenant for the test session will be used.
        vm_type (str): - either avp, virtio or vswitch
        num_vms (int|str): number of vms to launch, or launch all vms with given vif type if 'all' is set
        launch_timeout (int): timeout waiting for vm to be launched via script in seconds.
        con_ssh:

    Returns (list): ids for launched vms. (Either already launched, or launched by this script)

    """
    # vif_mapping = {'vswitch': 'DPDKAPPS',
    #                'avp': 'AVPAPPS',
    #                'virtio': 'VIRTIOAPPS',
    #                'vhost': 'VHOSTAPPS',
    #                'sriov': 'SRIOVAPPS',
    #                'pcipt': 'PCIPTAPPS'
    #                }

    if not tenant_name:
        tenant_name = Tenant.get_primary()['tenant']
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    if not con_ssh.get_hostname() == 'controller-0':
        host_helper.swact_host()

    vm_ids = []
    vm_names = []

    # Get the list of VMs that are already launched on the system by name
    current_vms = nova_helper.get_all_vms(return_val="Name", con_ssh=con_ssh)
    vm_limit = get_vm_apps_limit(vm_type=vm_type)
    if num_vms == 'all':
        num_vms = vm_limit
    elif num_vms > vm_limit:
        num_vms = vm_limit
        LOG.warning("Maximum {} vms is {}. Thus only {} vms will be launched.".format(vm_type, vm_limit, vm_limit))

    # Launch the desired VMs
    for vm_index in range(1, (num_vms + 1)):
        # Construct the name of VM to launch, i.e. tenant1-avp1
        vm_name = "{}-{}{}".format(tenant_name.lower(), vm_type.lower(), vm_index)
        LOG.info("Launching VM {}".format(vm_name))
        vm_names.append(vm_name)

        if vm_name in current_vms:
            vm_id = nova_helper.get_vm_id_from_name(vm_name, con_ssh=con_ssh, fail_ok=False)
            LOG.info("VM {} is already present on the system. Do nothing.".format(vm_name))
        else:
            script = "~/instances_group0/./launch_{}.sh".format(vm_name)
            con_ssh.exec_cmd(script, expect_timeout=launch_timeout, fail_ok=False)   # Up the timeout

            vm_id = nova_helper.get_vm_id_from_name(vm_name, con_ssh=con_ssh)
            if not nova_helper.vm_exists(vm_id, con_ssh):
                raise exceptions.VMPostCheckFailed("VM {} is not detected on the system after launch.".format(vm_name))

            LOG.info("VM {} launched successfully.".format(vm_name))

        vm_ids.append(vm_id)

    return vm_ids


def live_migrate_vm(vm_id, destination_host='', con_ssh=None, block_migrate=None, force=None, fail_ok=False,
                    auth_info=Tenant.ADMIN):
    """

    Args:
        vm_id (str):
        destination_host (str): such as compute-0, compute-1
        con_ssh (SSHClient):
        block_migrate (bool): whether to add '--block-migrate' to command
        force (str): force live migrate
        fail_ok (bool): if fail_ok, return a numerical number to indicate the execution status
                One exception is if the live-migration command exit_code > 1, which indicating the command itself may
                be incorrect. In this case CLICommandFailed exception will be thrown regardless of the fail_ok flag.
        auth_info (dict):

    Returns (tuple): (return_code (int), error_msg_if_migration_rejected (str))
        (0, 'Live migration is successful.'):
            live migration succeeded and post migration checking passed
        (1, <cli stderr>):  # This scenario is changed to host did not change as excepted
            live migration request rejected as expected. e.g., no available destination host,
            or live migrate a vm with block migration
        (2, <cli stderr>): live migration request rejected due to unknown reason.
        (3, 'Post action check failed: VM is in ERROR state.'):
            live migration command executed successfully, but VM is in Error state after migration
        (4, 'Post action check failed: VM is not in original state.'):
            live migration command executed successfully, but VM is not in before-migration-state
        (5, 'Post action check failed: VM host did not change!'):   (this scenario is removed from Newton)
            live migration command executed successfully, but VM is still on the same host after migration
        (6, <cli_stderr>) This happens when vote_note_to_migrate is set for vm, or pci device is used in vm, etc

    For the first two scenarios, results will be returned regardless of the fail_ok flag.
    For scenarios other than the first two, returns are only applicable if fail_ok=True

    Examples:
        1) If a test case is meant to test live migration with a specific flavor which would block the migration, the
        following call can be made:

         return_code, msg = live_migrate_vm(vm_id, fail_ok=True)
         expected_err_str = "your error string"
         assert return_code in [1, 2]
         assert expected_err_str in msg

        2) For a test that needs to live migrate

    """
    optional_arg = ''

    if block_migrate:
        optional_arg += '--block-migrate'

    if force:
        optional_arg += '--force'

    before_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    before_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh,
                                                       auth_info=Tenant.ADMIN)
    if not before_status == VMStatus.ACTIVE:
        LOG.warning("Non-active VM status before live migrate: {}".format(before_status))

    extra_str = ''
    if not destination_host == '':
        extra_str = ' to ' + destination_host
    positional_args = ' '.join([optional_arg.strip(), str(vm_id), destination_host]).strip()
    LOG.info("Live migrating VM {} from {}{} started.".format(vm_id, before_host, extra_str))
    LOG.info("nova live-migration {}".format(positional_args))
    exit_code, output = cli.nova('live-migration', positional_args=positional_args, ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info, rtn_list=True)

    if exit_code == 1:
        return 6, output

    LOG.info("Waiting for VM status change to {} with best effort".format(VMStatus.MIGRATING))
    in_mig_state = _wait_for_vm_status(vm_id, status=VMStatus.MIGRATING, timeout=60)
    if not in_mig_state:
        LOG.warning("VM did not reach {} state after triggering live-migration".format(VMStatus.MIGRATING))

    LOG.info("Waiting for VM status change to original state {}".format(before_status))
    end_time = time.time() + VMTimeout.LIVE_MIGRATE_COMPLETE
    while time.time() < end_time:
        time.sleep(2)
        status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh,
                                                    auth_info=Tenant.ADMIN)
        if status == before_status:
            LOG.info("Live migrate vm {} completed".format(vm_id))
            break
        elif status == VMStatus.ERROR:
            if fail_ok:
                return 3, "Post action check failed: VM is in ERROR state."
            raise exceptions.VMPostCheckFailed(
                "VM {} is in {} state after live migration. Original state before live migration is: {}".
                format(vm_id, VMStatus.ERROR, before_status))
    else:
        if fail_ok:
            return 4, "Post action check failed: VM is not in original state."
        else:
            raise exceptions.TimeoutException(
                "VM {} did not reach original state within {} seconds after live migration".
                format(vm_id, VMTimeout.LIVE_MIGRATE_COMPLETE))

    after_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)

    if before_host == after_host:
        LOG.warning("Live migration of vm {} failed. Checking if this is expected failure...".format(vm_id))
        if _is_live_migration_allowed(vm_id, block_migrate=block_migrate) and \
                (destination_host or get_dest_host_for_live_migrate(vm_id)):
            if fail_ok:
                return 2, "Unknown live migration failure"
            else:
                raise exceptions.VMPostCheckFailed("Unexpected failure of live migration!")
        else:
            LOG.debug("System does not allow live migrating vm {} as expected.".format(vm_id))
            return 1, "Live migration failed as expected"

    LOG.info("VM {} successfully migrated from {} to {}".format(vm_id, before_host, after_host))
    return 0, "Live migration is successful."


def _is_live_migration_allowed(vm_id, con_ssh=None, block_migrate=None):
    vm_info = VMInfo.get_vm_info(vm_id, con_ssh=con_ssh)
    storage_backing = vm_info.get_storage_type()
    vm_boot_from = vm_info.boot_info['type']

    if storage_backing == 'local_image':
        if block_migrate and vm_boot_from == 'volume' and not vm_info.has_local_disks():
            LOG.warning("Live block migration is not supported for boot-from-volume vm with local_lvm storage")
            return False
        return True

    elif storage_backing == 'local_lvm':
        if (not block_migrate) and vm_boot_from == 'volume' and not vm_info.has_local_disks():
            return True
        else:
            LOG.warning("Live (block) migration is not supported for local_lvm vm with localdisk")
            return False

    else:
        # remote backend
        if block_migrate:
            LOG.warning("Live block migration is not supported for vm with remote storage")
            return False
        else:
            return True


def get_dest_host_for_live_migrate(vm_id, con_ssh=None):
    """
    Check whether a destination host exists with following criteria:
    Criteria:
        1) host has same storage backing as the vm
        2) host is unlocked
        3) different than current host
    Args:
        vm_id (str):
        con_ssh (SSHClient):

    Returns (str): hostname for the first host found. Or '' if no proper host found
    """
    vm_info = VMInfo.get_vm_info(vm_id, con_ssh=con_ssh)
    vm_storage_backing = vm_info.get_storage_type()
    current_host = vm_info.get_host_name()
    candidate_hosts = host_helper.get_hypervisors_with_storage_backing(storage_backing=vm_storage_backing,
                                                                       con_ssh=con_ssh)

    hosts_table_ = table_parser.table(cli.system('host-list'))
    for host in candidate_hosts:
        if not host == current_host:
            host_state = table_parser.get_values(hosts_table_, 'administrative', hostname=host)[0]
            if host_state == 'unlocked':
                LOG.debug("At least one host - {} is available for live migrating vm {}".format(host, vm_id))
                return host

    LOG.warning("No valid host found for live migrating vm {}".format(vm_id))
    return ''


def cold_migrate_vm(vm_id, revert=False, con_ssh=None, fail_ok=False, auth_info=Tenant.ADMIN):
    """

    Args:
        vm_id (str): vm to cold migrate
        revert (bool): False to confirm resize, True to revert
        con_ssh (SSHClient):
        fail_ok (bool): True if fail ok. Default to False, ie., throws exception upon cold migration fail.
        auth_info (dict):

    Returns (tuple): (rtn_code, message)
        (0, success_msg) # Cold migration and confirm/revert succeeded. VM is back to original state or Active state.
        (1, <stderr>) # cold migration cli rejected as expected
        (2, <stderr>) # Cold migration cli command rejected. <stderr> is the err message returned by cli cmd.
        (3, <stdout>) # Cold migration cli accepted, but not finished. <stdout> is the output of cli cmd.
        (4, timeout_message] # Cold migration command ran successfully, but timed out waiting for VM to reach
            'Verify Resize' state or Error state.
        (5, err_msg) # Cold migration command ran successfully, but VM is in Error state.
        (6, err_msg) # Cold migration command ran successfully, and resize confirm/revert performed. But VM is not in
            Active state after confirm/revert.
        (7, err_msg) # Cold migration and resize confirm/revert ran successfully and vm in active state. But host for vm
            is not as expected. i.e., still the same host after confirm resize, or different host after revert resize.
        (8, <stderr>) # Confirm/Revert resize cli rejected

    """
    before_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    before_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh)
    if not before_status == VMStatus.ACTIVE:
        LOG.warning("Non-active VM status before cold migrate: {}".format(before_status))

    LOG.info("Cold migrating VM {} from {}...".format(vm_id, before_host))
    exitcode, output = cli.nova('migrate --poll', vm_id, ssh_client=con_ssh, auth_info=auth_info,
                                timeout=VMTimeout.COLD_MIGRATE_CONFIRM, fail_ok=True, rtn_list=True)

    if exitcode == 1:
        vm_storage_backing = nova_helper.get_vm_storage_type(vm_id=vm_id, con_ssh=con_ssh)
        if len(host_helper.get_hypervisors_with_storage_backing(vm_storage_backing, con_ssh=con_ssh)) < 2:
            LOG.info("Cold migration of vm {} rejected as expected due to no host with valid storage backing to cold "
                     "migrate to.".format(vm_id))
            return 1, output
        elif fail_ok:
            LOG.warning("Cold migration of vm {} is rejected.".format(vm_id))
            return 2, output
        else:
            raise exceptions.VMOperationFailed(output)

    if 'Finished' not in output:
        if fail_ok:
            LOG.warning("Cold migration is not finished.")
            return 3, output
        raise exceptions.VMPostCheckFailed("Failed to cold migrate vm. Output: {}".format(output))

    LOG.info("Waiting for VM status change to {}".format(VMStatus.VERIFY_RESIZE))

    vm_status = _wait_for_vm_status(vm_id=vm_id, status=[VMStatus.VERIFY_RESIZE, VMStatus.ERROR], timeout=300,
                                    fail_ok=fail_ok, con_ssh=con_ssh)

    if vm_status is None:
        return 4, 'Timed out waiting for Error or Verify_Resize status for VM {}'.format(vm_id)

    verify_resize_str = 'Revert' if revert else 'Confirm'
    if vm_status == VMStatus.VERIFY_RESIZE:
        LOG.info("{}ing resize..".format(verify_resize_str))
        res, out = _confirm_or_revert_resize(vm=vm_id, revert=revert, fail_ok=True, con_ssh=con_ssh)
        if res == 1:
            err_msg = "{} resize cli rejected".format(verify_resize_str)
            if fail_ok:
                LOG.warning(err_msg)
                return 8, out
            raise exceptions.VMOperationFailed(err_msg)

    elif vm_status == VMStatus.ERROR:
        err_msg = "VM {} in Error state after cold migrate. {} resize is not reached.".format(vm_id, verify_resize_str)
        if fail_ok:
            return 5, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    post_confirm_state = _wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, timeout=VMTimeout.COLD_MIGRATE_CONFIRM,
                                             fail_ok=fail_ok, con_ssh=con_ssh)

    if post_confirm_state is None:
        err_msg = "VM {} is not in Active state after {} Resize".format(vm_id, verify_resize_str)
        return 6, err_msg

    # Process results
    after_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    host_changed = before_host != after_host
    host_change_str = "changed" if host_changed else "did not change"
    operation_ok = not host_changed if revert else host_changed

    if not operation_ok:
        err_msg = ("VM {} host {} after {} Resize. Before host: {}. After host: {}".
                   format(vm_id, host_change_str, verify_resize_str, before_host, after_host))
        if fail_ok:
            return 7, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    success_msg = "VM {} successfully cold migrated and {}ed Resize.".format(vm_id, verify_resize_str)
    LOG.info(success_msg)
    return 0, success_msg


def resize_vm(vm_id, flavor_id, revert=False, con_ssh=None, fail_ok=False, auth_info=Tenant.ADMIN):
    """
    Resize vm to given flavor

    Args:
        vm_id (str):
        flavor_id (str): flavor to resize to
        revert (bool): True to revert resize, else confirm resize
        con_ssh (SSHClient):
        fail_ok (bool):
        auth_info (dict):

    Returns (tuple): (rtn_code, msg)
        (0, "VM <vm_id> successfully resized and confirmed/reverted.")
        (1, <std_err>)  # resize cli rejected
        (2, "Timed out waiting for Error or Verify_Resize status for VM <vm_id>")
        (3, "VM <vm_id> in Error state after resizing. VERIFY_RESIZE is not reached.")
        (4, "VM <vm_id> is not in Active state after confirm/revert Resize")
        (5, "Flavor is changed after revert resizing.")
        (6, "VM flavor is not changed to expected after resizing.")
    """
    before_flavor = nova_helper.get_vm_flavor(vm_id, con_ssh=con_ssh)
    before_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh)
    if not before_status == VMStatus.ACTIVE:
        LOG.warning("Non-active VM status before cold migrate: {}".format(before_status))

    LOG.info("Resizing VM {} to flavor {}...".format(vm_id, flavor_id))
    exitcode, output = cli.nova('resize --poll', ' '.join([vm_id, flavor_id]), ssh_client=con_ssh, auth_info=auth_info,
                                timeout=VMTimeout.COLD_MIGRATE_CONFIRM, fail_ok=fail_ok, rtn_list=True)
    if exitcode == 1:
        return 1, output

    LOG.info("Waiting for VM status change to {}".format(VMStatus.VERIFY_RESIZE))
    vm_status = _wait_for_vm_status(vm_id=vm_id, status=[VMStatus.VERIFY_RESIZE, VMStatus.ERROR], fail_ok=fail_ok,
                                    timeout=300, con_ssh=con_ssh)

    if vm_status is None:
        err_msg = 'Timed out waiting for Error or Verify_Resize status for VM {}'.format(vm_id)
        LOG.error(err_msg)
        return 2, err_msg

    verify_resize_str = 'Revert' if revert else 'Confirm'
    if vm_status == VMStatus.VERIFY_RESIZE:
        LOG.info("{}ing resize..".format(verify_resize_str))
        _confirm_or_revert_resize(vm=vm_id, revert=revert, con_ssh=con_ssh)

    elif vm_status == VMStatus.ERROR:
        err_msg = "VM {} in Error state after resizing. {} is not reached.".format(vm_id, VMStatus.VERIFY_RESIZE)
        if fail_ok:
            LOG.error(err_msg)
            return 3, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    post_confirm_state = _wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, timeout=VMTimeout.COLD_MIGRATE_CONFIRM,
                                             fail_ok=fail_ok, con_ssh=con_ssh)

    if post_confirm_state is None:
        err_msg = "VM {} is not in Active state after {} Resize".format(vm_id, verify_resize_str)
        LOG.error(err_msg)
        return 4, err_msg

    after_flavor = nova_helper.get_vm_flavor(vm_id)
    if revert and after_flavor != before_flavor:
        err_msg = "Flavor is changed after revert resizing. Before flavor: {}, after flavor: {}".format(
                before_flavor, after_flavor)
        if fail_ok:
            LOG.error(err_msg)
            return 5, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    if not revert and after_flavor != flavor_id:
        err_msg = "VM flavor is not changed to expected after resizing. Before flavor: {}, after flavor: {}".format(
                flavor_id, before_flavor, after_flavor)
        if fail_ok:
            LOG.error(err_msg)
            return 6, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    success_msg = "VM {} successfully resized and {}ed.".format(vm_id, verify_resize_str)
    LOG.info(success_msg)
    return 0, success_msg


def wait_for_vm_values(vm_id, timeout=VMTimeout.STATUS_CHANGE, check_interval=3, fail_ok=True, strict=True,
                       regex=False, con_ssh=None, auth_info=None, **kwargs):
    """
    Wait for vm to reach given states.

    Args:
        vm_id (str): vm id
        timeout (int): in seconds
        check_interval (int): in seconds
        fail_ok (bool): whether to return result or raise exception when vm did not reach expected value(s).
        strict (bool): whether to perform strict search(match) for the value(s)
            For regular string: if True, match the whole string; if False, find any substring match
            For regex: if True, match from start of the value string; if False, search anywhere of the value string
        regex (bool): whether to use regex to find matching value(s)
        con_ssh (SSHClient):
        auth_info (dict):
        **kwargs: field/value pair(s) to identify the waiting criteria.

    Returns (tuple): (result(bool), actual_vals(dict))

    """
    if not kwargs:
        raise ValueError("No field/value pair is passed via kwargs")
    LOG.info("Waiting for vm to reach state(s): {}".format(kwargs))

    fields_to_check = list(kwargs.keys())
    results = {}
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
        for field in fields_to_check:
            expt_vals = kwargs[field]
            actual_val = table_parser.get_value_two_col_table(table_, field)
            results[field] = actual_val
            if not isinstance(expt_vals, list):
                expt_vals = [expt_vals]
            for expt_val in expt_vals:
                if regex:
                    match_found = re.match(expt_val, actual_val) if strict else re.search(expt_val, actual_val)
                else:
                    match_found = expt_val == actual_val if strict else expt_val in actual_val

                if match_found:
                    fields_to_check.remove(field)

                if not fields_to_check:
                    LOG.info("VM has reached states: {}".format(results))
                    return True, results

        time.sleep(check_interval)

    msg = "VM {} did not reach expected states within timeout. Actual state(s): {}".format(vm_id, results)
    if fail_ok:
        LOG.warning(msg)
        return False, results
    else:
        raise exceptions.VMTimeout(msg)


def _wait_for_vm_status(vm_id, status, timeout=VMTimeout.STATUS_CHANGE, check_interval=3, fail_ok=True,
                        con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        vm_id:
        status (list|str):
        timeout:
        check_interval:
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns: The Status of the vm_id depend on what Status it is looking for

    """
    end_time = time.time() + timeout
    if isinstance(status, str):
        status = [status]

    current_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh,
                                                        auth_info=auth_info)
    while time.time() < end_time:
        for expected_status in status:
            if current_status == expected_status:
                LOG.info("VM status has reached {}".format(expected_status))
                return expected_status

        time.sleep(check_interval)
        current_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh,
                                                            auth_info=auth_info)

    err_msg = "Timed out waiting for vm status: {}. Actual vm status: {}".format(status, current_status)
    if fail_ok:
        LOG.warning(err_msg)
        return None
    else:
        raise exceptions.VMTimeout(err_msg)


def _confirm_or_revert_resize(vm, revert=False, con_ssh=None, fail_ok=False):
        cmd = 'resize-revert' if revert else 'resize-confirm'

        return cli.nova(cmd, vm, ssh_client=con_ssh, auth_info=Tenant.ADMIN, rtn_list=True,
                        fail_ok=fail_ok)


def _ping_vms(ssh_client, vm_ids=None, con_ssh=None, num_pings=5, timeout=15, fail_ok=False, use_fip=False,
              net_types='mgmt', retry=3, retry_interval=3, vlan_zero_only=True, exclude_nets=None, vshell=False,
              sep_file=None):
    """

    Args:
        vm_ids (list|str): list of vms to ping
        ssh_client (SSHClient): ping from this ssh client. Usually a natbox' ssh client or another vm's ssh client
        con_ssh (SSHClient): active controller ssh client to run cli command to get all the management ips
        num_pings (int): number of pings to send
        timeout (int): timeout waiting for response of ping messages in seconds
        fail_ok (bool): Whether it's okay to have 100% packet loss rate.
        use_fip (bool): Whether to ping floating ip only if a vm has more than one management ips
        sep_file (str|None)

    Returns (tuple): (res (bool), packet_loss_dict (dict))
        Packet loss rate dictionary format:
        {
         ip1: packet_loss_percentile1,
         ip2: packet_loss_percentile2,
         ...
        }

    """
    if isinstance(net_types, str):
        net_types = [net_types]

    if isinstance(vm_ids, str):
        vm_ids = [vm_ids]

    valid_net_types = ['mgmt', 'data', 'internal', 'external']
    if not set(net_types) <= set(valid_net_types):
        raise ValueError("Invalid net type(s) provided. Valid net_types: {}. net_types given: {}".
                         format(valid_net_types, net_types))

    if vshell and 'data' not in net_types:
        LOG.warning("'data' is not included in net_types, while vshell ping is only supported on 'data' network")

    vms_ips = []
    vshell_ips = []
    if 'mgmt' in net_types:
        mgmt_ips = network_helper.get_mgmt_ips_for_vms(vms=vm_ids, con_ssh=con_ssh, exclude_nets=exclude_nets)
        if not mgmt_ips:
            raise exceptions.VMNetworkError("Management net ip is not found for vms {}".format(vm_ids))
        vms_ips += mgmt_ips

    if 'external' in net_types:
        ext_ips = network_helper.get_external_ips_for_vms(vms=vm_ids, con_ssh=con_ssh, exclude_nets=exclude_nets)
        if not ext_ips:
            raise exceptions.VMNetworkError("No external network ip found for vms {}".format(vm_ids))
        vms_ips += ext_ips

    if 'data' in net_types:
        data_ips = network_helper.get_data_ips_for_vms(vms=vm_ids, con_ssh=con_ssh, exclude_nets=exclude_nets)
        if not data_ips:
            raise exceptions.VMNetworkError("Data network ip is not found for vms {}".format(vm_ids))
        if vshell:
            vshell_ips += data_ips
        else:
            vms_ips += data_ips

    if 'internal' in net_types:
        internal_ips = network_helper.get_internal_ips_for_vms(vms=vm_ids, con_ssh=con_ssh, exclude_nets=exclude_nets)
        if not internal_ips:
            raise exceptions.VMNetworkError("Internal net ip is not found for vms {}".format(vm_ids))
        # vlan subnets removed for US102722
        # if vlan_zero_only:
        #    internal_ips = network_helper.filter_ips_with_subnet_vlan_id(internal_ips, vlan_id=0, con_ssh=con_ssh)
        #    if not internal_ips:
        #        raise exceptions.VMNetworkError("Internal net ip with subnet vlan id 0 is not found for vms {}".
        #                                        format(vm_ids))
        vms_ips += internal_ips

    res_bool = False
    res_dict = {}
    for i in range(retry + 1):
        for ip in vms_ips:
            packet_loss_rate = network_helper._ping_server(server=ip, ssh_client=ssh_client, num_pings=num_pings,
                                                           timeout=timeout, fail_ok=True, vshell=False)[0]
            res_dict[ip] = packet_loss_rate

        for vshell_ip in vshell_ips:
            packet_loss_rate = network_helper._ping_server(server=vshell_ip, ssh_client=ssh_client, num_pings=num_pings,
                                                           timeout=timeout, fail_ok=True, vshell=True)[0]
            res_dict[vshell_ip] = packet_loss_rate

        res_bool = not any(loss_rate == 100 for loss_rate in res_dict.values())
        if res_bool:
            LOG.info("Ping successful from {}: {}".format(ssh_client.host, res_dict))
            return res_bool, res_dict

        if i < retry:
            LOG.info("Retry in {} seconds".format(retry_interval))
            time.sleep(retry_interval)

    if not res_dict:
        raise ValueError("Ping res dict contains no result.")

    err_msg = "Ping unsuccessful from vm (logged in via {}): {}".format(ssh_client.host, res_dict)
    if fail_ok:
        LOG.info(err_msg)
        return res_bool, res_dict
    else:
        if sep_file:
            msg = "==========================Ping unsuccessful from vm to vms===================="
            common.write_to_file(sep_file, content="{}\nLogged into vm via {}. Result: {}".format(msg, ssh_client.host,
                                                                                                  res_dict))
        raise exceptions.VMNetworkError(err_msg)


def ping_vms_from_natbox(vm_ids=None, natbox_client=None, con_ssh=None, num_pings=5, timeout=30, fail_ok=False,
                         use_fip=False, retry=0):
    """

    Args:
        vm_ids: vms to ping. If None, all vms will be ping'd.
        con_ssh (SSHClient): active controller client to retrieve the vm info
        natbox_client (NATBoxClient): ping vms from this client
        num_pings (int): number of pings to send
        timeout (int): timeout waiting for response of ping messages in seconds
        fail_ok (bool): When False, test will stop right away if one ping failed. When True, test will continue to ping
            the rest of the vms and return results even if pinging one vm failed.
        use_fip (bool): Whether to ping floating ip only if a vm has more than one management ips
        retry (int): number of times to retry if ping fails

    Returns (tuple): (res (bool), packet_loss_dict (dict))
        Packet loss rate dictionary format:
        {
         ip1: packet_loss_percentile1,
         ip2: packet_loss_percentile2,
         ...
        }
    """
    if isinstance(vm_ids, str):
        vm_ids = [vm_ids]

    if not natbox_client:
        natbox_client = NATBoxClient.get_natbox_client()

    net_type = 'external' if use_fip else 'mgmt'
    res_bool, res_dict = _ping_vms(vm_ids=vm_ids, ssh_client=natbox_client, con_ssh=con_ssh, num_pings=num_pings,
                                   timeout=timeout, fail_ok=True, use_fip=use_fip, net_types=net_type, retry=retry,
                                   vshell=False)
    if not res_bool and not fail_ok:
        msg = "==================Ping vm(s) from NatBox failed - Collecting extra information==============="
        LOG.error(msg)
        f_path = '{}/{}'.format(ProjVar.get_var('PING_FAILURE_DIR'), ProjVar.get_var("TEST_NAME"))
        common.write_to_file(file_path=f_path, content="\n{}\nResult(s): {}\n".format(msg, res_dict))
        ProjVar.set_var(PING_FAILURE=True)
        get_console_logs(vm_ids=vm_ids, sep_file=f_path)
        network_helper.collect_networking_info(vms=vm_ids, sep_file=f_path)
        raise exceptions.VMNetworkError("Ping failed from NatBox. Details: {}".format(res_dict))

    return res_bool, res_dict


def get_console_logs(vm_ids, length=None, con_ssh=None, sep_file=None):
    """
    Get console logs for given vm(s)
    Args:
        vm_ids (str|list):
        length (int|None): how many lines to tail
        con_ssh:
        sep_file (str|None): write vm console logs to given sep_file if specified.

    Returns (dict): {<vm1_id>: <vm1_console>, <vm2_id>: <vm2_console>, ...}
    """
    if isinstance(vm_ids, str):
        vm_ids = [vm_ids]
    console_logs = {}
    args = '--length={} '.format(length) if length else ''
    content = ''
    for vm_id in vm_ids:
        vm_args = '{}{}'.format(args, vm_id)
        output = cli.nova('console-log', vm_args, ssh_client=con_ssh)
        console_logs[vm_id] = output
        content += "Console log for vm {}:\n{}\n".format(vm_id, output)

    if sep_file:
        common.write_to_file(sep_file, content=content)

    return console_logs


def wait_for_cloud_init_finish(vm_id, timeout=300, con_ssh=None):
    """
    Wait for vm to reach login screen via console log. Normally used after vm reboot, evacuation, etc
    Args:
        vm_id (str):
        timeout (int):
        con_ssh:

    Returns (bool): True if login screen reached, else False

    """
    LOG.info("Waiting for vm to reach login screen via console log")
    end_time = time.time() + timeout
    while time.time() < end_time:
        console = get_console_logs(vm_ids=vm_id, length=5, con_ssh=con_ssh)[vm_id]
        if re.search(' Cloud-init .* finished at | login:', console):
            return True
        time.sleep(5)

    LOG.warning("VM {} did not reach login screen within {} seconds".format(vm_id, timeout))
    return False


def ping_vms_from_vm(to_vms=None, from_vm=None, user=None, password=None, prompt=None, con_ssh=None, natbox_client=None,
                     num_pings=5, timeout=60, fail_ok=False, from_vm_ip=None, to_fip=False, from_fip=False,
                     net_types='mgmt', retry=3, retry_interval=3, vlan_zero_only=True, exclude_nets=None, vshell=False):
    """

    Args:
        from_vm (str):
        to_vms (str|list|None):
        user (str):
        password (str):
        prompt (str):
        con_ssh (SSHClient):
        natbox_client (SSHClient):
        num_pings (int):
        timeout (int): max number of seconds to wait for ssh connection to from_vm
        fail_ok (bool):  When False, test will stop right away if one ping failed. When True, test will continue to ping
            the rest of the vms and return results even if pinging one vm failed.
        from_vm_ip (str): vm ip to ssh to if given. from_fip flag will be considered only if from_vm_ip=None
        to_fip (bool): Whether to ping floating ip if a vm has floating ip associated with it
        from_fip (bool): whether to ssh to vm's floating ip if it has floating ip associated with it
        net_types (list|str): 'mgmt', 'data', or 'internal'
        retry (int): number of times to retry
        retry_interval (int): seconds to wait between each retries
        vlan_zero_only (bool): used if 'internal' is included in net_types. Ping vm over internal net with vlan id 0 if
            True, otherwise ping all the internal net ips assigned to vm.
        exclude_nets (list): exclude ips from given network names
        vshell (bool): whether to ping vms' data interface through internal interface.
            Usage: when set to True, use 'vshell ping --count 3 <other_vm_data_ip> <internal_if_id>'
                - dpdk vms should be booted from lab_setup scripts
                - 'data' has to be included in net_types

    Returns (tuple):
        A tuple in form: (res (bool), packet_loss_dict (dict))

        Packet loss rate dictionary format:
        {
         ip1: packet_loss_percentile1,
         ip2: packet_loss_percentile2,
         ...
        }

    """
    if isinstance(net_types, str):
        net_types = [net_types]

    if from_vm is None or to_vms is None:
        vms_ips = network_helper.get_mgmt_ips_for_vms(con_ssh=con_ssh, rtn_dict=True)
        if not vms_ips:
            raise exceptions.NeutronError("No management ip found for any vms")

        vms_ids = list(vms_ips.keys())
        if from_vm is None:
            from_vm = random.choice(vms_ids)
        if to_vms is None:
            to_vms = vms_ids

    if isinstance(to_vms, str):
        to_vms = [to_vms]

    if not isinstance(from_vm, str):
        raise ValueError("from_vm is not a string: {}".format(from_vm))

    assert from_vm and to_vms, "from_vm: {}, to_vms: {}".format(from_vm, to_vms)

    f_path = '{}/{}'.format(ProjVar.get_var('PING_FAILURE_DIR'), ProjVar.get_var('TEST_NAME'))
    try:
        with ssh_to_vm_from_natbox(vm_id=from_vm, username=user, password=password, natbox_client=natbox_client,
                                   prompt=prompt, con_ssh=con_ssh, vm_ip=from_vm_ip, use_fip=from_fip) as from_vm_ssh:
                res = _ping_vms(ssh_client=from_vm_ssh, vm_ids=to_vms, con_ssh=con_ssh, num_pings=num_pings,
                                timeout=timeout, fail_ok=fail_ok, use_fip=to_fip, net_types=net_types, retry=retry,
                                retry_interval=retry_interval, vlan_zero_only=vlan_zero_only, exclude_nets=exclude_nets,
                                vshell=vshell, sep_file=f_path)
                return res

    except:
        ProjVar.set_var(PING_FAILURE=True)
        get_console_logs(vm_ids=from_vm, length=20, sep_file=f_path)
        get_console_logs(vm_ids=to_vms, sep_file=f_path)
        network_helper.collect_networking_info(vms=to_vms, sep_file=f_path)
        try:
            LOG.warning("Ping vm(s) from vm failed - Attempt to ssh to from_vm and collect vm networking info")
            with ssh_to_vm_from_natbox(vm_id=from_vm, username=user, password=password, natbox_client=natbox_client,
                                       prompt=prompt, con_ssh=con_ssh, vm_ip=from_vm_ip,
                                       use_fip=from_fip) as from_vm_ssh:
                _collect_vm_networking_info(vm_ssh=from_vm_ssh, sep_file=f_path)

            LOG.warning("Ping vm(s) from vm failed - Attempt to ssh to to_vms and collect vm networking info")
            for vm_ in to_vms:
                with ssh_to_vm_from_natbox(vm_, retry=False, con_ssh=con_ssh) as to_ssh:
                    _collect_vm_networking_info(to_ssh, sep_file=f_path)
        except:
            pass

        raise


def _collect_vm_networking_info(vm_ssh, sep_file=None):
    content = 'VM network info collected when logged in via {}:'.format(vm_ssh.host)
    output = vm_ssh.exec_cmd('ip addr', get_exit_code=False)[1]
    content += '\nSent: ip addr\nOutput:\n{}\n'.format(output)
    output = vm_ssh.exec_cmd('ip neigh', get_exit_code=False)[1]
    content += '\nSent: ip neigh\nOutput:\n{}\n'.format(output)
    output = vm_ssh.exec_cmd('ip route', get_exit_code=False)[1]
    content += '\nSent: ip route\nOutput:\n{}\n'.format(output)

    if sep_file:
        common.write_to_file(sep_file, content=content)


def ping_ext_from_vm(from_vm, ext_ip=None, user=None, password=None, prompt=None, con_ssh=None, natbox_client=None,
                     num_pings=5, timeout=30, fail_ok=False, vm_ip=None, use_fip=False):

    if ext_ip is None:
        ext_ip = EXT_IP

    with ssh_to_vm_from_natbox(vm_id=from_vm, username=user, password=password, natbox_client=natbox_client,
                               prompt=prompt, con_ssh=con_ssh, vm_ip=vm_ip, use_fip=use_fip) as from_vm_ssh:
        from_vm_ssh.exec_cmd('ip addr', get_exit_code=False)
        return network_helper._ping_server(ext_ip, ssh_client=from_vm_ssh, num_pings=num_pings,
                                           timeout=timeout, fail_ok=fail_ok)[0]


@contextmanager
def ssh_to_vm_from_natbox(vm_id, vm_image_name=None, username=None, password=None, prompt=None,
                          timeout=VMTimeout.SSH_LOGIN, natbox_client=None, con_ssh=None, vm_ip=None,
                          vm_ext_port=None, use_fip=False, retry=True, retry_timeout=120, close_ssh=True):
    """
    ssh to a vm from natbox.

    Args:
        vm_id (str): vm to ssh to
        vm_image_name (str): such as cgcs-guest, tis-centos-guest, ubuntu_14, etc
        username (str):
        password (str):
        prompt (str):
        timeout (int): 
        natbox_client (NATBoxClient):
        con_ssh (SSHClient): ssh connection to TiS active controller
        vm_ip (str): ssh to this ip from NatBox if given
        vm_ext_port (str): port forwarding rule external port. If given this port will be used. vm_ip must be external
        router ip address.
        use_fip (bool): Whether to ssh to floating ip if a vm has one associated. Not applicable if vm_ip is given.
        retry (bool): whether or not to retry if fails to connect
        retry_timeout (int): max time to retry

    Yields (VMSSHClient):
        ssh client of the vm

    Examples:
        with ssh_to_vm_from_natbox(vm_id=<id>) as vm_ssh:
            vm_ssh.exec_cmd(cmd)

    """
    if vm_image_name is None:
        vm_image_name = nova_helper.get_vm_image_name(vm_id=vm_id, con_ssh=con_ssh).strip().lower()

    if vm_ip is None:
        if use_fip:
            vm_ip = network_helper.get_external_ips_for_vms(vms=vm_id, con_ssh=con_ssh)[0]
        else:
            vm_ip = network_helper.get_mgmt_ips_for_vms(vms=vm_id, con_ssh=con_ssh)[0]

    if not natbox_client:
        natbox_client = NATBoxClient.get_natbox_client()

    vm_ssh = VMSSHClient(natbox_client=natbox_client, vm_ip=vm_ip, vm_ext_port=vm_ext_port, vm_img_name=vm_image_name,
                         user=username, password=password, prompt=prompt, timeout=timeout, retry=retry,
                         retry_timeout=retry_timeout)
    try:
        yield vm_ssh
    finally:
        if close_ssh:
            vm_ssh.close()


def get_vm_pid(instance_name, host_ssh):
    """
    Get instance pid on its host.

    Args:
        instance_name: instance name of a vm
        host_ssh: ssh for the host of the given instance

    Returns (str): pid of a instance on its host

    """
    code, vm_pid = host_ssh.exec_sudo_cmd(
            """ps aux | grep --color='never' {} | grep -v grep | awk '{{print $2}}'""".format(instance_name))
    if code != 0:
        raise exceptions.SSHExecCommandFailed("Failed to get pid for vm: {}".format(instance_name))

    if not vm_pid:
        LOG.warning("PID for {} is not found on host!".format(instance_name))

    return vm_pid


class VMInfo:
    """
    class for storing and retrieving information for specific VM using openstack admin.

    Notes: Do not use this class for vm actions, such as boot, delete, migrate, etc as these actions should be done by
    tenants.
    """
    __instances = {}
    active_controller_ssh = None

    def __init__(self, vm_id, con_ssh=None, auth_info=Tenant.ADMIN):
        """

        Args:
            vm_id:
            con_ssh: floating controller ssh for the system

        Returns:

        """
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller()
        VMInfo.active_controller_ssh = con_ssh
        self.vm_id = vm_id
        self.con_ssh = con_ssh
        self.auth_info = auth_info
        self.initial_table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=self.auth_info,
                                                          timeout=5))
        self.table_ = self.initial_table_
        self.name = table_parser.get_value_two_col_table(self.initial_table_, 'name', strict=True)
        self.tenant_id = table_parser.get_value_two_col_table(self.initial_table_, 'tenant_id')
        self.user_id = table_parser.get_value_two_col_table(self.initial_table_, 'user_id')
        self.interface = self.__get_nics()[0]['nic1']['vif_model']
        self.boot_info = self.__get_boot_info()
        VMInfo.__instances[vm_id] = self            # add instance to class variable for tracking

    def refresh_table(self):
        self.table_ = table_parser.table(cli.nova('show', self.vm_id, ssh_client=self.con_ssh,
                                                  auth_info=self.auth_info))

    def __get_nics(self):
        raw_nics = table_parser.get_value_two_col_table(self.initial_table_, 'wrs-if:nics')
        if isinstance(raw_nics, str):
            raw_nics = [raw_nics]
        print("raw_nics: {}".format(raw_nics))
        nics = [eval(nic) for nic in raw_nics]
        return nics

    def get_host_name(self):
        self.refresh_table()
        return table_parser.get_value_two_col_table(table_=self.table_, field=':host', strict=False)

    def get_flavor_id(self):
        """

        Returns: (dict) {'name': flavor_name, 'id': flavor_id}

        """
        flavor_output = table_parser.get_value_two_col_table(self.table_, 'flavor')
        return re.search(r'\((.*)\)', flavor_output).group(1)

    def __get_boot_info(self):
        image_ = table_parser.get_value_two_col_table(self.table_, 'image')
        if BOOT_FROM_VOLUME in image_:
            volumes = self.get_volume_ids()
            if len(volumes) == 0:
                raise exceptions.VMError("Booted from volume, but no volume id found.")
            elif len(volumes) > 1:
                raise exceptions.VMError("VM booted from volume. Multiple volumes found! Did you attach extra volume?")
            return {'type': 'volume', 'id': volumes[0]}
        else:
            match = re.search(UUID, image_)
            return {'type': 'image', 'id': match.group(0)}

    def get_volume_ids(self):
        """

        Returns (tuple): such as (volume_id1, 'volume_id2', ...)

        """
        false = False
        true = True
        volumes = eval(table_parser.get_value_two_col_table(self.table_, ':volumes_attached', strict=False))
        return tuple([volume['id'] for volume in volumes])

    def get_image_name(self):
        if self.boot_info['type'] == 'image':
            image_id = self.boot_info['id']
            image_show_table = table_parser.table(cli.glance('image-show', image_id))
            image_name = table_parser.get_value_two_col_table(image_show_table, 'name', strict=False)
        else:      # booted from volume
            vol_show_table = table_parser.table(cli.cinder('show', self.boot_info['id']))
            image_meta_data = table_parser.get_value_two_col_table(vol_show_table, 'volume_image_metadata')
            image_meta_data = table_parser.convert_value_to_dict(image_meta_data)
            image_name = image_meta_data['image_name']

        return image_name

    def get_vcpus(self):
        """
        Get vcpus info as a list

        Returns (list): [min(int), current(int), max(int)]     # such as [1, 1, 1]

        """
        # self.refresh_table()
        return eval(table_parser.get_value_two_col_table(self.table_, field=':vcpus', strict=False))

    def get_status(self):
        self.refresh_table()
        return table_parser.get_value_two_col_table(self.table_, field='status')

    def get_storage_type(self):
        flavor_id = self.get_flavor_id()
        table_ = table_parser.table(cli.nova('flavor-show', flavor_id, ssh_client=self.con_ssh, auth_info=Tenant.ADMIN))
        extra_specs = eval(table_parser.get_value_two_col_table(table_, 'extra_specs'))
        return extra_specs['aggregate_instance_extra_specs:storage']

    def has_local_disks(self):
        if self.boot_info['type'] == 'image':
            return True
        flavor_id = self.get_flavor_id()
        table_ = table_parser.table(cli.nova('flavor-list', ssh_client=self.con_ssh, auth_info=Tenant.ADMIN))
        swap = table_parser.get_values(table_, 'Swap', ID=flavor_id)[0]
        ephemeral = table_parser.get_values(table_, 'Ephemeral', ID=flavor_id)[0]
        return bool(swap or int(ephemeral))

    def has_volume_attached(self):
        return len(self.get_volume_ids()) > 0

    @classmethod
    def get_vms_info(cls):
        return tuple(cls.__instances)

    @classmethod
    def get_vm_info(cls, vm_id, con_ssh=None):
        if vm_id not in cls.__instances:
            if vm_id in nova_helper.get_all_vms(con_ssh=con_ssh):
                return cls(vm_id, con_ssh)
            else:
                raise exceptions.VMError("VM with id {} does not exist!".format(vm_id))
        instance = cls.__instances[vm_id]
        instance.refresh_table()
        return instance

    @classmethod
    def remove_instance(cls, vm_id):
        cls.__instances.pop(vm_id, default="No instance found")


def delete_vms(vms=None, delete_volumes=True, check_first=True, timeout=VMTimeout.DELETE, fail_ok=False,
               stop_first=True, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Delete given vm(s) (and attached volume(s)). If None vms given, all vms on the system will be deleted.

    Args:
        vms (list|str): list of vm ids to be deleted. If string input, assume only one vm id is provided.
        check_first (bool): Whether to check if given vm(s) exist on system before attempt to delete
        timeout (int): Max time to wait for delete cli finish and wait for vms actually disappear from system
        delete_volumes (bool): delete attached volume(s) if set to True
        fail_ok (bool):
        stop_first (bool): whether to stop active vm(s) first before deleting. Best effort only
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (rtn_code(int), msg(str))  # rtn_code 1,2,3 only returns when fail_ok=True
        (-1, 'No vm(s) to delete.')     # "Empty vm list/string provided and no vm exist on system.
        (-1, 'None of the given vm(s) exists on system.')
        (0, "VM(s) deleted successfully.")
        (1, <stderr>)   # delete vm(s) cli returns stderr, some or all vms failed to delete.
        (2, "VMs deletion reject all accepted, but some vms still exist in nova list: <vms>")
        (3, "Some vm(s) deletion request is rejected : <vms>; and some vm(s) still exist after deletion: <vms>")

    """
    if vms is None:
        vms = nova_helper.get_vms(con_ssh=con_ssh, auth_info=auth_info, all_vms=True)

    if isinstance(vms, str):
        vms = [vms]
    vms = list(vms)

    LOG.info("Deleting vm(s): {}".format(vms))

    for vm in vms:
        if vm:
            break
    else:
        LOG.warning("Empty vm list/string provided and no vm exist on system. Do Nothing")
        return -1, 'No vm(s) to delete.'

    if check_first:
        vms_to_del = []
        for vm in vms:
            vm_exist = nova_helper.vm_exists(vm, con_ssh=con_ssh)
            if vm_exist:
                vms_to_del.append(vm)
        if not vms_to_del:
            LOG.info("None of these vms exist on system: {}. Do nothing".format(vms))
            return -1, 'None of the given vm(s) exists on system.'
    else:
        vms_to_del = vms

    if stop_first:  # best effort only
        active_vms = nova_helper.get_vms(vms=vms_to_del, auth_info=Tenant.ADMIN, con_ssh=con_ssh, all_vms=True,
                                         Status=VMStatus.ACTIVE)
        if active_vms:
            stop_vms(active_vms, fail_ok=True, con_ssh=con_ssh, auth_info=auth_info)

    vms_to_del_str = ' '.join(vms_to_del)

    if delete_volumes:
        vols_to_del = cinder_helper.get_volumes_attached_to_vms(vms=vms_to_del, auth_info=auth_info, con_ssh=con_ssh)

    code, output = cli.nova('delete', vms_to_del_str, ssh_client=con_ssh, timeout=timeout, fail_ok=True, rtn_list=True,
                            auth_info=auth_info)

    if code == 1:
        vms_del_accepted = re.findall(NovaCLIOutput.VM_DELETE_ACCEPTED, output)
        vms_del_rejected = list(set(vms_to_del)-set(vms_del_accepted))
    else:
        vms_del_accepted = vms_to_del
        vms_del_rejected = []

    # check if vms are actually removed from nova list
    all_deleted, vms_deleted, vms_undeleted = _wait_for_vms_deleted(vms_del_accepted, fail_ok=True, auth_info=auth_info,
                                                                    timeout=timeout, con_ssh=con_ssh)

    # Delete volumes results will not be returned. Best effort only.
    if delete_volumes:
        cinder_helper.delete_volumes(vols_to_del, fail_ok=True, auth_info=auth_info, con_ssh=con_ssh)

    # Process returns
    if code == 1:
        if all_deleted:
            if fail_ok:
                return 1, output
            raise exceptions.CLIRejected(output)
        else:
            msg = "Some vm(s) deletion request is rejected : {}; and some vm(s) still exist after deletion: {}".\
                  format(vms_del_rejected, vms_undeleted)
            if fail_ok:
                LOG.warning(msg)
                return 3, msg
            raise exceptions.VMPostCheckFailed(msg)

    if not all_deleted:
        msg = "VMs deletion request all accepted, but some vms still exist in nova list: {}".format(vms_undeleted)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.VMPostCheckFailed(msg)

    LOG.info("VM(s) deleted successfully: {}".format(vms_to_del))
    return 0, "VM(s) deleted successfully."


def _wait_for_vms_deleted(vms, header='ID', timeout=VMTimeout.DELETE, fail_ok=True,
                          check_interval=3, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Wait for specific vm to be removed from nova list

    Args:
        vms (str|list): list of vms ids
        header: ID or Name
        timeout (int): in seconds
        fail_ok (bool):
        check_interval (int):
        con_ssh (SSHClient|None):
        auth_info (dict|None):

    Returns (tuple): (result(bool), vms_deleted(list), vms_failed_to_delete(list))

    """
    if isinstance(vms, str):
        vms = [vms]

    vms_to_check = list(vms)
    vms_deleted = []
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            output = cli.nova('list --all-tenants', ssh_client=con_ssh, auth_info=auth_info)
        except exceptions.CLIRejected as e:
            if 'The resource could not be found' in e.__str__():
                LOG.error("'nova list' failed post vm deletion. Workaround is being applied.")
                time.sleep(3)
                output = cli.nova('list --all-tenants', ssh_client=con_ssh, auth_info=auth_info)
            else:
                raise

        table_ = table_parser.table(output)
        existing_vms = table_parser.get_column(table_, header)
        for vm in vms_to_check:
            if vm not in existing_vms:
                vms_to_check.remove(vm)
                vms_deleted.append(vm)

        if not vms_to_check:
            return True, vms, []
        time.sleep(check_interval)

    if fail_ok:
        return False, vms_deleted, vms_to_check
    raise exceptions.VMPostCheckFailed("Some vm(s) are not removed from nova list within {} seconds: {}".
                                       format(timeout, vms_to_check))


def wait_for_vms_values(vms, header='Status', values=VMStatus.ACTIVE, timeout=VMTimeout.STATUS_CHANGE, fail_ok=True,
                        check_interval=3, con_ssh=None, auth_info=Tenant.ADMIN):

    """
    Wait for specific vms to reach any of the given state(s)

    Args:
        vms (str|list): id(s) of vms to check
        header (str): target header in nova list
        values (str|list): expected value(s)
        timeout (int): in seconds
        fail_ok (bool):
        check_interval (int):
        con_ssh (SSHClient|None):
        auth_info (dict|None):

    Returns (list): [result(bool), vms_in_state(list), vms_failed_to_reach_state(list)]

    """
    if isinstance(vms, str):
        vms = [vms]

    if isinstance(values, str):
        values = [values]

    vms_to_check = list(vms)
    res_pass = {}
    res_fail = {}
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.nova('list --all-tenants', ssh_client=con_ssh, auth_info=auth_info))

        for vm_id in list(vms_to_check):
            vm_val = table_parser.get_values(table_, target_header=header, ID=vm_id)[0]
            res_fail[vm_id] = vm_val
            if vm_val in values:
                vms_to_check.remove(vm_id)
                res_pass[vm_id] = vm_val
                res_fail.pop(vm_id)

        if not vms_to_check:
            return True, res_pass, res_fail

        time.sleep(check_interval)

    fail_msg = "Some vm(s) did not reach given status from nova list within {} seconds: {}".format(timeout, res_fail)
    if fail_ok:
        LOG.warning(fail_msg)
        return False, res_pass, res_fail
    raise exceptions.VMPostCheckFailed(fail_msg)


def set_vm_state(vm_id, check_first=False, error_state=True, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Set vm state to error or active via nova reset-state.

    Args:
        vm_id:
        check_first:
        error_state:
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):

    """
    expt_vm_status = VMStatus.ERROR if error_state else VMStatus.ACTIVE
    LOG.info("Setting vm {} state to: {}".format(vm_id, expt_vm_status))

    if check_first:
        pre_vm_status = nova_helper.get_vm_nova_show_value(vm_id, field='status', con_ssh=con_ssh, auth_info=auth_info)
        if pre_vm_status.lower() == expt_vm_status.lower():
            msg = "VM {} already in {} state. Do nothing.".format(vm_id, pre_vm_status)
            LOG.info(msg)
            return -1, msg

    cmd = 'reset-state'
    if not error_state:
        cmd += ' --active'

    code, output = cli.nova(cmd, vm_id, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True, fail_ok=fail_ok)
    if code == 1:
        return 1, output

    result = _wait_for_vm_status(vm_id, expt_vm_status, fail_ok=fail_ok)

    if result is None:
        msg = "VM {} did not reach expected state - {} after reset-state.".format(vm_id, expt_vm_status)
        LOG.warning(msg)
        return 2, msg

    msg = "VM state is successfully set to: {}".format(expt_vm_status)
    LOG.info(msg)
    return 0, msg


def reboot_vm(vm_id, hard=False, fail_ok=False, con_ssh=None, auth_info=None, cli_timeout=CMDTimeout.REBOOT_VM,
              reboot_timeout=VMTimeout.REBOOT):
    vm_status = nova_helper.get_vm_status(vm_id, con_ssh=con_ssh)
    if not vm_status.lower() == 'active':
        LOG.warning("VM is not in active state before rebooting. VM status: {}".format(vm_status))

    extra_arg = '--hard ' if hard else ''
    arg = "{}{}".format(extra_arg, vm_id)

    date_format = "%Y%m%d %T"
    start_time = common.get_date_in_format(date_format=date_format)
    code, output = cli.nova('reboot', arg, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True,
                            timeout=cli_timeout)

    if code == 1:
        return 1, output

    # expt_reboot = VMStatus.HARD_REBOOT if hard else VMStatus.SOFT_REBOOT
    # _wait_for_vm_status(vm_id, expt_reboot, check_interval=0, fail_ok=False)
    LOG.info("Wait for vm reboot events to appear in system event-list")
    expt_reason = 'hard-reboot' if hard else 'soft-reboot'
    system_helper.wait_for_events(timeout=30, num=10, entity_instance_id=vm_id, start=start_time, fail_ok=False,
                                  strict=False, **{'Event Log ID': EventLogID.REBOOT_VM_ISSUED,
                                                   'Reason Text': expt_reason})

    system_helper.wait_for_events(timeout=reboot_timeout, num=10, entity_instance_id=vm_id, start=start_time,
                                  fail_ok=False, **{'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})

    LOG.info("Check vm status from nova show")
    actual_status = _wait_for_vm_status(vm_id, [VMStatus.ACTIVE, VMStatus.ERROR], fail_ok=fail_ok, con_ssh=con_ssh,
                                        timeout=30)
    if not actual_status:
        msg = "VM {} did not reach active state after reboot.".format(vm_id)
        LOG.warning(msg)
        return 2, msg

    if actual_status.lower() == VMStatus.ERROR.lower():
        msg = "VM is in error state after reboot."
        if fail_ok:
            LOG.warning(msg)
            return 3, msg
        raise exceptions.VMPostCheckFailed(msg)

    succ_msg = "VM rebooted successfully."
    LOG.info(succ_msg)
    return 0, succ_msg


def __perform_vm_action(vm_id, action, expt_status, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None,
                        auth_info=None):

    LOG.info("{} vm {} begins...".format(action, vm_id))
    code, output = cli.nova(action, vm_id, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True,
                            timeout=120)

    if code == 1:
        return 1, output

    actual_status = _wait_for_vm_status(vm_id, [expt_status, VMStatus.ERROR], fail_ok=fail_ok, con_ssh=con_ssh,
                                        timeout=timeout)

    if not actual_status:
        msg = "VM {} did not reach expected state {} after {}.".format(vm_id, expt_status, action)
        LOG.warning(msg)
        return 2, msg

    if actual_status.lower() == VMStatus.ERROR.lower():
        msg = "VM is in error state after {}.".format(action)
        if fail_ok:
            LOG.warning(msg)
            return 3, msg
        raise exceptions.VMPostCheckFailed(msg)

    succ_msg = "{} VM succeeded.".format(action)
    LOG.info(succ_msg)
    return 0, succ_msg


def suspend_vm(vm_id, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_vm_action(vm_id, 'suspend', VMStatus.SUSPENDED, timeout=timeout, fail_ok=fail_ok,
                               con_ssh=con_ssh, auth_info=auth_info)


def resume_vm(vm_id, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_vm_action(vm_id, 'resume', VMStatus.ACTIVE, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                               auth_info=auth_info)


def pause_vm(vm_id, timeout=VMTimeout.PAUSE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_vm_action(vm_id, 'pause', VMStatus.PAUSED, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                               auth_info=auth_info)


def unpause_vm(vm_id, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_vm_action(vm_id, 'unpause', VMStatus.ACTIVE, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                               auth_info=auth_info)


def stop_vms(vms, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return _start_or_stop_vms(vms, 'stop', VMStatus.STOPPED, timeout, check_interval=1, fail_ok=fail_ok,
                              con_ssh=con_ssh, auth_info=auth_info)


def start_vms(vms, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return _start_or_stop_vms(vms, 'start', VMStatus.ACTIVE, timeout, check_interval=1, fail_ok=fail_ok,
                              con_ssh=con_ssh, auth_info=auth_info)


def _start_or_stop_vms(vms, action, expt_status, timeout=VMTimeout.STATUS_CHANGE, check_interval=3, fail_ok=False,
                       con_ssh=None, auth_info=None):

    LOG.info("{}ing vms {}...".format(action, vms))
    action = action.lower()
    if isinstance(vms, str):
        vms = [vms]

    code, output = cli.nova(action, ' '.join(vms), ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                            rtn_list=True)

    vms_to_check = list(vms)
    if code == 1:
        vms_to_check = re.findall(NovaCLIOutput.VM_ACTION_ACCEPTED.format(action), output)
        if not vms_to_check:
            return 1, output

    res_bool, res_pass, res_fail = wait_for_vms_values(vms_to_check, 'Status', [expt_status, VMStatus.ERROR],
                                                       fail_ok=fail_ok, check_interval=check_interval,
                                                       con_ssh=con_ssh, timeout=timeout)

    if not res_bool:
        msg = "Some VM(s) did not reach expected state(s) - {}. Actual states: {}".format(expt_status, res_fail)
        LOG.warning(msg)
        return 2, msg

    error_vms = [vm_id for vm_id in vms_to_check if res_pass[vm_id].lower() == VMStatus.ERROR.lower()]
    if error_vms:
        msg = "Some VM(s) in error state after {}: {}".format(action, error_vms)
        if fail_ok:
            LOG.warning(msg)
            return 3, msg
        raise exceptions.VMPostCheckFailed(msg)

    succ_msg = "Action {} performed successfully on vms.".format(action)
    LOG.info(succ_msg)
    return 0, succ_msg


def rebuild_vm(vm_id, image_id=None, new_name=None, preserve_ephemeral=None, fail_ok=False, con_ssh=None,
               auth_info=Tenant.ADMIN, **metadata):

    if image_id is None:
        image_id = glance_helper.get_image_id_from_name(GuestImages.DEFAULT_GUEST, strict=True)

    args = '{} {}'.format(vm_id, image_id)

    if new_name:
        args += ' --name {}'.format(new_name)

    if preserve_ephemeral:
        args += ' --preserve-ephemeral'

    for key, value in metadata.items():
        args += ' --meta {}={}'.format(key, value)

    LOG.info("Rebuilding vm {}".format(vm_id))
    code, output = cli.nova('rebuild', args, fail_ok=fail_ok, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True)
    if code == 1:
        return code, output

    LOG.info("Check vm status after vm rebuild")
    _wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, fail_ok=fail_ok, con_ssh=con_ssh)
    actual_status = _wait_for_vm_status(vm_id, [VMStatus.ACTIVE, VMStatus.ERROR], fail_ok=fail_ok, con_ssh=con_ssh,
                                        timeout=VMTimeout.REBUILD)

    if not actual_status:
        msg = "VM {} did not reach active state after rebuild.".format(vm_id)
        LOG.warning(msg)
        return 2, msg

    if actual_status.lower() == VMStatus.ERROR.lower():
        msg = "VM is in error state after rebuild."
        if fail_ok:
            LOG.warning(msg)
            return 3, msg
        raise exceptions.VMPostCheckFailed(msg)

    succ_msg = "VM rebuilded successfully."
    LOG.info(succ_msg)
    return 0, succ_msg


def scale_vm(vm_id, direction, resource='cpu', fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Scale up/down vm cpu

    Args:
        vm_id (str): id of vm to scale
        direction (str): up or down
        resource (str): currently only cpu
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (rtn_code(int), message(str))
        - 0, vm <resource> is successfully scaled <direction>
        - 1, Scale vm cli rejected

    """
    if direction not in ['up', 'down']:
        raise ValueError("Invalid direction provided. Valid values: 'up', 'down'")

    args = ' '.join([vm_id, resource, direction])
    code, output = cli.nova('scale', args, fail_ok=fail_ok, rtn_list=True, ssh_client=con_ssh, auth_info=auth_info)

    if code == 1:
        return 1, output

    # TODO add checking
    succ_msg = "vm {} is successfully scaled {}".format(resource, direction)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_vm_host_and_numa_nodes(vm_id, con_ssh=None):
    """
    Get vm host and numa nodes used for the vm on the host
    Args:
        vm_id (str):
        con_ssh (SSHClient):

    Returns (tuple): (<vm_hostname> (str), <numa_nodes> (list of integers))

    """
    nova_tab = system_helper.get_vm_topology_tables('servers', con_ssh=con_ssh)[0]
    nova_tab = table_parser.filter_table(nova_tab, ID=vm_id)

    host = table_parser.get_column(nova_tab, 'host')[0]
    instance_topology = table_parser.get_column(nova_tab, 'instance_topology')[0]
    if isinstance(instance_topology, str):
        instance_topology = [instance_topology]

    # Each numa node will have an entry for given instance, thus number of entries should be the same as number of
    # numa nodes for the vm
    actual_node_vals = []
    for actual_node_info in instance_topology:
        actual_node_val = int(re.findall(InstanceTopology.NODE, actual_node_info)[0])
        actual_node_vals.append(actual_node_val)

    return host, actual_node_vals


def parse_cpu_list(list_in_str, prefix=''):
    results = []
    found = re.search(r'[,]?\s*{}\s*(\d+(\d|\-|,)*)'.format(prefix), list_in_str, re.IGNORECASE)
    if found:
        for cpus in found.group(1).split(','):
            if not cpus:
                continue
            if '-' in cpus:
                b, e = str(cpus).split(sep='-')[0:2]
                results += list(range(int(b), int(e) + 1))
            else:
                results.append(int(cpus))
    return results


def _parse_cpu_siblings(siblings_str):
    results = []

    found = re.search(r'[,]?\s*siblings:\s*((\{\d+,\d+\})(,(\{\d+,\d+\}))*)', siblings_str, re.IGNORECASE)

    if found:
        for cpus in found.group(1).split('},'):
            if not cpus:
                continue
            n1, n2 = str(cpus[1:]).split(',')
            results.append((n1, n2))

    return results


def get_vm_pci_dev_info_via_nova_show(vm_id, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get vm pci devices info via nova show. Returns a list of dictionaries.
    Args:
        vm_id:
        con_ssh:
        auth_info:

    Returns (dict):
    Examples:
        {'0000:81:0f.7': {'node':0, 'addr':'0000:81:0f.7', 'type':'VF', 'vendor':'8086', 'product':'154c'},
        '0000:81:0f.9': {'node':0, 'addr':'0000:81:0f.9', 'type':'VF', 'vendor':'8086', 'product':'154c'},
        '0000:90:02.3': {'node':1, 'addr':'0000:90:02.3', 'type':'VF', 'vendor':'8086', 'product':'154c'}}

    """
    pci_devs_raw = nova_helper.get_vm_nova_show_value(vm_id, field='wrs-res:pci_devices', con_ssh=con_ssh,
                                                      auth_info=auth_info)
    if isinstance(pci_devs_raw, str):
        pci_devs_raw = [pci_devs_raw]

    pci_devs_info = {}
    for pci_dev in pci_devs_raw:
        pci_dev_dict = {}
        info = pci_dev.split(sep=', ')
        for item in info:
            k, v = item.split(sep=':', maxsplit=1)
            if k == 'node':
                v = int(v)
            pci_dev_dict[k] = v

        pci_devs_info[pci_dev_dict['addr']] = pci_dev_dict

    return pci_devs_info


def get_vm_irq_info_from_hypervisor(vm_id, con_ssh=None):
    """
    Gather vm irq info from vm host

    Args:
        vm_id (str):
        con_ssh (SSHClient):

    Returns (dict):
    Examples:
        {
            "0000:83:03.7":{
                "cpulist":[10,15,16,30,35],
                "irq":"69",
                "msi_irqs": ["69"],
                "nic":"83:03.7 Co-processor: Intel Corporation DH895XCC Series QAT Virtual Function",
                "node":"1",
                "product":"0443",
                "vendor":"8086"
                },
            }

    """
    vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    nova_show_pci_devs = get_vm_pci_dev_info_via_nova_show(vm_id, con_ssh=con_ssh)
    pci_addrs = list(nova_show_pci_devs.keys())

    pci_devs_dict = {}
    with host_helper.ssh_to_host(vm_host, con_ssh=con_ssh) as host_ssh:

        for pci_addr in pci_addrs:
            pci_dev_dict = dict(type=nova_show_pci_devs[pci_addr]['type'])
            pci_dev_info_path = '/sys/bus/pci/devices/{}'.format(pci_addr)

            irq = host_ssh.exec_sudo_cmd('cat {}/{}'.format(pci_dev_info_path, 'irq'))[1]
            pci_dev_dict['irq'] = irq

            numa_node = host_ssh.exec_sudo_cmd('cat {}/{}'.format(pci_dev_info_path, 'numa_node'))[1]
            pci_dev_dict['node'] = int(numa_node)

            msi_irqs = (host_ssh.exec_sudo_cmd('ls {}/{}/'.format(pci_dev_info_path, 'msi_irqs'))[1]).split()
            pci_dev_dict['msi_irqs'] = msi_irqs

            # compute-1:~$ cat /sys/bus/pci/devices/0000\:81\:0f.7/uevent |grep PCI_ID
            # PCI_ID=8086:154C
            vendor_product = host_ssh.exec_sudo_cmd('cat {}/{} | grep PCI_ID'.format(pci_dev_info_path, 'uevent'))[1]
            vendor, product = vendor_product.split('=', 1)[1].split(':', 1)
            pci_dev_dict['vendor'] = vendor
            pci_dev_dict['product'] = product

            lspci_info = host_ssh.exec_sudo_cmd('lspci -s {}'.format(pci_addr))[1]
            pci_dev_dict['nic'] = lspci_info

            irqs_to_check = list(msi_irqs)
            if irq and irq is not '0':
                irqs_to_check.append(irq)

            cpu_list = []
            for irq_to_check in irqs_to_check:

                code, output = host_ssh.exec_sudo_cmd('cat /proc/irq/{}/smp_affinity_list'.format(irq_to_check),
                                                      fail_ok=True)
                if code == 0:
                    cpu_list_irq = output
                    cpu_list += common._parse_cpus_list(cpu_list_irq)
            pci_dev_dict['cpulist'] = sorted(list(set([int(i) for i in cpu_list])))

            pci_devs_dict[pci_addr] = pci_dev_dict

    LOG.info("PCI dev info gathered from {} for vm {}: \n{}".format(vm_host, vm_id, pci_devs_dict))
    return pci_devs_dict


def get_vm_pcis_irqs_from_hypervisor(vm_id, hypervisor=None, con_ssh=None, retries=3, retry_interval=45):
    """
    Get information for all PCI devices using tool nova-pci-interrupts.

    Args:
        vm_id (str):
        hypervisor
        con_ssh:
        retries
        retry_interval

    Returns (pci_info, vm_topology): details of the PCI device and VM topology
        Examples:
            vm_topology: {
                "mem":1024,
                "node":1,
                "pcpus":[35,15,10,30,16],
                "siblings": None,
                "vcpus":[0,1,2,3,4]
                }

            pci_info: {
                "0000:83:03.7":{
                    "cpulist":[10,15,16,30,35],
                    "irq":"69",
                    "msi_irqs":"69",
                    "nic":"83:03.7 Co-processor: Intel Corporation DH895XCC Series QAT Virtual Function",
                    "node": 1,
                    "product":"0443",
                    "vendor":"8086"
                    },
                }
    """

    pci_infos = get_vm_irq_info_from_hypervisor(vm_id, con_ssh=con_ssh)
    vm_topology = get_instance_topology(vm_id, con_ssh=con_ssh)

    return pci_infos, vm_topology


def get_instance_topology(vm_id, con_ssh=None, source='vm-topology'):
    """
    Get instance_topology from 'vm-topology -s servers'

    Args:
        vm_id (str):
        # rtn_list (bool):
        con_ssh (SSHClient):
        source (str): 'vm-topology' or 'nova show'

    Returns (list):

    """
    if source == 'vm-topology':
        servers_tab = system_helper.get_vm_topology_tables('servers', con_ssh=con_ssh)[0]
        servers_tab = table_parser.filter_table(servers_tab, ID=vm_id)

        instance_topology = table_parser.get_column(servers_tab, 'instance_topology')[0]
    else:
        instance_topology = nova_helper.get_vm_nova_show_value(vm_id, 'wrs-res:topology', strict=True, con_ssh=con_ssh)

    if isinstance(instance_topology, str):
        instance_topology = [instance_topology]

    instance_topology_all = []
    for topology_for_numa_node in instance_topology:
        instance_topology_dict = {}
        items = topology_for_numa_node.split(sep=', ')
        for item in items:
            item_list = item.strip().split(sep=':')
            if len(item_list) == 2:
                key_ = item_list[0]
                value_ = item_list[1]
                if key_ in ['node']:
                    value_ = int(value_)
                elif key_ in ['vcpus', 'pcpus', 'shared_pcpu']:
                    values = value_.split(sep=',')
                    for val in value_.split(sep=','):
                        # convert '3-6' to [3, 4, 5, 6]
                        if '-' in val:
                            values.remove(val)
                            min_, max_ = val.split(sep='-')
                            values += list(range(int(min_), int(max_) + 1))

                    value_ = [int(val) for val in values]

                elif key_ == 'siblings':
                    # example: siblings:{0,1},{2,3},{5,6,8-10}
                    # initial value_ parsed: ['0,1', '2,3', '5,6,8-10']
                    value_ = re.findall('{([^}]*)}', value_)
                    value_ = [common._parse_cpus_list(item) for item in value_]
                instance_topology_dict[key_] = value_

            elif len(item_list) == 1:
                value_ = item_list[0]
                if re.match(InstanceTopology.TOPOLOGY, value_):
                    instance_topology_dict['topology'] = value_

                if value_.endswith('MB'):
                    instance_topology_dict['mem'] = int(value_.split('MB')[0])

        # Add as None if item is not displayed in vm-topology
        all_keys = ['node', 'pgsize', 'vcpus', 'pcpus', 'pol', 'thr', 'siblings', 'topology', 'mem', 'shared_pcpu']
        for key in all_keys:
            if key not in instance_topology_dict:
                instance_topology_dict[key] = None
        instance_topology_all.append(instance_topology_dict)

    LOG.info('Instance topology for vm {}: {}'.format(vm_id, instance_topology_all))
    return instance_topology_all


def perform_action_on_vm(vm_id, action, auth_info=Tenant.ADMIN, con_ssh=None, **kwargs):
    """
    Perform action on a given vm.

    Args:
        vm_id (str):
        action (str): action to perform on vm. Valid_actions: 'start', 'stop', 'suspend', 'resume', 'pause', 'unpause',
        'reboot', 'live_migrate', or 'cold_migrate'
        auth_info (dict):
        con_ssh (SSHClient):
        **kwargs: extra params to pass to action function, e.g.destination_host='compute-0' when action is live_migrate

    Returns (None):

    """
    action_function_map = {
        'start': start_vms,
        'stop': stop_vms,
        'suspend': suspend_vm,
        'resume': resume_vm,
        'pause': pause_vm,
        'unpause': unpause_vm,
        'reboot': reboot_vm,
        'rebuild': rebuild_vm,
        'live_migrate': live_migrate_vm,
        'cold_migrate': cold_migrate_vm,
        'cold_mig_revert': cold_migrate_vm,
    }
    if not vm_id:
        raise ValueError("vm id is not provided.")

    valid_actions = list(action_function_map.keys())
    action = action.lower().replace(' ', '_')
    if action not in valid_actions:
        raise ValueError("Invalid action provided: {}. Valid actions: {}".format(action, valid_actions))

    if action == 'cold_mig_revert':
        kwargs['revert'] = True

    return action_function_map[action](vm_id, con_ssh=con_ssh, auth_info=auth_info, **kwargs)


def add_vlan_for_vm_pcipt_interfaces(vm_id, net_seg_id, retry=3, exclude_nets=None, guest_os=None):
    """
    Add vlan for vm pci-passthrough interface and restart networking service.
    Do nothing if expected vlan interface already exists in 'ip addr'.

    Args:
        vm_id (str):
        net_seg_id (int|str|dict): such as 1792
        retry (int): max number of times to reboot vm to try to recover it from non-exit
        exclude_nets (list|None): network names to exclude
        guest_os (str): guest os type. Default guest os assumed if None is given.

    Returns: None

    Raises: VMNetworkError if vlan interface is not found in 'ip addr' after adding

    Notes:
        Known openstack issue that will not be fixed: CGTS-4705.
        Sometimes a non-exist 'rename6' interface will be used for pci-passthrough nic after vm maintenance
        Sudo reboot from the vm as workaround.
        By default will try to reboot for a maximum of 3 times

    """
    if not guest_os:
        guest_os = GuestImages.DEFAULT_GUEST

    if not vm_id or not net_seg_id:
        raise ValueError("vm_id and/or net_seg_id not provided.")

    net_seg_id_dict = None
    if isinstance(net_seg_id, dict):
        net_seg_id_dict = net_seg_id
        net_seg_id = None

    for i in range(retry):
        vm_pcipt_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id, vif_model='pci-passthrough')

        if not vm_pcipt_nics:
            LOG.warning("No pci-passthrough device found for vm from nova show {}".format(vm_id))
            return

        with ssh_to_vm_from_natbox(vm_id=vm_id) as vm_ssh:
            for pcipt_nic in vm_pcipt_nics:
                if exclude_nets:
                    if isinstance(exclude_nets, str):
                        exclude_nets = [exclude_nets]

                    skip_nic = False
                    for net_to_exclude in exclude_nets:
                        if pcipt_nic['network'] == net_to_exclude:
                            LOG.info("pcipt nic in {} is ignored: {}".format(net_to_exclude, pcipt_nic))
                            skip_nic = True
                            break

                    if skip_nic:
                        continue

                mac_addr = pcipt_nic['mac_address']
                eth_name = network_helper.get_eth_for_mac(mac_addr=mac_addr, ssh_client=vm_ssh)
                if not eth_name:
                    raise exceptions.VMNetworkError("Interface with mac {} is not listed in 'ip addr' in vm {}".
                                                    format(mac_addr, vm_id))
                elif 'rename' in eth_name:
                    LOG.warning("Retry {}: non-existing interface {} found on pci-passthrough nic in vm {}, "
                                "reboot vm to try to recover".format(i + 1, eth_name, vm_id))
                    sudo_reboot_from_vm(vm_id=vm_id, vm_ssh=vm_ssh)
                    wait_for_vm_pingable_from_natbox(vm_id)
                    break

                else:
                    if net_seg_id_dict:
                        net_name = pcipt_nic['network']
                        net_seg_id = net_seg_id_dict[net_name]
                        LOG.info("Seg id for {}: {}".format(net_name, net_seg_id))

                    vlan_name = "{}.{}".format(eth_name, net_seg_id)

                    output_pre_ipaddr = vm_ssh.exec_cmd('ip addr', fail_ok=False)[1]
                    if vlan_name in output_pre_ipaddr:
                        LOG.info("{} already in ip addr. Skip.".format(vlan_name))
                        continue

                    # 'ip link add' works for all linux guests but it does not persists after network service restart
                    # vm_ssh.exec_cmd('ip link add link {} name {} type vlan id {}'.format(eth_name, vlan_name,
                    # net_seg_id))
                    # vm_ssh.exec_cmd('ip link set {} up'.format(vlan_name))

                    wait_for_interfaces_up(vm_ssh, eth_name)

                    if 'centos' in guest_os.lower() and 'centos_6' not in guest_os.lower():
                        # guest based on centos7
                        ifcfg_dir = VMPath.VM_IF_PATH_CENTOS
                        ifcfg_eth = '{}ifcfg-{}'.format(ifcfg_dir, eth_name)
                        ifcfg_vlan = '{}ifcfg-{}'.format(ifcfg_dir, vlan_name)

                        output_pre = vm_ssh.exec_cmd('ls {}'.format(ifcfg_dir), fail_ok=False)[1]
                        if ifcfg_vlan not in output_pre:
                            LOG.info("Add {} ifcfg file".format(vlan_name))
                            vm_ssh.exec_sudo_cmd('cp {} {}'.format(ifcfg_eth, ifcfg_vlan), fail_ok=False)
                            vm_ssh.exec_sudo_cmd("sed -i 's/{}/{}/g' {}".format(eth_name, vlan_name, ifcfg_vlan),
                                                 fail_ok=False)
                            vm_ssh.exec_sudo_cmd(r"echo -e 'VLAN=yes' >> {}".format(ifcfg_vlan), fail_ok=False)

                        # restart network service regardless since vlan_name was not in ip addr
                        LOG.info("Restarting networking service for vm.")
                        vm_ssh.exec_sudo_cmd('systemctl restart network', expect_timeout=180)

                    else:
                        # assume it's wrl or ubuntu
                        output_pre = vm_ssh.exec_cmd('cat /etc/network/interfaces', fail_ok=False)[1]
                        if vlan_name not in output_pre:
                            if eth_name not in output_pre:
                                LOG.info("Append new interface {} to /etc/network/interfaces".format(eth_name))
                                if_to_add = VMNetworkStr.NET_IF.format(eth_name, eth_name)
                                vm_ssh.exec_cmd(r"echo -e '{}' >> /etc/network/interfaces".
                                                format(if_to_add), fail_ok=False)

                            if '.' + net_seg_id in output_pre:
                                LOG.info("Modify existing interface to {} in /etc/network/interfaces".format(vlan_name))
                                vm_ssh.exec_cmd(r"sed -i -e 's/eth[0-9]\+\(.{}\)/{}\1/g' /etc/network/interfaces".
                                                format(net_seg_id, eth_name), fail_ok=False)
                            else:
                                LOG.info("Append new interface {} to /etc/network/interfaces".format(vlan_name))
                                if_to_add = VMNetworkStr.NET_IF.format(vlan_name, vlan_name)
                                vm_ssh.exec_cmd(r"echo -e '{}' >> /etc/network/interfaces".
                                                format(if_to_add), fail_ok=False)

                            output_post = vm_ssh.exec_cmd('cat /etc/network/interfaces', fail_ok=False)[1]
                            if vlan_name not in output_post:
                                raise exceptions.VMNetworkError("Failed to add vlan to vm interfaces file")

                        LOG.info("Restarting networking service for vm.")
                        vm_ssh.exec_cmd("/etc/init.d/networking restart", expect_timeout=180)

                    LOG.info("Check if vlan is added successfully with IP assigned")
                    output_post_ipaddr = vm_ssh.exec_cmd('ip addr', fail_ok=False)[1]
                    if vlan_name not in output_post_ipaddr:
                        raise exceptions.VMNetworkError("vlan {} is not found in 'ip addr' after restarting networking "
                                                        "service.".format(vlan_name))
                    if not is_ip_assigned(vm_ssh, eth_name=vlan_name):
                        LOG.warning('No IP assigned to {} vlan interface'.format(vlan_name))
                    LOG.info("vlan {} is successfully added and an IP is assigned.".format(vlan_name))
            else:
                # did not break, meaning no 'rename' interface detected, vlan either existed or successfully added
                return

            # 'for' loop break which means 'rename' interface detected, and vm reboot triggered - known issue with wrl
            LOG.info("Reboot vm completed. Retry started.")

    else:
        raise exceptions.VMNetworkError("'rename' interface still exists in pci-passthrough vm {} with {} reboot "
                                        "attempts.".format(vm_id, retry))


def is_ip_assigned(vm_ssh, eth_name):
    output = vm_ssh.exec_cmd('ip addr show {}'.format(eth_name), fail_ok=False)[1]
    return re.search('inet {}'.format(Networks.IPV4_IP), output)


def wait_for_interfaces_up(vm_ssh, eth_names, check_interval=3, timeout=180):
    LOG.info("Waiting for vm interface(s) to be in UP state: {}".format(eth_names))
    end_time = time.time() + timeout
    if isinstance(eth_names, str):
        eth_names = [eth_names]
    ifs_to_check = list(eth_names)
    while time.time() < end_time:
        for eth in ifs_to_check:
            output = vm_ssh.exec_cmd('ip -d link show {}'.format(eth), fail_ok=False)[1]
            if 'state UP' in output:
                ifs_to_check.remove(eth)
                continue
            else:
                LOG.info("{} is not up - wait for {} seconds and check again".format(eth, check_interval))
                break

        if not ifs_to_check:
            LOG.info('interfaces are up: {}'.format(eth_names))
            return

        time.sleep(check_interval)

    raise exceptions.VMNetworkError("Interface(s) not up for given vm")


def sudo_reboot_from_vm(vm_id, vm_ssh=None, check_host_unchanged=True, con_ssh=None):

    if check_host_unchanged:
        pre_vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)

    LOG.info("Initiate sudo reboot from vm")

    def _sudo_reboot(vm_ssh_):
        extra_prompt = 'Broken pipe'
        output = vm_ssh_.exec_sudo_cmd('reboot -f', get_exit_code=False, extra_prompt=extra_prompt)[1]
        expt_string = 'The system is going down for reboot|Broken pipe'
        if re.search(expt_string, output):
            # Sometimes system rebooting msg will be displayed right after reboot cmd sent
            vm_ssh_.parent.flush()
            return

        try:
            time.sleep(10)
            vm_ssh_.send('')
            index = vm_ssh_.expect([expt_string, vm_ssh_.prompt], timeout=60)
            if index == 1:
                raise exceptions.VMOperationFailed("Unable to reboot vm {}")
            vm_ssh_.parent.flush()
        except ExpectTimeout:
            vm_ssh_.send_control('c')
            vm_ssh_.expect()
            raise

    if not vm_ssh:
        with ssh_to_vm_from_natbox(vm_id) as vm_ssh:
            _sudo_reboot(vm_ssh)
    else:
        _sudo_reboot(vm_ssh)

    LOG.info("sudo vm reboot initiated - wait for reboot completes and VM reaches active state")
    system_helper.wait_for_events(VMTimeout.AUTO_RECOVERY, strict=False, fail_ok=False, con_ssh=con_ssh,
                                  **{'Entity Instance ID': vm_id,
                                     'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})
    _wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, fail_ok=False, con_ssh=con_ssh)

    if check_host_unchanged:
        post_vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
        if not pre_vm_host == post_vm_host:
            raise exceptions.HostError("VM host changed from {} to {} after sudo reboot vm".format(
                    pre_vm_host, post_vm_host))


def get_proc_nums_from_vm(vm_ssh):
    total_cores = common._parse_cpus_list(vm_ssh.exec_cmd('cat /sys/devices/system/cpu/present', fail_ok=False)[1])
    online_cores = common._parse_cpus_list(vm_ssh.exec_cmd('cat /sys/devices/system/cpu/online', fail_ok=False)[1])
    offline_cores = common._parse_cpus_list(vm_ssh.exec_cmd('cat /sys/devices/system/cpu/offline', fail_ok=False)[1])

    return total_cores, online_cores, offline_cores


def get_affined_cpus_for_vm(vm_id, host_ssh=None, vm_host=None, instance_name=None, con_ssh=None):
    """
    cpu affinity list for vm via taskset -pc
    Args:
        vm_id (str):
        con_ssh (SSHClient):

    Returns (list): such as [10, 30]

    """
    cmd = '''ps-sched.sh | grep qemu | grep {} | grep -v grep | awk '{{print $2;}}' | xargs -i /bin/sh -c "taskset -pc {{}}"'''

    if host_ssh:
        if not vm_host or not instance_name:
            raise ValueError("vm_host and instance_name have to be provided together with host_ssh")

        output = host_ssh.exec_cmd(cmd.format(instance_name))[1]

    else:
        vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
        instance_name = nova_helper.get_vm_instance_name(vm_id, con_ssh=con_ssh)

        with host_helper.ssh_to_host(vm_host) as host_ssh:
            output = host_ssh.exec_cmd(cmd.format(instance_name))[1]

    # Sample output:
    # pid 6376's current affinity list: 10
    # pid 6380's current affinity list: 10
    # pid 6439's current affinity list: 10
    # pid 6441's current affinity list: 10
    # pid 6442's current affinity list: 30
    # pid 6445's current affinity list: 10
    # pid 24142's current affinity list: 10

    all_cpus = []
    lines = output.splitlines()
    for line in lines:

        # skip line if below output occurs due to timing in executing cmds
        # taskset: failed to get pid 17125's affinity: No such process
        if "No such process" in line:
            continue

        cpu_str = line.split(sep=': ')[-1].strip()
        cpus = common._parse_cpus_list(cpus=cpu_str)
        all_cpus += cpus

    all_cpus = sorted(list(set(all_cpus)))
    LOG.info("Affined cpus on host {} for vm {}: {}".format(vm_host, vm_id, all_cpus))

    return all_cpus


def _scp_net_config_cloud_init(guest_os):
    con_ssh = ControllerClient.get_active_controller()

    dest_dir = '/home/wrsroot/userdata/'
    if 'ubuntu' in guest_os:
        dest_name = 'ubuntu_cloud_init_if_conf.sh'
    elif 'centos' in guest_os:
        dest_name = 'centos_cloud_init_if_conf.sh'
    else:
        raise ValueError("Unknown guest_os")

    dest_path = dest_dir + dest_name

    if con_ssh.file_exists(file_path=dest_path):
        LOG.info('userdata {} already exists. Return existing path'.format(dest_path))
        return dest_path

    LOG.debug('Create userdata directory if not already exists')
    cmd = 'mkdir -p {}'.format(dest_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    # LOG.info('wget image from {} to {}/{}'.format(img_url, img_dest, new_name))
    # cmd = 'wget {} --no-check-certificate -P {} -O {}'.format(img_url, img_dest, new_name)
    # con_ssh.exec_cmd(cmd, expect_timeout=7200, fail_ok=False)

    source_path = '{}/userdata/{}'.format(SvcCgcsAuto.HOME, dest_name)
    LOG.info('scp image from test server to active controller')

    scp_cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {}@{}:{} {}'.format(
            SvcCgcsAuto.USER, SvcCgcsAuto.SERVER, source_path, dest_dir)

    con_ssh.send(scp_cmd)
    index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=3600)
    if index == 2:
        con_ssh.send('yes')
        index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT], timeout=3600)
    if index == 1:
        con_ssh.send(SvcCgcsAuto.PASSWORD)
        index = con_ssh.expect()
    if index != 0:
        raise exceptions.SSHException("Failed to scp files")


def _create_cloud_init_if_conf(guest_os, nics_num):
    """

    Args:
        guest_os:
        nics_num:

    Returns (str|None): file path of the cloud init userdata file for given guest os and number of nics
        Sample file content for Centos vm:
            #!/bin/bash
            sudo cp /etc/sysconfig/network-scripts/ifcfg-eth0 /etc/sysconfig/network-scripts/ifcfg-eth1
            sudo sed -i 's/eth0/eth1/g' /etc/sysconfig/network-scripts/ifcfg-eth1
            sudo ifup eth1

        Sample file content for Ubuntu vm:


    """

    file_dir = TiSPath.USERDATA
    guest_os = guest_os.lower()

    # default eth_path for non-ubuntu image
    eth_path = VMPath.ETH_PATH_CENTOS
    new_user = None

    if 'ubuntu' in guest_os:
        guest_os = 'ubuntu'
        # vm_if_path = VMPath.VM_IF_PATH_UBUNTU
        eth_path = VMPath.ETH_PATH_UBUNTU
        new_user = 'ubuntu'
    elif 'centos' in guest_os:
        # vm_if_path = VMPath.VM_IF_PATH_CENTOS
        new_user = 'centos'

    file_name = '{}_{}nic_cloud_init_if_conf.sh'.format(guest_os, nics_num)

    file_path = file_dir + file_name
    con_ssh = ControllerClient.get_active_controller()
    if con_ssh.file_exists(file_path=file_path):
        LOG.info('userdata {} already exists. Return existing path'.format(file_path))
        return file_path

    LOG.info('Create userdata directory if not already exists')
    cmd = 'mkdir -p {}'.format(file_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    tmp_file = ProjVar.get_var('TEMP_DIR') + file_name

    # No longer need to specify bash using cloud-config
    # if 'centos_7' in guest_os:
    #     shell = '/usr/bin/bash'
    # else:
    #     shell = '/bin/bash'

    with open(tmp_file, mode='a') as f:
        f.write("#cloud-config\n")

        if new_user is not None:
            f.write("user: {}\n"
                    "password: {}\n"
                    "chpasswd: {{ expire: False}}\n"
                    "ssh_pwauth: True\n\n".format(new_user, new_user))

        if eth_path is not None:
            eth0_path = eth_path.format('eth0')
            f.write("runcmd:\n")
            # f.write(" - echo '#!{}'\n".format(shell))
            for i in range(nics_num-1):
                ethi_name = 'eth{}'.format(i+1)
                ethi_path = eth_path.format(ethi_name)
                f.write(' - cp {} {}\n'.format(eth0_path, ethi_path))
                f.write(" - sed -i 's/eth0/{}/g' {}\n".format(ethi_name, ethi_path))
                f.write(' - ifup {}\n'.format(ethi_name))

    common.scp_to_active_controller(source_path=tmp_file, dest_path=file_path, is_dir=False)

    LOG.info("Userdata file created: {}".format(file_path))
    return file_path


def _get_cloud_config_add_user(con_ssh=None):
    """
    copy the cloud-config userdata to TiS server.
    This userdata adds wrsroot/li69nux user to guest

    Args:
        con_ssh (SSHClient):

    Returns (str): TiS filepath of the userdata

    """
    file_dir = TiSPath.USERDATA
    file_name = UserData.ADDUSER_WRSROOT
    file_path = file_dir + file_name

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if con_ssh.file_exists(file_path=file_path):
        LOG.info('userdata {} already exists. Return existing path'.format(file_path))
        return file_path

    LOG.debug('Create userdata directory if not already exists')
    cmd = 'mkdir -p {}'.format(file_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    source_file = TestServerPath.USER_DATA + file_name

    dest_path = common.scp_from_test_server_to_active_controller(source_path=source_file, dest_dir=file_dir,
                                                                 dest_name=file_name, con_ssh=con_ssh)

    if dest_path is None:
        raise exceptions.CommonError("userdata file {} does not exist after download".format(file_path))

    return file_path


def modified_cold_migrate_vm(vm_id, revert=False, con_ssh=None, fail_ok=False, auth_info=Tenant.ADMIN,
                             vm_image_name=None):
    """
    Cold migrate modifed for CGTS-4911
    Args:
        vm_id (str): vm to cold migrate
        revert (bool): False to confirm resize, True to revert
        con_ssh (SSHClient):
        fail_ok (bool): True if fail ok. Default to False, ie., throws exception upon cold migration fail.
        auth_info (dict):
        vm_image_name

    Returns (tuple): (rtn_code, message)
        (0, success_msg) # Cold migration and confirm/revert succeeded. VM is back to original state or Active state.
        (1, <stderr>) # cold migration cli rejected as expected
        (2, <stderr>) # Cold migration cli command rejected. <stderr> is the err message returned by cli cmd.
        (3, <stdout>) # Cold migration cli accepted, but not finished. <stdout> is the output of cli cmd.
        (4, timeout_message] # Cold migration command ran successfully, but timed out waiting for VM to reach
            'Verify Resize' state or Error state.
        (5, err_msg) # Cold migration command ran successfully, but VM is in Error state.
        (6, err_msg) # Cold migration command ran successfully, and resize confirm/revert performed. But VM is not in
            Active state after confirm/revert.
        (7, err_msg) # Cold migration and resize confirm/revert ran successfully and vm in active state. But host for vm
            is not as expected. i.e., still the same host after confirm resize, or different host after revert resize.

    """
    before_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    before_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh)
    if not before_status == VMStatus.ACTIVE:
        LOG.warning("Non-active VM status before cold migrate: {}".format(before_status))

    LOG.info("Cold migrating VM {} from {}...".format(vm_id, before_host))
    exitcode, output = cli.nova('migrate --poll', vm_id, ssh_client=con_ssh, auth_info=auth_info,
                                timeout=VMTimeout.COLD_MIGRATE_CONFIRM, fail_ok=True, rtn_list=True)

    if exitcode == 1:
        vm_storage_backing = nova_helper.get_vm_storage_type(vm_id=vm_id, con_ssh=con_ssh)
        if len(host_helper.get_hypervisors_with_storage_backing(vm_storage_backing, con_ssh=con_ssh)) < 2:
            LOG.info("Cold migration of vm {} rejected as expected due to no host with valid storage backing to cold "
                     "migrate to.".format(vm_id))
            return 1, output
        elif fail_ok:
            LOG.warning("Cold migration of vm {} is rejected.".format(vm_id))
            return 2, output
        else:
            raise exceptions.VMOperationFailed(output)

    if 'Finished' not in output:
        if fail_ok:
            LOG.warning("Cold migration is not finished.")
            return 3, output
        raise exceptions.VMPostCheckFailed("Failed to cold migrate vm. Output: {}".format(output))

    LOG.info("Waiting for VM status change to {}".format(VMStatus.VERIFY_RESIZE))

    vm_status = _wait_for_vm_status(vm_id=vm_id, status=[VMStatus.VERIFY_RESIZE, VMStatus.ERROR], timeout=300,
                                    fail_ok=fail_ok, con_ssh=con_ssh)

    if vm_status is None:
        return 4, 'Timed out waiting for Error or Verify_Resize status for VM {}'.format(vm_id)

    # Modified here
    # TODO Check file in vm
    wait_for_vm_pingable_from_natbox(vm_id, timeout=240)
    with ssh_to_vm_from_natbox(vm_id, vm_image_name=vm_image_name) as vm_ssh:
        filename = ""
        look_for = ''
        # vm_ssh.exec_cmd('cat {} | grep {}'.format(filename, look_for))

    verify_resize_str = 'Revert' if revert else 'Confirm'
    if vm_status == VMStatus.VERIFY_RESIZE:
        LOG.info("{}ing resize..".format(verify_resize_str))
        _confirm_or_revert_resize(vm=vm_id, revert=revert, con_ssh=con_ssh)

    elif vm_status == VMStatus.ERROR:
        err_msg = "VM {} in Error state after cold migrate. {} resize is not reached.".format(vm_id, verify_resize_str)
        if fail_ok:
            return 5, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    post_confirm_state = _wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, timeout=VMTimeout.COLD_MIGRATE_CONFIRM,
                                             fail_ok=fail_ok, con_ssh=con_ssh)

    if post_confirm_state is None:
        err_msg = "VM {} is not in Active state after {} Resize".format(vm_id, verify_resize_str)
        return 6, err_msg

    # Process results
    after_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    host_changed = before_host != after_host
    host_change_str = "changed" if host_changed else "did not change"
    operation_ok = not host_changed if revert else host_changed

    if not operation_ok:
        err_msg = ("VM {} host {} after {} Resize. Before host: {}. After host: {}".
                   format(vm_id, host_change_str, verify_resize_str, before_host, after_host))
        if fail_ok:
            return 7, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    success_msg = "VM {} successfully cold migrated and {}ed Resize.".format(vm_id, verify_resize_str)
    LOG.info(success_msg)
    return 0, success_msg


def wait_for_process(process, vm_id=None, vm_ssh=None, disappear=False, timeout=120, time_to_stay=1, check_interval=3,
                     fail_ok=True, con_ssh=None):
    """
    Wait for given process to appear or disappear on a VM

    Args:
        process (str): PID or unique proc name
        vm_id (str): vm id if vm_ssh is not provided
        vm_ssh (VMSSHClient): when vm_ssh is given, vm_id param will be ignored
        disappear (bool):
        timeout (int): max seconds to wait
        time_to_stay (int): time for result to persist
        check_interval (int):
        fail_ok (bool): whether to raise exception upon wait fail
        con_ssh (SSHClient): active controller ssh.

    Returns (bool): whether or not process appear/disappear within timeout. False return only possible when fail_ok=True

    """
    if not vm_ssh and not vm_id:
        raise ValueError("Either vm_id or vm_ssh has to be provided")

    if not vm_ssh:
        with ssh_to_vm_from_natbox(vm_id, con_ssh=con_ssh) as vm_ssh:
            return common.wait_for_process(ssh_client=vm_ssh, process=process, disappear=disappear,
                                           timeout=timeout, time_to_stay=time_to_stay, check_interval=check_interval,
                                           fail_ok=fail_ok)

    else:
        return common.wait_for_process(ssh_client=vm_ssh, process=process, disappear=disappear, timeout=timeout,
                                       check_interval=check_interval, time_to_stay=time_to_stay, fail_ok=fail_ok)


def boost_cpu_usage(vm_id, cpu_num=1, con_ssh=None):
    """
    Boost cpu usage on given number of cpu cores on specified vm using dd cmd

    Args:
        vm_id (str):
        cpu_num (int): number of times to run dd cmd. Each dd will normally be executed on different processor
        con_ssh:

    Returns (VMSSHClient): vm_ssh where the dd commands were sent.
        To terminate the dd to release the cpu resources, use: vm_ssh.exec_cmd('pkill dd')
    """
    LOG.info("Boosting cpu usage for vm {} using 'dd'".format(vm_id))
    dd_cmd = 'dd if=/dev/zero of=/dev/null &'

    with ssh_to_vm_from_natbox(vm_id, con_ssh=con_ssh, close_ssh=False) as vm_ssh:
        for i in range(cpu_num):
            vm_ssh.exec_cmd(cmd=dd_cmd)

    return vm_ssh


def boost_cpu_usage_new_thread(vm_id, cpu_num=1, timeout=1200):
    """
    Boost cpu usage on given number of cpu cores on specified vm using dd cmd on a new thread

    Args:
        vm_id (str):
        cpu_num (int): number of times to run dd cmd. Each dd will normally be executed on different processor
        timeout (int): max time to wait before killing the thread. Thread should be ended from test function.

    Returns (tuple): (<vm_ssh>, <thread for this function>)

    Examples:
        LOG.tc_step("Boost VM cpu usage")
        thread_timeout = 600
        vm_ssh, vm_thread = vm_helper.boost_cpu_usage_new_thread(vm_id=vm_id, cpu_num=vcpus, timeout=thread_timeout)

        LOG.tc_step("Check vm current vcpus in nova show is updated")
        check_helper.wait_for_vm_vcpus_update(vm_id, expt_min_cpu, expt_current_cpu, expt_max_cpu, timeout=120)

        # End vm thread explicitly after vcpus are changed to expected value. If test failed, then the thread will be
        # ended after the thread_timeout reaches.
        vm_thread.end_thread()
        vm_thread.wait_for_thread_end(timeout=3)

    """
    LOG.info("Creating new thread to spike cpu_usage on {} vm cores for vm {}".format(cpu_num, vm_id))
    thread = multi_thread.MThread(boost_cpu_usage, vm_id, cpu_num)
    thread.start_thread(timeout=timeout)
    vm_ssh = thread.get_output(wait=True)

    def _kill_dd(vm_ssh_):
        vm_ssh_.exec_cmd('pkill dd')

    thread.set_end_func(_kill_dd, vm_ssh)
    return vm_ssh, thread


def write_in_vm(vm_id, expect_timeout=120, thread_timeout=None, write_interval=5, end_now_flag=False, con_ssh=None):
    """
    Continue to write in vm using dd

    Args:
        vm_id (str):
        expect_timeout (int):
        thread_timeout (int):
        write_interval (int): how frequent to write. Note: 5 seconds seem to be a good interval,
            1 second interval might have noticeable impact on the performance of pexpect.
        end_now_flag (bool): whether to use thread.end_now flag to end the thread once thread.end_now is set to True
        con_ssh (SSHClient): controller ssh client

    Returns (tuple): (vm_ssh, new_thread)

    Examples:
        Sample test code to check write continues after swact:

        vm_ssh, vm_thread = vm_helper.write_in_vm(vm_id, end_now_flag=True, expect_timeout=40)
        vm_thread.end_now = False       # Initialize end_now flag
        vm_thread.end_thread()          # Start to read the dd output

        host_helper.swact_host()

        vm_thread.end_now = True        # set end_now flag to True after swact completes
        vm_thread.wait_for_thread_end(timeout=20)

        assert vm_thread.res is True, "Writing in vm stopped unexpectedly"

    """
    write_cmd = "while (true) do date; dd if=/dev/urandom of=output.txt bs=1k count=1 conv=fsync || break; echo ; " \
                "sleep {}; done 2>&1 | tee trace.txt".format(write_interval)

    def _keep_writing(vm_id_):
        LOG.info("starting to write to vm using dd...")
        with ssh_to_vm_from_natbox(vm_id_, con_ssh=con_ssh, close_ssh=False) as vm_ssh_:
            vm_ssh_.send(cmd=write_cmd)

        LOG.info("Write_in_vm returns while writing continues")
        return vm_ssh_

    thread = multi_thread.MThread(_keep_writing, vm_id)
    thread_timeout = expect_timeout + 30 if thread_timeout is None else thread_timeout
    thread.start_thread(timeout=thread_timeout, keep_alive=True)
    # thread.wait_for_thread_end(timeout=thread_timeout)
    thread.end_now = False
    vm_ssh = thread.get_output(wait=True, timeout=60)

    def _end_dd(vm_ssh_):
        LOG.info("Reading the dd output from vm {}".format(vm_id))
        thread.res = True
        try:
            while True:
                expt_output = '1024 bytes'
                index = vm_ssh.expect([expt_output, vm_ssh.prompt], timeout=expect_timeout, fail_ok=True,
                                      searchwindowsize=100)
                if index != 0:
                    LOG.warning("write has stopped or expected output-'{}' is not found".format(expt_output))
                    thread.res = False
                    break

                if end_now_flag:
                    if thread.end_now is True:
                        LOG.info("End thread now")
                        break

                LOG.info("Writing in vm continues...")
                time.sleep(write_interval)

        except:
            raise
        finally:
            vm_ssh_.send_control('c')

    thread.set_end_func(_end_dd, vm_ssh)

    return vm_ssh, thread


def attach_interface(vm_id, port_id=None, net_id=None, fixed_ip=None, vif_model=None, fail_ok=False, auth_info=None,
                     con_ssh=None):
    """
    Attach interface to a vm via port_id OR net_id
    Args:
        vm_id (str):
        port_id (str): port to attach to vm
        net_id (str): port from given net to attach to vm
        fixed_ip (str): fixed ip for attached interface. Only works when attaching interface via net_id
        vif_model (str): vif model for the interface
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple): (<return_code>, <attached_port_id>)
        (0, <port_id_attached>)
        (1, <std_err>)  - cli rejected
        (2, "Post interface attach check failed: <reasons>")     - net_id/port_id, vif_model, or fixed_ip do not match
                                                                    with given value

    """
    LOG.info("Attaching interface to VM {}".format(vm_id))
    if not vm_id:
        raise ValueError('vm_id is not supplied')

    args = ''
    args_dict = {
        '--port-id': port_id,
        '--net-id': net_id,
        '--fixed-ip': fixed_ip,
        '--wrs-if:vif_model': vif_model,
    }

    for key, val in args_dict.items():
        if val is not None:
            args += ' {} {}'.format(key, val)

    args += ' {}'.format(vm_id)

    prev_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id, auth_info=auth_info)
    code, output = cli.nova('interface-attach', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                            auth_info=auth_info)

    if code == 1:
        return code, output

    LOG.info("Post interface-attach checks started...")
    post_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id, auth_info=auth_info)
    last_nic = post_nics[-1]
    last_port = last_nic['port_id']

    err_msgs = []
    if len(post_nics) - len(prev_nics) != 1:
        err_msg = "NICs for vm {} is not incremented by 1".format(vm_id)
        err_msgs.append(err_msg)

    if net_id:
        net_name = network_helper.get_net_name_from_id(net_id, con_ssh=con_ssh, auth_info=auth_info)
        if not net_name == last_nic['network']:
            err_msg = "Network is not as specified for VM's last nic. Expt: {}. Actual: {}".\
                format(net_name, last_nic['network'])
            err_msgs.append(err_msg)

        if fixed_ip:
            net_ips = nova_helper.get_vm_nova_show_value(vm_id, field=net_name, strict=False, con_ssh=con_ssh,
                                                         auth_info=auth_info)
            if fixed_ip not in net_ips.split(sep=', '):
                err_msg = "specified fixed ip {} is not found in nova show {}".format(fixed_ip, vm_id)
                err_msgs.append(err_msg)

    elif port_id:
        if not port_id == last_port:
            err_msg = "port_id is not as specified for VM's last nic. Expt: {}. Actual: {}".format(port_id, last_port)
            err_msgs.append(err_msg)

    if vif_model:
        if not vif_model == last_nic['vif_model']:
            err_msg = "vif_model is not as specified for VM's last nic. Expt: {}. Actual:{}".\
                format(vif_model, last_nic['vif_model'])
            err_msgs.append(err_msg)

    if err_msgs:
        err_msgs_str = "Post interface attach check failed:\n{}".format('\n'.join(err_msgs))
        if fail_ok:
            LOG.warning(err_msgs_str)
            return 2, last_port
        raise exceptions.NovaError(err_msgs_str)

    succ_msg = "Port {} successfully attached to VM {}".format(last_port, vm_id)
    LOG.info(succ_msg)
    return 0, last_port


def detach_interface(vm_id, port_id, fail_ok=False, auth_info=None, con_ssh=None):
    """
    Detach a port from vm
    Args:
        vm_id (str):
        port_id (str): existing port that is attached to given vm
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple): (<return_code>, <msg>)
        (0, Port <port_id> is successfully detached from VM <vm_id>)
        (1, <stderr>)   - cli rejected
        (2, "Port <port_id> is not detached from VM <vm_id>")   - detached port is still shown in nova show

    """

    LOG.info("Detaching port {} from vm {}".format(port_id, vm_id))
    args = '{} {}'.format(vm_id, port_id)
    code, output = cli.nova('interface-detach', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                            auth_info=auth_info)

    if code == 1:
        return code, output

    post_nics = nova_helper.get_vm_interfaces_info(vm_id, auth_info=auth_info, con_ssh=con_ssh)
    for nic in post_nics:
        if port_id == nic['port_id']:
            err_msg = "Port {} is not detached from VM {}".format(port_id, vm_id)
            if fail_ok:
                return 2, err_msg

    succ_msg = "Port {} is successfully detached from VM {}".format(port_id, vm_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def evacuate_vms(host, vms_to_check, con_ssh=None, timeout=600, wait_for_host_up=False, fail_ok=False, post_host=None,
                 vlm=False, ping_vms=False):
    """
    Evacuate given vms by rebooting their host. VMs should be on specified host already when this keyword called.
    Args:
        host (str): host to reboot
        vms_to_check (list): vms to check status for after host reboot
        con_ssh (SSHClient):
        timeout (int): Max time to wait for vms to reach active state after reboot -f initiated on host
        wait_for_host_up (bool): whether to wait for host reboot completes before checking vm status
        fail_ok (bool): whether to return or to fail test when vm(s) failed to evacuate
        post_host (str): expected host for vms to be evacuated to
        vlm (False): whether to power-off host via vlm (assume host already reserved). When False, Run 'sudo reboot -f'
            from host.
        ping_vms (bool): whether to ping vms after evacuation

    Returns (tuple): (<code> (int), <vms_failed_to_evac> (list))
        - (0, [])   all vms evacuated successfully. i.e., active state, host changed, pingable from NatBox
        - (1, <inactive_vms>)   some vms did not reach active state after host reboot
        - (2, <vms_host_err>)   some vms' host did not change after host reboot

    """
    if isinstance(vms_to_check, str):
        vms_to_check = [vms_to_check]

    HostsToRecover.add(host)
    if vlm:
        LOG.tc_step("Power-off {} from vlm".format(host))
        vlm_helper.power_off_hosts(hosts=host, reserve=False)
    else:
        LOG.tc_step("'sudo reboot -f' from {}".format(host))
        host_helper.reboot_hosts(host, wait_for_reboot_finish=wait_for_host_up, con_ssh=con_ssh)

    try:
        if vlm or not wait_for_host_up:
            LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
            wait_for_vms_values(vms_to_check, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120,
                                con_ssh=con_ssh)

        LOG.tc_step("Check vms are in Active state and moved to other host(s) after host failure")
        res, active_vms, inactive_vms = wait_for_vms_values(vms=vms_to_check, values=VMStatus.ACTIVE, timeout=timeout,
                                                            con_ssh=con_ssh)

        vms_host_err = []
        for vm in vms_to_check:
            if post_host:
                if nova_helper.get_vm_host(vm) != post_host:
                    vms_host_err.append(vm)
            else:
                if nova_helper.get_vm_host(vm) == host:
                    vms_host_err.append(vm)

        if inactive_vms:
            err_msg = "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)
            if fail_ok:
                LOG.warning(err_msg)
                return 1, inactive_vms
            raise exceptions.VMError(err_msg)

        if vms_host_err:
            if post_host:
                err_msg = "Following VMs is not moved to expected host {} from {}: {}\nVMs did not reach Active " \
                          "state: {}".format(post_host, host, vms_host_err, inactive_vms)
            else:
                err_msg = "Following VMs stayed on the same host {}: {}\nVMs did not reach Active state: {}".\
                    format(host, vms_host_err, inactive_vms)

            if fail_ok:
                LOG.warning(err_msg)
                return 2, vms_host_err
            raise exceptions.VMError(err_msg)

        if ping_vms:
            LOG.tc_step("Ping vms after evacuated")
            for vm_ in vms_to_check:
                wait_for_vm_pingable_from_natbox(vm_id=vm_)

        LOG.info("All vms are successfully evacuated to other host")
        return 0, []
    except:
        raise
    finally:
        if vlm:
            LOG.tc_step("Powering on {} from vlm".format(host))
            vlm_helper.power_on_hosts(hosts=host, reserve=False, post_check=wait_for_host_up)


def boot_vms_various_types(storage_backing=None, target_host=None, cleanup='function', avail_zone='nova', vms_num=5):
    """
    Boot following 5 vms and ensure they are pingable from NatBox:
        - vm1: ephemeral=0, swap=0, boot_from_volume
        - vm2: ephemeral=1, swap=1, boot_from_volume
        - vm3: ephemeral=0, swap=0, boot_from_image
        - vm4: ephemeral=0, swap=0, boot_from_image, attach_volume
        - vm5: ephemeral=1, swap=1, boot_from_image
    Args:
        storage_backing (str|None): storage backing to set in flavor spec. When None, storage backing which used by
            most up hypervisors will be used.
        target_host (str|None): Boot vm on target_host when specified. (admin role has to be added to tenant under test)
        cleanup (str|None): Scope for resource cleanup, valid values: 'function', 'class', 'module', None.
            When None, vms/volumes/flavors will be kept on system
        avail_zone (str): availability zone to boot the vms

    Returns (list): list of vm ids

    """
    LOG.info("Create a flavor without ephemeral or swap disks")
    flavor_1 = nova_helper.create_flavor('flv_rootdisk', storage_backing=storage_backing)[1]
    if cleanup:
        ResourceCleanup.add('flavor', flavor_1, scope=cleanup)

    LOG.info("Create another flavor with ephemeral and swap disks")
    flavor_2 = nova_helper.create_flavor('flv_ephemswap', ephemeral=1, swap=512, storage_backing=storage_backing)[1]
    if cleanup:
        ResourceCleanup.add('flavor', flavor_2, scope=cleanup)

    launched_vms = []
    for i in range(int(math.ceil(vms_num/5.0))):
        LOG.info("Boot vm1 from volume with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm1_name = "vol_root"
        vm1 = boot_vm(vm1_name, flavor=flavor_1, source='volume', avail_zone=avail_zone, vm_host=target_host,
                      cleanup=cleanup)[1]

        wait_for_vm_pingable_from_natbox(vm1)
        launched_vms.append(vm1)
        if len(launched_vms) == vms_num:
            break

        LOG.info("Boot vm2 from volume with flavor flv_localdisk and wait for it pingable from NatBox")
        vm2_name = "vol_ephemswap"
        vm2 = boot_vm(vm2_name, flavor=flavor_2, source='volume', avail_zone=avail_zone, vm_host=target_host,
                      cleanup=cleanup)[1]

        wait_for_vm_pingable_from_natbox(vm2)
        launched_vms.append(vm2)
        if len(launched_vms) == vms_num:
            break

        LOG.info("Boot vm3 from image with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm3_name = "image_root"
        vm3 = boot_vm(vm3_name, flavor=flavor_1, source='image', avail_zone=avail_zone, vm_host=target_host,
                      cleanup=cleanup)[1]

        wait_for_vm_pingable_from_natbox(vm3)
        launched_vms.append(vm3)
        if len(launched_vms) == vms_num:
            break

        LOG.info("Boot vm4 from image with flavor flv_rootdisk, attach a volume to it and wait for it pingable from NatBox")
        vm4_name = 'image_root_attachvol'
        vm4 = boot_vm(vm4_name, flavor_1, source='image', avail_zone=avail_zone, vm_host=target_host, cleanup=cleanup)[1]

        vol = cinder_helper.create_volume(bootable=False, cleanup=cleanup)[1]
        attach_vol_to_vm(vm4, vol_id=vol, del_vol=cleanup)

        wait_for_vm_pingable_from_natbox(vm4)
        launched_vms.append(vm4)
        if len(launched_vms) == vms_num:
            break

        LOG.info("Boot vm5 from image with flavor flv_localdisk and wait for it pingable from NatBox")
        vm5_name = 'image_ephemswap'
        vm5 = boot_vm(vm5_name, flavor_2, source='image', avail_zone=avail_zone, vm_host=target_host, cleanup=cleanup)[1]

        wait_for_vm_pingable_from_natbox(vm5)
        launched_vms.append(vm5)
        if len(launched_vms) == vms_num:
            break

    assert len(launched_vms) == vms_num
    return launched_vms


def get_sched_policy_and_priority_for_vcpus(instance_pid, host_ssh, cpusets=None, comm=None):
    """
    Get cpu policy and priority for instance vcpus
    Args:
        instance_pid (str): pid from ps aux | grep <instance_name>
        host_ssh (SSHClient): ssh for vm host
        cpusets (int|list|None): such as 44, or [8, 44], etc. Will be used to grep ps with given cpuset(s) only
        comm (str|None): regex expression, used to search for given pattern in ps output. Such as 'qemu-kvm|CPU.*KVM'

    Returns (list of tuples): such as [('FF', '1'), ('TS', '-')]

    """
    LOG.info("Getting cpu scheduler policy and priority info for instance with pid {}".format(instance_pid))

    if not cpusets:
        if cpusets is not None:
            LOG.info("Empty cpusets provided, return []")
            return []

    cpuset_filters = []
    cpu_filter = ''
    if cpusets:
        if isinstance(cpusets, int):
            cpusets = [cpusets]

        for cpuset in cpusets:
            cpuset_filters.append('$5=="{}"'.format(cpuset))

        cpu_filter = ' || '.join(cpuset_filters)
        cpu_filter = ' && ({})'.format(cpu_filter)

    cmd = """ps -eL -o pid=,lwp=,class=,rtprio=,psr=,comm= | awk '{{if ( $1=="{}" {}) print}}'""".format(
            instance_pid, cpu_filter)

    output = host_ssh.exec_cmd(cmd, fail_ok=False)[1]
    out_lines = output.splitlines()

    cpu_pol_and_prios = []
    for out_line in out_lines:
        get_line = True
        if comm is not None:
            if not re.search(comm, out_line):
                get_line = False

        if get_line:
            items = out_line.split()
            rt_policy = items[2]
            rt_priority = items[3]
            cpu_pol_and_prios.append((rt_policy, rt_priority))

    LOG.info("CPU policy and priority for cpus with cpuset: {}; comm_pattern: {} - {}".format(cpusets, comm,
                                                                                              cpu_pol_and_prios))
    return cpu_pol_and_prios


def get_vcpu_model(vm_id, guest_os=None, con_ssh=None):
    """
    Get vcpu model of given vm. e.g., Intel(R) Xeon(R) CPU E5-2680 v2 @ 2.80GHz
    Args:
        vm_id (str):
        guest_os (str):
        con_ssh (SSHClient):

    Returns (str):

    """
    with ssh_to_vm_from_natbox(vm_id, vm_image_name=guest_os, con_ssh=con_ssh) as vm_ssh:
        out = vm_ssh.exec_cmd("cat /proc/cpuinfo | grep --color='never' 'model name'", fail_ok=False)[1]
        vcpu_model = out.strip().splitlines()[0].split(sep=': ')[1].strip()

    LOG.info("VM {} cpu model: {}".format(vm_id, vcpu_model))
    return vcpu_model


def ensure_vms_quotas(vms_num=10, cores_num=None, vols_num=None, tenant=None, con_ssh=None):
    """
    Update instances, cores, volumes quotas to given numbers
    Args:
        vms_num (int): max number of instances allowed for given tenant
        cores_num (int|None): twice of the vms quota when None
        vols_num (int|None): twice of the vms quota when None
        tenant (None|str): such as 'tenant1', 'tenant2'. Default tenant when None
        con_ssh (SSHClient):

    Returns:

    """
    if not vols_num:
        vols_num = 2 * vms_num
    if not cores_num:
        cores_num = 2 * vms_num
    cinder_helper.update_quotas(volumes=vols_num, con_ssh=con_ssh, tenant=tenant)
    nova_helper.update_quotas(instances=vms_num, cores=cores_num, con_ssh=con_ssh, tenant=tenant)
