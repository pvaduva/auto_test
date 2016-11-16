import time, random
from pytest import fixture, skip, mark

from utils.tis_log import LOG
from utils import table_parser
from keywords import host_helper, vm_helper, nova_helper, cinder_helper, glance_helper, system_helper
from consts.cgcs import VMStatus
from consts.auth import Tenant
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.verify_fixtures import check_alarms
from utils.ssh import ControllerClient


@fixture(scope='module', autouse=True)
def check_system():
    if not cinder_helper.is_volumes_pool_sufficient(min_size=80):
        skip("Cinder volume pool size is smaller than 80G")

    if len(host_helper.get_nova_hosts()) < 2:
        skip("at least two computes are required")


@fixture(scope='function', autouse=True)
def pre_alarm_():
    """
    Text fixture to get pre-test existing alarm list.
    Args:None

    Returns: list of alarms

    """
    pre_alarms = system_helper.get_alarms_table()
    pre_list = table_parser.get_all_rows(pre_alarms)
    # Time stamps are removed before comparing alarms with post test alarms.
    # The time stamp  is the last item in each alarm row.
    for n in pre_list:
        n.pop()
    return pre_list


@fixture(scope='module')
def image_():
    """
    Text fixture to get guest image
    Args:

    Returns: the guest image id

    """
    return glance_helper.get_image_id_from_name(name='cgcs-guest')


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
def vms_(volumes_):
    """
    Text fixture to create cinder volume with specific 'display-name', and 'size'
    Args:
        volumes_: list of two large volumes dict created by volumes_ fixture

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
        vm_id = vm_helper.boot_vm(name=instance_name, source='volume',
                                  source_id=vol_params['id'], user_data=get_user_data_file())[1]
        vm = {
                'id': vm_id,
                'display_name': instance_name,
             }
        vms.append(vm)
        ResourceCleanup.add('vm', vm_id, scope='function')
        index += 1
    return vms


@mark.storage_sanity
def test_vm_with_a_large_volume_live_migrate(vms_, pre_alarm_):
    """
    Test instantiate a vm with a large volume ( 20 GB and 40 GB) and live migrate:
    Args:
        vms_ (dict): vms created by vms_ fixture
        pre_alarm_ (list): alarm lists obtained by pre_alarm_ fixture

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
    pre_alarms = pre_alarm_
    for vm in vms_:
        vm_id = vm['id']

        LOG.tc_step("Checking VM status; VM Instance id is: {}......".format(vm_id))
        vm_state = nova_helper.get_vm_status(vm_id)

        assert vm_state == VMStatus.ACTIVE, 'VM {} state is {}; Not in ACTIVATE state as expected'\
            .format(vm_id, vm_state)

        LOG.tc_step("Verify  VM can be pinged from NAT box...")
        rc, boot_time = check_vm_boot_time(vm_id)
        assert rc,  "VM is not pingable after {} seconds ".format(boot_time)

        LOG.tc_step("Verify Login to VM and check filesystem is rw mode....")
        assert is_vm_filesystem_rw(vm_id), 'rootfs filesystem is not RW as expected for VM {}'\
            .format(vm['display_name'])

        LOG.tc_step("Attempting  live migration; vm id = {}; vm_name = {} ....".format(vm_id, vm['display_name']))

        code, msg = vm_helper.live_migrate_vm(vm_id=vm_id,  fail_ok=True)
        LOG.tc_step("Verify live migration succeeded...")
        assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

        LOG.tc_step("Verifying  filesystem is rw mode after live migration....")
        assert is_vm_filesystem_rw(vm_id), 'After live migration rootfs filesystem is not RW as expected for VM {}'.format(vm['display_name'])

        # LOG.tc_step("Checking for any new system alarm....")
        # rc, new_alarm = is_new_alarm_raised(pre_alarms)
        # assert not rc, " alarm(s) found: {}".format(new_alarm)


