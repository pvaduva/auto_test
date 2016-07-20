from pytest import fixture, mark
import time
from utils.tis_log import LOG
from utils import table_parser
from keywords import host_helper, vm_helper, nova_helper, cinder_helper, glance_helper, network_helper, system_helper
from consts.cgcs import VMStatus
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module', autouse=True)
def pre_alarm_():
    """
    Text fixture to get pre-test existing alarm list.
    Args:None

    Returns: list of alarms

    """
    pre_alarms = system_helper.get_alarms()
    pre_list = table_parser.get_all_rows(pre_alarms)
    return pre_list


@fixture(scope='module')
def flavor_id_():
    """
    Text fixture to get or create a flavor
    Args:None

    Returns: flavor_id

    """
    flavor_name = 'small'
    if nova_helper.flavor_exists(flavor_name, header="Name"):
        flavor_id = nova_helper.get_flavor_id(name='small')
    else:
        rc, flavor_id = nova_helper.create_flavor(name=flavor_name, vcpus=1, ram=512)
        ResourceCleanup.add('flavor', flavor_id, scope='module')

    return flavor_id


@fixture(scope='module')
def image_():
    """
    Text fixture to get guest image
    Args:

    Returns: the guest image id

    """
    return glance_helper.get_image_id_from_name(name='cgcs-guest')


@fixture(scope='module')
def net_():
    """
    Text fixture to get tenenat and managment netowrks
    Args:

    Returns: list of network dict as following:
        {'net-id' : <net_id> }

    """
    networks = []
    net_name = 'tenant1-net1'
    net_id = network_helper.get_tenant_net_id(net_name)

    network = {'net-id': net_id, }
    networks.append(network)

    net_id = network_helper.get_mgmt_net_id()
    if net_id is not None:
        network = {'net-id': net_id, }
        networks.append(network)
        
    return networks


@fixture(scope='function')
def volumes_(image_):
    """
    Text fixture to create two large cinder volumes with size of 20 and 40 GB.
    Args:
        image_: the guest image_id

    Returns: list of volume dict as following:
        {'id': <volume_id>,
         'display_name': <vol_inst1 or vol_inst2>,
         'size': <20 or 40>
        }
    """
    volumes = []
    cinder_params = [{'name': 'vol_inst1',
                      'size': 20},
                     {'name': 'vol_inst2',
                      'size': 40}]

    for param in cinder_params:
        volume_id = cinder_helper.create_volume(name=param['name'], image_id=image_, size=param['size'])[1]
        volume = {
            'id': volume_id,
            'display_name': param['name'],
            'size': param['size']
            }
        volumes.append(volume)
        ResourceCleanup.add('volume', volume['id'], scope='function')

    return volumes


@fixture(scope='function')
def vms_(volumes_, flavor_id_, net_):
    """
    Text fixture to create cinder volume with specific 'display-name', and 'size'
    Args:
        volumes_: list of two large volumes dict created by volumes_ fixture
        flavor_id_: flavor id from flavor_id_ fixture
        net_: tenant and management networks for vm boot.

    Returns: volume dict as following:
        {'id': <volume_id>,
         'display_name': <vol_inst1 or vol_inst2>,
         'size': <20 or 40>
        }
    """
    vms = []
    vm_names = ['test_inst1', 'test_inst2']
    index = 0
    for vol_params in volumes_:

        instance_name = vm_names[index]
        vm_id = vm_helper.boot_vm(name=instance_name, flavor=flavor_id_,  source='volume',
                                  source_id=vol_params['id'], nics=net_)[1]
        vm = {
                'id': vm_id,
                'display_name': instance_name,
             }
        vms.append(vm)
        ResourceCleanup.add('vm', vm_id, scope='function')
        index += 1
    return vms


