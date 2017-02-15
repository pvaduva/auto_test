import random
import re
import time
from contextlib import contextmanager

from pexpect import TIMEOUT as ExpectTimeout

from utils import exceptions, cli, table_parser, multi_thread
from utils.ssh import NATBoxClient, VMSSHClient, ControllerClient, Prompt
from utils.tis_log import LOG

from consts.auth import Tenant, SvcCgcsAuto
from consts.cgcs import VMStatus, UUID, BOOT_FROM_VOLUME, NovaCLIOutput, EXT_IP, InstanceTopology, VifMapping, \
    VMNetworkStr, EventLogID
from consts.filepaths import TiSPath, VMPath, UserData, TestServerPath
from consts.proj_vars import ProjVar
from consts.timeout import VMTimeout, CMDTimeout

from keywords import network_helper, nova_helper, cinder_helper, host_helper, glance_helper, common, system_helper
from testfixtures.recover_hosts import HostsToRecover

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
            return True
        time.sleep(3)

    return False


def attach_vol_to_vm(vm_id, vol_id=None, con_ssh=None, auth_info=None):
    if vol_id is None:
        vols = cinder_helper.get_volumes(auth_info=auth_info, con_ssh=con_ssh, status='available')
        if vols:
            vol_id = random.choice(vols)
        else:
            vol_id = cinder_helper.create_volume(auth_info=auth_info, con_ssh=con_ssh)[1]

    LOG.info("Attaching volume {} to vm {}".format(vol_id, vm_id))
    cli.nova('volume-attach', ' '.join([vm_id, vol_id]))

    if not wait_for_vol_attach(vm_id=vm_id, vol_id=vol_id, con_ssh=con_ssh, auth_info=auth_info):
        raise exceptions.VMPostCheckFailed("Volume {} is not attached to vm {} within {} seconds".
                                           format(vol_id, vm_id, VMTimeout.VOL_ATTACH))

    LOG.info("Volume {} is attached to vm {}".format(vol_id, vm_id))


