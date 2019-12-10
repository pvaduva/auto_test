import os
import time

import pexpect
from consts.proj_vars import RestoreVars, InstallVars
from keywords import common, install_helper
from utils.clients.ssh import SSHClient
from utils.tis_log import LOG

RESTORE_PLATFORM_PLAYBOOK = \
    '/usr/share/ansible/stx-ansible/playbooks/restore_platform.yml'
RESTORE_WAIT_TIMEOUT = 1800
STORE_BACKUP_PATH = '/tmp/dvoicule/backup'
HAS_WIPE_CEPH_OSDS = False
WIPE_CEPH_OSDS = False


def setup_ipv6_oam(controller0, conf_server=None):
    if not controller0.host_nic:
        controller0.host_nic = install_helper.get_nic_from_config(conf_server=conf_server)

    nic_interface = controller0.host_nic
    if not controller0.telnet_conn:
        controller0.telnet_conn = install_helper.open_telnet_session(controller0)

    con_telnet = controller0.telnet_conn
    sudo_prefix = 'echo {} | sudo -S'.format(controller0.telnet_conn.password)
    host_ip = controller0.host_ip
    dev = nic_interface

    con_telnet.exec_cmd("{} ip -6 addr add {}/64 dev {}".format(sudo_prefix, host_ip, dev))
    con_telnet.exec_cmd("{} ip -6 link set dev {} up".format(sudo_prefix, dev))
    time.sleep(30)
    con_telnet.exec_cmd("{} ip -6 route delete default".format(sudo_prefix), get_exit_code=False)
    con_telnet.exec_cmd("{} ip -6 route add default via 2620:10a:a001:a103::6:0".
                        format(sudo_prefix))
    con_telnet.exec_cmd('ip route; ip -6 route; ip -6 neigh; ip addr', get_exit_code=False)
    LOG.info("Wait for 60 seconds after configuring v6 IP for controller-0")
    time.sleep(60)
    con_telnet.exec_cmd('ip -6 route; ip -6 neigh', get_exit_code=False)


def get_ipv4_controller_0():
    lab = InstallVars.get_install_var('LAB')

    if InstallVars.get_install_var('IPV6_OAM'):
        ipv6 = lab['controller-0 ip']
        con0_v4_ip = ipv6.rsplit(':', maxsplit=1)[-1]

        if len(con0_v4_ip) == 4 and con0_v4_ip.startswith('1'):
            con0_v4_ip = '128.224.151.{}'.format(con0_v4_ip[-3:].lstrip("0"))
        else:
            con0_v4_ip = '128.224.150.{}'.format(con0_v4_ip[-3:])

        return con0_v4_ip
    else:
        return lab['controller-0 ip']


def collect_logs(con_ssh, ip, msg):
    """
    Collect logs from target machine

    Args:

    Returns:
    """
    try:
        LOG.info('Collecting logs: ' + msg)
        common.collect_software_logs(con_ssh=con_ssh, lab_ip=ip)
    except pexpect.exceptions.ExceptionPexpect:
        con_ssh.flush()
        con_ssh.exec_cmd('cat /etc/build.info')


def analyze_ansible_output(output):
    if output and len(output) > 0:
        lastlines = output.splitlines()[-2:]
        result_line = [line for line in lastlines if "PLAY RECAP" not in line]
        result_line = result_line[0] if len(result_line) > 0 else None
        LOG.info("Ansible result line = {}".format(result_line))
        if result_line and ":" in result_line:
            result = result_line.split(':')[1].split()
            failed = [i for i in result if "failed" in i]
            if failed:
                return int(failed[0].split('=')[1]), result
            return 1, result

    return 1, None


def prepare_restore_env():
    # Full path to the backup on test server
    global STORE_BACKUP_PATH
    global HAS_WIPE_CEPH_OSDS
    global WIPE_CEPH_OSDS

    STORE_BACKUP_PATH = RestoreVars.get_restore_var('BACKUP_SRC_PATH')
    HAS_WIPE_CEPH_OSDS = RestoreVars.get_restore_var('HAS_WIPE_CEPH_OSDS')
    WIPE_CEPH_OSDS = RestoreVars.get_restore_var('WIPE_CEPH_OSDS')


def restore_platform():
    """
    Test ansible restore_platform on controller-0


    Test Steps:
        - Prepare restore environment
        - ssh to given machine
        - collect logs
        - copy backup.tgz from test server to machine
        - collect logs
        - ansible-playbook restore_platform.yml
    """
    prepare_restore_env()

    # Ssh to machine that will become controller-0,
    c0_ip = get_ipv4_controller_0()
    prompt = r'.*\:~\$'
    con_ssh = SSHClient(host=c0_ip, user='sysadmin', password='Li69nux*',
                        initial_prompt=prompt)
    con_ssh.connect()

    # Test step 1
    backup_dest_path = STORE_BACKUP_PATH
    LOG.tc_step("Copy from test server {} to controller-0"
                .format(backup_dest_path))
    common.scp_from_test_server_to_active_controller(
        backup_dest_path,
        '~/',
        con_ssh=con_ssh,
        force_ipv4=True)

    wipe_ceph_osds = ''
    if HAS_WIPE_CEPH_OSDS and WIPE_CEPH_OSDS:
        wipe_ceph_osds = 'wipe_ceph_osds=true'
    if HAS_WIPE_CEPH_OSDS and not WIPE_CEPH_OSDS:
        wipe_ceph_osds = 'wipe_ceph_osds=false'

    # Test step 2
    cmd = "ansible-playbook {} -e ".format(RESTORE_PLATFORM_PLAYBOOK) \
          + "\"initial_backup_dir=/home/sysadmin " \
          + wipe_ceph_osds + " " \
          + "ansible_become_pass=Li69nux* admin_password=Li69nux* " \
          + "backup_filename=" + os.path.basename(STORE_BACKUP_PATH) + "\""
    LOG.tc_step("Run " + cmd)

    rc, output = con_ssh.exec_cmd(cmd, expect_timeout=RESTORE_WAIT_TIMEOUT)

    # Here prompt will change when collecting logs on controller-0
    con_ssh.set_prompt(r'.*\$')
    collect_logs(con_ssh, c0_ip, 'after restore')

    assert rc == 0 and analyze_ansible_output(output)[0] == 0, \
        "{} execution failed: {} {}".format(cmd, rc, output)