@mark.skipif(len(system_helper.get_storage_nodes()) < 1, reason="No storage hosts on the system")
@mark.skipif(len(system_helper.get_computes()) < 2, reason="at least two computes are required")
def test_vm_with_a_large_volume_live_migrate(vms_):
    """
    Test instantiate a vm with a large volume ( 20 GB and 40 GB) and live migrate:
    Args:
        vms_ (dict): vms created by vms_ fixture

    Test Setups:
    - get tenant1 and management networks which are already created for lab setup
    - get or create a "small" flavor
    - get the guest image id
    - create two large volumes (20 GB and 40 GB) in cinder
    - boot two vms ( test_inst1, test_inst2) using  volumes 20 GB and 40 GB respectively


    Test Steps:
    - Verify VM status is ACTIVE
    - Validate that VMs boot, and that no timeouts or error status occur.
    - Verify the VM can be pinged from NATBOX
    - Verify login to VM and rootfs (dev/vda) filesystem is rw mode
    - Attempt to live migrate of VMs
    - Validate that the VMs migrated and no errors or alarms are present
    - Log into both VMs and validate that file systems are read-write
    - Terminate VMs

    Skip conditions:
     - less that two computes
     - no  storage node

    """
    for vm in vms_:

        LOG.tc_step("Checking VM status; VM Instance id is: {}......".format(vm['id']))
        vm_state = nova_helper.get_vm_status(vm['id'])

        assert vm_state == VMStatus.ACTIVE, 'VM {} state is {}; Not in ACTIVATE state as expected'\
            .format(vm['id'], vm_state)

        LOG.tc_step("Verify  VM can be pinged from NAT box...")
        rc, boot_time = check_vm_boot_time(vm['id'])
        assert rc,  "VM is not pingable after {} seconds ".format(boot_time)

        LOG.tc_step("Verify Login to VM and check filesystem is rw mode....")
        assert is_vm_filesystem_rw(vm['id']), 'rootfs filesystem is not RW as expected for VM {}'\
            .format(vm['display_name'])

        LOG.tc_step("Attempting  live migration; vm id = {}; vm_name = {} ....".format(vm['id'], vm['display_name']))

        code, msg = vm_helper.live_migrate_vm(vm_id=vm['id'],  fail_ok=True)
        LOG.tc_step("Verify live migration succeeded...")
        assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

        LOG.tc_step("Verifying  filesystem is rw mode after live migration....")
        assert is_vm_filesystem_rw(vm['id']), 'After live migration rootfs filesystem is not RW as expected for VM {}'.format(vm['display_name'])

        LOG.tc_step("Checking for any new system alarm....")
        rc, new_alarm = is_new_alarm_raised(pre_alarm_)
        assert not rc, " alarm(s) found: {}".format(new_alarm)


