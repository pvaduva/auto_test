import time
from utils.tis_log import LOG
from consts.auth import HostLinuxCreds, ComplianceCreds
from keywords import vlm_helper, host_helper, system_helper, nova_helper, network_helper, cinder_helper
from utils.clients.ssh import ControllerClient, SSHClient
from consts.compliance import Dovetail
from consts.proj_vars import ProjVar
from testcases.compliance.dovetail import pre_config
from pytest import fixture, skip, mark

TESTAREA_MANDATORY_MAX_TIMEOUT = 20000

@fixture()
def restore_sshd_file_teardown(request):
    def teardown():
        """
        Removes the edits made to the sshd_config file
        Returns:

        """
        LOG.info('Repairing sshd_config file')
        con_ssh = ControllerClient.get_active_controller()
        con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin yes/PermitRootLogin no/g' /etc/ssh/sshd_config")
        con_ssh.exec_sudo_cmd("sed -ie 's/#Match User root/Match User root/g' /etc/ssh/sshd_config")
        con_ssh.exec_sudo_cmd(
            "sed -ie 's/ #PasswordAuthentication no/ PasswordAuthentication no/g' /etc/ssh/sshd_config")
        con_ssh.exec_sudo_cmd("sed -ie 's/#Match Address/Match Address/g' /etc/ssh/sshd_config")
        con_ssh.exec_sudo_cmd(
            "sed -ie 's/#PermitRootLogin without-password/PermitRootLogin without-password/g' /etc/ssh/sshd_config")
        LOG.info('Root Login capability removed')
    request.addfinalizer(teardown)


@mark.usefixtures('restore_sshd_file_teardown')
def test_dovetail():
    LOG.tc_step('Starting Dovetail Test on Cumulus Server {}'.format(Dovetail.DOVETAIL_HOST))
    ComplianceCreds().set_host(Dovetail.DOVETAIL_HOST)
    cumulus_host = ComplianceCreds().get_host()
    cumulus_user = ComplianceCreds().get_user()
    cumulus_password = ComplianceCreds().get_password()
    CUMULUS_PROMPT = '.*@.*:.* '

    LOG.info("Connecting to cumulus")

    server_ssh = SSHClient(cumulus_host, cumulus_user, cumulus_password, True, CUMULUS_PROMPT)
    server_ssh.connect()
    LOG.info("Connected to cumulus")

    server_ssh.exec_sudo_cmd('su - dovetail')
    LOG.info("Changed over to dovetail user")

    floating_ip = ProjVar.get_var('LAB')['floating ip']

    system_nodes = system_helper.get_hostnames()
    storage_nodes = [h for h in system_nodes if "storage" in h]
    compute_nodes = [h for h in system_nodes if "storage" not in h and 'controller' not in h]
    compute_ips = []
    storage_ips = []

    LOG.info("Connecting to active Controller")
    con_ssh = ControllerClient.get_active_controller()

    for computes in compute_nodes:
        ip = con_ssh.exec_cmd('nslookup ' + computes)
        ip = ip[1]
        ip = ip.split('Address')
        ip = ip[-1]
        ip = ip[2:]
        compute_ips.append(ip)

    for storage in storage_nodes:
        ip = con_ssh.exec_cmd('nslookup ' + storage)
        ip = ip[1]
        ip = ip.split('Address')
        ip = ip[-1]
        ip = ip[2:]
        storage_ips.append(ip)

    LOG.info("Generating YAML files")

    if len(compute_ips) == 2:
        pre_config.pod_update_2plus2('192.168.204.3', '192.168.204.4', compute_ips[0], compute_ips[1], server_ssh)
    else:
        pre_config.pod_update_non_standard('192.168.204.3', '192.168.204.4', compute_ips, storage_ips, server_ssh)

    pre_config.tempest_conf_update(len(compute_ips), server_ssh)
    pre_config.env_config_update(floating_ip, server_ssh)

    password = HostLinuxCreds.get_password()

    active_con = system_helper.get_active_controller_name()
    for host in system_nodes:
        with host_helper.ssh_to_host(host) as host_ssh:
            LOG.info('Fixing sshd file in ' + host)
            pre_config.fix_sshd_file(host_ssh)

            LOG.info("Setting root password on {}".format(host))
            host_ssh.send("sudo passwd root")
            host_ssh.expect('.*[pP]assword:.*')
            host_ssh.send(password)
            host_ssh.expect('.*[Nn]ew [Pp]assword:.*')
            host_ssh.send(password)

            LOG.info('Restarting SSH client'.format(host))
            host_ssh.send("sudo systemctl restart sshd")

            if host == active_con:
                LOG.info("Active controller sshd restarting. Sleeping 5 seconds before reconnect attempt.")
                time.sleep(5)
                con_ssh.connect()
            else:
                host_ssh.expect('Connection to.*closed.')

            LOG.info("Restarted host {}".format(host))

    LOG.info("Finding and repairing monitor.py")

    output = con_ssh.exec_cmd('ps -fC nova-api | grep -v UID | wc')
    output = output[1]
    nova_proc_count = output.split()[0]

    filepath = server_ssh.exec_sudo_cmd("find / -name monitor_process.py")[-1]
    LOG.info('Fixing monitor.py located at ' + filepath)
    filepath = filepath[-1]
    server_ssh.exec_sudo_cmd("sed -ie 's/processes=.*/processes=" + nova_proc_count + "/g' " + filepath)

    LOG.info("Updating Quotas")
    nova_helper.update_quotas(tenant='admin', instances=20, cores=50)
    cinder_helper.update_quotas(tenant='admin', volumes=100, snapshots=100)
    network_helper.update_quotas(tenant_name='admin', port=500, floatingip=100, subnet=100, network=100)

    LOG.info("Sourcing config files")
    server_ssh.exec_cmd('source '+Dovetail.DOVETAIL_HOME+'/pre_config/env_config.sh')

    LOG.info("Starting Docker Container")
    server_ssh.exec_sudo_cmd(
        "docker run --privileged=true -it -e DOVETAIL_HOME="+Dovetail.DOVETAIL_HOME+" -v $DOVETAIL_HOME:"+Dovetail.DOVETAIL_HOME+" -v /var/run/docker.sock:/var/run/docker.sock opnfv/dovetail:ovp.1.0.0 /bin/bash")
    LOG.info("Starting Dovetail Testarea Mandatory")
    server_ssh.exec_cmd('dovetail run --testarea mandatory', expect_timeout=TESTAREA_MANDATORY_MAX_TIMEOUT)