def boot_vm(name=None, flavor=None, source=None, source_id=None, min_count=None, nics=None, hint=None,
            max_count=None, key_name=None, swap=None, ephemeral=None, user_data=None, block_device=None,
            block_device_mapping=None,  vm_host=None, avail_zone=None, file=None, config_drive=False,
            fail_ok=False, auth_info=None, con_ssh=None, reuse_vol=False, guest_os='', poll=True):
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
        swap (int):
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
        fail_ok (bool):
        reuse_vol (bool): whether or not to reuse the existing volume
        guest_os (str): Valid values: 'cgcs-guest', 'ubuntu_14', 'centos_6', 'centos_7', etc
        poll (bool):

    Returns (tuple): (rtn_code(int), new_vm_id_if_any(str), message(str), new_vol_id_if_any(str))
        (0, vm_id, 'VM is booted successfully', <new_vol_id>)   # vm is created successfully and in Active state.
        (1, vm_id, <stderr>, <new_vol_id_if_any>)      # boot vm cli command failed, but vm is still booted
        (2, vm_id, "VM building is not 100% complete.", <new_vol_id>)   # boot vm cli accepted, but vm building is not
            100% completed. Only applicable when poll=True
        (3, vm_id, "VM <uuid> did not reach ACTIVE state within <seconds>. VM status: <status>", <new_vol_id>)
            # vm is not in Active state after created.
        (4, '', <stderr>, <new_vol_id>): create vm cli command failed, vm is not booted

    """
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

    # Handle mandatory arg - nics
    if not nics:
        mgmt_net_id = network_helper.get_mgmt_net_id(auth_info=auth_info, con_ssh=con_ssh)
        if not mgmt_net_id:
            raise exceptions.NeutronError("Cannot find management network")
        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}]

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
        source = 'volume'

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
        img_name = guest_os if guest_os else 'cgcs-guest'
        image = source_id if source_id else glance_helper.get_image_id_from_name(img_name, strict=True)

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

    if user_data is None and guest_os and 'cgcs-guest' not in guest_os:
        # create userdata cloud init file to run right after vm initialization to get ip on interfaces other than eth0.
        user_data = _create_cloud_init_if_conf(guest_os, nics_num=len(nics))

        # # Add wrsroot/li69nux user to non cgcs-guest vm
        # user_data_adduser = _get_cloud_config_add_user(con_ssh=con_ssh)
        # user_data.append(user_data_adduser)

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

    if poll:
        args_ += ' --poll'

    LOG.info("Booting VM {}...".format(name))
    exitcode, output = cli.nova('boot', positional_args=args_, ssh_client=con_ssh,
                                fail_ok=fail_ok, rtn_list=True, timeout=VMTimeout.BOOT_VM, auth_info=auth_info)

    table_ = table_parser.table(output)
    vm_id = table_parser.get_value_two_col_table(table_, 'id')

    if exitcode == 1:
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

    tmout = VMTimeout.STATUS_CHANGE
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


def wait_for_vm_pingable_from_natbox(vm_id, timeout=180, fail_ok=False, con_ssh=None, use_fip=False):
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
        msg = "Ping from NatBox to vm {} failed.".format(vm_id)
        if fail_ok:
            LOG.warning(msg)
            return False
        else:
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
        args_ = '--pub_key /home/wrsroot/.ssh/id_rsa.pub keypair-' + tenant
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
    return int(vm_limit) if vm_limit else 0


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

    with host_helper.ssh_to_host('controller-0') as host_ssh:
        vm_limit = host_ssh.exec_cmd("grep --color='never' -r {} lab_setup.conf | cut -d = -f2".
                                     format(VifMapping.VIF_MAP[vm_type]))[1]

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


def live_migrate_vm(vm_id, destination_host='', con_ssh=None, block_migrate=None, fail_ok=False,
                    auth_info=Tenant.ADMIN):
    """

    Args:
        vm_id (str):
        destination_host (str): such as compute-0, compute-1
        con_ssh (SSHClient):
        block_migrate (bool): whether to add '--block-migrate' to command
        fail_ok (bool): if fail_ok, return a numerical number to indicate the execution status
                One exception is if the live-migration command exit_code > 1, which indicating the command itself may
                be incorrect. In this case CLICommandFailed exception will be thrown regardless of the fail_ok flag.
        auth_info (dict):

    Returns (tuple): (return_code (int), error_msg_if_migration_rejected (str))
        (0, 'Live migration is successful.'):
            live migration succeeded and post migration checking passed
        (1, <cli stderr>):
            live migration request rejected as expected. e.g., no available destination host,
            or live migrate a vm with block migration
        (2, <cli stderr>): live migration request rejected due to unknown reason.
        (3, 'Post action check failed: VM is in ERROR state.'):
            live migration command executed successfully, but VM is in Error state after migration
        (4, 'Post action check failed: VM is not in original state.'):
            live migration command executed successfully, but VM is not in before-migration-state
        (5, 'Post action check failed: VM host did not change!'):
            live migration command executed successfully, but VM is still on the same host after migration

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
    if block_migrate:
        optional_arg = '--block-migrate'
    else:
        optional_arg = ''

    before_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    before_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh,
                                                       auth_info=Tenant.ADMIN)
    if not before_status == VMStatus.ACTIVE:
        LOG.warning("Non-active VM status before live migrate: {}".format(before_status))

    extra_str = ''
    if not destination_host == '':
        extra_str = ' to ' + destination_host
    LOG.info("Live migrating VM {} from {}{} started.".format(vm_id, before_host, extra_str))
    positional_args = ' '.join([optional_arg.strip(), str(vm_id), destination_host]).strip()
    exit_code, output = cli.nova('live-migration', positional_args=positional_args, ssh_client=con_ssh, fail_ok=True,
                                 auth_info=auth_info)

    if exit_code == 1:
        LOG.warning("Live migration of vm {} failed. Checking if this is expected failure...".format(vm_id))
        if _is_live_migration_allowed(vm_id, block_migrate=block_migrate) and \
                (destination_host or get_dest_host_for_live_migrate(vm_id)):
            if fail_ok:
                return 2, output
            else:
                raise exceptions.VMPostCheckFailed("Unexpected failure of live migration!")
        else:
            LOG.debug("System does not allow live migrating vm {} as expected.".format(vm_id))
            return 1, output
    elif exit_code > 1:             # this is already handled by CLI module
        raise exceptions.CLIRejected("Live migration command rejected.")

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
        if fail_ok:
            return 5, "Post action check failed: VM host did not change!"
        else:
            raise exceptions.VMPostCheckFailed("VM did not migrate to other host! VM: {}, Status:{}, Host: {}".
                                               format(vm_id, before_status, after_host))

    LOG.info("VM {} successfully migrated from {} to {}".format(vm_id, before_host, after_host))
    return 0, "Live migration is successful."


