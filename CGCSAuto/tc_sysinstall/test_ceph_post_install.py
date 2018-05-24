import time

from pytest import fixture, skip

from consts.auth import SvcCgcsAuto, Tenant
from consts.build_server import Server, get_build_server_info
from consts.cgcs import EventLogID
from consts.cgcs import Prompt
from consts.proj_vars import ProjVar, InstallVars
from keywords import install_helper, host_helper, system_helper, cinder_helper, \
    storage_helper,  local_storage_helper, glance_helper, vm_helper
from testfixtures.resource_mgmt import ResourceCleanup
from utils.clients.ssh import SSHClient
from utils.tis_log import LOG

MINIMUM_CEPH_MON_GIB = 20


@fixture(scope='session', autouse=True)
def pre_ceph_install_check():
    backend_info = storage_helper.get_storage_backends()
    lab = ProjVar.get_var("LAB")
    LOG.fixture_step('Verify no ceph backend is currently configured in system: {}'.format(lab['name']))
    # if 'ceph' in backend_info:
    #     skip("ceph backend is already configured  in the system {}".format(lab['name']))

    LOG.fixture_step('Verify system {} includes storage nodes'.format(lab['name']))
    if 'storage_nodes' not in lab:
        skip("ceph backend is already configured  in the system {}".format(lab['name']))

    LOG.fixture_step('Verify lvm backend is currently configured in system: {}'.format(lab['name']))
    if 'lvm' not in backend_info:
        skip("lvm backend is not configured  in the system {}".format(lab['name']))


@fixture(scope='session', autouse=True)
def ceph_post_install_info():
    controller0 = 'controller-0'
    controller1 = 'controller-1'

    controller0_disks = local_storage_helper.get_host_disks_values(controller0, rtn_val='device_node')
    controller1_disks = local_storage_helper.get_host_disks_values(controller1, rtn_val='device_node')

    rootfs = host_helper.get_hostshow_value(controller0, "rootfs_device")
    if '/dev/disk/by-path' in rootfs:
        rootfs = local_storage_helper.get_host_disks_values(controller0, rtn_val='device_node', device_path=rootfs)[0]
    elif '/dev/' not in rootfs:
        rootfs = '/dev/{}'.format(rootfs)

    size = local_storage_helper.get_host_disk_size(controller0, disk=rootfs)
    controller0_rootfs = [rootfs, int(size)]

    rootfs = host_helper.get_hostshow_value(controller1, "rootfs_device")
    if '/dev/disk/by-path' in rootfs:
        rootfs = local_storage_helper.get_host_disks_values(controller1, rtn_val='device_node', device_path=rootfs)[0]
    elif '/dev/' not in rootfs:
        rootfs = '/dev/{}'.format(rootfs)

    size = local_storage_helper.get_host_disk_size(controller1, disk=rootfs)

    controller1_rootfs = [rootfs, int(size)]

    assert controller0_rootfs[0] in controller0_disks, "Incorrect  controller-0 disk information: {}; rootfs: {} "\
        .format(controller0_disks, controller0_rootfs)
    assert controller1_rootfs[0] in controller1_disks, "Incorrect standby controller-1 disk information: {}; " \
                                                       "rootfs: {} "\
        .format(controller1_disks, controller1_rootfs)

    backend_info = storage_helper.get_storage_backend_info('lvm')
    cinder_device = backend_info['cinder_device']

    controller0_ceph_mon_dev = ['default', get_unused_rootfs_disk_space(controller0_rootfs[1])]
    controller1_ceph_mon_dev = ['default', get_unused_rootfs_disk_space(controller1_rootfs[1])]

    # selecting a disk device for ceph_mod_dev:
    # A spare unused  disk device is selected, if both controllers have more than three disks,
    # otherwise the default device is selected

    if len(controller0_disks) > 2 and len(controller1_disks) > 2:
        controller0_spare_devices = [d for d in controller0_disks if d != controller0_rootfs[0] and d != cinder_device]
        controller1_spare_devices = [d for d in controller1_disks if d != controller1_rootfs[0] and d != cinder_device]
        common_ceph_mon_dev = list(set(controller0_spare_devices).intersection(controller1_spare_devices))
        if len(common_ceph_mon_dev) > 0:
            size_0 = local_storage_helper.get_host_disk_size(controller0, disk=common_ceph_mon_dev[0])
            size_1 = local_storage_helper.get_host_disk_size(controller1, disk=common_ceph_mon_dev[0])
            controller0_ceph_mon_dev = [common_ceph_mon_dev[0], int(size_0)]
            controller1_ceph_mon_dev = [common_ceph_mon_dev[0], int(size_1)]
        else:
            size_0 = local_storage_helper.get_host_disk_size(controller0, disk=controller0_spare_devices[0])
            size_1 = local_storage_helper.get_host_disk_size(controller1, disk=controller1_spare_devices[0])
            controller0_ceph_mon_dev = [controller0_spare_devices[0], int(size_0)]
            controller1_ceph_mon_dev = [controller1_spare_devices[0], int(size_1)]

    ceph_mon_gib = InstallVars.get_install_var('CEPH_MON_GIB')
    if not ceph_mon_gib:
        ceph_mon_gib = MINIMUM_CEPH_MON_GIB

    bld_server = get_build_server_info(InstallVars.get_install_var('BUILD_SERVER'))
    load_path = InstallVars.get_install_var('TIS_BUILD_DIR')

    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    bld_server_attr['prompt'] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', bld_server['name'])
    bld_server_conn = SSHClient(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])
    bld_server_conn.connect()
    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)

    ceph_post_install_info_ = dict()

    ceph_post_install_info_['controller-0'] = {'disks': controller0_disks,
                                               'rootfs': controller0_rootfs,
                                               'ceph_mon_dev': controller0_ceph_mon_dev,
                                               }
    ceph_post_install_info_['controller-1'] = {'disks': controller1_disks,
                                               'rootfs': controller1_rootfs,
                                               'ceph_mon_dev': controller1_ceph_mon_dev,
                                               }

    ceph_post_install_info_['ceph_mon_gib'] = ceph_mon_gib
    ceph_post_install_info_['cinder_device'] = cinder_device
    ceph_post_install_info_['load_path'] = load_path
    ceph_post_install_info_['build_server'] = bld_server_obj

    LOG.info("Ceph post install info: {}".format(ceph_post_install_info_))
    return ceph_post_install_info_


