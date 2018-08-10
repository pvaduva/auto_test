import re
from consts.auth import CliAuth, Tenant
from utils.tis_log import LOG
from keywords import keystone_helper
from utils.clients.ssh import ControllerClient
from consts.compliance import Dovetail
from pytest import fixture, skip, mark

def env_config_update(floating_ip, server_ssh):
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.exec_cmd('source /etc/nova/openrc')
    projectID_admin = keystone_helper.get_tenant_ids(tenant_name='admin')

    user_admin = Tenant.ADMIN['user']
    password_admin = Tenant.ADMIN['password']
    filepath = Dovetail.DOVETAIL_HOME+'/pre_config/env_config.sh'

    server_ssh.exec_cmd('sed -i "s/^export OS_PROJECT_NAME=.*/export OS_PROJECT_NAME={}/g" {}'.format(user_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_TENANT_NAME=.*/export OS_TENANT_NAME={}/g" {}'.format(user_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_USERNAME=.*/export OS_USERNAME={}/g" {}'.format(user_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_PASSWORD=.*/export OS_PASSWORD={}/g" {}'.format(password_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_AUTH_URL=.*/export OS_AUTH_URL={}/g" {}'.format(Dovetail.OS_AUTH_URL.format((floating_ip)), filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_IDENTITY_API_VERSION=.*/export OS_IDENTITY_API_VERSION={}/g" {}'.format(CliAuth.get_var('OS_IDENTITY_API_VERSION'), filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_PROJECT_ID=.*/export OS_PROJECT_ID={}/g" {}'.format(projectID_admin, filepath))


def pod_update_2plus2(n1ip, n2ip, n3ip, n4ip, server_ssh):

    server_ssh.exec_cmd('~/pre_config$ cp ~/templates/pod.yaml ~/pre_config/')
    pod_yaml = server_ssh.exec_sudo_cmd('cat ' + Dovetail.POD_DIR)
    pod_yaml = pod_yaml[-1]
    controller_0_ip_tochange = re.findall("ip:.*", pod_yaml)[0]
    controller_1_ip_tochange = re.findall("ip:.*", pod_yaml)[1]
    compute_0_ip_tochange = re.findall("ip:.*", pod_yaml)[2]
    compute_1_ip_tochange = re.findall("ip:.*", pod_yaml)[3]

    server_ssh.exec_cmd('sed -i "s/^.*'+controller_0_ip_tochange+'.*/    ip: '+n1ip+'/g" {}'.format(Dovetail.POD_DIR))
    server_ssh.exec_cmd('sed -i "s/^.*'+controller_1_ip_tochange+'.*/    ip: '+n2ip+'/g" {}'.format(Dovetail.POD_DIR))
    server_ssh.exec_cmd('sed -i "s/^.*'+compute_0_ip_tochange+'.*/    ip: '+n3ip+'/g" {}'.format(Dovetail.POD_DIR))
    server_ssh.exec_cmd('sed -i "s/^.*'+compute_1_ip_tochange+'.*/    ip: '+n4ip+'/g" {}'.format(Dovetail.POD_DIR))


def pod_update_non_standard(con0, con1, compute_ips, storage_ips, server_ssh):
    server_ssh.exec_cmd('~/pre_config$ cp ~/templates/pod.yaml ~/pre_config/')
    pod_yaml = server_ssh.exec_sudo_cmd('cat ' + Dovetail.POD_DIR)
    pod_yaml = pod_yaml[-1]
    controller_0_ip_tochange = re.findall("ip:.*", pod_yaml)[0]
    controller_1_ip_tochange = re.findall("ip:.*", pod_yaml)[1]
    compute_0_ip_tochange = re.findall("ip:.*", pod_yaml)[2]
    compute_1_ip_tochange = re.findall("ip:.*", pod_yaml)[3]

    server_ssh.exec_cmd('sed -i "s/^.*' + controller_0_ip_tochange + '.*/    ip: ' + con0 + '/g" {}'.format(Dovetail.POD_DIR))
    server_ssh.exec_cmd('sed -i "s/^.*' + controller_1_ip_tochange + '.*/    ip: ' + con1 + '/g" {}'.format(Dovetail.POD_DIR))
    server_ssh.exec_cmd('sed -i "s/^.*' + compute_0_ip_tochange + '.*/    ip: ' + compute_ips[0] + '/g" {}'.format(Dovetail.POD_DIR))
    server_ssh.exec_cmd('sed -i "s/^.*' + compute_1_ip_tochange + '.*/    ip: ' + compute_ips[1] + '/g" {}'.format(Dovetail.POD_DIR))

    template_compute = '''-
    name: {}
    role: {}
    ip: {}
    user: root
    password: Li69nux*
#    key_filename: /home/cumulus/.ssh/id_rsa
'''

    for i in range(2,len(compute_ips)):
        server_ssh.exec_cmd('echo "'+template_compute.format('node'+str(i+3),'compute', compute_ips[i])+'" >> '+Dovetail.POD_DIR)

    for i in range(len(storage_ips)):
        server_ssh.exec_cmd('echo "'+template_compute.format('node'+str(i+len(compute_ips)+3),'storage', storage_ips[i])+'" >> '+Dovetail.POD_DIR)



def tempest_conf_update(computes, server_ssh):

    server_ssh.exec_sudo_cmd('sed -i "s/.*min_compute_nodes:.*/  min_compute_nodes: '+str(computes)+'/g" '+Dovetail.TEMPEST_CONF_DIR)
    server_ssh.exec_sudo_cmd('sed -i "s/.*volume_device_name:.*/  volume_device_name: vdb/g" ' + Dovetail.TEMPEST_CONF_DIR)

@fixture()
def fix_sshd_file(con_ssh):
    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin no/PermitRootLogin yes/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match User root/#Match User root/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/ PasswordAuthentication no/ #PasswordAuthentication no/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match Address/#Match Address/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin without-password/#PermitRootLogin without-password/g' /etc/ssh/sshd_config")