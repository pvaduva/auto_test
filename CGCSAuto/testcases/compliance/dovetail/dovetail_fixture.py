import time
import pexpect

from pytest import fixture, skip

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.proj_vars import ProjVar, ComplianceVar
from consts.compliance import Dovetail
from consts.stx import HostAvailState
from consts.auth import HostLinuxCreds, ComplianceCreds, Tenant, CliAuth
from keywords import host_helper, system_helper, network_helper, keystone_helper, common, compliance_helper

TEST_NODE_PROMPT = '.*@.*:.* '


@fixture(scope='session')
def pre_configs(request):
    """
    Dovetail test fixture
    Args:
        request:

    - configure sshd_config on tis hosts to allow root access
    - update conf files on dovetail test node on cumulus

    """
    if not ComplianceVar.get_var('DOVETAIL_SUITE'):
        skip('--dovetail-suite unspecified.')

    try:
        import yaml
    except ImportError:
        skip('pyymal package is not installed.')

    computes = host_helper.get_up_hypervisors()
    if len(computes) < 2:
        skip('Less than 2 computes in available states')

    active, standby = system_helper.get_active_standby_controllers()
    if not standby:
        skip('No standby controller on system')

    LOG.fixture_step("Ensure dovetail test node mgmt nic connects to lab under test")
    compliance_helper.update_dovetail_mgmt_interface()

    controllers = [active, standby]
    storages = system_helper.get_hosts(personality='storage', availability=HostAvailState.AVAILABLE)
    hosts_dict = {'controller': controllers,
                  'compute': computes,
                  'storage': storages
                  }
    all_hosts = list(set(controllers + computes + storages))

    LOG.fixture_step("Enable port_security for the system and update existing networks")
    port_security = network_helper.get_network_values('external-net0', 'port_security_enabled')[0]
    port_security = eval(port_security)
    if not port_security:
        system_helper.add_ml2_extension_drivers(drivers='port_security')
        networks = network_helper.get_networks(auth_info=Tenant.get('admin'))
        for net in networks:
            network_helper.set_network(net_id=net, enable_port_security=True)

    configure_tis(all_hosts, request=request)
    configure_dovetail_server(hosts_per_personality=hosts_dict)


def configure_dovetail_server(hosts_per_personality):
    """
    - Update env_config.sh on dovetail test node
    - Update tempest_conf.yaml min_compute_nodes count
    - Update nova-api process count in docker overlay monitor_process.py
    - Update monitor.py
    - Create pod.yaml file on localhost and scp to dovetail test node

    Args:
        hosts_per_personality:

    """
    con_ssh = ControllerClient.get_active_controller()
    # # Do not modify the tool
    # nova_proc_count = int(con_ssh.exec_cmd('ps -fC nova-api | grep nova | wc -l')[1])
    # assert nova_proc_count > 0, "0 nova-api processes running on active controller"

    LOG.fixture_step("Update {} on dovetail test node".format(Dovetail.ENV_SH))
    admin_dict = Tenant.get('admin')
    tenant_name = admin_dict['tenant']
    keystone_public_url = keystone_helper.get_endpoints(service_name='keystone', interface='public',
                                                        region=admin_dict['region'], field='url')[0]
    env_conf_dict = {
        'OS_PROJECT_NAME': tenant_name,
        'OS_PROJECT_ID': keystone_helper.get_projects(field='ID', name=tenant_name)[0],
        'OS_TENANT_NAME': tenant_name,
        'OS_USERNAME': admin_dict['user'],
        'OS_PASSWORD': admin_dict['password'],
        'OS_AUTH_URL': keystone_public_url.replace(':', r'\:').replace(r'/', r'\/'),
        'OS_IDENTITY_API_VERSION': CliAuth.get_var('OS_IDENTITY_API_VERSION'),
    }

    Dovetail.set_auth_url(keystone_public_url)
    ComplianceCreds.set_host(Dovetail.TEST_NODE)
    ComplianceCreds.set_user(Dovetail.USERNAME)
    ComplianceCreds.set_password(Dovetail.PASSWORD)
    with compliance_helper.ssh_to_compliance_server() as compliance_ssh:
        env_path = Dovetail.ENV_SH
        for var, value in env_conf_dict.items():
            compliance_ssh.exec_cmd('sed -i "s/^export {}=.*/export {}={}/g" {}'.format(var, var, value, env_path))
            compliance_ssh.exec_cmd('grep "export {}={}" {}'.format(var, value, env_path), fail_ok=False)

        LOG.fixture_step("Update tempest_conf.yaml min_compute_nodes count")
        compliance_ssh.exec_sudo_cmd('sed -i "s/^  min_compute_nodes:.*/  min_compute_nodes: {}/g" {}'.
                                     format(len(hosts_per_personality['compute']), Dovetail.TEMPEST_YAML))

        # # Do not modify the tool
        # LOG.fixture_step("Update nova-api process count in docker overlay monitor_process.py")
        # file_path = compliance_ssh.exec_sudo_cmd("find / -name monitor_process.py")[1]
        # LOG.fixture_step('Fixing monitor.py located at {}'.format(file_path))
        # compliance_ssh.exec_sudo_cmd("sed -ie 's/processes=.*/processes={}/g' {}".format(nova_proc_count, file_path))

        compliance_helper.add_route_for_vm_access(compliance_ssh)

    LOG.fixture_step("Collect hosts info, create pod.yaml file on localhost and scp to dovetail test node")
    import yaml
    yaml_nodes = []
    controllers = hosts_per_personality['controller']
    computes = hosts_per_personality['compute']

    node_count = 1
    for host in controllers:
        node_ip = con_ssh.exec_cmd('nslookup {} | grep -A 2 "Name:" | grep --color=never "Address:"'.
                                   format(host), fail_ok=False)[1].split('Address:')[1].strip()
        yaml_nodes.append({'name': 'node{}'.format(node_count),
                           'role': 'Controller',
                           'ip': node_ip,
                           'user': 'root',
                           'password': HostLinuxCreds.get_password()
                           })
        node_count += 1

    for compute in computes:
        node_ip = con_ssh.exec_cmd('nslookup {} | grep -A 2 "Name:" | grep --color=never "Address:"'.
                                   format(compute), fail_ok=False)[1].split('Address:')[1].strip()
        yaml_nodes.append({'name': 'node{}'.format(node_count),
                           'role': 'Compute',
                           'ip': node_ip,
                           'user': 'root',
                           'password': HostLinuxCreds.get_password()
                           })
        node_count += 1

    pod_yaml_dict = {'nodes': yaml_nodes}
    local_path = '{}/pod.yaml'.format(ProjVar.get_var('TEMP_DIR'))
    with open(local_path, 'w') as f:
        yaml.dump(pod_yaml_dict, f, default_flow_style=False)

    common.scp_from_local(source_path=local_path, dest_path=Dovetail.POD_YAML, dest_ip=Dovetail.TEST_NODE,
                          dest_user=Dovetail.USERNAME, dest_password=Dovetail.PASSWORD, timeout=30)