@mark.domain_sanity
def test_vm_with_large_volume_and_evacuation(vms_, pre_alarm_):
    """
   Test instantiate a vm with a large volume ( 20 GB and 40 GB) and evacuate:

    Args:
        vms_ (dict): vms created by vms_ fixture
        pre_alarm_ (list): alarm lists obtained by pre_alarm_ fixture

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
    pre_alarms = pre_alarm_
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

    computes = host_helper.get_nova_hosts()
    computes.remove(host_0)
    after_evac_host_0 = nova_helper.get_vm_host((vms_[0])['id'])
    after_evac_host_1 = nova_helper.get_vm_host((vms_[1])['id'])

    assert after_evac_host_0 and after_evac_host_0 != host_0, "VM {} evacuation failed; " \
        "current host: {}; expected host: {}".format((vms_[0])['id'], after_evac_host_0, host_1)

    assert after_evac_host_1 and after_evac_host_1 != host_0, "VM {} evacuation failed; " \
        "current host: {}; expected host: {}".format((vms_[0])['id'], after_evac_host_1, host_1)

    LOG.tc_step("Login to VM and to check filesystem is rw mode....")
    assert is_vm_filesystem_rw((vms_[0])['id']), 'After evacuation the rootfs filesystem is not RW as expected ' \
                                                 'for VM {}'.format((vms_[0])['display_name'])

    LOG.tc_step("Login to VM and to check filesystem is rw mode....")
    assert is_vm_filesystem_rw((vms_[1])['id']), 'After evacuation the rootfs filesystem is not RW as expected ' \
                                                 'for VM {}'.format((vms_[1])['display_name'])


@mark.domain_sanity
def test_instantiate_a_vm_with_a_large_volume_and_cold_migrate(vms_, pre_alarm_):
    """
    Test instantiate a vm with a large volume ( 20 GB and 40 GB) and cold migrate:
    Args:
        vms_ (dict): vms created by vms_ fixture
        pre_alarm_ (list): alarm lists obtained by pre_alarm_ fixture

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
    pre_alarms = pre_alarm_

    for vm in vms:
        vm_id = vm['id']
        LOG.tc_step("Checking VM status; VM Instance id is: {}......".format(vm_id))
        vm_state = nova_helper.get_vm_status(vm_id)

        assert vm_state == VMStatus.ACTIVE, 'VM {} state is {}; Not in ACTIVATE state as expected'\
            .format(vm_id, vm_state)

        LOG.tc_step("Verify  VM can be pinged from NAT box...")
        rc, boot_time = check_vm_boot_time(vm_id)
        assert rc,  "VM is not pingable after {} seconds ".format(boot_time)

        LOG.tc_step("Verify Login to VM and check filesystem is rw mode....")
        assert is_vm_filesystem_rw(vm_id), 'rootfs filesystem is not RW as expected for VM {}'\
            .format(vm['display_name'])

        LOG.tc_step("Attempting  cold migration; vm id = {}; vm_name = {} ....".format(vm_id, vm['display_name']))

        code, msg = vm_helper.cold_migrate_vm(vm_id=vm_id,  fail_ok=True)
        LOG.tc_step("Verify cold migration succeeded...")
        assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

        LOG.tc_step("Verifying  filesystem is rw mode after cold migration....")
        assert is_vm_filesystem_rw(vm_id), 'After cold migration rootfs filesystem is not RW as expected for ' \
                                              'VM {}'.format(vm['display_name'])

        # LOG.tc_step("Checking for any system alarm ....")
        # rc, new_alarm = is_new_alarm_raised(pre_alarms)
        # assert not rc, " alarm(s) found: {}".format(new_alarm)


