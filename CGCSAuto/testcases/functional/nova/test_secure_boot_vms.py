import time
from utils.tis_log import LOG
from consts.cgcs import GuestImages, ImageMetadata
from consts.cli_errs import LiveMigErr      # Don't remove this import, used by eval()
from keywords import vm_helper, nova_helper, host_helper, cinder_helper, glance_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup
from utils import exceptions


def _check_secure_boot_on_vm(vm_id):
    retry = 3
    count = 0
    in_vm = False
    while count <= retry and not in_vm:
        try:
            with vm_helper.ssh_to_vm_from_natbox(vm_id, username='ubuntu', password='ubuntu', retry_timeout=800,
                                                 timeout=800) as vm_ssh:
                in_vm = True
                code, output = vm_ssh.exec_cmd('mokutil --sb-state', fail_ok=False)
                assert "SecureBoot enabled" in output, "Vm did not boot in secure mode: {}".format(output)
        except exceptions.SSHException:
            time.sleep(60)
            with vm_helper.ssh_to_vm_from_natbox(vm_id, username='ubuntu', password='ubuntu', retry_timeout=800,
                                                 timeout=800) as vm_ssh:
                code, output = vm_ssh.exec_cmd('mokutil --sb-state', fail_ok=False)
                assert "SecureBoot enabled" in output, "Vm did not boot in secure mode: {}".format(output)
        count += 1


def create_image_with_metadata(guest_os, property_key, values, disk_format, container_format):
    """
    Create image with given metadata/property.

    Args:
        guest_os:
        property_key (str): the key for the property, such as sw_wrs_auto_recovery
        values (list): list of values to test for the specific key
        disk_format (str): such as 'raw', 'qcow2'
        container_format (str): such as bare

    Test Steps;
        - Create image with given disk format, container format, property key and value pair
        - Verify property value is correctly set via glance image-show

    Returns: List of image ids


    """
    image_ids = []

    for value in values:
        LOG.tc_step("Creating image with property {}={}, disk_format={}, container_format={}".
                    format(property_key, value, disk_format, container_format))
        image_name = GuestImages.IMAGE_FILES[guest_os][0]
        image_name = str(image_name) + "_auto"
        img_id = glance_helper.get_image_id_from_name(image_name, strict=True)
        if not img_id:
            image_path = glance_helper._scp_guest_image(img_os=guest_os)

            image_id = glance_helper.create_image(source_image_file=image_path, cleanup='function',
                                                  disk_format=disk_format, container_format=container_format,
                                                  **{property_key: value})[1]
            image_ids.append(image_id)

            LOG.tc_step("Verify image property is set correctly via glance image-show.")
            actual_property_val = glance_helper.get_image_properties(image_id, property_key)[property_key]
            assert value.lower() == actual_property_val.lower(), \
                "Actual image property {} value - {} is different than set value - {}".format(
                    property_key, actual_property_val, value)
        else:
            image_ids.append(img_id)

    return image_ids


def test_vm_actions_secure_boot_vm():
    """
    This is to test a vm that is booted with secure boot and do the vm actions such as reboot, migrations

    :return:

    """
    guests_os = ['trusty_uefi', 'uefi_shell']
    disk_format = ['qcow2', 'raw']
    image_ids = []
    volume_ids = []
    for guest_os, disk_format in zip(guests_os, disk_format):
        image_ids.append(create_image_with_metadata(guest_os=guest_os,
                                                    property_key=ImageMetadata.FIRMWARE_TYPE, values=['uefi'],
                                                    disk_format=disk_format, container_format='bare'))
    # create a flavor
    flavor_id = nova_helper.create_flavor(vcpus=2, ram=1024, root_disk=5)[1]
    ResourceCleanup.add('flavor', flavor_id)
    # boot a vm using the above image
    for image_id in image_ids:
        volume_ids.append(cinder_helper.create_volume(image_id=image_id[0], size=5, cleanup='function')[1])

    block_device_dic = [{'id': volume_ids[1], 'source': 'volume', 'bootindex': 0},
                        {'id': volume_ids[0], 'source': 'volume', 'bootindex': 1}]

    vm_id = vm_helper.boot_vm(name='sec-boot-vm', source='block_device', flavor=flavor_id,
                              block_device=block_device_dic, cleanup='function', guest_os=guests_os[0])[1]

    _check_secure_boot_on_vm(vm_id=vm_id)
    if system_helper.is_simplex():
        vm_actions_list = [['reboot'], ['pause', 'unpause'], ['suspend', 'resume']]
    else:
        vm_actions_list = [['reboot'], ['pause', 'unpause'], ['suspend', 'resume'], ['live_migrate'],
                      ['cold_migrate'], ['cold_mig_revert']]

    for vm_actions in vm_actions_list:

        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_id, vm_actions))
        for action in vm_actions:
            vm_helper.perform_action_on_vm(vm_id, action=action)

        LOG.tc_step("Verifying Secure boot is still enabled after vm action {}".format(vm_actions))
        _check_secure_boot_on_vm(vm_id=vm_id)


