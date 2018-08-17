import re
from consts.auth import CliAuth, Tenant
from utils.tis_log import LOG
from keywords import keystone_helper, system_helper, host_helper
from utils.clients.ssh import ControllerClient
from consts.compliance import Dovetail
from pytest import fixture, skip, mark

CUMULUS_PROMPT = '.*@.*:.* '

def env_config_update(floating_ip):
    projectID_admin = keystone_helper.get_tenant_ids(tenant_name=Tenant.ADMIN['tenant'])[0]

    user_admin = Tenant.ADMIN['user']
    password_admin = Tenant.ADMIN['password']
    filepath = '{}/pre_config/env_config.sh'.format(Dovetail.DOVETAIL_HOME)
    Dovetail.set_os_auth_url(keystone_helper.get_endpoints(service_name='keystone', interface='public', region='RegionOne', rtn_val='url')[0])

    with host_helper.ssh_to_compliance_server(prompt=CUMULUS_PROMPT) as server_ssh:
        server_ssh.exec_cmd('sed -i "s/^export OS_PROJECT_NAME=.*/export OS_PROJECT_NAME={}/g" {}'.format(user_admin, filepath))
        server_ssh.exec_cmd('sed -i "s/^export OS_TENANT_NAME=.*/export OS_TENANT_NAME={}/g" {}'.format(user_admin, filepath))
        server_ssh.exec_cmd('sed -i "s/^export OS_USERNAME=.*/export OS_USERNAME={}/g" {}'.format(user_admin, filepath))
        server_ssh.exec_cmd('sed -i "s/^export OS_PASSWORD=.*/export OS_PASSWORD={}/g" {}'.format(password_admin, filepath))
        server_ssh.exec_cmd('sed -i "s/^export OS_AUTH_URL=.*/export OS_AUTH_URL={}/g" {}'.format(Dovetail.OS_AUTH_URL.format((floating_ip)), filepath))
        server_ssh.exec_cmd('sed -i "s/^export OS_IDENTITY_API_VERSION=.*/export OS_IDENTITY_API_VERSION={}/g" {}'.format(CliAuth.get_var('OS_IDENTITY_API_VERSION'), filepath))
        server_ssh.exec_cmd('sed -i "s/^export OS_PROJECT_ID=.*/export OS_PROJECT_ID={}/g" {}'.format(projectID_admin, filepath))


def pod_update(con0, con1, compute_ips, storage_ips):
    with host_helper.ssh_to_compliance_server(prompt=CUMULUS_PROMPT) as server_ssh:
        server_ssh.exec_cmd('cp {}/templates/pod.yaml {}/pre_config/'.format(Dovetail.DOVETAIL_HOME, Dovetail.DOVETAIL_HOME))
        pod_yaml = server_ssh.exec_sudo_cmd('cat {}'.format(Dovetail.POD))[1]
        ips = re.findall("ip:.*", pod_yaml)
        controller_0_ip_tochange = ips[0]
        controller_1_ip_tochange = ips[1]
        compute_0_ip_tochange = ips[2]
        compute_1_ip_tochange = ips[3]

        server_ssh.exec_cmd('sed -i "s/^.*{}.*/    ip: {}/g" {}'.format(controller_0_ip_tochange, con0, Dovetail.POD))
        server_ssh.exec_cmd('sed -i "s/^.*{}.*/    ip: {}/g" {}'.format(controller_1_ip_tochange, con1, Dovetail.POD))
        server_ssh.exec_cmd('sed -i "s/^.*{}.*/    ip: {}/g" {}'.format(compute_0_ip_tochange, compute_ips[0], Dovetail.POD))
        server_ssh.exec_cmd('sed -i "s/^.*{}.*/    ip: {}/g" {}'.format(compute_1_ip_tochange, compute_ips[1], Dovetail.POD))

    if len(compute_ips)>2 or len(storage_ips)>0:
        template_compute = '''-
        name: {}
        role: {}
        ip: {}
        user: root
        password: Li69nux*
    #    key_filename: /home/cumulus/.ssh/id_rsa
    '''

        for i in range(2,len(compute_ips)):
            server_ssh.exec_cmd('echo "{}" >> {}'.format(template_compute.format('node'+str(i+3), 'compute', compute_ips[i]), Dovetail.POD))

        for i in range(len(storage_ips)):
            server_ssh.exec_cmd('echo "{}" >> {}'.format(template_compute.format('node'+str(i+len(compute_ips)+3),'storage', storage_ips[i]), Dovetail.POD))


def tempest_conf_update(computes):
    with host_helper.ssh_to_compliance_server(prompt=CUMULUS_PROMPT) as server_ssh:
        server_ssh.exec_sudo_cmd('sed -i "s/.*min_compute_nodes:.*/  min_compute_nodes: {}/g" {}'.format(str(computes), Dovetail.TEMPEST_CONF))
        server_ssh.exec_sudo_cmd('sed -i "s/.*volume_device_name:.*/  volume_device_name: vdb/g" {}'.format(Dovetail.TEMPEST_CONF))


@fixture()
def fix_sshd_file(con_ssh):
    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin no/PermitRootLogin yes/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match User root/#Match User root/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/ PasswordAuthentication no/ #PasswordAuthentication no/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match Address/#Match Address/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin without-password/#PermitRootLogin without-password/g' /etc/ssh/sshd_config")


