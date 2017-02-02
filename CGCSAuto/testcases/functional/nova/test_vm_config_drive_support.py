
from pytest import fixture, skip

from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.cgcs import FlavorSpec
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, host_helper, cinder_helper, glance_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def hosts_per_stor_backing():
    hosts_per_backing = host_helper.get_hosts_per_storage_backing()
    LOG.fixture_step("Hosts per storage backing: {}".format(hosts_per_backing))

    return hosts_per_backing


def test_cold_migrate_vm_with_config_drive(hosts_per_stor_backing):
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
    if len(hosts_per_stor_backing['local_image']) < 2:
        skip("Less than two hosts have local_image storage backing")

    image_id = glance_helper.get_image_id_from_name(name='cgcs-guest')
    volume_id = cinder_helper.create_volume(name='vol_inst1', image_id=image_id, size=2)[1]
    ResourceCleanup.add('volume', volume_id, scope='module')
    block_device = 'source=volume,dest=volume,id={},device=vda'.format(volume_id)
    block_device_mapping = 'vda={}:::0'.format(volume_id)
    file = "/home/wrsroot/ip.txt={}".format(get_test_file())

    vm_id = vm_helper.boot_vm(name='tenant2-test6',
                              key_name='keypair-tenant2', config_drive=True,
                              block_device=block_device, file=file)[1]

    ResourceCleanup.add('vm', vm_id, scope='module')
    LOG.tc_step("Confirming the config drive is set to True in vm ...")
    assert nova_helper.get_vm_nova_show_value(vm_id, "config_drive") == 'True', "vm config-drive not true"

    LOG.tc_step("Confirming the config drive data ...")
    config_drive_data = check_vm_config_drive_data(vm_id)
    assert "test file for tenant2" in config_drive_data, "The content of config drive data: {} is not expected value:" \
                                                         " \"test file for tenent2\"".format(config_drive_data)
    LOG.tc_step("Attempting  cold migrate VM...")
    code, msg = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)
    LOG.tc_step("Verify cold migration succeeded...")
    assert code == 0, "Expected return code 0. Actual return code: {}; details: {}".format(code,  msg)

    LOG.tc_step("Confirming the config drive can be accessed after cold migrate VM...")

    config_drive_data = check_vm_config_drive_data(vm_id)
    assert "test file for tenant2" in config_drive_data, "The config drive data not accessible after cold migration. " \
                                                         "Output is : {}".format(config_drive_data)

    LOG.tc_step("Locking the compute host ...")
    compute_host = vm_helper.get_vm_host_and_numa_nodes(vm_id)[0]
    HostsToRecover.add(compute_host)
    code, msg = host_helper.lock_host(compute_host)
    assert code == 0, "Unable to lock vm host {}: {}".format(compute_host, msg)

    LOG.tc_step("Confirming the config drive can be accessed after locking VM host...")
    config_drive_data = check_vm_config_drive_data(vm_id)
    assert "test file for tenant2" in config_drive_data, "The config drive data not accessible after lock vm host. " \
                                                         "Output is : {}".format(config_drive_data)

    new_compute_host = vm_helper.get_vm_host_and_numa_nodes(vm_id)[0]
    LOG.info("The vm host is now: {}".format(new_compute_host))
    with host_helper.ssh_to_host(new_compute_host) as vm_ssh:
        cmd = " ls /etc/nova/instances/{}".format(vm_id)
        cmd_output = vm_ssh.exec_cmd(cmd)[1]
        assert all(x in cmd_output for x in ['console.log', 'disk.config', 'disk.info', 'libvirt.xml']),\
            "VM not in host {}".format(new_compute_host)


def get_test_file():
    """
    This function is a workaround to adds user_data  for restarting the sshd. The
    sshd daemon fails to start in VM evacuation testcase.


    Returns:(str) - the file path of the userdata text file

    """

    auth_info = Tenant.get_primary()
    tenant = auth_info['tenant']
    test_file = "/home/wrsroot/test.txt"
    controller_ssh = ControllerClient.get_active_controller()
    cmd = "test -e {}".format(test_file)
    rc = controller_ssh.exec_cmd(cmd)[0]
    if rc != 0:
        cmd = "cat <<EOF > {}\n" \
              "test file for tenant2\n" \
              "EOF".format(test_file)
        print(cmd)
        code, output = controller_ssh.exec_cmd(cmd)
        LOG.info("Code: {} output: {}".format(code, output))

    return test_file


def check_vm_config_drive_data(vm_id):
    """

    Args:
        vm_id:

    Returns:

    """
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        mount = get_mount(vm_id, vm_ssh )
        location = get_config_drive_data_location(vm_id, mount, vm_ssh)
        content = get_config_drive_data_content(vm_id, mount, location, vm_ssh)
        return content


def get_mount(vm_id, vm_ssh):
    """

    Args:
        vm_id:

    Returns:

    """
    # Run mount command to determine the /dev/hdX is mount at:
    cmd = "mount | grep \"/dev/hd\" | awk '{print  $3} '"
    cmd_output = vm_ssh.exec_cmd(cmd)[1]
    LOG.info("The /dev/hdX is mount at: {}".format( cmd_output))
    return cmd_output


def get_config_drive_data_location(vm_id, mount, vm_ssh):
    """

    Args:
        vm_id:
        mount:

    Returns:

    """
    cmd = "python -m json.tool {}/openstack/latest/meta_data.json  | grep content | " \
          "awk '{{ print $2 }}' | tr -d '\",'".format(mount)
    LOG.info("command : {}".format(cmd))
    cmd_output = vm_ssh.exec_cmd(cmd)[1]
    LOG.info("The test.txt file maps to : {}".format(cmd_output))
    return cmd_output


def get_config_drive_data_content(vm_id, mount, location, vm_ssh):
    """

    Args:
        vm_id:
        mount:
        location:

    Returns:

    """
    cmd = "cat {}/openstack/{}".format(mount, location)
    cmd_output = vm_ssh.exec_cmd(cmd)[1]
    LOG.info("The config drive data content : {}".format(cmd_output))
    return cmd_output