def is_infra_network_configured():

    infra = system_helper.get_host_interfaces_info("controller-0", net_type='infra')
    return len(infra) > 0


def test_negative_ceph_post_install(ceph_post_install_info):
    LOG.info("Ceph post install: {}".format(ceph_post_install_info))
    pass


def test_ceph_post_install(ceph_post_install_info):
    """

    Args:
        ceph_post_install_info:

    Returns:

    """
    controllers = ['controller-0', 'controller-1']

    LOG.tc_step("Checking the disk device for ceph-mon-dev")
    ceph_mon_dev = None
    uuid_0 = None
    uuid_1 = None
    controller0_info = ceph_post_install_info['controller-0']
    controller1_info = ceph_post_install_info['controller-1']
    if controller0_info['ceph_mon_dev'][0] == controller1_info['ceph_mon_dev'][0]:
        dev = controller0_info['ceph_mon_dev'][0]
        if dev == 'default':
            LOG.info("The ceph-mod-dev is the default rootfs device")
        else:
            LOG.info("The ceph-mod-dev is {}".format(dev))
            ceph_mon_dev = dev

    else:
        dev_0 = controller0_info['ceph_mon_dev'][0]
        uuid_0 = local_storage_helper.get_host_disks_values('controller-0', rtn_val='uuid', dev_node=dev_0)
        dev_1 = controller1_info['ceph_mon_dev'][0]
        uuid_1 = local_storage_helper.get_host_disks_values('controller-1', rtn_val='uuid', dev_node=dev_1)

    LOG.tc_step("Verifying sufficient disk space for ceph-mon")
    ceph_mon_gib = ceph_post_install_info['ceph_mon_gib']
    for host in controllers:
        disk = ceph_post_install_info[host]['ceph_mon_dev'][0]
        size = ceph_post_install_info[host]['ceph_mon_dev'][1]
        assert size >= ceph_mon_gib, \
            "Not sufficient space left for ceph-mon in {}; Available space = {} GiB in {}; Required = {} GiB"\
            .format(host, size, disk, ceph_mon_gib)

    LOG.info("Verified enough space for ceph-mon")

    LOG.tc_step("Verifying the provisioning of ceph backend post install ...")

    rc, output = storage_helper.add_storage_backend(backend='ceph', ceph_mon_gib=ceph_mon_gib,
                                                    ceph_mon_dev=ceph_mon_dev,
                                                    ceph_mon_dev_controller_0_uuid=uuid_0,
                                                    ceph_mon_dev_controller_1_uuid=uuid_1)
    assert rc == 0, "Fail to add ceph backend post install: {}".format(output)

    LOG.tc_step('Checking ceph is added and the task is set to reconfig-controller ...')

    task = storage_helper.get_storage_backend_task('ceph')
    state = storage_helper.get_storage_backend_state('ceph')

    assert task and 'reconfig-controller' == task.strip(), "Unexpected task value {}".format(task)
    assert state and 'configuring' == state.strip(), "Unexpected state value: {}".format(state)

    LOG.tc_step('Checking Config out-of-date events for controllers ...')
    for host in controllers:
        entity_instance = 'host={}'.format(host)
        events = system_helper.wait_for_events(30, num=5, strict=False, fail_ok=True,
                                               **{'Entity Instance ID': entity_instance,
                                                  'Event Log ID': EventLogID.CONFIG_OUT_OF_DATE,
                                                  'State': 'set'})
        assert events, "No '{} Configuration is out-of-date' event generated".format(host)

    LOG.info("Configuration out of date event generated; Lock/unlock controllers")

    LOG.tc_step('Locking/Unlocking controllers......')
    active_controller = system_helper.get_active_controller_name()
    standby_controller = system_helper.get_standby_controller_name()

    for controller in [standby_controller, active_controller]:
        host_helper.lock_host(controller, swact=True)
        host_helper.unlock_host(controller)
    assert system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, fail_ok=True),\
        "Alarm {} not cleared".format(EventLogID.CONFIG_OUT_OF_DATE)

    LOG.info("Swact back to controller-0...")
    host_helper.swact_host('controller-1')

    assert 'ceph' in storage_helper.get_storage_backends(), "Ceph backend not added"
    assert 'provision-storage' == storage_helper.get_storage_backend_task('ceph'),\
        "Ceph backend task is not provision-storage"

    LOG.tc_step('Adding storage nodes ......')
    lab = ProjVar.get_var("LAB")
    bld_server = ceph_post_install_info['build_server']
    load_path = ceph_post_install_info['load_path']
    rc, output = install_helper.add_storages(lab, bld_server, load_path)
    assert rc == 0, "Fail to add storage nodes after ceph post install"

    LOG.tc_step('Verifying ceph status after addition on storages ......')
    assert storage_helper.is_ceph_healthy(), "Ceph not healthy after ceph post install"

    LOG.tc_step('Verifying system health after addition of storage nodes ......')
    end_time = time.time() + 120
    while time.time() < end_time:
        rc, output = system_helper.get_system_health_query()
        if rc == 0:
            break
        else:
            time.sleep(5)

    assert rc == 0, "System health check failed: {}".format(output)

    LOG.info('Verifying image creation using lvm and ceph backends ......')
    current_images, img_dir = storage_helper.find_images(image_type='all')
    LOG.tc_step("Verifying all current images use lvm backend....")
    image_names = glance_helper.get_images(rtn_val='name')
    for name in image_names:
        id_ = glance_helper.get_image_id_from_name(name=name)
        store = glance_helper.get_image_properties(id_, ['store'])
        assert 'store' in store and store['store'] == 'file', "Unexpected store value {} for image {}"\
            .format(store, name)

    LOG.tc_step("Creating  image, volume and VM using ceph backend ....")
    # for image_file in current_images:
    new_img_name = '{}_rbd_store'.format(current_images[0].split('.')[0])
    source_image = '{}/{}'.format(img_dir, current_images[0])
    rc, image_id_rbd, msg = glance_helper.create_image(name=new_img_name, source_image_file=source_image)
    ResourceCleanup.add("image", image_id_rbd)
    assert rc == 0, "Fail to create image {} ceph as backend storage: {}".format(new_img_name, msg)
    store = glance_helper.get_image_properties(image_id_rbd, 'store')['store']
    assert store == 'rbd', "Invalid backend; store value used = {}; expected rbd".format(store)

    vol_name = 'vol_{}'.format(new_img_name)
    LOG.info('Creating Volume {} from  image {}  ......'.format(vol_name, new_img_name))
    ProjVar.set_var(**{"SOURCE_CREDENTIAL": Tenant.TENANT2})
    rc, vol_id = cinder_helper.create_volume(name=vol_name, image_id=image_id_rbd, vol_type='ceph',
                                             auth_info=Tenant.TENANT2, fail_ok=True)
    if rc != 1:
        ResourceCleanup.add("volume", vol_id)
    assert rc == 0, "Fail to create volume {}: {} ".format(vol_name, vol_id)
    vol_type = cinder_helper.get_volume_show_values(vol_id, "volume_type")
    assert vol_type.strip() == 'ceph', "Unexpected volume type {} for volume {}; expected type is ceph"\
        .format(vol_type, vol_name)

    LOG.info('Creating VM using image {}  ......'.format(new_img_name))
    vm_name = 'vm_{}'.format(new_img_name)
    rc, vm_id, msg, new_vol_id = vm_helper.boot_vm(name=vm_name, source='volume', source_id=vol_id,
                                                   auth_info=Tenant.TENANT2, cleanup='function')
    assert rc == 0, "VM {} boot failed: {}".format(vm_name, msg)

    LOG.info("Created  images, volumes and Vms  successfully  ceph as backend ....")

    # LOG.tc_step("Creating  image, volume and Vm  using lvm as backend ....")
    # new_img_name = '{}_file_store'.format(current_images[0].split('.')[0])
    # source_image = '{}/{}'.format(GuestImages.IMAGE_DIR, current_images[0])
    # rc, image_id_file, msg = glance_helper.create_image(name=new_img_name,
    # source_image_file=source_image, store='file')
    # ResourceCleanup.add("image", image_id_rbd)
    # assert rc == 0, "Fail to create image {} lvm as backend storage: {}".format(new_img_name, msg)
    # store = glance_helper.get_image_properties(image_id_file, 'store')['store']
    # assert store == 'file', "Invalid backend; store value used = {}; expected file".format(store)
    #
    # vol_name = 'vol_{}'.format(new_img_name)
    # LOG.info('Creating Volume {} from  image {}  ......'.format(vol_name, new_img_name))
    # rc, vol_id = cinder_helper.create_volume(name=vol_name, image_id=image_id_file, vol_type='iscsi',
    #                                          auth_info=Tenant.TENANT2, fail_ok=True)
    # if rc != 1:
    #     ResourceCleanup.add("volume", vol_id)
    # assert rc == 0, "Fail to create volume {}: {} ".format(vol_name, vol_id)
    # vol_type = cinder_helper.get_volume_show_values(vol_id, "volume_type")
    # assert vol_type.strip() == 'iscsi', "Unexpected volume type {} for volume {}; expected type is iscsi"\
    #     .format(vol_type,vm_name)
    #
    # LOG.info('Creating VM using image {}  ......'.format(new_img_name))
    # vm_name = 'vm_{}'.format(new_img_name)
    # rc, vm_id, msg, new_vol = vm_helper.boot_vm(name=vm_name, source='volume', source_id=vol_id,
    #                                             auth_info=Tenant.TENANT2, cleanup='function')
    # assert rc == 0, "VM {} boot failed: {}".format(vm_name,msg)
    # LOG.info("Created  images, volumes and Vms  successfully  ceph as backend ....")


def get_unused_rootfs_disk_space(total_size):

    control_fs = system_helper.get_controller_fs_values()
    total_used = 0
    if control_fs['database_gib']:
        total_used += int(control_fs['database_gib'])
    if control_fs['glance_gib']:
        total_used += int(control_fs['glance_gib'])
    if control_fs['backup_gib']:
        total_used += int(control_fs['backup_gib'])
    if control_fs['img_conversions_gib']:
        total_used += int(control_fs['img_conversions_gib'])
    if control_fs['scratch_gib']:
        total_used += int(control_fs['scratch_gib'])

    return int(total_size) - total_used if int(total_size) > total_used else 0
