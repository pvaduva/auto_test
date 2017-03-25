"""
This file contains SWIFT API related storage test cases.
"""

from pytest import mark, fixture, skip
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from keywords import glance_helper, vm_helper, host_helper, system_helper, \
    storage_helper, keystone_helper, cinder_helper, network_helper, swift_helper
from consts.cgcs import GuestImages
from consts.proj_vars import ProjVar
from testfixtures.resource_mgmt import ResourceCleanup
import time


TEST_OBJ_DIR = "test_objects"
TEST_OBJ_PATH = "/home/wrsroot/" + TEST_OBJ_DIR
TEST_OBJ_DOWNLOAD_PATH = "/home/wrsroot/downloads"


def get_ceph_backend_info():
    if 'ceph' in storage_helper.get_configured_system_storage_backend():
        ceph_info = storage_helper.get_storage_backend_info('ceph')
        LOG.info('Ceph backend info: {}'.format(ceph_info))
        return ceph_info
    else:
        return None


@mark.usefixtures('ceph_precheck')
@fixture(scope='module', autouse=True)
def ceph_backend_installed():
    ceph_info = get_ceph_backend_info()
    if not ceph_info:
        skip("No ceph system installed in the lab")
    else:
        if ProjVar.get_var("LAB")['short_name'] == 'pv0':
            skip("swift not stable yet after upgrade")
    rel, msg = storage_helper.is_ceph_healthy()
    if not rel:
        skip("Ceph health not OK: {}".format(msg))

    return ceph_info


@fixture(scope="module", autouse=True)
def collect_object_files(request, ceph_backend_installed):
    cmd = "cd; mkdir {}; cp *.sh {}".format(TEST_OBJ_DIR, TEST_OBJ_DIR)
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.exec_cmd(cmd)

    def teardown():
        delete_object_file(TEST_OBJ_PATH, rm_dir=True)
        delete_object_file(TEST_OBJ_DOWNLOAD_PATH, rm_dir=True)

    request.addfinalizer(teardown)


@fixture(scope='function', autouse=True)
def delete_swift_containers(request):
    """

    Args:
        request:

    Returns:

    """

    def teardown():
        output = swift_helper.get_swift_containers(fail_ok=True)[1]
        if len(output) > 0:
            swift_helper.delete_objects(delete_all=True)

    request.addfinalizer(teardown)
    return None

@fixture(scope='function')
def pre_swift_check():
    """

    Args:
        request:

    Returns:

    """
    ceph_backend_info = get_ceph_backend_info()
    if not eval(ceph_backend_info['object_gateway']):
        return False, "Swift is NOT  enabled"
    if swift_helper.get_swift_containers(fail_ok=True)[0] != 0:
            return False, "Swift enabled but NOT properly configured in the system"

    return True, 'Swift enabled and configured'

def get_large_img_file():
    cmd = "df -h ~ | awk ' {print $4}'"
    ctl_ssh = ControllerClient.get_active_controller()
    rc, output = ctl_ssh.exec_cmd(cmd)

    if rc == 0:
        avail = output.split('\n')[1]
        g = avail[len(avail)-1:]
        s = avail[:len(avail)-1]
        if g != 'G' or eval(s) - 8 < 1:

            return None
    else:
        return None

    glance_helper._scp_guest_image(img_os='win_2012', dest_dir=TEST_OBJ_PATH, timeout=300)
    large_filename = GuestImages.IMAGE_FILES['win_2012'][2]
    large_file_info = get_test_obj_file_names(pattern=large_filename)
    return large_file_info