@mark.usefixtures('centos7_image')
def test_instantiate_a_vm_with_multiple_volumes_and_migrate(image_):
    """
    Test  a vm with a multiple volumes live, cold  migration and evacuation:

    Args:
        image_ (str): the guest image_id

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
    skip("Currently not working. Centos image doesn't see both volumes")
    LOG.tc_step("Creating  a volume size=8GB.....")
    vol_id_0 = cinder_helper.create_volume(name='vol_0', image_id='centos_7', size=8)[1]
    ResourceCleanup.add('volume', vol_id_0, scope='function')

    LOG.tc_step("Creating  a second volume size=8GB.....")
    vol_id_1 = cinder_helper.create_volume(name='vol_1', image_id='centos_7', size=8)[1]
    LOG.tc_step("Volume id is: {}".format(vol_id_1))
    ResourceCleanup.add('volume', vol_id_1, scope='function')

    LOG.tc_step("Booting instance vm_0...")

    rc, vm_id, msg, new_vol = vm_helper.boot_vm(name='vm_0', source='volume',
                                                source_id=vol_id_0, guest_os='centos_7')
    ResourceCleanup.add('vm', vm_id, scope='function')
    assert rc == 0, "VM vm_0 did not succeed: reaon {}".format(msg)
    time.sleep(5)

    LOG.tc_step("Verify  VM can be pinged from NAT box...")
    rc, boot_time = check_vm_boot_time(vm_id)
    assert rc,  "VM is not pingable after {} seconds ".format(boot_time)

    LOG.tc_step("Login to VM and to check filesystem is rw mode....")
    assert is_vm_filesystem_rw(vm_id, vm_image_name='centos_7'), 'vol_0 rootfs filesystem is not RW as expected.'

    LOG.tc_step("Attemping to attach a second volume to VM...")
    vm_helper.attach_vol_to_vm(vm_id, vol_id_1)

    LOG.tc_step("Login to VM and to check filesystem is rw mode for both volumes....")
    assert is_vm_filesystem_rw(vm_id, rootfs=['vda', 'vdb'], vm_image_name='centos_7'), 'volumes rootfs filesystem is ' \
                                                                                        'not RW as expected.'

    LOG.tc_step("Attemping live migrate VM...")
    code, msg = vm_helper.live_migrate_vm(vm_id=vm_id,  fail_ok=True)
    LOG.tc_step("Verify live migration succeeded...")
    assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

    LOG.tc_step("Login to VM and to check filesystem is rw mode after live migration....")
    assert is_vm_filesystem_rw(vm_id, rootfs=['vda', 'vdb'], vm_image_name='centos_7'), 'After live migration rootfs ' \
                                                                                        'filesystem is not RW ' \
                                                                                        'as expected'
    LOG.tc_step("Attempting  cold migrate VM...")
    code, msg = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)
    LOG.tc_step("Verify cold migration succeeded...")
    assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

    LOG.tc_step("Login to VM and to check filesystem is rw mode after live migration....")
    assert is_vm_filesystem_rw(vm_id, rootfs=['vda', 'vdb'], vm_image_name='centos_7'), 'After cold migration rootfs ' \
                                                                                        'filesystem is not ' \
                                                                                        'RW as expected'
    LOG.tc_step("Testing VM evacuation.....")
    before_host_0 = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Rebooting compute {} to initiate vm evacuation .....".format(before_host_0))
    rc, msg = host_helper.reboot_hosts(before_host_0, fail_ok=False)

    assert rc == 0, "{} reboot not succeeded; return code: {}; detail error message: {}".format(before_host_0, rc, msg)

    LOG.tc_step("Verify VMs are evacuated.....")

    after_evac_host_0 = nova_helper.get_vm_host(vm_id)

    assert after_evac_host_0 != before_host_0, "VM {} evacuation failed; " \
        "previous host: {}; current host: {}".format(vm_id, before_host_0, after_evac_host_0)

    LOG.tc_step("Login to VM and to check filesystem is rw mode after live migration....")
    assert is_vm_filesystem_rw(vm_id, rootfs=['vda', 'vdb'], vm_image_name='centos_7'), 'After evacuation filesystem is ' \
                                                                                        'not RW as expected for VM vm_0'


def check_vm_boot_time(vm_id):
    start_time = time.time()
    output = vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)
    elapsed_time = time.time() - start_time
    return output, elapsed_time


def is_vm_filesystem_rw(vm_id, rootfs='vda', vm_image_name='cgcs-guest'):
    """

    Args:
        vm_id:
        rootfs (str|list):

    Returns:

    """
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id, vm_image_name=vm_image_name) as vm_ssh:
        if isinstance(rootfs, str):
            rootfs = [rootfs]
        for fs in rootfs:
            cmd = "mount | grep {} | grep rw | wc -l".format(fs)
            cmd_output = vm_ssh.exec_sudo_cmd(cmd)[1]
            if cmd_output != '1':
                LOG.info("Filesystem /dev/{} is not rw for VM: {}".format(fs, vm_id))
                return False
        return True


# def is_new_alarm_raised(pre_list):
#     alarms = system_helper.get_alarms_table()
#     new_list = table_parser.get_all_rows(alarms)
#     LOG.info("Pre-alarm: {}".format(pre_list))
#     LOG.info("New-alarm: {}".format(new_list))
#     for alarm in new_list:
#         alarm.pop()     # to remove the time stamp
#         if alarm not in pre_list:
#             return True, new_list
#
#     return False, None


def get_user_data_file():
    """
    This function is a workaround to adds user_data  for restarting the sshd. The
    sshd daemon fails to start in VM evacuation testcase.


    Returns:(str) - the file path of the userdata text file

    """

    auth_info = Tenant.get_primary()
    tenant = auth_info['tenant']
    user_data_file = "/home/wrsroot/userdata/{}_test_userdata.txt".format(tenant)
    controller_ssh = ControllerClient.get_active_controller()
    cmd = "test -e {}".format(user_data_file)
    rc = controller_ssh.exec_cmd(cmd)[0]
    if rc != 0:
        cmd = "cat <<EOF > {}\n" \
              "#cloud-config\n\nruncmd: \n - /etc/init.d/sshd restart\n" \
              "EOF".format(user_data_file)
        print(cmd)
        code, output = controller_ssh.exec_cmd(cmd)
        LOG.info("Code: {} output: {}".format(code, output))

    return user_data_file


def get_file_data(vm_ssh, file, to_look_for=None):
    code, out = vm_ssh.exec_cmd('cat {} | grep {}'.format(file, to_look_for))
    return out


# temp stress test to reproduce a CGTS-4911
@mark.usefixtures('centos7_image')
@mark.parametrize(('image_id', 'backing', 'vol_size'), [
    ('guest1', 'image', 'big'),
    ('centos_7', 'image', 'big'),   # copy/rename cgcs-guest
    ('cgcsguestconsole', 'image', 'big'),
    ('guest1', 'remote', 'big'),
    ('centos_7', 'remote', 'big'),
    ('cgcsguestconsole', 'remote', 'big'),
    ('guest1', 'image', 'small'),
    ('cgcsguestconsole', 'image', 'small'),
    ('guest1', 'remote', 'small'),
    ('cgcsguestconsole', 'remote', 'small'),
])
def test_cold_migrate_vms_with_large_volume_stress(image_id, backing, vol_size):
    end_time = time.time() + 12 * 3600
    # image_id = glance_helper.get_image_id_from_name('cgcs-guest')

    i = 0
    zone = 'nova'
    from consts.proj_vars import ProjVar
    if '35_60' in ProjVar.get_var('LAB_NAME'):
        zone = 'chris'
    if backing == 'image':
        backing = 'local_image'

    flav_id = nova_helper.get_flavor_id(name=backing, strict=False)
    if not flav_id:
        flav_id = nova_helper.create_flavor(name=backing, storage_backing=backing, check_storage_backing=False)[1]

    while time.time() < end_time:
        i += 1
        LOG.tc_step("Iteration number: {}".format(i))
        hosts = host_helper.get_hosts_by_storage_aggregate(backing)
        vm_host = random.choice(hosts)

        if vol_size == 'small':
            LOG.info("Boot two vms from 1G volumes")
            vol_1 = cinder_helper.create_volume(name='vol-1G', image_id=image_id, size=1)[1]
            vol_2 = cinder_helper.create_volume(name='vol-1G', image_id=image_id, size=1)[1]

            vm_1 = vm_helper.boot_vm(name='1g_{}_{}'.format(image_id, backing), source='volume',
                                     source_id=vol_1, flavor=flav_id, vm_host=vm_host)[1]
            vm_2 = vm_helper.boot_vm(name='1g_{}_{}'.format(image_id, backing), source='volume',
                                     source_id=vol_2, flavor=flav_id, vm_host=vm_host)[1]

        else:
            LOG.info("Boot two vms from 20g and 40g volume respectively")
            vol_1 = cinder_helper.create_volume(name='vol-20', image_id=image_id, size=20)[1]
            vol_2 = cinder_helper.create_volume(name='vol-40', image_id=image_id, size=40)[1]

            if image_id == 'centos_7':
                vm_1 = vm_helper.boot_vm(name='20g_{}_{}'.format(image_id, backing), source='volume',
                                         source_id=vol_1, flavor=flav_id, guest_os='centos_7', vm_host=vm_host)[1]
                vm_2 = vm_helper.boot_vm(name='40g_{}_{}'.format(image_id, backing), source='volume',
                                         source_id=vol_2, flavor=flav_id, guest_os='centos_7', vm_host=vm_host)[1]
            else:
                vm_1 = vm_helper.boot_vm(name='20g_{}_{}'.format(image_id, backing), source='volume',
                                         source_id=vol_1, flavor=flav_id, vm_host=vm_host)[1]
                vm_2 = vm_helper.boot_vm(name='40g_{}_{}'.format(image_id, backing), source='volume',
                                         source_id=vol_2, flavor=flav_id, vm_host=vm_host)[1]

        host_1 = nova_helper.get_vm_host(vm_1)
        host_2 = nova_helper.get_vm_host(vm_2)
        if host_1 != host_2:
            vm_helper.live_migrate_vm(vm_2, host_1)
            host_1 = nova_helper.get_vm_host(vm_1)
            host_2 = nova_helper.get_vm_host(vm_2)
            LOG.info("vm_1 is on {}.    vm_2 is on {}".format(host_1, host_2))

        LOG.info("Wait for both vms pingable before cold migration")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_1)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_2)

        for j in range(2):
            LOG.info("\n----------------- Cold migration iteration: {}.{}".format(i, j+1))

            for vm in [vm_1, vm_2]:
                vol_size = '20g' if vm == vm_1 else '40g'

                LOG.info("Cold migrate {} vm".format(vol_size))
                for m in range(10):
                    code, msg = vm_helper.cold_migrate_vm(vm_id=vm, fail_ok=True)
                    if code == 0:
                        break
                    elif code == 2 and 'Platform CPU usage' in msg:
                        time.sleep(5)
                    else:
                        assert False, "Cold mig {} vm failed with msg: {}".format(vol_size, msg)
                else:
                    assert False, "Cold migration {} vm failed 10 times due to CPU usage too high".format(vol_size)

                LOG.info("Ping {} vm after cold migration".format(vol_size))
                vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)
                assert is_vm_filesystem_rw(vm_id=vm, vm_image_name=image_id), \
                       'rootfs filesystem is not RW for {} vm'.format(vol_size)

        LOG.info("Delete both vms")
        vm_helper.delete_vms([vm_1, vm_2], stop_first=False)


@mark.usefixtures('centos7_image')
@mark.parametrize(('action', 'backing', 'image', 'size'), [
    ('livemigrate', 'image', 'guest1', 'big'),
    ('reboot', 'image', 'guest1', 'big'),
    ('stop', 'image', 'guest1', 'big'),
    ('livemigrate', 'remote', 'guest1', 'big'),
    ('reboot', 'remote', 'guest1', 'big'),
    ('stop', 'remote', 'guest1', 'big'),
    ('livemigrate', 'image', 'centos_7', 'big'),
    ('reboot', 'image', 'centos_7', 'big'),
    ('stop', 'image', 'centos_7', 'big'),
    ('livemigrate', 'remote', 'centos_7', 'big'),
    ('reboot', 'remote', 'centos_7', 'big'),
    ('stop', 'remote', 'centos_7', 'big'),
    ('livemigrate', 'image', 'guest1', 'small'),
    ('reboot', 'image', 'guest1', 'small'),
    ('stop', 'image', 'guest1', 'small'),
    ('livemigrate', 'remote', 'guest1', 'small'),
    ('reboot', 'remote', 'guest1', 'small'),
    ('stop', 'remote', 'guest1', 'small'),
])
def test_4911_other_stress_tests(action, backing, image, size):
    end_time = time.time() + 12 * 3600
    if backing == 'image':
        backing = 'local_image'
    i = 0

    flav_id = nova_helper.get_flavor_id(name=backing, strict=False)
    if not flav_id:
        flav_id = nova_helper.create_flavor(name=backing, storage_backing=backing, check_storage_backing=False)[1]

    while time.time() < end_time:
        i += 1
        LOG.tc_step("Iteration number: {}".format(i))

        if action == 'reboot':
            if size == 'small':
                LOG.info("Booting vm with 1G volume")
                vol = cinder_helper.create_volume(name='reboot-1G', image_id=image, size=1)[1]
                vm_id = vm_helper.boot_vm('reboot_vm_1G', flavor=flav_id, source='volume', source_id=vol, guest_os=image)[1]
            else:
                LOG.info("Booting vm with 40G volume")
                vol = cinder_helper.create_volume(name='reboot-40G', image_id=image, size=40)[1]
                vm_id = vm_helper.boot_vm('reboot_vm_40G', flavor=flav_id, source='volume', source_id=vol, guest_os=image)[1]

            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
            LOG.info("Vm is up and pingable")
            for j in range(2):
                LOG.info("\n----------------- Reboot iteration: {}.{}".format(i, j + 1))
                for m in range(10):
                    code, msg = vm_helper.reboot_vm(vm_id, fail_ok=True)
                    if code == 0:
                        break
                else:
                    assert False, "Vm failed to reboot 10 times"

                vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
                LOG.info("Vm is up and pingable after reboot")
                assert is_vm_filesystem_rw(vm_id=vm_id, vm_image_name=image), \
                       'rootfs filesystem is not RW after reboot'
            LOG.info("Delete the vm")
            vm_helper.delete_vms(vm_id, stop_first=False)

        elif action == 'livemigrate':
            vm_hosts = host_helper.get_hosts_by_storage_aggregate(backing)
            vm_host = random.choice(vm_hosts)

            if size == 'small':
                LOG.info("Boot two vms from 1G volumes")
                vol_1 = cinder_helper.create_volume(name='live_vm_1G', image_id=image, size=1)[1]
                vol_2 = cinder_helper.create_volume(name='live_vm_1G', image_id=image, size=1)[1]

                vm_1 = vm_helper.boot_vm(name='live_migrate_1g', source='volume', source_id=vol_1,
                                         flavor=flav_id, vm_host=vm_host, guest_os=image)[1]
                vm_2 = vm_helper.boot_vm(name='live_migrate_1g', source='volume', source_id=vol_2,
                                         flavor=flav_id, vm_host=vm_host, guest_os=image)[1]
            else:
                LOG.info("Boot two vms from 20g and 40g volume respectively")
                vol_1 = cinder_helper.create_volume(name='live_vm_20G', image_id=image, size=20)[1]
                vol_2 = cinder_helper.create_volume(name='live_vm_40G', image_id=image, size=40)[1]

                vm_1 = vm_helper.boot_vm(name='live_migrate_20g', source='volume', source_id=vol_1,
                                         flavor=flav_id, vm_host=vm_host, guest_os=image)[1]
                vm_2 = vm_helper.boot_vm(name='live_migrate_40g', source='volume', source_id=vol_2,
                                         flavor=flav_id, vm_host=vm_host, guest_os=image)[1]

            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_1)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_2)
            LOG.info("Vms are up and pingable")


            for j in range(2):
                vm_hosts = host_helper.get_hosts_by_storage_aggregate(backing)
                vm_hosts.remove(nova_helper.get_vm_host(vm_1))
                vm_host = random.choice(vm_hosts)
                LOG.info("\n----------------- Live migration iteration: {}.{}".format(i, j + 1))
                for vm_id in [vm_1, vm_2]:
                    for m in range(10):
                        code, msg = vm_helper.live_migrate_vm(vm_id, fail_ok=True, destination_host=vm_host)
                        if code == 0:
                            break
                    else:
                        assert False, "Vm {} failed to live migrate 10 times"

                vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_1)
                vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_2)
                LOG.info("Vms are up and pingable after live migration")

                assert is_vm_filesystem_rw(vm_id=vm_1, vm_image_name=image), \
                       'rootfs filesystem is not RW after reboot'
                assert is_vm_filesystem_rw(vm_id=vm_2, vm_image_name=image), \
                       'rootfs filesystem is not RW after reboot'
                assert nova_helper.get_vm_host(vm_1) == nova_helper.get_vm_host(vm_2)

            LOG.info("Delete the two vms")
            vm_helper.delete_vms([vm_1, vm_2], stop_first=False)

        elif action == 'stop':
            if size == 'small':
                LOG.info("Booting vm with 1G volume")
                vol = cinder_helper.create_volume(name='stop-1G', image_id=image, size=1)[1]
                vm_id = vm_helper.boot_vm('stop_1G', flavor=flav_id, source='volume', source_id=vol, guest_os=image)[1]
            else:
                LOG.info("Booting vm with 40G volume")
                vol = cinder_helper.create_volume(name='stop-40G', image_id=image, size=40)[1]
                vm_id = vm_helper.boot_vm('stop_40G', flavor=flav_id, source='volume', source_id=vol, guest_os=image)[1]

            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
            LOG.info("Vm is up and pingable")
            for j in range(2):
                LOG.info("\n----------------- Stop/Start iteration: {}.{}".format(i, j + 1))
                for m in range(10):
                    code_1, msg_1 = vm_helper.stop_vms(vm_id, fail_ok=True)
                    time.sleep(10)
                    code_2, msg_2 = vm_helper.start_vms(vm_id, fail_ok=True)
                    if code_1 == code_2 == 0:
                        break
                else:
                    assert False, "Vm failed to stop/start 10 times"

                vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
                LOG.info("Vm is up and pingable after stop/start")

                assert is_vm_filesystem_rw(vm_id=vm_id, vm_image_name=image), \
                       'rootfs filesystem is not RW after stop/start'
            LOG.info("Delete the vm")
            vm_helper.delete_vms(vm_id, stop_first=False)
