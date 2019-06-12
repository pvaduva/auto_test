import time

from pytest import fixture

from consts.auth import HostLinuxCreds
from consts.cgcs import GuestImages
from consts.filepaths import TestServerPath, SYSADMIN_HOME, TiSPath
from consts.proj_vars import ProjVar
from keywords import host_helper, system_helper, common
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG

generated_vm_dict = {}


def create_simple_orphan(host_ssh, vm_host, vm_name):
    """ Creates a simple orphan out of the orphan_guest.xml file and the given vm_host and vm_name"""

    global generated_vm_dict
    define_xml_cmd = "virsh define orphan_guest.xml"
    start_guest_cmd = "virsh start {}".format(vm_name)

    LOG.info("Creating vm via virsh")
    host_ssh.exec_sudo_cmd(cmd=define_xml_cmd, fail_ok=False)
    if vm_host not in generated_vm_dict:
        generated_vm_dict[vm_host] = []
    (generated_vm_dict[vm_host]).append(vm_name)

    host_ssh.exec_sudo_cmd('cat orphan_guest.xml')
    code, output = host_ssh.exec_sudo_cmd(cmd=start_guest_cmd, fail_ok=False)

    LOG.info("Verify vm was created")
    assert code == 0 and output == 'Domain {} started'.format(vm_name), 'virsh start failed, output: {}'.format(output)


def wait_for_deletion(compute_ssh, vm_name):
    list_check_cmd = "virsh list --all | grep {}".format(vm_name)

    orphan_audit_wait_limit = 330
    end_time = time.time() + orphan_audit_wait_limit
    while time.time() < end_time:
        exitcode = compute_ssh.exec_sudo_cmd(cmd=list_check_cmd)[0]
        if exitcode != 0:  # Indicates vm has been deleted
            return True
        time.sleep(10)

    return False


@fixture(scope='module')
def orphan_audit_setup(request):
    """ SCPs files to setup test orphan audit test """

    con_ssh = ControllerClient.get_active_controller()
    vm_host = host_helper.get_up_hypervisors()[0]

    LOG.fixture_step("SCP orphan_guest.xml to active controller")
    source_file = TestServerPath.TEST_FILES + 'orphan_guest.xml'
    common.scp_from_test_server_to_active_controller(source_file, dest_dir=SYSADMIN_HOME, dest_name='orphan_guest.xml',
                                                     timeout=120, con_ssh=None)

    LOG.fixture_step("Change orphan_guest.xml specs allow a vm to be properly launched")
    LOG.info("If test is running on VBox, change domain type in xml to qemu")
    nat_name = ProjVar.get_var('NATBOX').get('name')

    if nat_name == 'localhost' or nat_name.startswith('128.224.'):
        LOG.info("Changing domain type in xml to qemu")
        con_ssh.exec_sudo_cmd("sed -i 's/kvm/qemu/g' orphan_guest.xml")
        con_ssh.exec_sudo_cmd("sed -i 's/qemu-qemu/qemu-kvm/g' orphan_guest.xml")

    if GuestImages.DEFAULT['guest'] != 'tis-centos-guest':
        LOG.info("Update xml files to use default image")
        con_ssh.exec_sudo_cmd("sed -i 's/tis-centos-guest/{}/g' orphan_guest.xml".format(GuestImages.DEFAULT['guest']))

    # Check if system is AIO, skip scp to computes if it is
    if not system_helper.is_aio_system():
        LOG.fixture_step("Non-AIO system detected, SCP files to compute")
        with host_helper.ssh_to_host(vm_host) as host_ssh:
            LOG.info("Create images dir in compute host")
            host_ssh.exec_cmd('mkdir -p images')

        def teardown():
            LOG.fixture_step("Delete all files scp'd over")
            with host_helper.ssh_to_host(vm_host) as host_ssh_:
                host_ssh_.exec_cmd('rm -rf images/{}.img'.format(GuestImages.DEFAULT['guest']))
                host_ssh_.exec_cmd('rm orphan_guest.xml')
        request.addfinalizer(teardown)

        # copy Default guest img and XML file over to compute
        img_path = TiSPath.IMAGES + GuestImages.IMAGE_FILES.get(GuestImages.DEFAULT['guest'])[2]
        con_ssh.scp_on_source(SYSADMIN_HOME + 'orphan_guest.xml', HostLinuxCreds.get_user(), vm_host, SYSADMIN_HOME,
                              HostLinuxCreds.get_password(), timeout=60)
        con_ssh.scp_on_source(img_path, HostLinuxCreds.get_user(), vm_host, TiSPath.IMAGES,
                              HostLinuxCreds.get_password(), timeout=300)

    else:
        vm_host = system_helper.get_active_controller_name()

    return vm_host


@fixture(scope='function')
def clear_virsh_vms(request):
    """ Clears leftover vms made by tests """
    def teardown():
        global generated_vm_dict
        for host in generated_vm_dict:
            with host_helper.ssh_to_host(host) as host_ssh:
                for vm in generated_vm_dict[host]:
                    host_ssh.exec_sudo_cmd('virsh destroy {}'.format(vm))
                    host_ssh.exec_sudo_cmd('virsh undefine {}'.format(vm))
        generated_vm_dict = {}
    request.addfinalizer(teardown)


# TC2990
def test_orphan_audit(orphan_audit_setup, clear_virsh_vms):
    """
    Tests the orphan audit by booting an instance directly on compute node to bypass nova, wait for 5 minutes and
    ensure that it gets cleaned up (TC2990 on rally)

    Test setup:
        - SCP two files to a compute node:
        - The DEFAULT_GUEST image currently on the controller node
        - An XML file that is on the test server (orphan_guest.xml) that will be used to define an start a VM
          with virsh
        - Change domain type in XML file to qemu if the test is being ran in a vbox

    Test steps:
        - Change the vm name in the XML file to an auto-generated name
        - SSH onto the node hosting the VM and run virsh define orphan_guest.xml and then virsh start Orphan_VM
          to start the VM
            - Assert that vm creation was successful by checking output of virsh start. Output of virsh list is logged
          as well
        - Check virsh list output to make sure that openstack has automatically cleaned up the orphan instance by
          5.5 minutes. This check is periodically done every 10 seconds to a maximum of 5.5 minutes. The test
          immediately passes if any of the checks reports the abscence of the orphan_vm and fails if the vm is
          still present in the list after 5.5 minutes.

    Test Teardown:
        - Delete created VMs

    """
    vm_host = orphan_audit_setup

    # Create standalone vm
    vm_name = common.get_unique_name('orphan', resource_type='vm')

    LOG.tc_step("Change orphan_vm name to an auto-generated name")
    with host_helper.ssh_to_host(vm_host) as host_ssh:
        host_ssh.exec_sudo_cmd("sed -r -i 's#<name>.*</name>#<name>{}</name>#g' orphan_guest.xml".format(vm_name))

        LOG.tc_step("Create a simple orphan vm")
        create_simple_orphan(host_ssh, vm_host, vm_name)

        list_cmd = 'virsh list --all'
        host_ssh.exec_sudo_cmd(list_cmd)

        # wait and check for deletion
        LOG.tc_step("Check for deletion of vm")
        assert wait_for_deletion(host_ssh, vm_name), "{} is still in virsh list after 330 seconds".format(vm_name)

    global generated_vm_dict
    generated_vm_dict[vm_host].remove(vm_name)
