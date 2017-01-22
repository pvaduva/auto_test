
import time
from pytest import mark, fixture
from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import NATBoxClient
from utils.multi_thread import MThread
from consts.cgcs import FlavorSpec, Prompt
from keywords import network_helper, vm_helper, nova_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def router_info(request):
    LOG.fixture_step("get router id.")

    router_id = network_helper.get_tenant_router()
    network_helper.update_router_ext_gateway_snat(router_id, enable_snat=True)

    def teardown():
        network_helper.update_router_ext_gateway_snat(router_id, enable_snat=False)
    request.addfinalizer(teardown)

    return router_id


@fixture(scope='function')
def delete_scp_files_from_nat(request):
    def teardown():
        nat_ssh = NATBoxClient.get_natbox_client()
        cmd = "ls test_80*"
        rc, output = nat_ssh.exec_cmd(cmd)
        if rc == 0:
            if output is not None:
                cmd = " rm -f test_80*"
                nat_ssh.exec_cmd(cmd)

    request.addfinalizer(teardown)
    return None


@fixture(scope='function')
def delete_pfs(request):
    def teardown():
        router_id = network_helper.get_tenant_router()
        pf_ids = network_helper.get_portforwarding_rules(router_id)
        network_helper.delete_portforwarding_rules(pf_ids)
    request.addfinalizer(teardown)
    return None


@fixture(scope='function')
@mark.usefixtures('ubuntu14_image')
def _vms(ubuntu14_image):
    """

    Args:
        ubuntu14_image:

    Returns:

    """

    image_id = ubuntu14_image
    guest_os = 'ubuntu_14'
    size = 9

    LOG.fixture_step("Create a favor with {}G root disk and dedicated cpu policy".format(size))
    flavor_id = nova_helper.create_flavor(name='dedicated-{}g'.format(size), root_disk=size)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_ids = network_helper.get_tenant_net_ids()
    internal_net_id = network_helper.get_internal_net_id()
    vm_names = ['virtio1_vm', 'avp1_vm', 'avp2_vm', 'vswitch1_vm']
    vm_vif_models = {'virtio1_vm': 'virtio',
                     'avp1_vm': 'avp',
                     'avp2_vm': 'avp',
                     'vswitch1_vm': 'avp'}

    vms = []

    for (vm, i) in zip(vm_names, range(0, 4)):
        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_ids[i], 'vif-model': vm_vif_models[vm]},
                {'net-id': internal_net_id, 'vif-model': vm_vif_models[vm]}]

        LOG.fixture_step("Create a {}G volume from {} image".format(size, image_id))
        vol_id = cinder_helper.create_volume(name='vol-{}'.format(vm), image_id=image_id, size=size)[1]
        ResourceCleanup.add('volume', vol_id)

        LOG.fixture_step("Boot a ubuntu14 vm with {} nics from above flavor and volume".format(vm_vif_models[vm]))
        vm_id = vm_helper.boot_vm('{}'.format(vm), flavor=flavor_id, source='volume',
                                  source_id=vol_id, nics=nics, guest_os=guest_os)[1]
        ResourceCleanup.add('vm', vm_id, del_vm_vols=True)
        vms.append(vm_id)

    return vms

def test_port_forwarding_rule_create_for_vm(_vms, delete_pfs):

    for vm_id, i in zip(_vms, range(len(_vms))):
        vm_name = nova_helper.get_vm_name_from_id(vm_id)
        public_port = str(9090 + i)
        LOG.info("Creating  port forwarding rule for VM: {}: outside_port={}.".format(vm_name, public_port))

        rc, pf_id, msg = network_helper.create_port_forwarding_rule_for_vm(vm_id,
                                                                    inside_port=str(90),
                                                                    outside_port=public_port)

        assert rc == 0, "Port forwarding rule create failed for VM {}: {}".format(vm_name, msg)

    LOG.info("rc {}; pf_id {} msg {}".format(rc, pf_id, msg))