@mark.skipif(len(system_helper.get_storage_nodes()) < 1, reason="No storage hosts on the system")
@mark.skipif(len(system_helper.get_computes()) < 2, reason="at least two computes are required")
def test_vm_with_large_volume_and_evacuation(vms_):
    """
   Test instantiate a vm with a large volume ( 20 GB and 40 GB) and evacuate:

    Args:
        vms_ (dict): vms created by vms_ fixture

    Test Setups:
    - get tenant1 and management networks which are already created for lab setup
    - get or create a "small" flavor
    - get the guest image id
    - create two large volumes (20 GB and 40 GB) in cinder
    - boot two vms ( test_inst1, test_inst2) using  volumes 20 GB and 40 GB respectively


    Test Steps:
    - Verify VM status is ACTIVE
    - Validate that VMs boot, and that no timeouts or error status occur.
    - Verify the VM can be pinged from NATBOX
    - Verify login to VM and rootfs (dev/vda) filesystem is rw mode
    - live migrate, if required, to bring both VMs to the same compute
    - Validate  migrated VM and no errors or alarms are present
    - Reboot compute host to initiate evacuation
    - Verify VMs are evacuated
    - Check for any system alarms
    - Verify login to VM and rootfs (dev/vda) filesystem is still rw mode after evacuation
    - Terminate VMs

    Skip conditions:
    - less that two computes
    - no  storage node

    """

    for vm in vms_:

        LOG.tc_step("Checking VM status; VM Instance id is: {}......".format(vm['id']))
        vm_state = nova_helper.get_vm_status(vm['id'])
        assert vm_state == VMStatus.ACTIVE, 'VM {} state is {}; Not in ACTIVATE state as expected'\
            .format(vm['id'], vm_state)

        LOG.tc_step("Verify  VM can be pinged from NAT box...")
        rc, boot_time = check_vm_boot_time(vm['id'])
        assert rc, "VM is not pingable after {} seconds ".format(boot_time)

        LOG.tc_step("Verify Login to VM and check filesystem is rw mode....")
        assert is_vm_filesystem_rw(vm['id']), 'rootfs filesystem is not RW as expected for VM {}'\
            .format(vm['display_name'])

        LOG.tc_step("Checking for any system alarm ....")
        rc, new_alarm = is_new_alarm_raised(pre_alarm_)
        assert not rc, " alarm(s) found: {}".format(new_alarm)

    LOG.tc_step("Checking if live migration is required to put the vms to a single compute....")
    host_0 = nova_helper.get_vm_host((vms_[0])['id'])
    host_1 = nova_helper.get_vm_host((vms_[1])['id'])

    if host_0 != host_1:
        LOG.tc_step("Attempting to live migrate  vm {} to host {} ....".format((vms_[1])['display_name'],
                                                                               host_0))
        code, msg = vm_helper.live_migrate_vm((vms_[1])['id'], host_0)
        LOG.tc_step("Verify live migration succeeded...")
        assert code == 0, "Live migration of vm {} to host {} did not success".format((vms_[1])['display_name'],
                                                                                      host_0)

    LOG.tc_step("Verify both VMs are in same host....")

    assert host_0 == nova_helper.get_vm_host((vms_[1])['id']), "VMs are not in the same compute host"

    LOG.tc_step("Rebooting compute {} to initiate vm evacuation .....")
    rc, msg = host_helper.reboot_hosts(host_0, fail_ok=True)
    assert rc == 0, "{} reboot not succeeded; return code: {}; detail error message: {}".format(host_0, rc, msg)

    LOG.tc_step("Verify VMs are evacuated.....")

    after_evac_host_0 = nova_helper.get_vm_host((vms_[0])['id'])
    after_evac_host_1 = nova_helper.get_vm_host((vms_[1])['id'])

    assert after_evac_host_0 and after_evac_host_0 != host_0, "VM {} evacuation failed; " \
        "current host: {}; expected host: {}".format((vms_[0])['id'], after_evac_host_0, host_1)

    assert after_evac_host_1 and after_evac_host_1 != host_0, "VM {} evacuation failed; " \
        "current host: {}; expected host: {}".format((vms_[0])['id'], after_evac_host_1, host_1)

    LOG.tc_step("Checking for any system alarm ....")
    rc, new_alarm = is_new_alarm_raised(pre_alarm_)
    assert not rc, " alarm(s) found: {}".format(new_alarm)

    LOG.tc_step("Login to VM and to check filesystem is rw mode....")
    assert is_vm_filesystem_rw((vms_[0])['id']), 'After evacuation the rootfs filesystem is not RW as expected ' \
                                                 'for VM {}'.format((vms_[0])['display_name'])

    assert is_vm_filesystem_rw((vms_[1])['id']), 'After evacuation the rootfs filesystem is not RW as expected ' \
                                                 'for VM {}'.format((vms_[1])['display_name'])