@mark.parametrize('pool_size', ['default', 'fixed_size'])
def test_basic_swift_provisioning(pool_size, pre_swift_check):
    """
    Verifies basic swift provisioning works as expected
    Args:
        pool_size:
        ceph_backend_installed:

    Returns:

    """
    ceph_backend_info = get_ceph_backend_info()

    if pool_size == 'default' and pre_swift_check[0]:
        skip (msg = "Swift is already provisioned")

    object_pool_gib = None
    if pool_size == 'default':
        if not eval(ceph_backend_info['object_gateway'].strip()):
            LOG.tc_step("Enabling SWIFT object store .....")

    else:
        assert pre_swift_check()[0], pre_swift_check[1]

        unallocated_gib = int(ceph_backend_info['ceph_total_space_gib']) - \
                           (int(ceph_backend_info['cinder_pool_gib']) +
                            int(ceph_backend_info['glance_pool_gib']) +
                            int(ceph_backend_info['ephemeral_pool_gib']))
        object_pool_gib = str(unallocated_gib)
        LOG.tc_step("Enabling SWIFT object store and setting object pool size to {}.....".format(object_pool_gib))

    rc, updated_backend_info = storage_helper.modify_storage_backend('ceph', object_gateway=True,
                                                                     object_gib=object_pool_gib)

    LOG.info("Verifying if swift object gateway is enabled...")
    assert updated_backend_info['object_gateway'] == 'True', "Fail to enable Swift object gateway: {}"\
        .format(updated_backend_info)
    LOG.info("Swift object gateway is enabled.")
    LOG.info("Verifying ceph task ...")
    task = storage_helper.get_storage_backend_task_value('ceph')
    if system_helper.wait_for_alarm(alarm_id="250.001", timeout=10, fail_ok=True)[0]:
        LOG.info("Verifying ceph task is set to 'add-object-gateway'...")
        assert task == "add-object-gateway", "Unexpected ceph state = {} after swift object gateway update "\
            .format(task)

        LOG.info("Lock/Unlock controllers...")
        active_controller = system_helper.get_active_controller_name()
        standby_controller = system_helper.get_standby_controller_name()
        LOG.info("Active Controller is {}; Standby Controller is {}...".format(active_controller, standby_controller))

        for controller in [standby_controller, active_controller]:
            host_helper.lock_host(controller, swact=True)
            host_helper.unlock_host(controller)
        assert system_helper.wait_for_alarm_gone(alarm_id="250.001", fail_ok=True), "Alarm 250.001 not cleared"
    else:
        assert task == "None", "Unexpected ceph state = {} after swift object gateway update ".format(task)

    LOG.info("Verifying Swift provisioning setups...")
    assert verify_swift_object_setup(), "Failure in swift setups"

    guest_os = 'centos_7'
    image_id = glance_helper.get_guest_image(guest_os=guest_os)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'avp'},
            {'net-id': internal_net_id, 'vif-model': 'virtio'}]

    for i in range(1, 3):
        vol_name = "vol_{}_{}".format(guest_os, i)
        LOG.tc_step("Creating a volume {} from {} image {}".format(vol_name, guest_os, image_id))

        code, vol_id = cinder_helper.create_volume(name=vol_name, image_id=image_id, guest_image=guest_os,
                                                   fail_ok=True)
        ResourceCleanup.add('volume', vol_id)
        assert 0 == code, "Fail to  creating volume {}".format(vol_name)

        vm_name = 'vm_swift_api_{}'.format(i)
        LOG.tc_step("Boot a vm {} using flavor  and volume ")
        vm_id = vm_helper.boot_vm(name=vm_name, nics=nics, source_id=vol_id, guest_os=guest_os)[1]
        ResourceCleanup.add('vm', vm_id)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        LOG.tc_step("Attempting cold migrate VM {} ....".format(vm_name))
        rc = vm_helper.cold_migrate_vm(vm_id=vm_id)[0]
        LOG.info("Verifying cold migration succeeded...")
        assert rc == 0, "VM {} failed to cold migrate".format(vm_name)

        LOG.tc_step("Attempting live migrate VM {} ....".format(vm_name))
        rc = vm_helper.live_migrate_vm(vm_id=vm_id)[0]
        LOG.info("Verifying live migration succeeded...")
        assert rc == 0, "VM {} failed to live migrate".format(vm_name)

        LOG.tc_step("Attempting to suspend VM {} ....".format(vm_name))
        rc = vm_helper.suspend_vm(vm_id)[0]
        LOG.info("Verifying vm suspended...")
        assert rc == 0, "VM {} failed to suspend".format(vm_name)

        LOG.tc_step("Attempting to resume VM {} ....".format(vm_name))
        rc = vm_helper.resume_vm(vm_id)[0]
        LOG.info("Verifying vm resumed...")
        assert rc == 0, "VM {} failed to resume".format(vm_name)

    LOG.info("Checking overall system health...")
    assert system_helper.get_system_health_query(), "System health not OK after VMs"

    LOG.tc_step("Verifying creating Swift container using swift post cli command ...")
    container_names = ["test_container_1", "test_container_2", "test_container_3"]

    for container in container_names:
        LOG.info("Creating swift object container {}".format(container))
        rc, out = swift_helper.create_swift_container(container)
        assert rc == 0, "Fail to create swift container {}".format(container)
        LOG.info("Create swift object container {} successfully".format(container))

    LOG.tc_step("Verifying swift list to list containers ...")
    container_list = swift_helper.get_swift_containers()[1]
    assert set(container_names) <= set(container_list), "Swift containers {} not listed in {}"\
        .format(container_names, container_list)

    LOG.tc_step("Verifying swift delete a container...")
    container_to_delete = container_names[2]
    rc, out = swift_helper.delete_swift_container(container_to_delete)
    assert rc == 0, "Swift delete container rejected: {}".format(out)
    assert container_to_delete not in swift_helper.get_swift_containers()[1], "Unable to delete swift container {}"\
        .format(container_to_delete)

    LOG.tc_step("Verifying swift stat to show info of a single container...")
    container_to_stat = container_names[0]
    out = swift_helper.get_swift_container_stat_info(container_to_stat)
    assert out["Container"] == container_to_stat, "Unable to stat swift container {}"\
        .format(container_to_stat)
    assert out["Objects"] == '0', "Incorrect number of objects container {}. Expected O objects, but has {} objects"\
        .format(container_to_stat, out["Objects"])