def _is_live_migration_allowed(vm_id, con_ssh=None, block_migrate=None):
    vm_info = VMInfo.get_vm_info(vm_id, con_ssh=con_ssh)
    storage_backing = vm_info.get_storage_type()
    vm_boot_from = vm_info.boot_info['type']
    has_volume_attached = vm_info.has_volume_attached()

    if vm_boot_from == 'image' and storage_backing == 'local_image' and not has_volume_attached:
        return True

    elif block_migrate:
        LOG.warning("Live migration with block is not allowed for vm {}".format(vm_id))
        return False

    # auto choose block-mig with local disk
    elif vm_info.has_local_disks():
        if storage_backing == 'remote':
            return True
        else:
            LOG.warning("Live migration is not allowed for localdisk vm with non-remote storage. vm: {}".format(vm_id))
            return False

    # auto choose block-mig without local disk
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
    candidate_hosts = host_helper.get_nova_hosts_with_storage_backing(storage_backing=vm_storage_backing,
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
        if len(host_helper.get_nova_hosts_with_storage_backing(vm_storage_backing, con_ssh=con_ssh)) < 2:
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
              net_types='mgmt', retry=3, retry_interval=3, vlan_zero_only=True):
    """

    Args:
        vm_ids (list|str): list of vms to ping
        ssh_client (SSHClient): ping from this ssh client. Usually a natbox' ssh client or another vm's ssh client
        con_ssh (SSHClient): active controller ssh client to run cli command to get all the management ips
        num_pings (int): number of pings to send
        timeout (int): timeout waiting for response of ping messages in seconds
        fail_ok (bool): Whether it's okay to have 100% packet loss rate.
        use_fip (bool): Whether to ping floating ip only if a vm has more than one management ips

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

    valid_net_types = ['mgmt', 'data', 'internal']
    if not set(net_types) <= set(valid_net_types):
        raise ValueError("Invalid net type(s) provided. Valid net_types: {}. net_types given: {}".
                         format(valid_net_types, net_types))

    vms_ips = []
    if 'mgmt' in net_types:
        mgmt_ips = network_helper.get_mgmt_ips_for_vms(vms=vm_ids, con_ssh=con_ssh, use_fip=use_fip)
        vms_ips += mgmt_ips
        if not mgmt_ips:
            raise exceptions.VMNetworkError("Management net ip is not found for vms {}".format(vm_ids))

    if 'data' in net_types:
        data_ips = network_helper.get_data_ips_for_vms(vms=vm_ids, con_ssh=con_ssh)
        vms_ips += data_ips
        if not data_ips:
            raise exceptions.VMNetworkError("Data network ip is not found for vms {}".format(vm_ids))

    if 'internal' in net_types:
        internal_ips = network_helper.get_internal_ips_for_vms(vms=vm_ids, con_ssh=con_ssh)
        if not internal_ips:
            raise exceptions.VMNetworkError("Internal net ip is not found for vms {}".format(vm_ids))
        if vlan_zero_only:
            internal_ips = network_helper.filter_ips_with_subnet_vlan_id(internal_ips, vlan_id=0, con_ssh=con_ssh)
            if not internal_ips:
                raise exceptions.VMNetworkError("Internal net ip with subnet vlan id 0 is not found for vms {}".
                                                format(vm_ids))
        vms_ips += internal_ips

    res_bool = False
    res_dict = {}
    for i in range(retry + 1):
        for ip in vms_ips:
            packet_loss_rate = network_helper._ping_server(server=ip, ssh_client=ssh_client, num_pings=num_pings,
                                                           timeout=timeout, fail_ok=True)[0]
            res_dict[ip] = packet_loss_rate

        res_bool = not any(loss_rate == 100 for loss_rate in res_dict.values())
        if res_bool:
            LOG.info("Ping successful from {}: {}".format(ssh_client.host, res_dict))
            return res_bool, res_dict

        if i < retry:
            LOG.info("Retry in {} seconds".format(retry_interval))
            time.sleep(retry_interval)

    if not res_dict:
        raise ValueError("Ping res dict contains no result.")

    err_msg = "Ping unsuccessful from {}: {}".format(ssh_client.host, res_dict)
    if fail_ok:
        LOG.info(err_msg)
        return res_bool, res_dict
    else:
        raise exceptions.VMNetworkError(err_msg)


def ping_vms_from_natbox(vm_ids=None, natbox_client=None, con_ssh=None, num_pings=5, timeout=15, fail_ok=False,
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
    if not natbox_client:
        natbox_client = NATBoxClient.get_natbox_client()

    return _ping_vms(vm_ids=vm_ids, ssh_client=natbox_client, con_ssh=con_ssh, num_pings=num_pings, timeout=timeout,
                     fail_ok=fail_ok, use_fip=use_fip, net_types='mgmt', retry=retry)


def ping_vms_from_vm(to_vms=None, from_vm=None, user=None, password=None, prompt=None, con_ssh=None, natbox_client=None,
                     num_pings=5, timeout=15, fail_ok=False, from_vm_ip=None, to_fip=False, from_fip=False,
                     net_types='mgmt', retry=3, retry_interval=3, vlan_zero_only=True):
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

    with ssh_to_vm_from_natbox(vm_id=from_vm, username=user, password=password, natbox_client=natbox_client,
                               prompt=prompt, con_ssh=con_ssh, vm_ip=from_vm_ip, use_fip=from_fip) as from_vm_ssh:

        from_vm_ssh.exec_cmd("ip addr")
        res = _ping_vms(ssh_client=from_vm_ssh, vm_ids=to_vms, con_ssh=con_ssh, num_pings=num_pings, timeout=timeout,
                        fail_ok=fail_ok, use_fip=to_fip, net_types=net_types, retry=retry,
                        retry_interval=retry_interval, vlan_zero_only=vlan_zero_only)
        return res


def ping_ext_from_vm(from_vm, ext_ip=None, user=None, password=None, prompt=None, con_ssh=None, natbox_client=None,
                     num_pings=5, timeout=15, fail_ok=False, vm_ip=None, use_fip=False):

    if ext_ip is None:
        ext_ip = EXT_IP

    with ssh_to_vm_from_natbox(vm_id=from_vm, username=user, password=password, natbox_client=natbox_client,
                               prompt=prompt, con_ssh=con_ssh, vm_ip=vm_ip, use_fip=use_fip) as from_vm_ssh:
        return network_helper._ping_server(ext_ip, ssh_client=from_vm_ssh, num_pings=num_pings,
                                           timeout=timeout, fail_ok=fail_ok)[0]


@contextmanager
def ssh_to_vm_from_natbox(vm_id, vm_image_name=None, username=None, password=None, prompt=None,
                          timeout=VMTimeout.SSH_LOGIN, natbox_client=None, con_ssh=None, vm_ip=None,
                          vm_ext_port=None, use_fip=False,  retry=True, retry_timeout=120, close_ssh=True):
    """
    ssh to a vm from natbox.

    Args:
        vm_id (str): vm to ssh to
        vm_image_name (str): such as cgcs-guest
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

    vm_name = nova_helper.get_vm_name_from_id(vm_id=vm_id)

    if vm_ip is None:
        vm_ip = network_helper.get_mgmt_ips_for_vms(vms=vm_id, use_fip=use_fip)[0]

    if not natbox_client:
        natbox_client = NATBoxClient.get_natbox_client()

    vm_ssh = VMSSHClient(natbox_client=natbox_client, vm_ip=vm_ip, vm_ext_port=vm_ext_port, vm_name=vm_name, vm_img_name=vm_image_name,
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
        self.table_ = table_parser.table(cli.nova('show', self.vm_id, ssh_client=self.con_ssh, auth_info=self.auth_info,
                                                  timeout=5))

    def __get_nics(self):
        raw_nics = table_parser.get_value_two_col_table(self.initial_table_, 'wrs-if:nics')
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
            image_name = table_parser.get_value_two_col_table(image_show_table, 'image_name', strict=False)
        else:      # booted from volume
            vol_show_table = table_parser.table(cli.cinder('show', self.boot_info['id']))
            image_meta_data = table_parser.get_value_two_col_table(vol_show_table, 'volume_image_metadata')
            image_name = eval(image_meta_data)['image_name']

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


def _wait_for_vms_values(vms, header='Status', values=VMStatus.ACTIVE, timeout=VMTimeout.STATUS_CHANGE, fail_ok=True,
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

    code, output = cli.nova('reboot', arg, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True,
                            timeout=cli_timeout)

    if code == 1:
        return 1, output

    expt_reboot = VMStatus.HARD_REBOOT if hard else VMStatus.SOFT_REBOOT
    _wait_for_vm_status(vm_id, expt_reboot, check_interval=1, fail_ok=False)

    actual_status = _wait_for_vm_status(vm_id, [VMStatus.ACTIVE, VMStatus.ERROR], fail_ok=fail_ok, con_ssh=con_ssh,
                                        timeout=reboot_timeout)
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

    res_bool, res_pass, res_fail = _wait_for_vms_values(vms_to_check, 'Status', [expt_status, VMStatus.ERROR],
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
        image_id = glance_helper.get_image_id_from_name('cgcs-guest', strict=True)

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
                b, e = cpus.split('-')[0:2]
                results += list(range(int(b), int(e) + 1))
            else:
                results.append(int(cpus))
    return results


def _parse_cpu_siblings(siblings_str):
    results = []

    found = re.search(r'[,]?\s*siblings:\s*((\{\d+\,\d+\})(,(\{\d+\,\d+\}))*)', siblings_str, re.IGNORECASE)

    if found:
        for cpus in found.group(1).split('},'):
            if not cpus:
                continue
            n1, n2 = cpus[1:].split(',')
            results.append((n1, n2))

    return results


def get_vm_pcis_irqs_from_hypervisor(vm_id, hypervisor=None, con_ssh=None, retries=3, retry_interval=45):
    """
    Get information for all PCI devices using tool nova-pci-interrupts.

    Args:
        vm_id (str):
        con_ssh:

    Returns (pci_info, vm_topology): details of the PCI device and VM topology
        Examples:
            vm_topology:
            {
                "memory":1024,
                "numa_node":1,
                "pcpus":[35,15,10,30,16],
                "siblings":[],
                "vcpus":[0,1,2,3,4]
            }

            pci_info:
            {
                "memory":1024, "numa_node":1, "pcpus":[35, 15, 10, 30, 16], "siblings":[],"vcpus":[0,1,2,3,4]}

                pci_info:
                    {"0000:83:03.7":{
                        "cpulist":[10,15,16,30,35],
                        "irq":"69",
                        "msi_irqs":"69",
                        "nic":"83:03.7 Co-processor: Intel Corporation DH895XCC Series QAT Virtual Function",
                        "numa_node":"1",
                        "product":"0443",
                        "vendor":"8086"
                    },
            }


    """
    hypervisor = hypervisor or get_vm_host_and_numa_nodes(vm_id=vm_id, con_ssh=con_ssh)[0]

    details = ''
    try_count = 0
    while try_count < retries and not details:
        with host_helper.ssh_to_host(hypervisor, con_ssh=con_ssh) as compute_ssh:
            code, details = compute_ssh.exec_sudo_cmd('nova-pci-interrupts')

        try_count += 1
        time.sleep(retry_interval)

    pci_infos = {}
    vm_topology = {}
    stage = 0
    prev_pci_addr = None
    for line in details.splitlines():
        if stage == 0:
            begin =  re.match(r'^\s*\|\s*{}\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)\|\s*'.format(vm_id), line)
            if begin:
                topology_str = begin.group(1)
                numa_node = re.search(r'node:\s*(\d+)', topology_str, re.IGNORECASE)
                if numa_node:
                    vm_topology['numa_node'] = numa_node.group(1)

                memory = re.search(r'[,]?\s*(\d+)(MB|GB)', topology_str, re.IGNORECASE)
                if memory:
                    memory_size = int(memory.group(1))
                    memory_size *= 1024 if memory.group(2).upper() == 'GB' else 1
                    vm_topology['memory'] = memory_size

                vm_topology['vcpus'] = parse_cpu_list(topology_str, 'vcpus:')
                vm_topology['pcpus'] = parse_cpu_list(topology_str, 'pcpus:')
                vm_topology['siblings'] = _parse_cpu_siblings(topology_str)

                pci_info = re.search(
                    '\|\s*node:(\d+)\,\s*addr:(\w{4}:\w{2}:\w{2}\.\w),\s*type:([^\,]+),\s*vendor:([^\,]+),\s*product:([^\|]+)\s*\|', line)

                if pci_info:
                    pci_numa_node, pci_addr, pci_type, vendor, product = pci_info.groups()
                    pci_infos[pci_addr] = {
                        'node': pci_numa_node, 'addr': pci_addr, 'type': pci_type, 'vendor': vendor, 'product': product}
                stage = 1
                continue

        elif stage == 1:
            pci_info = re.match(
                '\|\s*node:(\d+)\,\s*addr:(\w{4}:\w{2}:\w{2}\.\w),\s*type:([^\,]+),\s*vendor:([^\,]+),\s*product:([^\|]+)\s*\|', line)

            if pci_info:
                pci_numa_node, pci_addr, pci_type, vendor, product = pci_info.groups()
                pci_infos[pci_addr] = {
                    'node': pci_numa_node, 'addr': pci_addr, 'type': pci_type, 'vendor': vendor, 'product': product}
                continue
            else:
                stage = 2

        if stage == 2:
            all_pcis = re.search('INFO Found: pci_addrs:((\s*(\w{4}:\w{2}:\w{2}\.\w))+)', line)
            if all_pcis:
                # this list contains all pci-addrs for all the VMs on the host, so we have to remove those for other VMs
                pci_infos['pci_addr_list'] = list(pci_infos.keys())
                stage = 3
                continue

        if stage == 3:
            pci_raw = re.match(r'.*INFO addr:\s*(\w{4}:\w{2}:\w{2}\.\w)\s*(.*)', line)
            if pci_raw:
                pci_addr = str(pci_raw.group(1))
                prev_pci_addr = pci_addr

                if pci_addr not in pci_infos:
                    LOG.warn('UNKNOWN pci_addr:{}, \nraw line:\n{}'.format(pci_addr, line))
                else:
                    pci_info, nic_info = pci_raw.group(2).split(';')
                    pci = re.findall('([^: ]+):([^ :]*)', pci_info)
                    pci_infos[pci_addr].update({k.strip(): v.strip() for k, v in dict(pci).items()})
                    pci_infos[pci_addr].update(
                        {pci[-1][0].strip(): pci_info.split(':')[-1].strip(), 'nic': nic_info.strip()})
                continue

            irq_cpulist = re.search('irq:(\d+) \s*cpulist:(.*)$', line)
            if irq_cpulist:
                irq = irq_cpulist.group(1)
                cpulist = parse_cpu_list(irq_cpulist.group(2))
                # LOG.info('pci_addr:{}\ncpulist:{}\n'.format(prev_pci_addr or '', cpulist))

                if prev_pci_addr is not None and prev_pci_addr in pci_infos:
                    if irq != pci_infos[prev_pci_addr]['irq'] and irq not in pci_infos[prev_pci_addr]['msi_irqs']:
                        LOG.warn('Mismatched irq, expecting:{}, actual:{}, \nline:\n{}\n'.format(
                            pci_infos[prev_pci_addr]['irq'], irq, line))
                        pci_infos[prev_pci_addr]['irq'] = irq
                    # simply update the cpulist with the assumption all cpulists are same
                    pci_infos[prev_pci_addr]['cpulist'] = sorted(set(cpulist))
                else:
                    LOG.warn('UNKOWN PCI addr:{} to vm:{}'.format(prev_pci_addr, vm_id))

    # make sure to exclude irrelated PCI info
    for pci_addr in list(pci_infos.keys()):
        if pci_addr == 'pci_addr_list':
            continue
        if pci_addr not in pci_infos['pci_addr_list']:
            pci_infos.pop(pci_addr)

    return pci_infos, vm_topology


def get_instance_topology(vm_id, con_ssh=None, source='vm-topology'):
    """
    Get instance_topology from 'vm-topology -s servers'

    Args:
        vm_id (str):
        # rtn_list (bool):
        con_ssh (SSHClient):
        source (str): 'vm-topology' or 'nova show'

    Returns (list|dict):

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
                elif key_ in ['vcpus', 'pcpus']:
                    values = value_.split(sep=',')
                    for val in value_.split(sep=','):
                        # convert '3-6' to [3, 4, 5, 6]
                        if '-' in val:
                            values.remove(val)
                            min_, max_ = val.split(sep='-')
                            values += list(range(int(min_), int(max_) + 1))

                    value_ = sorted([int(val) for val in values])

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
                # TODO add mem size

        # Add as None if item is not displayed in vm-topology
        all_keys = ['node', 'pgsize', 'vcpus', 'pcpus', 'pol', 'thr', 'siblings', 'topology']   # TODO: add mem
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


def add_vlan_for_vm_pcipt_interfaces(vm_id, net_seg_id, retry=3):
    """
    Add vlan for vm pci-passthrough interface and restart networking service.
    Do nothing if expected vlan interface already exists in 'ip addr'.

    Args:
        vm_id (str):
        net_seg_id (int|str): such as 1792
        retry (int): max number of times to reboot vm to try to recover it from non-exit

    Returns: None

    Raises: VMNetworkError if vlan interface is not found in 'ip addr' after adding

    Notes:
        Known openstack issue that will not be fixed: CGTS-4705.
        Sometimes a non-exist 'rename6' interface will be used for pci-passthrough nic after vm maintenance
        Sudo reboot from the vm as workaround.
        By default will try to reboot for a maximum of 3 times

    """
    if not vm_id or not net_seg_id:
        raise ValueError("vm_id and/or net_seg_id not provided.")

    for i in range(retry):
        vm_pcipt_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id, vif_model='pci-passthrough')

        if not vm_pcipt_nics:
            LOG.warning("No pci-passthrough device found for vm from nova show {}".format(vm_id))
            return

        with ssh_to_vm_from_natbox(vm_id=vm_id) as vm_ssh:
            for pcipt_nic in vm_pcipt_nics:
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
                    vlan_name = "{}.{}".format(eth_name, net_seg_id)

                    output_pre_ipaddr = vm_ssh.exec_cmd('ip addr', fail_ok=False)[1]
                    if vlan_name in output_pre_ipaddr:
                        LOG.info("{} already in ip addr. Skip.".format(vlan_name))
                        continue

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
                    vm_ssh.exec_cmd("/etc/init.d/networking restart", expect_timeout=60)
                    output_pre_ipaddr = vm_ssh.exec_cmd('ip addr', fail_ok=False)[1]
                    if vlan_name not in output_pre_ipaddr:
                        raise exceptions.VMNetworkError("vlan {} is not found in 'ip addr' after restarting networking "
                                                        "service.".format(vlan_name))
                    LOG.info("vlan {} is successfully added.".format(vlan_name))
            else:
                return

            LOG.info("Reboot vm completed. Retry started.")

    else:
        raise exceptions.VMNetworkError("pci-passthrough interface(s) not found in vm {}".format(vm_id))


def sudo_reboot_from_vm(vm_id, vm_ssh=None, check_host_unchanged=True, con_ssh=None):

    if check_host_unchanged:
        pre_vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)

    LOG.info("Initiate sudo reboot from vm")

    def _sudo_reboot(vm_ssh_):
        code, output = vm_ssh_.exec_sudo_cmd('reboot', get_exit_code=False)
        expt_string = 'The system is going down for reboot'
        if expt_string in output:
            # Sometimes system rebooting msg will be displayed right after reboot cmd sent
            vm_ssh_.parent.flush()
            return
        try:
            index = vm_ssh_.expect([expt_string, vm_ssh.prompt], timeout=60)
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
        guest_os = 'ubuntu_14'
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
                                                                 dest_name=file_name, is_dir=False, con_ssh=con_ssh)

    if dest_path is None:
        raise exceptions.CommonError("userdata file {} does not exist after download".format(file_path))

    return file_path


def modified_cold_migrate_vm(vm_id, revert=False, con_ssh=None, fail_ok=False, auth_info=Tenant.ADMIN, vm_image_name='cgcs-guest'):
    """
    Cold migrate modifed for CGTS-4911
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
        if len(host_helper.get_nova_hosts_with_storage_backing(vm_storage_backing, con_ssh=con_ssh)) < 2:
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
        To terminate the dd to release the cpu resources, use: vm_ssh.exec_cmd('killall dd')
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
        vm_ssh_.exec_cmd('killall dd')

    thread.set_end_func(_kill_dd, vm_ssh)
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


def evacuate_vms(host, vms_to_check, con_ssh=None, timeout=600, wait_for_host_up=False, fail_ok=False):

    LOG.info("Evacuate following vms from {}: {}".format(host, vms_to_check))
    host_helper.reboot_hosts(host, wait_for_reboot_finish=wait_for_host_up, con_ssh=con_ssh)
    HostsToRecover.add(host)

    if not wait_for_host_up:
        LOG.info("Wait for vms to reach ERROR or REBUILD state with best effort")
        _wait_for_vms_values(vms_to_check, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120,
                             con_ssh=con_ssh)

    LOG.tc_step("Check vms are in Active state and moved to other host(s) after host reboot")
    res, active_vms, inactive_vms = _wait_for_vms_values(vms=vms_to_check, values=VMStatus.ACTIVE, timeout=timeout,
                                                         con_ssh=con_ssh)

    vms_host_err = []
    for vm in vms_to_check:
        if nova_helper.get_vm_host(vm) == host:
            vms_host_err.append(vm)

    if inactive_vms:
        err_msg = "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)
        if fail_ok:
            LOG.warning(err_msg)
            return 1, inactive_vms
        raise exceptions.VMError(err_msg)

    if vms_host_err:
        err_msg = "Following VMs stayed on the same host {}: {}\nVMs did not reach Active state: {}".\
            format(host, vms_host_err, inactive_vms)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, vms_host_err
        raise exceptions.VMError(err_msg)

    LOG.info("All vms are successfully evacuated to other host")
    return 0, []