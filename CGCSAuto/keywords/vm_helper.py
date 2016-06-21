import random
import re
import time
from collections import Counter
from contextlib import contextmanager

from utils import exceptions, cli, table_parser
from utils.ssh import NATBoxClient, VMSSHClient, ControllerClient
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.timeout import VMTimeout
from consts.cgcs import VMStatus, PING_LOSS_RATE, UUID, BOOT_FROM_VOLUME, NovaCLIOutput, EXT_IP
from keywords import network_helper, nova_helper, cinder_helper, host_helper, glance_helper, common


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
            max_count=None, key_name=None, swap=None, ephemeral=None, user_data=None, block_device=None, fail_ok=False,
            auth_info=None, con_ssh=None):
    """

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
        user_data (str):
        block_device:
        auth_info (dict):
        con_ssh (SSHClient):
        nics (list): [{'net-id': <net_id1>, 'vif-model': <vif1>}, {'net-id': <net_id2>, 'vif-model': <vif2>}, ...]
        hint (dict): key/value pair(s) sent to scheduler for custom use. such as group=<server_group_id>
        fail_ok (bool):

    Returns (tuple): (rtn_code(int), new_vm_id_if_any(str), message(str), new_vol_id_if_any(str))
        (0, vm_id, 'VM is booted successfully', <new_vol_id>)   # vm is created successfully and in Active state.
        (1, vm_id, <stderr>, <new_vol_id_if_any>)      # boot vm cli command failed, but vm is still booted
        (2, vm_id, "VM building is not 100% complete.", <new_vol_id>)   # boot vm cli accepted, but vm building is not
            100% completed.
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

    # if name is None:
    #     existing_names = nova_helper.get_all_vms('Name')
    #     for i in range(20):
    #         tmp_name = '-'.join([tenant, 'vm', str(i+1)])
    #         if tmp_name not in existing_names:
    #             name = tmp_name
    #             break
    #     else:
    #         exceptions.VMError("Unable to get a proper name for booting new vm.")
    # else:
    #     name = '-'.join([tenant, name])

    # Handle mandatory arg - flavor
    if flavor is None:
        flavor = nova_helper.get_basic_flavor(auth_info=auth_info, con_ssh=con_ssh)

    # Handle mandatory arg - nics
    if not nics:
        mgmt_net_id = network_helper.get_mgmt_net_id(auth_info=auth_info, con_ssh=con_ssh)
        tenant_net_id = network_helper.get_tenant_net_id(auth_info=auth_info, con_ssh=con_ssh)
        tenant_vif = random.choice(['virtio', 'avp'])
        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': tenant_vif}]
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
            is_new, volume_id = cinder_helper.get_any_volume(new_name=vol_name, auth_info=auth_info, con_ssh=con_ssh)
            if is_new:
                new_vol = volume_id
    elif source.lower() == 'image':
        image = source_id if source_id else glance_helper.get_image_id_from_name('cgcs-guest')
    elif source.lower() == 'snapshot':
        if not snapshot_id:
            snapshot_id = cinder_helper.get_snapshot_id(auth_info=auth_info, con_ssh=con_ssh)
            if not snapshot_id:
                raise ValueError("snapshot id is required to boot vm; however no snapshot exists on the system.")
    # Handle mandatory arg - key_name
    key_name = key_name if key_name is not None else get_any_keypair(auth_info=auth_info, con_ssh=con_ssh)

    if hint:
        hint = ','.join(["{}={}".format(key, hint[key]) for key in hint])

    optional_args_dict = {'--flavor': flavor,
                          '--image': image,
                          '--boot-volume': volume_id,
                          '--snapshot': snapshot_id,
                          '--min-count': str(min_count) if min_count is not None else None,
                          '--max-count': str(max_count) if max_count is not None else None,
                          '--key-name': key_name,
                          '--swap': swap,
                          '--ephemeral': ephemeral,
                          '--user-data': user_data,
                          '--block-device': block_device,
                          '--hint': hint
                          }

    args_ = ' '.join([__compose_args(optional_args_dict), nics_args, name])

    LOG.info("Booting VM {}...".format(name))
    exitcode, output = cli.nova('boot --poll', positional_args=args_, ssh_client=con_ssh,
                                fail_ok=fail_ok, rtn_list=True, timeout=VMTimeout.BOOT_VM, auth_info=auth_info)

    table_ = table_parser.table(output)
    vm_id = table_parser.get_value_two_col_table(table_, 'id')

    if exitcode == 1:
        if vm_id:
            return 1, vm_id, output, new_vol       # vm_id = '' if cli is rejected without vm created
        return 4, '', output, new_vol     # new_vol = '' if no new volume created. Pass this to test for proper teardown

    LOG.info("Post action check...")
    if "100% complete" not in output:
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


def wait_for_vm_pingable_from_natbox(vm_id, timeout=180, fail_ok=True, con_ssh=None):
    """
    Wait for ping vm from natbox succeeds.

    Args:
        vm_id (str): id of the vm to ping
        timeout (int): max retry time for pinging vm
        fail_ok (bool): whether to raise exception if vm cannot be ping'd successfully from natbox within timeout
        con_ssh (SSHClient): TiS server ssh handle

    Returns (bool): True if ping vm succeeded, False otherwise.

    """
    ping_end_time = time.time() + timeout
    while time.time() < ping_end_time:
        if ping_vms_from_natbox(vm_ids=vm_id, fail_ok=True, con_ssh=con_ssh, num_pings=3)[0]:
            return True
    else:
        msg = "Ping from NatBox to vm {} failed.".format(vm_id)
        if fail_ok:
            LOG.warning(msg)
            return False
        else:
            raise exceptions.VMPostCheckFailed(msg)


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
    vif_mapping = {'vswitch': 'DPDKAPPS',
                   'avp': 'AVPAPPS',
                   'virtio': 'VIRTIOAPPS'
                   }

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
                                     format(vif_mapping[vm_type]))[1]

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


def live_migrate_vm(vm_id, destination_host='', con_ssh=None, block_migrate=False, fail_ok=False,
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

    LOG.info("Waiting for VM status change to original state {}".format(before_status))
    end_time = time.time() + VMTimeout.LIVE_MIGRATE_COMPLETE
    while time.time() < end_time:
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
        time.sleep(2)
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


def _is_live_migration_allowed(vm_id, con_ssh=None, block_migrate=False):
    vm_info = VMInfo.get_vm_info(vm_id, con_ssh=con_ssh)
    storage_backing = vm_info.get_storage_type()

    if block_migrate:
        vm_boot_from = vm_info.boot_info['type']
        has_volume_attached = vm_info.has_volume_attached()
        if vm_boot_from == 'image' and storage_backing == 'local_image' and not has_volume_attached:
            return True
        else:
            LOG.warning("Live migration with block is not allowed for vm {}".format(vm_id))
            return False

    elif vm_info.has_local_disks():
        if storage_backing == 'remote':
            return True
        else:
            LOG.warning("Live migration without block is not allowed for vm {}".format(vm_id))
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

    """
    before_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)
    before_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh)
    if not before_status == VMStatus.ACTIVE:
        LOG.warning("Non-active VM status before cold migrate: {}".format(before_status))

    LOG.info("Colding migrating VM {} from {}...".format(vm_id, before_host))
    exitcode, output = cli.nova('migrate --poll', vm_id, ssh_client=con_ssh, auth_info=auth_info,
                                timeout=VMTimeout.COLD_MIGRATE_CONFIRM, fail_ok=True, rtn_list=True)

    if exitcode == 1:
        vm_storage_backing = nova_helper.get_vm_storage_type(vm_id=vm_id, con_ssh=con_ssh)
        if len(host_helper.get_nova_hosts_with_storage_backing(vm_storage_backing, con_ssh=con_ssh)) < 2:
            LOG.info("Cold migration of vm {} rejected as expected due to no valid host to cold migrate to.".
                     format(vm_id))
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

    vm_status = _wait_for_vm_status(vm_id=vm_id, status=[VMStatus.VERIFY_RESIZE, VMStatus.ERROR], fail_ok=fail_ok,
                                    con_ssh=con_ssh)

    if vm_status is None:
        return 4, 'Timed out waiting for Error or Verify_Resize status for VM {}'.format(vm_id)

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