@mark.parametrize("tc", ['small', 'large'])
def test_swift_cli_interaction(tc, pre_swift_check):

    if not pre_swift_check[0]:
        skip(msg=pre_swift_check[1])

    if tc == 'large':
        test_objects_info = get_large_img_file()
        if not test_objects_info:
            skip("Not enough space in /home/wrsroot for 8G large file")
    else:
        test_objects_info = get_test_obj_file_names()

    LOG.tc_step("Verifying {} object{} swift upload cli command ...".format(tc, 's' if tc is 'multiple' else ''))

    container = "test_container"
    LOG.info("Creating swift object container {}".format(container))
    rc, out = swift_helper.create_swift_container(container)
    assert rc == 0, "Fail to create swift container {}".format(container)

    LOG.tc_step("Verifying  container ...")
    container_list = swift_helper.get_swift_containers()[1]
    assert container in container_list, "Swift containers {} not listed in {}"\
        .format(container, container_list)

    LOG.tc_step("Verifying swift stat to show info of a single container...")

    out = swift_helper.get_swift_container_stat_info(container)
    assert out["Container"] == container, "Unable to stat swift container {}"\
        .format(container)
    assert out["Objects"] == '0', "Incorrect number of objects container {}. Expected O objects, but has {} objects"\
        .format(container, out["Objects"])

    LOG.tc_step("Verifying {} object{} upload {} to Swift container ..."
                .format(tc, 's' if tc is 'multiple' else '', 'by segments' if tc is 'large' else ''))
    upload_object = test_objects_info[0][0]
    src_obj = "{}/{}".format(TEST_OBJ_PATH, upload_object)

    segment_size = '2G'
    LOG.info("uploading {} object file {} with size {}   ...".format(tc, upload_object, test_objects_info[0][1]))

    rc, output = swift_helper.upload_objects(container, src_obj, object_name=upload_object,
                                             segment_size=segment_size if tc is 'large' else None)

    assert rc == 0, "Fail to upload object file {}".format(upload_object)

    LOG.info("Verifying if object file {} is uploaded  ...".format(upload_object))
    object_list = swift_helper.get_swift_container_object_list(container)[1]
    assert upload_object in object_list, "Object file {} missing from uploaded objects list {}"\
        .format(upload_object, object_list)

    LOG.info("Object file {} is uploaded successfully: {}".format(upload_object, object_list))

    if tc == 'large':
        delete_object_file(src_obj)

    LOG.tc_step("Verifying status of  container after upload {} object {}..."
                .format(tc, 'in chunks' if tc is 'large' else ''))

    stat_info = swift_helper.get_swift_container_stat_info(container)

    assert stat_info["Container"] == container, "Unable to stat swift container {}"\
        .format(container)

    assert stat_info["Objects"] == '1', \
        "Incorrect number of objects container {}. Expected 1 object, but has {} objects"\
        .format(container, stat_info["Objects"])

    LOG.tc_step("Verifying status of  object in container after upload ...")

    stat_object_info = swift_helper.get_swift_container_stat_info(container, upload_object)

    assert stat_object_info["Container"] == container, "Unable to stat swift container {}"\
        .format(container)

    assert stat_object_info["Object"] == upload_object, "Incorrect object name {} in container {}. Expected {}"\
        .format(stat_object_info["Object"], container, upload_object)

    assert stat_object_info["Content Length"] == test_objects_info[0][1], \
        "Incorrect Bytes size {} in stat. Expected {} Bytes."\
        .format(stat_object_info["Content Length"], test_objects_info[0][1])

    LOG.tc_step("Verifying download of  {} object file from container ...".format(tc))
    output_file = "{}/download_{}".format(TEST_OBJ_PATH, upload_object)
    out = swift_helper.download_objects(container=container, objects=upload_object, out_file=output_file)[1]
    assert any(upload_object in o for o in out), "Downloaded object {} not in {}".format(upload_object, out)

    assert delete_object_file(output_file),\
        "Unable to delete the source object file {}".format(upload_object)

    LOG.tc_step("Verifying deleting {} object file from container ...".format(tc))
    rc, msg = swift_helper.delete_objects(container=container, objects=upload_object)
    assert rc == 0, "Swift delete container object failed: {}".format(msg)

    LOG.tc_step("Verifying status of  container after deleting object ...")

    stat_info = swift_helper.get_swift_container_stat_info(container)

    assert stat_info["Container"] == container, "Unable to stat swift container {}"\
        .format(container)

    assert stat_info["Objects"] == '0', "Incorrect number of objects {} in container {}. Expected 0"\
        .format(stat_info["Objects"], container)

    assert stat_info["Bytes"] == '0', "Incorrect Bytes size {} in stat. Expected 0 Bytes."\
        .format(stat_info["Bytes"])

    LOG.info("{} object file {} is deleted successfully from container {}.".format(tc, upload_object, container))


