import time

from pytest import fixture

from consts.stx import FlavorSpec, Prompt
from keywords import network_helper, vm_helper, nova_helper, glance_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup
from utils import exceptions
from utils.clients.ssh import NATBoxClient
from utils.multi_thread import MThread, Events
from utils.tis_log import LOG

GUEST_OS = 'ubuntu_14'
VMS_COUNT = 4


@fixture(scope='module')
def router_info(request):
    LOG.fixture_step("Enable snat on tenant router")
    router_id = network_helper.get_tenant_router()
    network_helper.set_router_gateway(router_id, enable_snat=True)

    def teardown():
        LOG.fixture_step("Disable snat on tenant router")
        network_helper.set_router_gateway(router_id, enable_snat=False)
    request.addfinalizer(teardown)

    return router_id


@fixture(scope='function')
def delete_scp_files_from_nat(request):
    def teardown():
        LOG.fixture_step("Delete scp files on NatBox")
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
        LOG.fixture_step("Delete portforwarding rules")
        router_id = network_helper.get_tenant_router()
        pf_ids = network_helper.get_portforwarding_rules(router_id)
        network_helper.delete_portforwarding_rules(pf_ids)
    request.addfinalizer(teardown)
    return None


@fixture(scope='module')
def _vms():
    vm_helper.ensure_vms_quotas(vms_num=8)
    glance_helper.get_guest_image(guest_os=GUEST_OS, cleanup='module')

    LOG.fixture_step("Create a favor with dedicated cpu policy")
    flavor_id = nova_helper.create_flavor(name='dedicated-ubuntu', guest_os=GUEST_OS)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')
    nova_helper.set_flavor(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    mgmt_net_id = network_helper.get_mgmt_net_id()
    internal_net_id = network_helper.get_internal_net_id()
    tenant_net_ids = network_helper.get_tenant_net_ids()
    if len(tenant_net_ids) < VMS_COUNT:
        tenant_net_ids += tenant_net_ids
    assert len(tenant_net_ids) >= VMS_COUNT

    vif = 'avp' if system_helper.is_avs() else 'virtio'
    vm_vif_models = {'virtio_vm1': ('virtio', tenant_net_ids[0]),
                     '{}_vm1'.format(vif): (vif, tenant_net_ids[1]),
                     'virtio_vm2': ('virtio', tenant_net_ids[2]),
                     '{}_vm2'.format(vif): (vif, tenant_net_ids[3])}

    vms = []
    for vm_name, vifs in vm_vif_models.items():
        vif_model, tenant_net_id = vifs
        nics = [{'net-id': mgmt_net_id},
                {'net-id': tenant_net_id, 'vif-model': vif_model},
                {'net-id': internal_net_id, 'vif-model': vif_model}]

        LOG.fixture_step("Boot a ubuntu14 vm with {} nics from above flavor and volume".format(vif_model))
        vm_id = vm_helper.boot_vm(vm_name, flavor=flavor_id, source='volume', cleanup='module',
                                  nics=nics, guest_os=GUEST_OS)[1]
        vms.append(vm_id)

    return vms


def test_port_forwarding_rule_create_for_vm(_vms, delete_pfs):

    for vm_id, i in zip(_vms, range(len(_vms))):
        vm_name = vm_helper.get_vm_name_from_id(vm_id)
        public_port = str(9090 + i)
        LOG.info("Creating  port forwarding rule for VM: {}: outside_port={}.".format(vm_name, public_port))
        rc, pf_id, msg = network_helper.create_port_forwarding_rule_for_vm(vm_id,
                                                                           inside_port=str(90),
                                                                           outside_port=public_port)

        assert rc == 0, "Port forwarding rule create failed for VM {}: {}".format(vm_name, msg)
        LOG.info("rc {}; pf_id {} msg {}".format(rc, pf_id, msg))


def test_dnat_ubuntu_vm_tcp(_vms, router_info, delete_pfs, delete_scp_files_from_nat):
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

    ext_gateway_ip = network_helper.get_router_external_gateway_ips(router_id)[0]
    nat_ssh = NATBoxClient.get_natbox_client()
    LOG.tc_step("Testing external access to vms and TCP packets ...")
    check_port_forwarding_protocol(ext_gateway_ip, nat_ssh, vm_pfs=vm_tcp_pfs, vm_ssh_pfs=vm_ssh_pfs, protocol='tcp')

    LOG.tc_step("Testing SCP to and from VMs ...")
    for vm_id_, v in vm_tcp_pfs.items():
        vm_name = vm_helper.get_vm_name_from_id(vm_id_)
        ssh_public_port = vm_ssh_pfs[vm_id_]['public_port']
        scp_to_vm_from_nat_box(nat_ssh, vm_id_, "ubuntu", ext_gateway_ip, ssh_public_port)
        LOG.info("SCP to/from VM {} is successful .... ".format(vm_name))

    LOG.info("SCP to/from VMs successful.... ")

    LOG.tc_step("Testing changes to forwarding rules ...")
    # get the first VM and external port forwarding rule
    vm_id_, v = list(vm_tcp_pfs.items())[0]
    # get the pf id and pf external port
    pf_id = v['pf_id']
    pf_external_port = v['public_port']
    pf_ssh_external_port = vm_ssh_pfs[vm_id_]['public_port']
    new_pf_external_port = str(int(pf_external_port) + 1000)

    LOG.info("Update external port forwarding {} external port {} with new external port {} ".
             format(pf_id, pf_external_port, new_pf_external_port))
    network_helper.update_portforwarding_rule(pf_id, outside_port=new_pf_external_port)
    LOG.info("Checking if port forwarding rules is updated.... ")
    ext_port = network_helper.get_portforwarding_rule_info(pf_id, field='outside_port')
    assert ext_port == new_pf_external_port, "Failed to update port-forwarding rule {} external port"

    LOG.info("Port forwarding rule external port updated successfully to {}".format(ext_port))
    LOG.info("Check old external port {} cannot be reached, while new port {} can be reached".
             format(pf_external_port, new_pf_external_port))
    check_port_forwarding_ports(ext_gateway_ip, nat_ssh, vm_id=vm_id_, protocol='tcp', ssh_port=pf_ssh_external_port,
                                old_port=pf_external_port, new_port=new_pf_external_port)
    LOG.info(" Updating port-forwarding rule to new external port {} is successful".format(pf_external_port))


def test_dnat_ubuntu_vm_udp(_vms, router_info):
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

    ext_gateway_ip = network_helper.get_router_external_gateway_ips(router_id)[0]
    LOG.info("External Router IP address = {}".format(ext_gateway_ip))

    LOG.info("Setting NATBox SSH session ...")
    nat_ssh = NATBoxClient.get_natbox_client()

    LOG.tc_step("Testing external access to vms and UDP packets ...")
    check_port_forwarding_protocol(ext_gateway_ip, nat_ssh, vm_pfs=vm_udp_pfs, vm_ssh_pfs=vm_ssh_pfs, protocol='udp')
    LOG.info("UDP protocol external access VMs passed")

    # LOG.tc_step("Testing tftp to and from VMs ...")
    # LOG.info("TODO: The tftp tool not available in NAT box. Test skipped")


def check_ssh_to_vm_and_wait_for_packets(start_event, end_event, received_event, vm_id, vm_ip, vm_ext_port,
                                         expt_output, protocol='tcp', timeout=1200):
    """

    Args:
        start_event (Events):
        end_event (Events):
        received_event (Events):
        vm_id:
        vm_ip:
        vm_ext_port:
        expt_output:
        protocol:
        timeout:

    Returns:

    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id, vm_image_name='ubuntu_14', vm_ip=vm_ip, vm_ext_port=vm_ext_port,
                                         username='ubuntu', password='ubuntu', retry=False) as vm_ssh:

        with vm_ssh.login_as_root() as root_ssh:
            LOG.info("Start listening on port 80 on vm {}".format(vm_id))
            cmd = "nc -l{}w 1 80".format('u' if protocol == 'udp' else '')
            root_ssh.send(cmd)
            start_event.set()

            def _check_receive_event():
                # set receive event if msg received
                index = root_ssh.expect(timeout=10, fail_ok=True)
                if index == 0:
                    received_event.set()
                    output = root_ssh.cmd_output
                    assert expt_output in output, \
                        "Output: {} received, but not as expected: {}".format(output, expt_output)
                    LOG.info("Received output: {}".format(output))

            end_time = time.time() + timeout
            while time.time() < end_time:
                # Exit the vm ssh, end thread
                if end_event.is_set():
                    if not received_event.is_set():
                        _check_receive_event()

                    root_ssh.send_control()
                    root_ssh.expect(timeout=10, fail_ok=True)
                    return

                # start_event is unset for a new test step
                if not start_event.is_set():
                    root_ssh.send(cmd)
                    start_event.set()
                    received_event.clear()

                _check_receive_event()
                time.sleep(5)

    assert 0, "end_event is not set within timeout"


def send_packets_to_vm_from_nat_box(ssh_nat, vm_ip, vm_ext_port, send_msg, protocol):
    udp_param = '-4u ' if protocol == 'udp' else ''
    cmd = "echo \"{}\" | nc {}-w 1 {} {}".format(send_msg, udp_param, vm_ip, vm_ext_port)

    rc, output = ssh_nat.exec_cmd(cmd, fail_ok=True)
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
    if vm_mgmt_ips is None or not isinstance(vm_mgmt_ips, dict) or len(vm_mgmt_ips) == 0 or router_id is None \
            or protocol is None:
        msg = "Value for vm_mgmt_ips, router_id, and protocol must be specified "
        LOG.warn(msg)
        raise exceptions.InvalidStructure(msg)

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
        vm_name = vm_helper.get_vm_name_from_id(key)
        public_port = str(base_port + i)
        LOG.info("Creating port forwarding rule for VM: {}: protocol={}, inside_address={}, inside_port={},"
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


def check_port_forwarding_ports(ext_gateway_ip, nat_ssh, vm_id, ssh_port, old_port, new_port, protocol):

    end_event = Events("Hello msg sent to ports")
    start_event = Events("VM {} started listening".format(vm_id))
    received_event = Events("Greeting received on vm {}".format(vm_id))

    LOG.tc_step("Starting VM ssh session threads .... ")
    new_greeting = "Hello {}".format(new_port)
    vm_thread = MThread(check_ssh_to_vm_and_wait_for_packets, start_event, end_event, received_event,
                        vm_id, ext_gateway_ip, ssh_port, new_greeting, protocol)
    vm_thread.start_thread()
    try:
        start_event.wait_for_event(timeout=180, fail_ok=False)
        LOG.tc_step("Send Hello msg to vm from NATBox via old {} port {}, and check it's not received".
                    format(protocol, old_port))

        greeting = "Hello {}".format(old_port)
        send_packets_to_vm_from_nat_box(nat_ssh, ext_gateway_ip, old_port, greeting, protocol)

        time.sleep(10)
        assert not received_event.is_set(), "Event {} is set".format(received_event)

        LOG.tc_step("Check greeting is received on vm via new {} port {}".format(protocol, new_port))
        send_packets_to_vm_from_nat_box(nat_ssh, ext_gateway_ip, new_port, new_greeting, protocol)

        assert received_event.wait_for_event(timeout=30), "Event {} is not set".format(received_event)

    finally:
        end_event.set()
        vm_thread.wait_for_thread_end(timeout=40, fail_ok=False)


def check_port_forwarding_protocol(ext_gateway_ip, nat_ssh, vm_pfs, vm_ssh_pfs, protocol):
    vm_threads = []
    end_event = Events("Hello msg sent to ports")
    start_events = []
    received_events = []

    try:
        LOG.tc_step("Start listening on vms {} ports .... ".format(protocol))
        for vm_id_, v in vm_pfs.items():
            greeting = "Hello {}".format(v['public_port'])
            ssh_public_port = vm_ssh_pfs[vm_id_]['public_port']
            start_event = Events("VM {} started listening".format(vm_id_))
            start_events.append(start_event)
            received_event = Events("Greeting received on vm {}".format(vm_id_))
            received_events.append(received_event)
            thread_vm = MThread(check_ssh_to_vm_and_wait_for_packets, start_event, end_event, received_event,
                                vm_id_, ext_gateway_ip, ssh_public_port, greeting, protocol)
            thread_vm.start_thread()
            vm_threads.append(thread_vm)

        for event_ in start_events:
            event_.wait_for_event(timeout=180, fail_ok=False)

        diff_protocol = 'udp' if protocol == 'tcp' else 'tcp'
        LOG.tc_step("Send Hello msg to vms from NATBox via {} ports, and check they are not received via {} ports".
                    format(diff_protocol, protocol))
        for vm_id_, v in vm_pfs.items():
            greeting = "Hello {}".format(v['public_port'])
            send_packets_to_vm_from_nat_box(nat_ssh, ext_gateway_ip, v['public_port'], greeting, diff_protocol)

        time.sleep(10)
        for event in received_events:
            assert not event.is_set(), "Event {} is set".format(event)

        LOG.tc_step("Send Hello msg to vms from NATBox via {} ports, and check they are received".
                    format(protocol, protocol))
        for vm_id_, v in vm_pfs.items():
            greeting = "Hello {}".format(v['public_port'])
            send_packets_to_vm_from_nat_box(nat_ssh, ext_gateway_ip, v['public_port'], greeting, protocol)

        time.sleep(10)
        for event in received_events:
            assert event.wait_for_event(timeout=40, fail_ok=False), "Event {} is not set".format(event)

    finally:
        end_event.set()
        for thread in vm_threads:
            thread.wait_for_thread_end(timeout=40, fail_ok=True)