def resize_vm(vm_id, flavor_id, revert=False, con_ssh=None, fail_ok=False, auth_info=Tenant.ADMIN):
    before_flavor = nova_helper.get_vm_flavor(vm_id, con_ssh=con_ssh)
    before_status = nova_helper.get_vm_nova_show_value(vm_id, 'status', strict=True, con_ssh=con_ssh)
    if not before_status == VMStatus.ACTIVE:
        LOG.warning("Non-active VM status before cold migrate: {}".format(before_status))

    LOG.info("Resizing VM {} to flavor {}...".format(vm_id, flavor_id))
    exitcode, output = cli.nova('resize --poll', ' '.join([vm_id, flavor_id]), ssh_client=con_ssh, auth_info=auth_info,
                                timeout=VMTimeout.COLD_MIGRATE_CONFIRM, fail_ok=fail_ok, rtn_list=True)
    if exitcode == 1:
        return [exitcode, output]

    LOG.info("Waiting for VM status change to {}".format(VMStatus.VERIFY_RESIZE))
    vm_status = _wait_for_vm_status(vm_id=vm_id, status=[VMStatus.VERIFY_RESIZE, VMStatus.ERROR], fail_ok=fail_ok,
                                    con_ssh=con_ssh)

    if vm_status is None:
        return 2, 'Timed out waiting for Error or Verify_Resize status for VM {}'.format(vm_id)

    verify_resize_str = 'Revert' if revert else 'Confirm'
    if vm_status == VMStatus.VERIFY_RESIZE:
        LOG.info("{}ing resize..".format(verify_resize_str))
        _confirm_or_revert_resize(vm=vm_id, revert=revert, con_ssh=con_ssh)

    elif vm_status == VMStatus.ERROR:
        err_msg = "VM {} in Error state after resizing. {} resize is not reached.".format(vm_id, verify_resize_str)
        if fail_ok:
            return 3, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    post_confirm_state = _wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, timeout=VMTimeout.COLD_MIGRATE_CONFIRM,
                                             fail_ok=fail_ok, con_ssh=con_ssh)

    if post_confirm_state is None:
        err_msg = "VM {} is not in Active state after {} Resize".format(vm_id, verify_resize_str)
        return 4, err_msg

    after_flavor = nova_helper.get_vm_flavor(vm_id)
    if revert and after_flavor != before_flavor:
        err_msg = "Flavor is changed after revert resizing. Before flavor: {}, after flavor: {}".format(
                before_flavor, after_flavor)
        if fail_ok:
            return 5, err_msg
        raise exceptions.VMPostCheckFailed(err_msg)

    if not revert and after_flavor != flavor_id:
        err_msg = "VM flavor is not changed to expected after resizing. Before flavor: {}, after flavor: {}".format(
                flavor_id, before_flavor, after_flavor)
        if fail_ok:
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
            expt_val = kwargs[field]
            actual_val = table_parser.get_value_two_col_table(table_, field)
            results[field] = actual_val
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

    if fail_ok:
        LOG.warning("Timed out waiting for vm status: {}. Actual vm status: {}".format(status, current_status))
        return None
    else:
        raise exceptions.VMTimeout