def test_external_access_to_vm_tcp_protocol(_vms, router_info, delete_pfs, delete_scp_files_from_nat):
    """

    Args:
        _vms:
        router_info:

    Returns:

    """

    router_id = router_info
    vm_mgmt_ips = network_helper.get_mgmt_ips_for_vms(_vms, rtn_dict=True)

    LOG.tc_step("Creating ssh port forwarding rules for VMs: {}.".format(_vms))
    vm_ssh_pfs = create_portforwarding_rules_for_vms(vm_mgmt_ips, router_id, "tcp", for_ssh=True)

    LOG.tc_step("Creating tcp port forwarding rules for VMs: {}.".format(_vms))
    vm_tcp_pfs = create_portforwarding_rules_for_vms(vm_mgmt_ips, router_id, "tcp", for_ssh=False)

    LOG.tc_step("Testing external access to vms and  TCP packets ...")

    ext_ip_address = network_helper.get_router_ext_gateway_subnet_ip_address(router_id)
    LOG.info("External Router IP address = {}".format(ext_ip_address))

    LOG.info("Setting NATBox SSH session ...")
    ssh_nat = NATBoxClient.set_natbox_client()

    vm_threads = [None] * 4
    index = 0
    for k, v in vm_tcp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        ssh_public_port = vm_ssh_pfs[k]['public_port']
        thread_vm = MThread(check_ssh_to_vm_and_wait_for_packets, k, ext_ip_address, ssh_public_port, greeting)
        vm_threads[index] = thread_vm
        index += 1

    LOG.info("Starting VM ssh session threads .... ")

    for t in vm_threads:
        t.start_thread()

    time.sleep(90)

    for k, v in vm_tcp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        rc, output = send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, v['public_port'],
                                                     greeting, "tcp")
        LOG.info("Send {} to {}:{}".format(greeting, ext_ip_address, v['public_port']))
        LOG.info("Result rc= {}; Output = {}".format(rc, output))

    for t in vm_threads:
        t.wait_for_thread_end(fail_ok=True)

    outputs = []
    for t in vm_threads:
        output = t.get_output()
        LOG.info("Thread {} output: {}".format(t.name, output))
        outputs.append(output)
    for i in range(0, 4):
        assert outputs[i][1] in outputs[i][0], "VM  did not receive the expected packets {}".format(outputs[i][1])
        for j in range(0, 4):
            if j != i:
                assert outputs[i][1] not in outputs[j][0], "VM  received the unexpected packets {}"\
                    .format(outputs[i][1])

    LOG.info("TCP protocol external access VMs passed")

    LOG.tc_step("Testing non tcp packets  in  TCP protocol port forwarding rules ...")

    vm_threads = [None] * 4
    index = 0
    for k, v in vm_tcp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        ssh_public_port = vm_ssh_pfs[k]['public_port']
        thread_vm = MThread(check_ssh_to_vm_and_wait_for_packets, k, ext_ip_address, ssh_public_port, greeting)
        vm_threads[index] = thread_vm
        index += 1

    LOG.info("Starting VM ssh session threads and NAT ssh session threads .... ")

    for t in vm_threads:
        t.start_thread()
    time.sleep(90)

    for k, v in vm_tcp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        rc, output = send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, v['public_port'],
                                                     greeting, "udp")
        LOG.info("Send {} to {}:{}".format(greeting, ext_ip_address, v['public_port']))
        LOG.info("Result rc= {}; Output = {}".format(rc, output))

    outputs = []
    for t in vm_threads:
        output = t.get_output()
        LOG.info("Thread {} output: {}".format(t.name, output))
        outputs.append(output)

    LOG.info("Terminating VM ssh sessions  by sending valid tcp packets .... ")
    for k, v in vm_tcp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        rc, output = send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, v['public_port'],
                                                     greeting, "tcp")
        LOG.info("Send {} to {}:{}".format(greeting, ext_ip_address, v['public_port']))
        LOG.info("Result rc= {}; Output = {}".format(rc, output))

    LOG.info("Checking non-tcp packets are not received by vms......")
    for i in range(0, 4):
        assert outputs[i] is None or outputs[i][1] not in outputs[i][0], "VM received UDP packets on TCP port " \
                                                                         "forwarding rules {}".format(outputs[i][1])
    LOG.info("Non-tcp packets not received as expected .... ")

    LOG.tc_step("Testing SCP to and from VMs ...")
    for k, v in vm_tcp_pfs.items():
        vm_name = nova_helper.get_vm_name_from_id(k)
        ssh_public_port = vm_ssh_pfs[k]['public_port']
        scp_to_vm_from_nat_box(ssh_nat, k, "ubuntu", ext_ip_address, ssh_public_port)
        LOG.info("SCP to/from VM {} is successful .... ".format(vm_name))

    LOG.info("SCP to/from VMs successful.... ")

    LOG.tc_step("Testing changes to forwarding rules ...")
    # get the first VM and external port forwarding rule
    k, v = list(vm_tcp_pfs.items())[0]
    # get the pf id and pf external port
    pf_id = v['pf_id']
    pf_external_port = v['public_port']
    pf_ssh_external_port = vm_ssh_pfs[k]['public_port']
    new_pf_external_port = str(int(pf_external_port) + 1000)
    LOG.info("Update external port forwarding {} external port {} with new external port {} ".
             format(pf_id, pf_external_port, new_pf_external_port))
    network_helper.update_portforwarding_rule(pf_id, outside_port=new_pf_external_port)
    LOG.info("Checking if port forwarding rules is updated.... ")
    ext_port = network_helper.get_portforwarding_rule_info(pf_id, field='outside_port')
    assert ext_port == new_pf_external_port, "Failed to update port-forwarding rule {} external port"

    LOG.info("Port forwarding rule external port updated successfully to {}".format(ext_port))

    LOG.info("Checking old external port {} is not reachable anymore.....".format(pf_external_port))

    greeting = "Hello {}".format(pf_external_port)
    thread_vm = MThread(check_ssh_to_vm_and_wait_for_packets, k, ext_ip_address, pf_ssh_external_port, greeting)

    LOG.info("Starting VM ssh session thread  .... ")
    thread_vm.start_thread()
    time.sleep(30)
    send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, pf_external_port, greeting, "tcp")
    LOG.info("Send {} to {}:{}".format(greeting, ext_ip_address, pf_external_port))
    LOG.info("Asserting the previous external port {} is not reachable".format(pf_external_port))
    output = thread_vm.get_output()
    assert output is None, "VM received TCP packets using previous external port {} ruling. Update " \
                           "failed to change port: {}".format(pf_external_port, thread_vm.get_output())

    LOG.info("The previous external port {} is not reachable as expected".format(pf_external_port))

    LOG.info("Testing the  updated external port {} ....".format(new_pf_external_port))
    greeting = "Hello {}".format(new_pf_external_port)
    send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, new_pf_external_port, greeting, "tcp")
    LOG.info("Asserting the updated external port {} is reachable".format(new_pf_external_port))
    thread_vm.wait_for_thread_end(60)
    LOG.info("Output = {}".format(thread_vm.get_output()))
    output = thread_vm.get_output()
    assert greeting in output[0], "Updated external port not reachable; packets not received: " \
                                  "{}".format(output[0])

    LOG.info(" Updating port-forwarding rule to new external port {} is successful".format(pf_external_port))