def configure_tis(hosts, request):
    """
    - Modify host ssh configs to allow root access
    - Update system quotas
    Args:
        hosts
        request:

    Returns (tuple): (controllers(list), computes(list))

    """

    LOG.fixture_step("Modify sshd_config on hosts to allow root access: {}".format(hosts))
    hosts_configured = []
    try:
        __config_sshd(hosts=hosts, hosts_configured=hosts_configured)
    finally:
        if hosts_configured:
            def _revert_sshd():
                LOG.fixture_step("Revert sshd configs on: {}".format(hosts_configured))
                __config_sshd(hosts=hosts, revert=True)
            request.addfinalizer(_revert_sshd)

    LOG.fixture_step("Update quotas for admin project")
    compliance_helper.create_tenants_and_update_quotas(new_tenants_index=None)

    return hosts_configured


def __config_sshd(hosts, hosts_configured=None, revert=False):
    """
    Configure sshd_config on specified host
    Args:
        hosts (tuple|list):
        hosts_configured (list): mutable list from external, the list will be updated
        revert:

    Returns:

    """

    con_ssh = ControllerClient.get_active_controller()
    prefix_new = prefix_old = ''
    permit_login_old = permit_login_new = 'no'
    if revert:
        prefix_old = '# '
        permit_login_old = 'yes'
    else:
        prefix_new = '# '
        permit_login_new = 'yes'

    for host in hosts:
        with host_helper.ssh_to_host(host) as host_ssh:

            LOG.info('---Update sshd_config file')
            options = ('Match User root',
                       '    PasswordAuthentication',
                       'Match Address',
                       '    PermitRootLogin without-password')

            for option in options:
                host_ssh.exec_sudo_cmd("sed -ie 's/^{}{}/{}{}/g' /etc/ssh/sshd_config".format(prefix_old, option,
                                                                                              prefix_new, option))
            host_ssh.exec_sudo_cmd("sed -ie 's/^PermitRootLogin {}/PermitRootLogin {}/g' /etc/ssh/sshd_config".
                                   format(permit_login_old, permit_login_new))

            with host_ssh.login_as_root() as root_ssh:
                if not revert:
                    output = host_ssh.exec_sudo_cmd('passwd -S root')[1]
                    if 'Password set' not in output:
                        LOG.info('---Set root password')
                        root_ssh.send('passwd root')
                        root_ssh.expect('New password:', timeout=15)
                        root_ssh.send(HostLinuxCreds.get_password())
                        root_ssh.expect('Retype new password:', timeout=10)
                        root_ssh.send(HostLinuxCreds.get_password())
                        root_ssh.expect(timeout=30)

                LOG.info('---Restart sshd')
                root_ssh.send('systemctl restart sshd')
                time.sleep(15)

        try:
            con_ssh.flush()
            con_ssh.send()
            con_ssh.expect(timeout=5)
        except (pexpect.EOF, pexpect.TIMEOUT):
            time.sleep(5)
            con_ssh.connect()

        if not revert:
            hosts_configured.append(host)