@mark.skipif(len(system_helper.get_storage_nodes()) < 1, reason="No storage hosts on the system")
@mark.skipif(len(system_helper.get_computes()) < 2, reason="at least two computes are required")
def test_instantiate_a_vm_with_a_large_volume_and_cold_migrate(vms_):
    """
    Test instantiate a vm with a large volume ( 20 GB and 40 GB) and cold migrate:
    Args:
        vms_ (dict): vms created by vms_ fixture

    Test Setups:
    - get tenant1 and management networks which are already created for lab setup
    - get or create a "small" flavor
    - get the guest image id
    - create two large volumes (20 GB and 40 GB) in cinder
    - boot two vms ( test_inst1, test_inst2) using  volumes 20 GB and 40 GB respectively


    Test Steps:
    - Verify VM status is ACTIVE
    - Validate that VMs boot, and that no timeouts or error status occur.
    - Verify the VM can be pinged from NATBOX
    - Verify login to VM and rootfs (dev/vda) filesystem is rw mode
    - Attempt to cold migrate of VMs
    - Validate that the VMs migrated and no errors or alarms are present
    - Log into both VMs and validate that file systems are read-write
    - Terminate VMs

    Skip conditions:
    - less that two computes
    - no storage node

    """
    LOG.tc_step("Instantiate a vm with large volume.....")

    vms = vms_

    for vm in vms:

        LOG.tc_step("Checking VM status; VM Instance id is: {}......".format(vm['id']))
        vm_state = nova_helper.get_vm_status(vm['id'])

        assert vm_state == VMStatus.ACTIVE, 'VM {} state is {}; Not in ACTIVATE state as expected'\
            .format(vm['id'], vm_state)

        LOG.tc_step("Verify  VM can be pinged from NAT box...")
        rc, boot_time = check_vm_boot_time(vm['id'])
        assert rc,  "VM is not pingable after {} seconds ".format(boot_time)

        LOG.tc_step("Verify Login to VM and check filesystem is rw mode....")
        assert is_vm_filesystem_rw(vm['id']), 'rootfs filesystem is not RW as expected for VM {}'\
            .format(vm['display_name'])

        LOG.tc_step("Attempting  cold migration; vm id = {}; vm_name = {} ....".format(vm['id'], vm['display_name']))

        code, msg = vm_helper.cold_migrate_vm(vm_id=vm['id'],  fail_ok=True)
        LOG.tc_step("Verify cold migration succeeded...")
        assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

        LOG.tc_step("Verifying  filesystem is rw mode after cold migration....")
        assert is_vm_filesystem_rw(vm['id']), 'After cold migration rootfs filesystem is not RW as expected for ' \
                                              'VM {}'.format(vm['display_name'])

        LOG.tc_step("Checking for any system alarm ....")
        rc, new_alarm = is_new_alarm_raised(pre_alarm_)
        assert not rc, " alarm(s) found: {}".format(new_alarm)


