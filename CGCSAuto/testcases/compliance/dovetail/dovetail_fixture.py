import time
import pexpect

from pytest import fixture, skip

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.proj_vars import ProjVar
from consts.compliance import Dovetail
from consts.cgcs import HostAvailState
from consts.auth import HostLinuxCreds, ComplianceCreds, Tenant, CliAuth
from keywords import host_helper, system_helper, nova_helper, network_helper, cinder_helper, keystone_helper, common
from testcases.compliance import compliance_helper


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
    try:
        import yaml
    except ImportError:
        skip('pyymal package is not installed.')

    active, standby = system_helper.get_active_standby_controllers()
    if not standby:
        skip('No standby controller on system')

    hosts_dict = system_helper.get_hostnames_per_personality(HostAvailState.AVAILABLE)
    computes = hosts_dict['compute']
    if len(computes) < 2:
        skip('Less than 2 computes in available states')

    controllers = hosts_dict['controller']
    storages = hosts_dict['storage']
    all_hosts = controllers + computes + storages

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
    nova_proc_count = int(con_ssh.exec_cmd('ps -fC nova-api | grep nova | wc -l')[1])
    assert nova_proc_count > 0, "0 nova-api processes running on active controller"

    LOG.fixture_step("Update {} on dovetail test node".format(Dovetail.ENV_SH))
    admin_dict = Tenant.get('admin')
    tenant_name = admin_dict['tenant']
    keystone_public_url = keystone_helper.get_endpoints(service_name='keystone', interface='public',
                                                        region=admin_dict['region'], rtn_val='url')[0]
    env_conf_dict = {
        'OS_PROJECT_NAME': tenant_name,
        'OS_PROJECT_ID': keystone_helper.get_tenant_ids(tenant_name=tenant_name)[0],
        'OS_TENANT_NAME': tenant_name,
        'OS_USERNAME': admin_dict['user'],
        'OS_PASSWORD': admin_dict['password'],
        'OS_AUTH_URL': keystone_public_url.replace(':', '\:').replace('/', '\/'),
        'OS_IDENTITY_API_VERSION': CliAuth.get_var('OS_IDENTITY_API_VERSION'),
    }

    Dovetail.set_auth_url(keystone_public_url)
    ComplianceCreds.set_host(Dovetail.TEST_NODE)
    ComplianceCreds.set_user(Dovetail.USERNAME)
    ComplianceCreds.set_password(Dovetail.PASSWORD)
    with host_helper.ssh_to_compliance_server() as compliance_ssh:
        env_path = Dovetail.ENV_SH
        for var, value in env_conf_dict.items():
            compliance_ssh.exec_cmd('sed -i "s/^export {}=.*/export {}={}/g" {}'.format(var, var, value, env_path))
            compliance_ssh.exec_cmd('grep "export {}={}" {}'.format(var, value, env_path), fail_ok=False)

        LOG.fixture_step("Update tempest_conf.yaml min_compute_nodes count")
        compliance_ssh.exec_sudo_cmd('sed -i "s/^  min_compute_nodes:.*/  min_compute_nodes: {}/g" {}'.
                                     format(len(hosts_per_personality['compute']), Dovetail.TEMPEST_YAML))

        LOG.fixture_step("Update nova-api process count in docker overlay monitor_process.py")
        file_path = compliance_ssh.exec_sudo_cmd("find / -name monitor_process.py")[1]
        LOG.fixture_step('Fixing monitor.py located at {}'.format(file_path))
        compliance_ssh.exec_sudo_cmd("sed -ie 's/processes=.*/processes={}/g' {}".format(nova_proc_count, file_path))

        compliance_helper.add_route_for_vm_access(compliance_ssh)

    LOG.fixture_step("Collect hosts info, create pod.yaml file on localhost and scp to dovetail test node")
    import yaml
    yaml_nodes = []
    hosts = list(hosts_per_personality['controller'])
    hosts += hosts_per_personality['compute']
    for i in range(len(hosts)):
        node = 'node{}'.format(i+1)
        hostname = hosts[i]
        role = 'Controller' if 'controller' in hostname else 'Compute'
        node_ip = con_ssh.exec_cmd(
            'nslookup {} | grep -A 2 "Name:" | grep --color=never "Address:"'.format(hostname), fail_ok=False)[1]
        node_ip = node_ip.split('Address:')[1].strip()
        yaml_nodes.append({'name': node,
                           'role': role,
                           'ip': node_ip,
                           'user': 'root',
                           'password': HostLinuxCreds.get_password()
                           })
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

    LOG.fixture_step("Update Quotas for admin tenant")
    tenant = Tenant.get('admin')['tenant']
    nova_helper.update_quotas(tenant=tenant, instances=20, cores=50)
    cinder_helper.update_quotas(tenant=tenant, volumes=100, snapshots=100)
    network_helper.update_quotas(tenant_name=tenant, port=500, floatingip=100, subnet=100, network=100)

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

        try:
            time.sleep(10)
            con_ssh.send()
            con_ssh.expect(timeout=5)
        except (pexpect.EOF, pexpect.TIMEOUT):
            time.sleep(5)
            con_ssh.connect()

        if not revert:
            hosts_configured.append(host)