def _confirm_or_revert_resize(vm, revert=False, con_ssh=None):
        if revert:
            cli.nova('resize-revert', vm, ssh_client=con_ssh, auth_info=Tenant.ADMIN)
        else:
            cli.nova('resize-confirm', vm, ssh_client=con_ssh, auth_info=Tenant.ADMIN)


__PING_LOSS_MATCH = re.compile(PING_LOSS_RATE)


def _ping_server(server, ssh_client, num_pings=5, timeout=15, fail_ok=False):
    """

    Args:
        server (str): server ip to ping
        ssh_client (SSHClient): ping from this ssh client
        num_pings (int):
        timeout (int): max time to wait for ping response in seconds
        fail_ok (bool): whether to raise exception if packet loss rate is 100%

    Returns (int): packet loss percentile, such as 100, 0, 25

    """
    cmd = 'ping -c {} {}'.format(num_pings, server)

    output = ssh_client.exec_cmd(cmd=cmd, expect_timeout=timeout)[1]
    packet_loss_rate = __PING_LOSS_MATCH.findall(output)[-1]
    packet_loss_rate = int(packet_loss_rate)

    if packet_loss_rate == 100:
        if not fail_ok:
            raise exceptions.VMNetworkError("Ping from {} to {} failed.".format(ssh_client.host, server))
    elif packet_loss_rate > 0:
        LOG.warning("Some packets dropped when ping from {} to {}. Packet loss rate: {}\%".
                    format(ssh_client.host, server, packet_loss_rate))
    else:
        LOG.info("All packets received by {}".format(server))

    return packet_loss_rate


