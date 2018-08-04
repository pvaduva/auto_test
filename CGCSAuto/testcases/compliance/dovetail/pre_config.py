import configparser
import yaml
from utils.tis_log import LOG
from consts.auth import HostLinuxCreds, CliAuth, Tenant, ComplianceCreds
from keywords import vlm_helper, host_helper
from utils.clients.ssh import ControllerClient, SSHClient
from utils import table_parser
from consts.filepaths import Dovetail

DOVETAIL_HOST = 'tis-dovetail-test-node.cumulus.wrs.com'


def env_config_generate(floating_ip, server_ssh):
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.connect()
    con_ssh.exec_cmd('source /etc/nova/openrc')
    projectID = con_ssh.exec_cmd('openstack project list')
    projectID = table_parser.table(projectID[1])
    projectID_admin = table_parser._get_values(projectID, 'Name', 'admin', 'ID')
    projectID_admin = projectID_admin.pop(0)
    user_admin = Tenant.ADMIN['user']
    password_admin = Tenant.ADMIN['password']
    config = configparser.ConfigParser()
    config.optionxform = str
    filepath = '${DOVETAIL_HOME}/pre_config/env_config.sh'

    server_ssh.exec_cmd('sed -i "s/^export OS_PROJECT_NAME=.*/export OS_PROJECT_NAME= {}/g" {}'.format(user_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_TENANT_NAME=.*/export OS_TENANT_NAME= {}/g" {}'.format(user_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_USERNAME=.*/export OS_USERNAME= {}/g" {}'.format(user_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_PASSWORD=.*/export OS_PASSWORD= {}/g" {}'.format(password_admin, filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_AUTH_URL=.*/export OS_AUTH_URL= {}/g" {}'.format(Dovetail.OS_AUTH_URL.format((floating_ip)), filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_IDENTITY_API_VERSION=.*/export OS_IDENTITY_API_VERSION= {}/g" {}'.format(CliAuth.get_var('OS_IDENTITY_API_VERSION'), filepath))
    server_ssh.exec_cmd('sed -i "s/^export OS_PROJECT_ID=.*/export OS_PROJECT_ID= {}/g" {}'.format(projectID_admin, filepath))


    # config[None] = {'# Project-level authentication scope (name or ID), recommend admin project.':'',
    #                     'export OS_PROJECT_NAME':user_admin,
    #                     '# For identity v2, it uses OS_TENANT_NAME rather than OS_PROJECT_NAME.':'',
    #                     'export OS_TENANT_NAME':user_admin,
    #                     '# Authentication username, belongs to the project above, recommend admin user.':'',
    #                     'export OS_USERNAME':user_admin,
    #                     '# Authentication password. Use your own password':'',
    #                     'export OS_PASSWORD':password_admin,
    #                     '# Authentication URL, one of the endpoints of keystone service. If this is v3 version, \n# there need some extra variables as follows.' : '',
    #                     'export OS_AUTH_URL' : Dovetail.OS_AUTH_URL.format(floating_ip),
    #                     '# Default is 2.0. If use keystone v3 API, this should be set as 3.': '',
    #                     'export OS_IDENTITY_API_VERSION':CliAuth.get_var('OS_IDENTITY_API_VERSION'),
    #                     '# Domain name or ID containing the user above. \n# Command to check the domain: openstack user show <OS_USERNAME>':'',
    #                     'export OS_USER_DOMAIN_NAME':'Default',
    #                     '# Domain name or ID containing the project aove.':'',
    #                     '# Command to check the domain: openstack project show <OS_PROJECT_NAME>':'',
    #                     'export OS_PROJECT_DOMAIN_NAME':'Default',
    #                     '# Special environment parameters for https. \n# If using https + cacert, the path of cacert file should be provided. \n# The cacert file should be put at $DOVETAIL_HOME/pre_config. \n#export OS_CACERT=/home/opnfv/dovetail/pre_config/cacert.pem \n\n# If using https + no cacert, should add OS_INSECURE environment parameter.':'',
    #                     'export OS_INSECURE':'True',
    #                     "export DOVETAIL_HOME":'/home/dovetail',
    #                     'export OS_PROJECT_ID':projectID_admin,
    #                     'export OS_REGION_NAME':'"RegionOne"'}
    #
    # with open('${DOVETAIL_HOME}/pre_config/env_config.sh', 'w+') as configfile:
    #   config.write(configfile, space_around_delimiters=False)


def pod_generate_2plus2(n1ip, n2ip, n3ip, n4ip, server_ssh):

    server_ssh.exec_sudo_cmd('')
    sample = '''nodes:
-
    name: node1
    role: Controller
    ip: 128.224.151.192
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
-
    name: node2
    role: Controller
    ip: 192.168.204.4
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
-
    name: node3
    role: Compute
    ip: 192.168.204.175
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
-
    name: node4
    role: Compute
    ip: 192.168.204.208
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
'''
    yaml.load(sample)

    config = {'nodes': [{'name': 'node1', 'role': 'Controller', 'ip': n1ip, 'user': 'root', 'password': 'Li69nux*'},
                        {'name': 'node2', 'role': 'Controller', 'ip': n2ip, 'user': 'root', 'password': 'Li69nux*'},
                        {'name': 'node3', 'role': 'Compute', 'ip': n3ip, 'user': 'root', 'password': 'Li69nux*'},
                        {'name': 'node4', 'role': 'Compute', 'ip': n4ip, 'user': 'root', 'password': 'Li69nux*'}]}

    # server_ssh.exec_sudo_cmd('rm -f ${DOVETAIL_HOME}/pre_config/pod.yaml')
    # server_ssh.exec_sudo_cmd('cat '+yaml.dump(config, default_flow_style=False)+ ' >> ${DOVETAIL_HOME}/pre_config/pod.yaml')

    # with open('./pod.yaml', 'w+') as yaml_file:
    #     yaml_file.write(yaml.dump(config, default_flow_style=False))

    return config


def tempest_conf_generate_2plus2(server_ssh):

    server_ssh.exec_sudo_cmd('sed -i "s/^min_compute_nodes:.*/min_compute_nodes: 2/g" ${DOVETAIL_HOME}/pre_config/tempest_conf.yaml')
    server_ssh.exec_sudo_cmd('sed -i "s/^volume_device_name:.*/volume_device_name: vdb/g" ${DOVETAIL_HOME}/pre_config/tempest_conf.yaml')

#     sample = '''compute:
#   # The minimum number of compute nodes expected.
#
#   #   # This should be no less than 2 and no larger than the compute nodes the SUT actually has.
#   min_compute_nodes: 2
#   #
#   # Expected device name when a volume is attached to an instance.
#   volume_device_name: vdb
# '''
#     sample = yaml.load(sample)
#     with open('${DOVETAIL_HOME}/pre_config/tempest_conf.yaml', 'w+') as yaml_file:
#         yaml_file.write(yaml.dump(sample, default_flow_style=False))


def fix_sshd_file(con_ssh):

    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin no/PermitRootLogin yes/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match User root/#Match User root/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/ PasswordAuthentication no/ #PasswordAuthentication no/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match Address/#Match Address/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin without-password/#PermitRootLogin without-password/g' /etc/ssh/sshd_config")


##############################
# main
##############################
def test():
    cumulus = ComplianceCreds()
    cumulus.set_host(DOVETAIL_HOST)
    cumulus_host = cumulus.get_host()
    cumulus_user = cumulus.get_user()
    cumulus_password = cumulus.get_password()
    CUMULUS_PROMPT = '.*@.*:.*\$ '

    LOG.info("Connecting to cumulus")

    server_ssh = SSHClient(cumulus_host, cumulus_user, cumulus_password, True, CUMULUS_PROMPT)
    server_ssh.connect()

    LOG.info("Connected to cumulus")

    server_ssh.exec_sudo_cmd('su - dovetail')

    LOG.info("Changed over to dovetail user")

    LOG.info("export DOVETAIL_HOME="+Dovetail.DOVETAIL_HOME)

    server_ssh.exec_cmd("export DOVETAIL_HOME="+Dovetail.DOVETAIL_HOME)
    server_ssh.exec_cmd('mkdir -p ${DOVETAIL_HOME}/pre_config')

    lab_info = vlm_helper.get_lab_dict()
    # controller0_ip = lab_info.get('controller-0 ip')

    floating_ip = lab_info.get('floating ip')
    # controller1_ip = lab_info.get('controller-1 ip')

    LOG.info("Connecting to active Controller")

    con_ssh = ControllerClient.get_active_controller()
    con_ssh.connect()
    compute0_ip = con_ssh.exec_cmd('nslookup compute-0')

    compute0_ip = compute0_ip[1]
    compute0_ip = compute0_ip.split('Address')
    compute0_ip = compute0_ip[-1]
    compute0_ip = compute0_ip[2:]

    compute1_ip = con_ssh.exec_cmd('nslookup compute-1')
    compute1_ip = compute1_ip[1]
    compute1_ip = compute1_ip.split('Address')
    compute1_ip = compute1_ip[-1]
    compute1_ip = compute1_ip[2:]

    LOG.info("Generating YAML files")

    #pod_generate_2plus2('192.168.204.3', '192.168.204.3', compute0_ip, compute1_ip, server_ssh)
    tempest_conf_generate_2plus2(server_ssh)
    env_config_generate(floating_ip, server_ssh)

    password = HostLinuxCreds.get_password()

    nodes = ['controller-0', 'controller-1', 'compute-0', 'compute-1']

    for x in nodes:
        with host_helper.ssh_to_host(x) as con_ssh:
            fix_sshd_file(con_ssh)
            LOG.info('Fixed sshd file in ' + x)
            con_ssh.exec_sudo_cmd("printf '" + password + "\n" + password + "\n" + password + "\n' | passwd root", )
            con_ssh.exec_sudo_cmd('systemctl restart sshd')
            # con_ssh.close()
            # input("press enter to continue")

    con_ssh = ControllerClient.get_active_controller()
    con_ssh.connect()

    LOG.info("Finding and repairing monitor.py")

    stdout = con_ssh.exec_cmd('ps -fC nova-api | grep -v UID | wc')
    stdout = stdout[1]
    stdout = stdout.split()
    stdout = stdout[0]
    filepath = server_ssh.exec_sudo_cmd("find / -name monitor_process.py")
    server_ssh.exec_sudo_cmd("sed -ie 's/processes=.*/processes="+stdout+"/g' "+filepath)

    LOG.info("Running Dovetail")

    server_ssh.exec_cmd('export DOVETAIL_HOME='+Dovetail.DOVETAIL_HOME)
    server_ssh.exec_cmd('source ${DOVETAIL_HOME}/pre_config/env_config.sh')
    server_ssh.exec_sudo_cmd("docker run --privileged=true -it -e DOVETAIL_HOME=$DOVETAIL_HOME -v $DOVETAIL_HOME:$DOVETAIL_HOME -v /var/run/docker.sock:/var/run/docker.sock opnfv/dovetail:ovp.1.0.0 /bin/bash")
    # os.system('dovetail run --testsuite ovp.1.0.0')
    server_ssh.exec_cmd('dovetail run --testsuite madatory')