def test_swift_cli_multiple_object_upload(pre_swift_check):

    if not pre_swift_check[0]:
        skip(msg=pre_swift_check[1])

    LOG.tc_step("Creating Swift container using swift post cli command ...")
    container = "test_container"

    LOG.info("Creating swift object container {}".format(container))
    rc, out = swift_helper.create_swift_container(container)
    assert rc == 0, "Fail to create swift container {}".format(container)
    LOG.info("Create swift object container {} successfully".format(container))

    LOG.tc_step("Verifying swift list to list containers ...")
    container_list = swift_helper.get_swift_containers()[1]
    assert container in container_list, "Swift containers {} not listed in {}"\
        .format(container, container_list)

    LOG.tc_step("Verifying swift stat to show info of a single container...")
    out = swift_helper.get_swift_container_stat_info(container)
    assert out["Container"] == container, "Unable to stat swift container {}"\
        .format(container)
    assert out["Objects"] == '0', "Incorrect number of objects container {}. Expected O objects, but has {} objects"\
        .format(container, out["Objects"])

    LOG.tc_step("Verifying upload multiple objects to Swift container ...")
    LOG.info("uploading objects from {} as swift objects ...".format(TEST_OBJ_PATH))

    object_files = get_test_obj_file_names()

    LOG.info("uploading test files {} as objects  ...".format(object_files))
    upload_dir = TEST_OBJ_PATH
    upload_prefix = 'multiple_'
    rc, output = swift_helper.upload_objects(container, upload_dir, object_name=upload_prefix)
    assert rc == 0, "Fail to upload mulitple object files {}".format(object_files)

    LOG.info("Verifying if object files  are uploaded  ...")
    object_list = swift_helper.get_swift_container_object_list(container)[1]
    t_files = [x[0] for x in object_files]
    for t in t_files:
        assert any(t in f for f in object_list), "Object file {} missing from uploaded objects list {}"\
            .format("multiple_" + t, object_list)

    LOG.info("Object file {} is uploaded successfully: {}".format(object_files[0][0], object_list))
    total_bytes = 0
    for obj in object_files:
        total_bytes += eval(obj[1])

    LOG.tc_step("Verifying status of  container after upload ...")
    stat_info = swift_helper.get_swift_container_stat_info(container)

    assert stat_info["Container"] == container, "Unable to stat swift container {}"\
        .format(container)

    assert stat_info["Objects"] == str(len(object_files)),\
        "Incorrect number of objects in container {}. Expected {} object, but has {} objects"\
        .format(container, stat_info["Objects"])

    assert eval(stat_info["Bytes"]) == total_bytes, "Incorrect Bytes size {} in stat. Expected {} Bytes."\
        .format(stat_info["Bytes"], total_bytes)

    LOG.tc_step("Verifying status of  objects in container after upload ...")

    LOG.info("Object list: {}".format(swift_helper.get_swift_container_object_list(container)))
    for img in object_files:
        upload_object = "multiple_/{}".format(img[0])
        object_size = img[1]

        stat_object_info = swift_helper.get_swift_container_stat_info(container, upload_object)
        LOG.info("Stat info: {}".format(stat_object_info))

        assert stat_object_info["Container"] == container, "Unable to stat swift container {}"\
            .format(stat_object_info)

        assert stat_object_info["Object"] == upload_object, "Incorrect object name {} in container {}. Expected {}"\
            .format(stat_object_info["Object"], container, upload_object)

        assert stat_object_info["Content Length"] == object_size,\
            "Incorrect Bytes size {} in stat. Expected {} Bytes."\
            .format(stat_object_info["Content Length"], object_size)

    LOG.tc_step("Verifying download of  multiple object files from container ...")
    download_file_dir = TEST_OBJ_DOWNLOAD_PATH
    out = swift_helper.download_objects(container=container, objects=object_list,
                                        output_dir=download_file_dir)[1]

    for obj in object_list:
        assert any(obj in o for o in out), "Downloaded object {} not in {}".format(obj, out)

    LOG.tc_step("Verifying deleting multiple object files from container ...")
    rc, msg = swift_helper.delete_objects(container=container, objects=object_list)
    assert rc == 0, "Swift delete container object failed: {}".format(msg)

    LOG.tc_step("Verifying status of  container after deleting multiple objects ...")

    stat_info = swift_helper.get_swift_container_stat_info(container)

    assert stat_info["Container"] == container, "Unable to stat swift container {}"\
        .format(container)

    assert stat_info["Objects"] == '0', "Incorrect number of objects {} in container {}. Expected 0"\
        .format(stat_info["Objects"], container)

    assert stat_info["Bytes"] == '0', "Incorrect Bytes size {} in stat. Expected 0 Bytes."\
        .format(stat_info["Bytes"])

    LOG.info("Objects {} are deleted successfully".format(object_list))