def _ping_vms(ssh_client, vm_ids=None, con_ssh=None, num_pings=5, timeout=15, fail_ok=False, use_fip=False,
              net_types='mgmt'):
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

    vms_ips = []
    if 'data' in net_types:
        vms_ips += network_helper.get_data_ips_for_vms(vms=vm_ids, con_ssh=con_ssh, use_fip=use_fip)
    if 'mgmt' in net_types:
        vms_ips += network_helper.get_mgmt_ips_for_vms(vms=vm_ids, con_ssh=con_ssh, use_fip=use_fip)
    if not vms_ips:
        raise ValueError("Invalid net_types or vms ips for given net types are not found.")

    res_dict = {}
    for ip in vms_ips:
        packet_loss_rate = _ping_server(server=ip, ssh_client=ssh_client, num_pings=num_pings, timeout=timeout,
                                        fail_ok=fail_ok)
        res_dict[ip] = packet_loss_rate

    LOG.info("Ping results from {}: {}".format(ssh_client.host, res_dict))

    res_bool = not any(loss_rate == 100 for loss_rate in res_dict.values())
    return res_bool, res_dict


def ping_vms_from_natbox(vm_ids=None, natbox_client=None, con_ssh=None, num_pings=5, timeout=15, fail_ok=False,
                         use_fip=False):
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
                     fail_ok=fail_ok, use_fip=use_fip, net_types='mgmt')


def ping_vms_from_vm(to_vms=None, from_vm=None, user=None, password=None, prompt=None, con_ssh=None, natbox_client=None,
                     num_pings=5, timeout=15, fail_ok=False, from_vm_ip=None, to_fip=False, from_fip=False,
                     net_types='mgmt'):
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
        net_types (list|str): 'mgmt' or 'data'

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

        res = _ping_vms(ssh_client=from_vm_ssh, vm_ids=to_vms, con_ssh=con_ssh, num_pings=num_pings, timeout=timeout,
                        fail_ok=fail_ok, use_fip=to_fip, net_types=net_types)

    return res


def ping_ext_from_vm(from_vm, ext_ip=None, user=None, password=None, prompt=None, con_ssh=None, natbox_client=None,
                     num_pings=5, timeout=15, fail_ok=False, vm_ip=None, use_fip=False):

    if ext_ip is None:
        ext_ip = EXT_IP

    with ssh_to_vm_from_natbox(vm_id=from_vm, username=user, password=password, natbox_client=natbox_client,
                               prompt=prompt, con_ssh=con_ssh, vm_ip=vm_ip, use_fip=use_fip) as from_vm_ssh:
        return _ping_server(ext_ip, ssh_client=from_vm_ssh, num_pings=num_pings, timeout=timeout, fail_ok=fail_ok)