def test_external_access_to_vm_udp_protocol(_vms, router_info):
    """

    Args:
        _vms:
        router_info:

    Returns:

    """

    LOG.tc_step("Testing external access to vms and sending UDP packets ...")

    router_id = router_info
    vm_mgmt_ips = network_helper.get_mgmt_ips_for_vms(_vms, rtn_dict=True)

    LOG.tc_step("Creating ssh port forwarding rules for VMs: {}.".format(_vms))
    vm_ssh_pfs = create_portforwarding_rules_for_vms(vm_mgmt_ips, router_id, "tcp", for_ssh=True)

    LOG.tc_step("Creating udp port forwarding rules for VMs: {}.".format(_vms))
    vm_udp_pfs = create_portforwarding_rules_for_vms(vm_mgmt_ips, router_id, "udp", for_ssh=False)

    ext_ip_address = network_helper.get_router_ext_gateway_subnet_ip_address(router_id)
    LOG.info("External Router IP address = {}".format(ext_ip_address))

    LOG.info("Setting NATBox SSH session ...")
    ssh_nat = NATBoxClient.set_natbox_client()

    vm_threads = [None] * 4
    index = 0
    for k, v in vm_udp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        ssh_public_port = vm_ssh_pfs[k]['public_port']
        thread_vm = MThread(check_ssh_to_vm_and_wait_for_packets, k, ext_ip_address, ssh_public_port, greeting,
                            protocol='udp')
        vm_threads[index] = thread_vm
        index += 1

    LOG.info("Starting VM ssh session threads .... ")

    for t in vm_threads:
        t.start_thread()
    time.sleep(90)

    for k, v in vm_udp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        rc, output = send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, v['public_port'],
                                                     greeting, "udp")
        LOG.info("Send {} to {}:{}".format(greeting, ext_ip_address, v['public_port']))
        LOG.info("Result rc= {}; Output = {}".format(rc, output))

    for t in vm_threads:
        t.wait_for_thread_end(fail_ok=True)

    outputs = []
    for t in vm_threads:
        output = t.get_output()
        LOG.info("Thread {} output: {}".format(t.name, output))
        outputs.append(output)
    for i in range(0, 4):
        assert outputs[i][1] in outputs[i][0], "VM  did not receive the expected packets {}".format(outputs[i][1])
        for j in range(0, 4):
            if j != i:
                assert outputs[i][1] not in outputs[j][0], "VM  received the unexpected packets {}"\
                    .format(outputs[i][1])

    LOG.info("UDP protocol external access VMs passed")

    LOG.tc_step("Testing non udp packets  in  UDP protocol port forwarding rules ...")

    vm_threads = [None] * 4
    index = 0
    for k, v in vm_udp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        ssh_public_port = vm_ssh_pfs[k]['public_port']
        thread_vm = MThread(check_ssh_to_vm_and_wait_for_packets, k, ext_ip_address, ssh_public_port, greeting,
                            protocol='udp')
        vm_threads[index] = thread_vm
        index += 1

    LOG.info("Starting VM ssh session threads  .... ")

    for t in vm_threads:
        t.start_thread()
    time.sleep(90)

    for k, v in vm_udp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        rc, output = send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, v['public_port'],
                                                     greeting, "tcp")
        LOG.info("Send {} to {}:{}".format(greeting, ext_ip_address, v['public_port']))
        LOG.info("Result rc= {}; Output = {}".format(rc, output))

    outputs = []
    for t in vm_threads:
        output = t.get_output()
        LOG.info("Thread {} output: {}".format(t.name, output))
        outputs.append(output)

    LOG.info("Terminating VM ssh sessions  by sending valid udp packets .... ")
    for k, v in vm_udp_pfs.items():
        greeting = "Hello {}".format(v['public_port'])
        rc, output = send_packets_to_vm_from_nat_box(ssh_nat, ext_ip_address, v['public_port'],
                                                     greeting, "udp")
        LOG.info("Send {} to {}:{}".format(greeting, ext_ip_address, v['public_port']))
        LOG.info("Result rc= {}; Output = {}".format(rc, output))

    LOG.info("Checking non-udp packets are not received by vms......")
    for i in range(0, 4):
        assert outputs[i] is None or outputs[i][1] not in outputs[i][0], "VM received UDP packets on TCP port " \
                                                                         "forwarding rules {}".format(outputs[i][1])
    LOG.info("Non-udp packets not received as expected .... ")

    LOG.tc_step("Testing TFTP to and from VMs ...")
    LOG.info("TODO: The tftp tool not available in NAT box. Test skipped")


