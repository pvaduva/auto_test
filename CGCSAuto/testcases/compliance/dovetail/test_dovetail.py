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
CUMULUS_PROMPT = '.*@.*:.* '

@mark.usefixtures('restore_sshd_file_teardown')
def test_dovetail():
    """
    Test the Dovetail Compliance Suite through Cumulus Server

    Test Steps:
        -SSH into a provisioned Cumulus server
        -Modify Config Files on Cumulus
        -Enable Root on TiS
        -Modify monitor.py file on Cumulus
        -Update Quotas on TiS
        -Source config files and launch Docker Container on Cumulus
        -Run Dovetail test in Docker Container
    Teardown:
        -Disable Root login on TiS

    """
    # LOG.tc_step('Starting Dovetail Test on Cumulus Server {}'.format(Dovetail.DOVETAIL_HOST))
    # ComplianceCreds().set_host(Dovetail.DOVETAIL_HOST)
    # cumulus_host = ComplianceCreds().get_host()
    # cumulus_user = ComplianceCreds().get_user()
    # cumulus_password = ComplianceCreds().get_password()
    # CUMULUS_PROMPT = '.*@.*:.* '
    #
    # LOG.info("Connecting to cumulus")
    #
    # server_ssh = SSHClient(cumulus_host, cumulus_user, cumulus_password, True, CUMULUS_PROMPT)
    # server_ssh.connect()
    # LOG.info("Connected to cumulus")
    #
    # LOG.info("Changed over to dovetail user")
    #
    # floating_ip = ProjVar.get_var('LAB')['floating ip']
    #
    # system_nodes = system_helper.get_hostnames()
    # storage_nodes = [h for h in system_nodes if "storage" in h]
    # compute_nodes = [h for h in system_nodes if "storage" not in h and 'controller' not in h]
    # compute_ips = []
    # storage_ips = []
    #
    # LOG.info("Connecting to active Controller")
    # con_ssh = ControllerClient.get_active_controller()
    #
    # for computes in compute_nodes:
    #     ip = extract_ip(computes)
    #     compute_ips.append(ip)
    #
    # for storage in storage_nodes:
    #     ip = extract_ip(storage)
    #     storage_ips.append(ip)
    #
    # LOG.info("Generating YAML files")
    #
    # pre_config.pod_update('192.168.204.3', '192.168.204.4', compute_ips, storage_ips, server_ssh)
    #
    # pre_config.tempest_conf_update(len(compute_ips), server_ssh)
    # pre_config.env_config_update(floating_ip, server_ssh)
    #
    # password = HostLinuxCreds.get_password()
    #
    # active_con = system_helper.get_active_controller_name()
    # for host in system_nodes:
    #     with host_helper.ssh_to_host(host) as host_ssh:
    #         LOG.info('Fixing sshd file in ' + host)
    #         pre_config.fix_sshd_file(host_ssh)
    #
    #         LOG.info("Setting root password on {}".format(host))
    #         host_ssh.send("sudo passwd root")
    #         host_ssh.expect('.*[pP]assword:.*')
    #         host_ssh.send(password)
    #         host_ssh.expect('.*[Nn]ew [Pp]assword:.*')
    #         host_ssh.send(password)
    #
    #         LOG.info('Restarting SSH client'.format(host))
    #         host_ssh.send("sudo systemctl restart sshd")
    #
    #         if host == active_con:
    #             LOG.info("Active controller sshd restarting. Sleeping 5 seconds before reconnect attempt.")
    #             time.sleep(5)
    #             con_ssh.connect()
    #         else:
    #             host_ssh.expect('Connection to.*closed.')
    #
    #         LOG.info("Restarted host {}".format(host))
    #
    # LOG.info("Finding and repairing monitor.py")
    #
    # output = con_ssh.exec_cmd('ps -fC nova-api | grep -v UID | wc')[1]
    # nova_proc_count = output.split()[0]
    #
    # filepath = server_ssh.exec_sudo_cmd("find / -name monitor_process.py")[-1]
    # LOG.info('Fixing monitor.py located at ' + filepath)
    # filepath = filepath[-1]
    # server_ssh.exec_sudo_cmd("sed -ie 's/processes=.*/processes=" + nova_proc_count + "/g' " + filepath)
    #
    # LOG.info("Updating Quotas")
    # nova_helper.update_quotas(tenant='admin', instances=20, cores=50)
    # cinder_helper.update_quotas(tenant='admin', volumes=100, snapshots=100)
    # # network_helper.update_quotas(tenant_name='admin', port=500, floatingip=100, subnet=100, network=100)
    # ComplianceCreds().set_user(Dovetail.DOVETAIL_USER)
    # ComplianceCreds().set_password(Dovetail.DOVETAIL_PASSWORD)
    # ComplianceCreds().set_host(Dovetail.DOVETAIL_HOST)
    with host_helper.ssh_to_compliance_server(prompt=CUMULUS_PROMPT) as server_ssh:
        LOG.info("Sourcing config files")
        server_ssh.exec_cmd('source {}/pre_config/env_config.sh'.format(Dovetail.DOVETAIL_HOME))

        LOG.info("Starting Docker Container")
        code, output = server_ssh.exec_sudo_cmd(
            "docker run --privileged=true -it -e DOVETAIL_HOME={} -v {}:{} -v /var/run/docker.sock:/var/run/docker.sock opnfv/dovetail:ovp.1.0.0 /bin/bash".format(Dovetail.DOVETAIL_HOME, Dovetail.DOVETAIL_HOME, Dovetail.DOVETAIL_HOME))
        print(output)
        LOG.info("Starting Dovetail Testarea Mandatory")
        server_ssh.exec_cmd('dovetail run --testarea mandatory', expect_timeout=TESTAREA_MANDATORY_MAX_TIMEOUT, fail_ok=False)
        LOG.info('Results can be found on tis-dovetail-test-node.cumulus.wrs.com in /home/dovetail/results')