@contextmanager
def ssh_to_vm_from_natbox(vm_id, vm_image_name=None, username=None, password=None, prompt=None,
                          timeout=VMTimeout.SSH_LOGIN, natbox_client=None, con_ssh=None, vm_ip=None, use_fip=False,
                          retry=True, retry_timeout=120):
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

    vm_ssh = VMSSHClient(natbox_client=natbox_client, vm_ip=vm_ip, vm_name=vm_name, vm_img_name=vm_image_name,
                         user=username, password=password, prompt=prompt, timeout=timeout, retry=retry,
                         retry_timeout=retry_timeout)
    try:
        yield vm_ssh
    finally:
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


def delete_vms(vms=None, delete_volumes=True, check_first=True, timeout=VMTimeout.DELETE, fail_ok=False, con_ssh=None,
               auth_info=Tenant.ADMIN):
    """
    Delete given vm (and attached volume(s))

    Args:
        vms (list|str): list of vm ids to be deleted. If string input, assume only one vm id is provided.
        check_first (bool): Whether to check if given vm(s) exist on system before attempt to delete
        timeout (int): Max time to wait for delete cli finish and wait for vms actually disappear from system
        delete_volumes (bool): delete attached volume(s) if set to True
        fail_ok (bool):
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
        table_ = table_parser.table(cli.nova('list --all-tenant', ssh_client=con_ssh, auth_info=auth_info))
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
        table_ = table_parser.table(cli.nova('list --all-tenant', ssh_client=con_ssh, auth_info=auth_info))

        for vm_id in vms_to_check:
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


def reboot_vm(vm_id, hard=False, fail_ok=False, con_ssh=None, auth_info=None):
    vm_status = nova_helper.get_vm_status(vm_id, con_ssh=con_ssh)
    if not vm_status.lower() == 'active':
        LOG.warning("VM is not in active state before rebooting. VM status: {}".format(vm_status))

    extra_arg = '--hard ' if hard else ''
    arg = "{}{}".format(extra_arg, vm_id)

    code, output = cli.nova('reboot', arg, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    expt_reboot = VMStatus.HARD_REBOOT if hard else VMStatus.SOFT_REBOOT
    _wait_for_vm_status(vm_id, expt_reboot, check_interval=1, fail_ok=False)

    actual_status = _wait_for_vm_status(vm_id, [VMStatus.ACTIVE, VMStatus.ERROR], fail_ok=fail_ok, con_ssh=con_ssh)
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


def __perform_action_on_vm(vm_id, action, expt_status, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None,
                           auth_info=None):

    LOG.info("{}ing vm {}...".format(action, vm_id))
    code, output = cli.nova(action, vm_id, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

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

    succ_msg = "VM {}ed successfully.".format(action)
    LOG.info(succ_msg)
    return 0, succ_msg


def suspend_vm(vm_id, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_action_on_vm(vm_id, 'suspend', VMStatus.SUSPENDED, timeout=timeout, fail_ok=fail_ok,
                                  con_ssh=con_ssh, auth_info=auth_info)


def resume_vm(vm_id, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_action_on_vm(vm_id, 'resume', VMStatus.ACTIVE, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                                  auth_info=auth_info)


def pause_vm(vm_id, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_action_on_vm(vm_id, 'pause', VMStatus.PAUSED, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                                  auth_info=auth_info)


def unpause_vm(vm_id, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_action_on_vm(vm_id, 'unpause', VMStatus.ACTIVE, timeout=timeout, fail_ok=fail_ok, con_ssh=con_ssh,
                                  auth_info=auth_info)


def stop_vms(vms, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_action_on_vms(vms, 'stop', VMStatus.STOPPED, timeout, check_interval=1, fail_ok=fail_ok,
                                   con_ssh=con_ssh, auth_info=auth_info)


def start_vms(vms, timeout=VMTimeout.STATUS_CHANGE, fail_ok=False, con_ssh=None, auth_info=None):
    return __perform_action_on_vms(vms, 'start', VMStatus.ACTIVE, timeout, check_interval=1, fail_ok=fail_ok,
                                   con_ssh=con_ssh, auth_info=auth_info)


def __perform_action_on_vms(vms, action, expt_status, timeout=VMTimeout.STATUS_CHANGE, check_interval=3, fail_ok=False,
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