def test_swift_cli_update_metadata(pre_swift_check):
    """
    Verifies container and object metadata can be updated as expected
    Args:
        ceph_backend_installed:

    Returns:

    """
    if not pre_swift_check[0]:
        skip(msg=pre_swift_check[1])

    container_metadata = {
        'X-Container-Meta-Author': 'xxx',
        'X-Container-Meta-Web-Directory-Type': 'general',
        'X-Container-Meta-Century': 'yyy',
        }

    object_metedata = {
        'X-Object-Meta-Content-Type': 'binary',
        'X-Object-Meta-Content-Encoding': 'std',
        'X-Delete-At': str(time.time() + 3600),
        }
    upload_object = get_test_obj_file_names()[0][0]
    container = "test_container"

    LOG.tc_step("Verifying user can update container meta data ...")
    LOG.info("Creating container: {} ...".format(container))
    rc, out = swift_helper.create_swift_container(container)

    LOG.info("Verifying container {} is created ...".format(container))
    assert rc == 0, "Fail to create a container {}".format(container)
    container_list = swift_helper.get_swift_containers()[1]
    assert container in container_list, "Swift containers {} not listed in {}"\
        .format(container, container_list)

    LOG.info("Updating container with following meta data: {} ...".format(container_metadata))
    rc, out = swift_helper.post(container=container, meta=container_metadata)
    assert rc == 0, "Fail to create swift container {} with metadata: {} ".format(container, out)

    LOG.info("Getting swift stat to show info of container {}...".format(container))
    out = swift_helper.get_swift_container_stat_info(container)
    assert out["Container"] == container, "Unable to stat swift container {}"\
        .format(container)
    assert out["Objects"] == '0', "Incorrect number of objects container {}. Expected O objects, but has {} objects"\
        .format(container, out["Objects"])

    LOG.info("Checking for metadata {} in container {}...".format(container_metadata, container))
    for k, v in container_metadata.items():
        meta = 'Meta {}'.format(k)
        assert meta in out, "Meta-data {} missing from stat output {}".format(meta, out)
        assert out[meta] == v, "Container {} meta-data {} value is not expected value {}: {}"\
            .format(container, meta, v, out)
    LOG.info("Container {} metadata are successfully verified : {}".format(container, out))

    LOG.tc_step("Verifying certain container {} metadata value update ...".format(container))
    container_metadata['X-Container-Meta-Author'] = 'www'
    container_metadata['X-Container-Meta-Web-Directory-Type'] = 'specific'
    LOG.info("Updating container {} metadata ...".format(container))
    rc, out = swift_helper.post(container=container, meta=container_metadata)
    assert rc == 0, "Fail to update swift container {} with metadata: {} ".format(container, out)
    LOG.info("Checking container {} metadata values  are updated...".format(container))
    out = swift_helper.get_swift_container_stat_info(container)
    assert 'www' == out['Meta X-Container-Meta-Author'], \
        "Container {} meta-data 'X-Container-Meta-Author' value is not expected value 'www': {}".format(container, out)
    assert 'specific' == out['Meta X-Container-Meta-Web-Directory-Type'],\
        "Container {} meta-data 'X-Object-Meta-Content-Encoding' value is not expected value 'specific': {}"\
        .format(container, out)
    LOG.info("Container {} metadata updates are successfully verified : {}".format(container, out))

    LOG.tc_step("Verifying deleting container metadata values ...")
    container_metadata_2 = container_metadata.fromkeys(container_metadata, '')
    rc, out = swift_helper.post(container=container, meta=container_metadata_2)
    assert rc == 0, "Fail to delete swift container {}  metadata: {} ".format(container, out)

    LOG.tc_step("Verifying container {} metadata are deleted  ...".format(container))
    LOG.info("Getting swift stat to show info of container {}...".format(container))
    out = swift_helper.get_swift_container_stat_info(container)
    assert out["Container"] == container, "Unable to stat swift container {}"\
        .format(container)
    assert out["Objects"] == '0', "Incorrect number of objects container {}. Expected O objects, but has {} objects"\
        .format(container, out["Objects"])

    LOG.info("Checking for metadata {} in container {}...".format(container_metadata, container))
    for k in container_metadata_2:
        assert k not in out, "Meta-data {} still present in stat output {}".format(k, out)

    LOG.info("Container {} metadata are successfully deleted : {}".format(container, out))

    LOG.tc_step("Creating object with following meta data: {} ...".format(object_metedata))
    src_obj = "{}/{}".format(TEST_OBJ_PATH, upload_object)

    rc, out = swift_helper.upload_objects(container, src_obj, object_name=upload_object)
    assert rc == 0, "Fail to upload object file {}: {}".format(upload_object, out)

    LOG.info("Updating object {} metadata  in container {}...".format(upload_object, container))
    rc, out = swift_helper.post(container=container, object_=upload_object, meta=object_metedata)
    assert rc == 0, "Fail to update swift object {} with metadata: {} ".format(upload_object, out)

    LOG.tc_step("Verifying object {} metadata are updated with correct values ...".format(upload_object))

    LOG.info("Getting swift stat to show info of object {}...".format(upload_object))
    out = swift_helper.get_swift_container_stat_info(container=container, object_=upload_object)
    assert out["Container"] == container, "Unable to stat swift container {} object {}"\
        .format(container, upload_object)

    assert out["Object"] == upload_object, "Unexpected object name {} in container {}. Expected {}"\
        .format(out["Object"], container, upload_object)

    LOG.info("Checking for metadata {} in object {}...".format(object_metedata, upload_object))
    for k, v in object_metedata.items():
        meta = 'Meta {}'.format(k)
        assert meta in out, "Meta-data {} missing from stat output {}".format(meta, out)
        assert out[meta] == v,\
            "Container {} meta-data {} value is not expected value {}: {}".format(container, meta, v, out)
    LOG.info("Object {} metadata are successfully verified : {}".format(upload_object, out))

    object_metedata['X-Object-Meta-Content-Type'] = 'octet-stream'
    object_metedata['X-Object-Meta-Content-Encoding'] = 'base64'

    LOG.tc_step("Verifying certain object {} metadata value update ...".format(upload_object))
    LOG.info("Updating object {} metadata  in container {}...".format(upload_object, container))
    rc, out = swift_helper.post(container=container, object_=upload_object, meta=object_metedata)
    assert rc == 0, "Fail to update swift object {} with metadata: {} ".format(upload_object, out)

    out = swift_helper.get_swift_container_stat_info(container=container, object_=upload_object)
    LOG.info("Checking metadata values  object {}...".format(object_metedata, upload_object))
    assert 'octet-stream' == out['Meta X-Object-Meta-Content-Type'],\
        "Object {} meta-data 'X-Object-Meta-Content-Type' value is not expected value 'octet-stream': {}"\
        .format(upload_object, out)
    assert 'base64' == out['Meta X-Object-Meta-Content-Encoding'],\
        "Object {} meta-data 'X-Object-Meta-Content-Encoding' value is not expected value 'base64': {}"\
        .format(upload_object, out)
    LOG.info("Object {} metadata updates are successfully verified : {}".format(upload_object, out))

    LOG.tc_step("Verifying deleting object metadata values ...")
    object_metedata_2 = object_metedata.fromkeys(object_metedata, '')
    rc, out = swift_helper.post(container=container, object_=upload_object, meta=object_metedata_2)
    assert rc == 0, "Fail to delete swift object {}  metadata: {} ".format(upload_object, out)

    LOG.tc_step("Verifying object {} metadata are deleted  ...".format(upload_object))
    LOG.info("Getting swift stat to show info of object {}...".format(upload_object))
    out = swift_helper.get_swift_container_stat_info(container=container, object_=upload_object)
    assert out["Container"] == container, "Unable to stat swift container {}"\
        .format(container)
    assert out["Object"] == upload_object, "Unexpected object {} in container {}. Expected object: {}"\
        .format(out["Object"], container, upload_object)

    LOG.info("Checking for metadata {} in object {}...".format(object_metedata_2, upload_object))
    for k in object_metedata_2:
        assert k not in out, "Meta-data {} still present in stat output {}".format(k, out)

    LOG.info("Object {} metadata are successfully deleted : {}".format(upload_object, out))