def check_ssh_to_vm_and_wait_for_packets(vm_id, vm_ip, vm_ext_port, expect_output, protocol='tcp'):
    ssh_nat = NATBoxClient.set_natbox_client()
    with vm_helper.ssh_to_vm_from_natbox(vm_id, vm_image_name='ubuntu_14', username='ubuntu',
                                         password='ubuntu', natbox_client=ssh_nat, vm_ip=vm_ip, vm_ext_port=vm_ext_port, retry=False) as vm_ssh:
        if protocol == 'udp':
            cmd = "nc -luw 1 80"
        else:
            cmd = "nc -lw 1 80"

        rc, output = vm_ssh.exec_sudo_cmd(cmd, expect_timeout=300)
        LOG.info("Expected output: {}".format(expect_output))
        LOG.info("Received output: {}".format(output))

    return output, expect_output


def send_packets_to_vm_from_nat_box(ssh_nat, vm_ip, vm_ext_port, send_msg, protocol):

    if protocol == 'udp':
        cmd = "echo \"{}\" | nc -4u -w 1 {} {}".format(send_msg, vm_ip, vm_ext_port)
    else:
        cmd = "echo \"{}\" | nc -w 1 {} {}".format(send_msg, vm_ip, vm_ext_port)

    rc, output = ssh_nat.exec_cmd(cmd)
    return rc, output


def check_scp_to_vm(vm_id, vm_user, vm_password, vm_ip,  vm_ext_port, expect_filename):

    with vm_helper.ssh_to_vm_from_natbox(vm_id, vm_image_name='ubuntu_14', username=vm_user,
                                         password=vm_password,  vm_ip=vm_ip, vm_ext_port=vm_ext_port) as vm_ssh:
        cmd = "test -f {}".format(expect_filename)
        rc, output = vm_ssh.exec_cmd(cmd)

    return rc, output