@mark.skipif(len(system_helper.get_storage_nodes()) < 1, reason="No storage hosts on the system")
@mark.skipif(len(system_helper.get_computes()) < 2, reason="at least two computes are required")
def test_instantiate_a_vm_with_multiple_volumes_and_migrate(image_, flavor_id_, net_):
    """
    Test  a vm with a multiple volumes live, cold  migration and evacuation:

    Args:
        image_ (str): the guest image_id
        flavor_id_ (str): the flavor id created by flavor_id_ fixture
        net_ (dict): the tenant and management networks from fixture net_

    Test Setups:
    - get guest image_id
    - get or create 'small' flavor_id
    - get tenenat and managment network ids

    Test Steps:
    - create volume for boot and another extra size 4GB
    - boot vms from the created volume
    - Validate that VMs boot, and that no timeouts or error status occur.
    - Verify VM status is ACTIVE
    - Attach the second volume to VM
    - Attempt live migrate  VM
    - Login to VM and verify the filesystem is rw mode on both volumes
    - Attempt cold migrate  VM
    - Login to VM and verify the filesystem is rw mode on both volumes
    - Reboot the compute host to initiate evacuation
    - Login to VM and verify the filesystem is rw mode on both volumes
    - Terminate VMs

    Skip conditions:
    - less than two computes
    - less than one storage

    """
    LOG.tc_step("Creating  a volume size=4GB.....")
    vol_id_0 = cinder_helper.create_volume(name='vol_0', image_id=image_, size=4)[1]
    ResourceCleanup.add('volume', vol_id_0, scope='function')

    LOG.tc_step("Creating  a second volume size=4GB.....")
    vol_id_1 = cinder_helper.create_volume(name='vol_1', image_id=image_, size=4)[1]
    LOG.tc_step("Volume id is: {}".format(vol_id_1))
    ResourceCleanup.add('volume', vol_id_1, scope='function')

    LOG.tc_step("Booting instance vm_0...")
    rc, vm_id, msg, new_vol = vm_helper.boot_vm(name='vm_0', flavor=flavor_id_, source='volume', source_id=vol_id_0, nics=net_)
    ResourceCleanup.add('vm', vm_id, scope='function')
    assert rc == 0, "VM vm_0 did not succeed: reaon {}".format(msg)

    LOG.tc_step("Verify  VM can be pinged from NAT box...")
    rc, boot_time = check_vm_boot_time(vm_id)
    assert rc,  "VM is not pingable after {} seconds ".format(boot_time)

    LOG.tc_step("Login to VM and to check filesystem is rw mode....")
    assert is_vm_filesystem_rw(vm_id), 'vol_0 rootfs filesystem is not RW as expected.'

    LOG.tc_step("Attemping to attach a second volume to VM...")
    vm_helper.attach_vol_to_vm(vm_id, vol_id_1)

    LOG.tc_step("Attemping live migrate VM...")
    code, msg = vm_helper.live_migrate_vm(vm_id=vm_id,  fail_ok=True)
    LOG.tc_step("Verify live migration succeeded...")
    assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

    LOG.tc_step("Login to VM and to check filesystem is rw mode after live migration....")
    assert is_vm_filesystem_rw(vm_id), 'After live migration vol_0 rootfs filesystem is not RW as expected.'
    assert is_vm_filesystem_rw(vm_id, rootfs='vdb'), 'After live migration vol_1 rootfs filesystem is not RW ' \
                                                     'as expected'

    LOG.tc_step("Attempting  cold migrate VM...")
    code, msg = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)
    LOG.tc_step("Verify cold migration succeeded...")
    assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

    LOG.tc_step("Login to VM and to check filesystem is rw mode after live migration....")
    assert is_vm_filesystem_rw(vm_id), 'After cold migration rootfs filesystem is not RW as expected'
    assert is_vm_filesystem_rw(vm_id, rootfs='vdb'), 'After cold migration vol_1 rootfs filesystem is not RW ' \
                                                     'as expected'

    LOG.tc_step("Testing VM evacuation.....")
    before_host_0 = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Rebooting compute {} to initiate vm evacuation .....".format(before_host_0))
    rc, msg = host_helper.reboot_hosts(before_host_0, fail_ok=True)

    assert rc == 0, "{} reboot not succeeded; return code: {}; detail error message: {}".format(before_host_0, rc, msg)

    LOG.tc_step("Verify VMs are evacuated.....")

    after_evac_host_0 = nova_helper.get_vm_host(vm_id)

    assert after_evac_host_0 != before_host_0, "VM {} evacuation failed; " \
        "previous host: {}; current host: {}".format(vm_id, before_host_0, after_evac_host_0)

    LOG.tc_step("Login to VM and to check filesystem is rw mode after live migration....")
    assert is_vm_filesystem_rw(vm_id), 'After evacuation rootfs filesystem is not RW as expected for VM vm_0'


def check_vm_boot_time(vm_id):
    start_time = time.time()
    output = vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    elapsed_time = time.time() - start_time
    return output, elapsed_time


def is_vm_filesystem_rw(vm_id, rootfs='vda'):
    with vm_helper.ssh_to_vm_from_natbox(vm_id, vm_image_name='cgcs-guest') as vm_ssh:
        cmd = "mount | grep {} | grep rw | wc -l".format(rootfs)
        cmd_output = vm_ssh.exec_sudo_cmd(cmd)[1]
        return True if cmd_output is '1' else False


def is_new_alarm_raised(pre_list):
    alarms = system_helper.get_alarms()
    new_list = table_parser.get_all_rows(alarms)
    old_list = pre_list()
    for alarm in new_list:
        if alarm not in old_list:
            return True, new_list
    return False, None