@mark.parametrize("tc", ['small', 'large'])
def test_swift_basic_object_copy(tc, ceph_backend_installed, pre_swift_check):
    """
    Verifies basic object copy works as expected
    Args:
        tc:
        ceph_backend_installed:

    Returns:

    """
    if not pre_swift_check[0]:
        skip(msg=pre_swift_check[1])

    upload_object_info = get_test_obj_file_names()[0] if tc == 'small' else get_large_img_file()[0]
    container = "test_container"
    dest_container = "copy_container"
    upload_object = upload_object_info[0]

    object_metedata = {
        'X-Object-Meta-Content-Type': 'binary',
        'X-Object-Meta-Content-Encoding': 'std',
        'X-Delete-At': str(time.time() + 3600),
        }

    LOG.info("Verifying object copy from container {}  to destination container {} with metadata..."
             .format(container, dest_container))

    LOG.tc_step("Creating a source container  ...")
    rc, out = swift_helper.create_swift_container(container)
    assert rc == 0, "Fail to create swift container {}: {} ".format(container, out)
    container_list = swift_helper.get_swift_containers()[1]
    assert container in container_list, "Swift containers {} not listed in {}"\
        .format(container, container_list)

    LOG.tc_step("Uploading object {} to container {}  ...".format(upload_object, container))
    src_obj = "{}/{}".format(TEST_OBJ_PATH, upload_object)
    rc, out = swift_helper.upload_objects(container, src_obj, object_name=upload_object)
    assert rc == 0, "Fail to upload object file {}: {}".format(upload_object, out)

    LOG.info("Verifying if object files  are uploaded  ...")
    object_list = swift_helper.get_swift_container_object_list(container)[1]
    assert upload_object in object_list, "Object file {} missing from uploaded objects list {}"\
        .format(upload_object, object_list)
    LOG.info("Object file {} is uploaded successfully: {}".format(upload_object, object_list))
    if tc == 'large':
        delete_object_file(src_obj)

    LOG.tc_step("Updating object {} metadata  ...".format(upload_object))
    LOG.info("Updating object {} metadata  in container {}...".format(upload_object, container))
    rc, out = swift_helper.post(container=container, object_=upload_object, meta=object_metedata)
    assert rc == 0, "Fail to update swift object {} with metadata: {} ".format(upload_object, out)

    LOG.tc_step("Verifying object {} metadata are updated with correct values ...".format(upload_object))

    LOG.info("Getting swift stat to show info of object {}...".format(upload_object))
    out = swift_helper.get_swift_container_stat_info(container=container, object_=upload_object)
    assert out["Container"] == container, "Unable to stat swift container {} object {}"\
        .format(container, upload_object)

    assert out["Object"] == upload_object, "Unexpected object name {} in container {}. Expected {}"\
        .format(out["Object"], container, upload_object)

    LOG.info("Checking for metadata {} in object {}...".format(object_metedata, upload_object))
    for k, v in object_metedata.items():
        meta = 'Meta {}'.format(k)
        assert meta in out, "Meta-data {} missing from stat output {}".format(meta, out)
        assert out[meta] == v, \
            "Container {} meta-data {} value is not expected value {}: {}".format(container, meta, v, out)
    LOG.info("Object {} metadata are successfully verified : {}".format(upload_object, out))

    LOG.tc_step("Creating a destination container  ...")
    rc, out = swift_helper.create_swift_container(dest_container)
    assert rc == 0, "Fail to create swift container {}: {} ".format(dest_container, out)
    container_list = swift_helper.get_swift_containers()[1]
    assert dest_container in container_list, "Swift containers {} not listed in {}"\
        .format(dest_container, container_list)

    LOG.tc_step("Copying object {} from container {} to  destination container {} ..."
                .format(upload_object, container, dest_container))
    dest_object = "copy_{}".format(upload_object)
    rc, out = swift_helper.copy(container=container, object_=upload_object, dest_container=dest_container,
                                dest_object=dest_object)
    assert rc == 0, "Fail to copy object {} to dest container {}: {} ".format(upload_object, dest_container, out)

    LOG.info("Verifying if object file  is copied to dest container  ...")
    object_list = swift_helper.get_swift_container_object_list(dest_container)[1]
    assert dest_object in object_list, "Object file {} missing from dest container {} objects list {}"\
        .format(dest_object, dest_container, object_list)
    LOG.info("Object file {} is copied to dest container successfully: {}".format(dest_object, object_list))

    LOG.tc_step("Verifying metadata on copied object {}  ...".format(dest_object))

    LOG.info("Getting swift stat to show info of copied object {}...".format(dest_container))
    out = swift_helper.get_swift_container_stat_info(container=dest_container, object_=dest_object)
    assert out["Container"] == dest_container, "Unable to stat swift container {} object {}"\
        .format(dest_container, dest_object)

    assert out["Object"] == dest_object, "Unexpected object name {} in container {}. Expected {}"\
        .format(out["Object"], dest_container, dest_object)

    LOG.info("Checking for metadata {} in copied object {}...".format(object_metedata, dest_object))
    for k, v in object_metedata.items():
        meta = 'Meta {}'.format(k)
        assert meta in out, "Meta-data {} missing from stat output {}".format(meta, out)
        assert out[meta] == v, \
            "Container {} meta-data {} value is not expected value {}: {}".format(dest_container, meta, v, out)
    LOG.info("Object {} metadata are successfully verified : {}".format(dest_object, out))

    LOG.tc_step("Verifying object copy from container {}  to destination container {} with fresh metadata..."
                .format(container, dest_container))

    dest_object = "copy_2_{}".format(upload_object)
    rc, out = swift_helper.copy(container=container, object_=upload_object, dest_container=dest_container,
                                dest_object=dest_object, fresh_metadata=True)
    assert rc == 0, "Fail to copy object {} to dest container {}: {} ".format(upload_object, dest_container, out)

    LOG.info("Verifying if object file  is copied to dest container with fresh meta-data ...")
    object_list = swift_helper.get_swift_container_object_list(dest_container)[1]
    assert dest_object in object_list, "Object file {} missing from dest container {} objects list {}"\
        .format(dest_object, dest_container, object_list)
    LOG.info("Object file {} is copied to dest container successfully: {}".format(dest_object, object_list))

    LOG.tc_step("Verifying updated metadata from source object are not copied to destination object {}  ..."
                .format(dest_object))

    LOG.info("Getting swift stat to show info of copied object {}...".format(dest_container))
    out = swift_helper.get_swift_container_stat_info(container=dest_container, object_=dest_object)
    assert out["Container"] == dest_container, "Unable to stat swift container {} object {}"\
        .format(dest_container, dest_object)

    assert out["Object"] == dest_object, "Unexpected object name {} in container {}. Expected {}"\
        .format(out["Object"], dest_container, dest_object)

    LOG.info("Checking for metadata {} in copied object {}...".format(object_metedata, dest_object))
    for k in object_metedata:
        meta = 'Meta {}'.format(k)
        assert meta not in out, "Meta-data {} present in stat output {}".format(meta, out)

    LOG.info("Object {} metadata are successfully verified : {}".format(dest_object, out))