def scp_to_vm_from_nat_box(ssh_nat, vm_id, vm_user,  vm_ip, vm_ext_port):
    cmd = "test -f test"
    rc = ssh_nat.exec_cmd(cmd)[0]
    if rc != 0:
        cmd = "echo 'hello world'  > ~/test"
        ssh_nat.exec_cmd(cmd)
    scp_options = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    cmd = "scp {} -P {} test {}@{}:.".format(scp_options, vm_ext_port, vm_user, vm_ip)
    ssh_nat.send(cmd)
    index = ssh_nat.expect([ssh_nat.prompt, Prompt.PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=900)
    if index == 2:
        ssh_nat.send('yes')
        index = ssh_nat.expect([ssh_nat.prompt, Prompt.PASSWORD_PROMPT], timeout=900)
    if index == 1:
        ssh_nat.send(vm_user)
        index = ssh_nat.expect()
    if index != 0:
        raise exceptions.SSHException("Failed to scp file to VM {}:{}".format(vm_ip, vm_ext_port))

    LOG.info("Checking if VMs received test file .... ")
    rc, output = check_scp_to_vm(vm_id, vm_user, "ubuntu", vm_ip,  vm_ext_port, "test")
    assert rc == 0, "SCPed test file  not found in VM {}:{}".format(vm_ip, vm_ext_port)
    LOG.info("VM {}:{} received test file .... ".format(vm_ip, vm_ext_port))

    LOG.info("Testing SCP from VM .... ")
    cmd = "scp {} -P {}  {}@{}:test test_{}".format(scp_options, vm_ext_port, vm_user, vm_ip, vm_ext_port)
    ssh_nat.send(cmd)
    index = ssh_nat.expect([ssh_nat.prompt, Prompt.PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=900)
    if index == 2:
        ssh_nat.send('yes')
        index = ssh_nat.expect([ssh_nat.prompt, Prompt.PASSWORD_PROMPT], timeout=900)
    if index == 1:
        ssh_nat.send(vm_user)
        index = ssh_nat.expect()
    if index != 0:
        raise exceptions.SSHException("Failed to scp file from VM {}:{}".format(vm_ip, vm_ext_port))

    LOG.info("Checking SCP if VM {}:{}".format(vm_ip, vm_ext_port))
    cmd = "test -f test_{}".format(vm_ext_port)
    rc = ssh_nat.exec_cmd(cmd)[0]
    assert rc == 0, "File test_{} not found. Failed to scp file from VM {}:{}".format(vm_ext_port, vm_ip, vm_ext_port)


def create_portforwarding_rules_for_vms(vm_mgmt_ips, router_id, protocol, for_ssh=False):
    """
    Creates port-forwarding rules for  vms. The public port is selected based on protocol for the purpose of this test:
       tcp - if for_ssh is True  [8080, 8081, ..., 8089], otherwise [8090, 8091, ..., 8099]
       udp -  [8100, 8101, ..., 8109]

    This functions creates max 10 rules for the purpose this test

    Args:
        vm_mgmt_ips (dict): {vm_di: mgmt_ip}
        router_id (str): Id of tenant router where the portforwarding rules are created
        protocol (str): tcp/udp
        for_ssh(bool): valid only with tcp protocol, otherwise ignored.

    Returns: (tuple)
        code, dict  { vm_id: { 'pf_id': <pf_id>, 'public_port': <public_port>} }

    """
    if vm_mgmt_ips is None or  not isinstance(vm_mgmt_ips, dict) or len(vm_mgmt_ips) == 0 or router_id is None \
            or protocol is None:
        msg = "Value for vm_mgmt_ips, router_id, and protocol must be specified "
        LOG.warn(msg)
        raise exceptions.InvalidStructure(msg)

    base_port = 0
    inside_port = 80
    if protocol == "tcp":
        if for_ssh:
            base_port = 8080
            inside_port = 22
        else:
            base_port = 8090
    elif protocol == "udp":
        base_port = 8100
    else:
        msg = "Invalid protocol value {} provided".format(protocol)
        LOG.warn(msg)
        raise exceptions.InvalidStructure(msg)

    vm_pfs = {}
    for key, i in zip(vm_mgmt_ips, range(0, 10)):
        vm_name = nova_helper.get_vm_name_from_id(key)
        public_port = str(base_port + i)
        LOG.info("Creating  port forwarding rule for VM: {}: protocol={}, inside_address={}, inside_port={},"
                 "outside_port={}.".format(vm_name, protocol,  vm_mgmt_ips[key][0], inside_port, public_port))

        rc, pf_id, msg = network_helper.create_port_forwarding_rule(router_id, inside_addr=vm_mgmt_ips[key][0],
                                                                    inside_port=str(inside_port),
                                                                    outside_port=public_port,
                                                                    protocol=protocol)

        assert rc == 0, "Port forwarding rule create failed for VM {}: {}".format(vm_name, msg)

        LOG.info("Port forwarding rule {} created for VM: {}".format(pf_id, vm_name))

        vm_pf_info = {'pf_id': pf_id, 'private_port': str(inside_port),  'public_port': public_port}

        vm_pfs[key] = vm_pf_info

    return vm_pfs