def test_lock_unlock_secure_boot_vm():

    """
    This is to test host lock with secure boot vm.

    :return:
    """
    guests_os = ['trusty_uefi', 'uefi_shell']
    disk_format = ['qcow2', 'raw']
    image_ids = []
    volume_ids = []
    for guest_os, disk_format in zip(guests_os, disk_format):
        image_ids.append(create_image_with_metadata(guest_os=guest_os,
                                                    property_key=ImageMetadata.FIRMWARE_TYPE, values=['uefi'],
                                                    disk_format=disk_format, container_format='bare'))
    # create a flavor
    flavor_id = nova_helper.create_flavor(vcpus=2, ram=1024, root_disk=5)[1]
    ResourceCleanup.add('flavor', flavor_id)
    # boot a vm using the above image
    for image_id in image_ids:
        volume_ids.append(cinder_helper.create_volume(image_id=image_id[0], size=5, cleanup='function')[1])

    block_device_dic = [{'id': volume_ids[1], 'source': 'volume', 'bootindex': 0},
                        {'id': volume_ids[0], 'source': 'volume', 'bootindex': 1}]

    vm_id = vm_helper.boot_vm(name='sec-boot-vm', source='block_device', flavor=flavor_id,
                              block_device=block_device_dic, cleanup='function', guest_os=guests_os[0])[1]

    _check_secure_boot_on_vm(vm_id=vm_id)

    # Lock the compute node with the secure Vms
    compute_host = nova_helper.get_vm_host(vm_id=vm_id)
    host_helper.lock_host(compute_host, timeout=800)
    if not system_helper.is_simplex():
        _check_secure_boot_on_vm(vm_id=vm_id)
    host_helper.unlock_host(compute_host, timeout=800)

    if system_helper.is_simplex():
        _check_secure_boot_on_vm(vm_id=vm_id)


def test_host_reboot_secure_boot_vm():
    """
    This is to test host evacuation for secure boot vm

    :return:
    """
    guests_os = ['trusty_uefi', 'uefi_shell']
    disk_format = ['qcow2', 'raw']
    image_ids = []
    volume_ids = []
    for guest_os, disk_format in zip(guests_os, disk_format):
        image_ids.append(create_image_with_metadata(guest_os=guest_os,
                                                    property_key=ImageMetadata.FIRMWARE_TYPE, values=['uefi'],
                                                    disk_format=disk_format, container_format='bare'))
    # create a flavor
    flavor_id = nova_helper.create_flavor(vcpus=2, ram=1024, root_disk=5)[1]
    ResourceCleanup.add('flavor', flavor_id)
    # boot a vm using the above image
    for image_id in image_ids:
        volume_ids.append(cinder_helper.create_volume(image_id=image_id[0], size=5, cleanup='function')[1])

    block_device_dic = [{'id': volume_ids[1], 'source': 'volume', 'bootindex': 0},
                        {'id': volume_ids[0], 'source': 'volume', 'bootindex': 1}]

    vm_id = vm_helper.boot_vm(name='sec-boot-vm', source='block_device', flavor=flavor_id,
                              block_device=block_device_dic, cleanup='function', guest_os=guests_os[0])[1]

    _check_secure_boot_on_vm(vm_id=vm_id)

    compute_host = nova_helper.get_vm_host(vm_id=vm_id)
    vm_helper.evacuate_vms(compute_host, vms_to_check=vm_id, timeout=800)
    _check_secure_boot_on_vm(vm_id=vm_id)