def verify_swift_object_setup():

    LOG.info("Verifying if swift object pools are setup...")

    if 'ceph' in storage_helper.get_configured_system_storage_backend():
        con_ssh = ControllerClient.get_active_controller()
        cmd = "rados df | awk 'NR>1 && NR < 11 {print $1}'"
        rc, output = con_ssh.exec_cmd(cmd, fail_ok=True)
        LOG.info("Swift object pools:{}".format(output))
        if rc == 0:
            pools = output.split('\n')
            if {'.rgw', '.rgw.buckets', '.rgw.control', '.rgw.gc', '.rgw.root'}.issubset(pools):
                LOG.info("Swift object pools: ['.rgw', '.rgw.buckets', '.rgw.control', '.rgw.gc', '.rgw.root']"
                         " are set...")
            else:
                LOG.info("Expected Swift object pools: ['.rgw', '.rgw.buckets', '.rgw.control', '.rgw.gc', '.rgw.root']"
                         " are NOT set. Pools = {}".format(pools))
                return False
        else:
            return False

    LOG.info("Verifying  swift endpoints...")
    port = '7480'
    endpoints_url = keystone_helper.get_endpoints(rtn_val='URL', service_name='swift', interface='public')[0]
    LOG.info("Swift  public endpoint url: {}".format(endpoints_url))
    url_port = endpoints_url.split(':')[2].split('/')[0].strip()
    if url_port != port:
        LOG.warning("Swift endpoint  use unexpected port {}. Expected port is {}.".format(url_port, port))
        return False

    LOG.info("Verifying if swift object service (ceph-radosgw) is listed via 'sudo sm-dump' on the "
             "active controller...")
    cmd = "sm-dump | grep ceph-radosgw | awk ' {print $1\" \" $2\" \" $3}'"
    con_ssh = ControllerClient.get_active_controller()
    rc, output = con_ssh.exec_sudo_cmd(cmd, fail_ok=True)

    if rc == 0 and "ceph-radosgw enabled-active enabled-active" in output:
        LOG.info("swift object service (ceph-radosgw) is listed via 'sudo sm-dump' on the active controller...")
    else:
        LOG.warning(" Unable to verify Swift object service ceph-radosgw: {}.".format(output))
        return False
    return True


def get_test_obj_file_names(directory=TEST_OBJ_DIR, pattern='.sh'):
    cmd = "cd; ls -l {} | grep {} | awk ' {{print $5 \" \" $9}}'".format(directory, pattern)
    con_ssh = ControllerClient.get_active_controller()
    rc, output = con_ssh.exec_cmd(cmd)
    obj_files = []
    if rc == 0:
        objects = output.split('\n')
        for obj in objects:
            size = obj.split(' ')[0]
            name = obj.split(' ')[1]
            obj_files.append([name, size])

    return obj_files


def delete_object_file(object_path, rm_dir=False):
    cmd = "ls {}".format(object_path)
    con_ssh = ControllerClient.get_active_controller()
    rc, output = con_ssh.exec_cmd(cmd)
    if rc == 0:
        cmd = 'rm {} {}'.format('-r' if rm_dir else '', object_path)
        con_ssh.exec_cmd(cmd)
        return True
    LOG.warning("File not found or unable to delete file {}: {}".format(object_path, output))
    return False

