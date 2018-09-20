from pytest import fixture, skip, mark

from consts.proj_vars import ProjVar
from keywords import vm_helper, nova_helper, host_helper, cinder_helper, glance_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover
from utils.tis_log import LOG
from utils.clients.ssh import get_cli_client

TEST_STRING = 'Config-drive test file content'


@fixture(scope='module')
def hosts_per_stor_backing():
    hosts_per_backing = host_helper.get_hosts_per_storage_backing()
    LOG.fixture_step("Hosts per storage backing: {}".format(hosts_per_backing))

    return hosts_per_backing


@mark.nightly
@mark.sx_nightly
def test_vm_with_config_drive(hosts_per_stor_backing):
    """
    Skip Condition:
        - Less than two hosts have  storage backing

    Test Steps:
        - create flavor with specified vcpus, cpu_policy, ephemeral, swap, storage_backing
        - boot vm from specified boot source with above flavor
        - (attach volume to vm if 'image_with_vol', specified in vm_type)
        - Cold migrate vm
        - Confirm/Revert resize as specified
        - Verify VM is successfully cold migrated and confirmed/reverted resize

    Teardown:
        - Delete created vm, volume, flavor

    """
    guest_os = 'cgcs-guest'
    # guest_os = 'tis-centos-guest'  # CGTS-6782
    img_id = glance_helper.get_guest_image(guest_os)
    hosts_num = len(hosts_per_stor_backing['local_image'])
    if hosts_num < 1:
        skip("No host with local_image storage backing")

    volume_id = cinder_helper.create_volume(name='vol_inst1', guest_image=guest_os, image_id=img_id)[1]
    ResourceCleanup.add('volume', volume_id, scope='function')

    block_device = {'source': 'volume', 'dest': 'volume', 'id': volume_id, 'device': 'vda'}
    test_file, file_dir = get_test_file()
    file = "{}/ip.txt={}".format(file_dir, test_file)

    vm_id = vm_helper.boot_vm(name='config_drive', config_drive=True, block_device=block_device, file=file,
                              cleanup='function', guest_os=guest_os)[1]

    LOG.tc_step("Confirming the config drive is set to True in vm ...")
    assert nova_helper.get_vm_nova_show_value(vm_id, "config_drive") == 'True', "vm config-drive not true"

    LOG.tc_step("Confirming the config drive data ...")
    config_drive_data = check_vm_config_drive_data(vm_id)
    assert TEST_STRING in config_drive_data, "The actual content of config drive data: {} is not as expected".\
        format(config_drive_data)

    if hosts_num < 2:
        LOG.info("Skip migration steps due to less than 2 local_image hosts on system")
        return

    LOG.tc_step("Attempting  cold migrate VM...")
    code, msg = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)
    LOG.tc_step("Verify cold migration succeeded...")
    assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

    LOG.tc_step("Confirming the config drive can be accessed after cold migrate VM...")

    config_drive_data = check_vm_config_drive_data(vm_id)
    assert TEST_STRING in config_drive_data, "The config drive data incorrect after cold migration. Output is : {}".\
        format(config_drive_data)

    LOG.tc_step("Locking the compute host ...")
    compute_host = vm_helper.get_vm_host_and_numa_nodes(vm_id)[0]
    HostsToRecover.add(compute_host)
    code, msg = host_helper.lock_host(compute_host, swact=True)
    assert code == 0, "Unable to lock vm host {}: {}".format(compute_host, msg)

    LOG.tc_step("Confirming the config drive can be accessed after locking VM host...")
    config_drive_data = check_vm_config_drive_data(vm_id)
    assert TEST_STRING in config_drive_data, "The config drive data incorrect after lock vm host. Output is : {}".\
        format(config_drive_data)

    new_host = vm_helper.get_vm_host_and_numa_nodes(vm_id)[0]
    instance_name = nova_helper.get_vm_instance_name(vm_id)
    LOG.info("The vm host is now: {}".format(new_host))
    LOG.tc_step("Check vm files exist on new vm host after migrated")
    with host_helper.ssh_to_host(new_host) as host_ssh:
        cmd = " ls /etc/nova/instances/{}".format(vm_id)
        cmd_output = host_ssh.exec_cmd(cmd)[1]
        # 'libvirt.xml' is removed from /etc/nova/instances in newton
        assert all(x in cmd_output for x in ['console.log', 'disk.config', 'disk.info']),\
            "VM not in host {}".format(new_host)

        output = host_ssh.exec_cmd('ls /run/libvirt/qemu')[1]
        libvirt = "{}.xml".format(instance_name)
        assert libvirt in output, "{} is not found in /run/libvirt/qemu on {}".format(libvirt, new_host)


def get_test_file():
    """
    This function is a workaround to adds user_data  for restarting the sshd. The
    sshd daemon fails to start in VM evacuation testcase.


    Returns:(str) - the file path of the userdata text file

    """
    file_dir = ProjVar.get_var('USER_FILE_DIR')
    test_file = "{}/test.txt".format(file_dir)
    client = get_cli_client()

    if not client.file_exists(test_file):
        cmd = "cat <<EOF > {}\n" \
              "{}\n" \
              "EOF".format(test_file, TEST_STRING)
        print(cmd)
        code, output = client.exec_cmd(cmd)
        LOG.info("Code: {} output: {}".format(code, output))

    return test_file, file_dir


def check_vm_config_drive_data(vm_id):
    """

    Args:
        vm_id:

    Returns:

    """
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        mount = get_mount(vm_ssh)
        location = get_config_drive_data_location(mount, vm_ssh)
        content = get_config_drive_data_content(mount, location, vm_ssh)
        return content


def get_mount(vm_ssh):
    """

    Args:
        vm_ssh:

    Returns:

    """
    dev = '/dev/hd'
    # Run mount command to determine the /dev/hdX is mount at:
    cmd = """mount | grep "{}" | awk '{{print  $3}} '""".format(dev)
    cmd_output = vm_ssh.exec_cmd(cmd)[1]
    assert cmd_output, "{} is not mounted".format(dev)
    LOG.info("The /dev/hdX is mount at: {}".format(cmd_output))
    return cmd_output


def get_config_drive_data_location(mount, vm_ssh):
    """

    Args:
        mount:
        vm_ssh

    Returns:

    """
    cmd = "python -m json.tool {}/openstack/latest/meta_data.json  | grep content | " \
          "awk '{{ print $2 }}' | tr -d '\",'".format(mount)
    LOG.info("command : {}".format(cmd))
    cmd_output = vm_ssh.exec_cmd(cmd)[1]
    assert cmd_output, "Config drive data location is not found"
    LOG.info("The test.txt file maps to : {}".format(cmd_output))
    return cmd_output


def get_config_drive_data_content(mount, location, vm_ssh):
    """

    Args:
        mount:
        location:
        vm_ssh

    Returns:

    """
    cmd = "cat {}/openstack/{}".format(mount, location)
    cmd_output = vm_ssh.exec_cmd(cmd)[1]
    assert cmd_output, "No config drive data found"
    LOG.info("The config drive data content : {}".format(cmd_output))
    return cmd_output
