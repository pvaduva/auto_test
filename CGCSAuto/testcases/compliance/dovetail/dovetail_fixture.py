import time
from utils.tis_log import LOG
from consts.auth import HostLinuxCreds, ComplianceCreds
from keywords import vlm_helper, host_helper, system_helper, nova_helper, network_helper, cinder_helper
from utils.clients.ssh import ControllerClient, SSHClient
from consts.compliance import Dovetail
from consts.proj_vars import ProjVar
from testcases.compliance.dovetail import pre_config
from pytest import fixture, skip, mark

CUMULUS_PROMPT = '.*@.*:.* '

@fixture(scope='session')
def dovetail_pre_check():
    LOG.info('Checking if lab is compatiable')
    if system_helper.is_small_footprint():
        skip('Dovetail can only be run on a standard or storage lab')


@fixture(scope='session')
def dovetail_setup(dovetail_pre_check):
    LOG.tc_step('Starting Dovetail Test on Cumulus Server {}'.format(Dovetail.DOVETAIL_HOST))
    ComplianceCreds().set_host(Dovetail.DOVETAIL_HOST)

    floating_ip = ProjVar.get_var('LAB')['floating ip']

    system_nodes = system_helper.get_hostnames()
    storage_nodes = [h for h in system_nodes if "storage" in h]
    compute_nodes = [h for h in system_nodes if "storage" not in h and 'controller' not in h]
    compute_ips = []
    storage_ips = []

    LOG.info("Connecting to active Controller")
    con_ssh = ControllerClient.get_active_controller()

    for computes in compute_nodes:
        ip = extract_ip(computes)
        compute_ips.append(ip)

    for storage in storage_nodes:
        ip = extract_ip(storage)
        storage_ips.append(ip)

    LOG.info("Generating YAML files")

    # pre_config.pod_update('192.168.204.3', '192.168.204.4', compute_ips, storage_ips)
    pre_config.pod_update(floating_ip, '192.168.204.4', compute_ips, storage_ips)

    pre_config.tempest_conf_update(len(compute_ips))
    pre_config.env_config_update(floating_ip)

    password = HostLinuxCreds.get_password()

    active_con = system_helper.get_active_controller_name()
    for host in system_nodes:
        with host_helper.ssh_to_host(host) as host_ssh:
            LOG.info('Fixing sshd file in {}'.format(host))
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

    output = con_ssh.exec_cmd('ps -fC nova-api | grep -v UID | wc')[1]
    nova_proc_count = output.split()[0]

    with host_helper.ssh_to_compliance_server() as server_ssh:
        server_ssh.exec_sudo_cmd('su - dovetail')
        filepath = server_ssh.exec_sudo_cmd("find / -name monitor_process.py")[-1]
        LOG.info('Fixing monitor.py located at {}'.format(filepath))
        filepath = filepath[-1]
        server_ssh.exec_sudo_cmd("sed -ie 's/processes=.*/processes={}/g' {}".format(nova_proc_count, filepath))

    LOG.info("Updating Quotas")
    nova_helper.update_quotas(tenant='admin', instances=20, cores=50)
    cinder_helper.update_quotas(tenant='admin', volumes=100, snapshots=100)
    network_helper.update_quotas(tenant_name='admin', port=500, floatingip=100, subnet=100, network=100)


def extract_ip(node):
    con_ssh=ControllerClient.get_active_controller()
    ip = con_ssh.exec_cmd('nslookup {}'.format(node))[1]
    ip = ip.split('Address')
    ip = ip[-1][2:]
    return ip

