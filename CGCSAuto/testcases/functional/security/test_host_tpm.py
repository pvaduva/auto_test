import os
import re
import time
import shutil
import functools

from pytest import skip, fixture, mark, param

from consts import build_server
from consts.auth import HostLinuxCreds, SvcCgcsAuto
from consts.cgcs import Prompt, EventLogID
from consts.filepaths import SecurityPath, BuildServerPath, SYSADMIN_HOME
from consts.proj_vars import ProjVar

from utils import cli, lab_info, table_parser
from utils.clients.ssh import ControllerClient, SSHFromSSH
from utils.tis_log import LOG
from keywords import system_helper, keystone_helper, host_helper
from keywords import common


tpm_modes = {
    'enabled': 'tpm_mode',
    'tpm_mode': 'tpm_mode',
    'ssl': 'ssl',
    'disabled': 'ssl',
    'murano': 'murano',
    'murano_ca': 'murano_ca',
}
default_ssl_file = '/etc/ssl/private/server-cert.pem'
testing_ssl_file = 'server-cert.pem.bk'
conf_backup_dir = 'bk-conf'
local_conf_backup_dir = '/tmp/bk-conf'
cert_id_line = r'^\|\s* uuid \s*\|\s* ([a-z0-9-]+) \s*\|$'
fmt_password = r'{password}'

expected_install = (
    ('Password: ', fmt_password),
    (r'Enter password for the CA-Signed certificate file \[Enter <CR> for no password\]', fmt_password),
    (r'Enter \[sudo\] password for sysadmin', fmt_password),
    ('Installing certificate file ', ''),
    ('WARNING, Installing an invalid or expired certificate', ''),
    (r'OK to Proceed\? \(yes/NO\)', 'yes'),
    ('In {mode} mode...', ''),
    ('WARNING, For security reasons, the original certificate', ''),
    (r'OK to Proceed\? \(yes/NO\)', 'yes'),
    ('Configuring TPM on all enabled controller hosts...', ''),
    ('Auditing TPM configuration state...', ''),
    (r'^done$', ''),
)

file_changes = {
    'haproxy': {
        r'/etc/haproxy/haproxy.cfg': (
            r'tpm-engine\s+/usr/lib64/openssl/engines/libtpm2.so',
            r'tpm-object\s+/etc/ssl/private/object.tpm',
        )
    },

    'lighttpd': {
        r'/etc/lighttpd/lighttpd.conf': (
            r'server.tpm-object\s+=\s+"/etc/ssl/private/object.tpm"',
            r'server.tpm-engine\s+=\s+"/usr/lib64/openssl/engines/libtpm[1-9]+.so"'
        ),
    },
}


@fixture(scope='session', autouse=True)
def check_lab_status(request):
    current_lab = ProjVar.get_var('lab')
    if not current_lab or not current_lab.get('tpm_installed', False):
        skip('Non-TPM lab, skip the test.')

    if not keystone_helper.is_https_enabled():
        skip('Non-HTTPs lab, skip the test.')

    ssh_client = ControllerClient.get_active_controller()
    working_ssl_file = os.path.join(SYSADMIN_HOME, testing_ssl_file)
    LOG.info('backup default ssl pem file to:' + working_ssl_file)
    ssh_client.exec_sudo_cmd('cp -f ' + default_ssl_file + ' ' + testing_ssl_file)

    def cleaup():
        ssh_client.exec_sudo_cmd('rm -rf ' + working_ssl_file)
        backup_dir = os.path.join(SYSADMIN_HOME, conf_backup_dir)
        ssh_client.exec_sudo_cmd('rm -rf ' + backup_dir)
        LOG.info('remove saved configuration files on local')
        if os.path.exists(local_conf_backup_dir):
            shutil.rmtree(local_conf_backup_dir)
    request.addfinalizer(cleaup)


@fixture(scope='function', autouse=True)
def backup_configuration_files():
    backup_dir = os.path.join(SYSADMIN_HOME, conf_backup_dir)
    ssh_client = ControllerClient.get_active_controller()
    LOG.info('Save current configuration files')
    ssh_client.exec_sudo_cmd('rm -f ' + backup_dir + '; mkdir -p ' + backup_dir)

    for service, file_info in file_changes.items():
        for conf_file in file_info:
            ssh_client.exec_sudo_cmd('cp -f ' + conf_file + ' ' + backup_dir)
    source_ip = system_helper.get_oam_values()['oam_floating_ip']
    # if os.path.exists(local_conf_backup_dir):
    #     os.rmdir(local_conf_backup_dir)
    common.scp_to_local(backup_dir, source_ip=source_ip, dest_path=local_conf_backup_dir, is_dir=True)

    if os.path.exists(local_conf_backup_dir):
        shutil.rmtree(local_conf_backup_dir)

    source_ip = system_helper.get_oam_values()['oam_floating_ip']
    common.scp_to_local(backup_dir, source_ip=source_ip, dest_path=local_conf_backup_dir, is_dir=True)


def fetch_cert_file(ssh_client, search_path=None):

    save_cert_to = os.path.dirname(SecurityPath.ALT_CERT_PATH)

    code, output = ssh_client.exec_cmd('mkdir -p {}'.format(save_cert_to), fail_ok=True)
    if code != 0:
        msg = 'failed to create path for certificate files:{}, error:'.format(save_cert_to, output)
        LOG.warn(msg)
        return code, msg

    from_server = build_server.DEFAULT_BUILD_SERVER['ip']
    prompt = r'\[{}@.* \~\]\$'.format(SvcCgcsAuto.USER)
    ssh_to_server = SSHFromSSH(ssh_client, from_server, SvcCgcsAuto.USER, SvcCgcsAuto.PASSWORD, initial_prompt=prompt)
    ssh_to_server.connect(retry=5)

    if search_path is None:
        search_path = os.path.join(BuildServerPath.DEFAULT_HOST_BUILD_PATH, BuildServerPath.LAB_CONF_DIR_PREV)

    search_cmd = "\\find {} -maxdepth 5 -type f -name '*.pem'".format(search_path)
    code, output = ssh_to_server.exec_cmd(search_cmd, fail_ok=True)

    lab_name = ProjVar.get_var('lab')['name']

    LOG.info('Get the PEM for current lab ({}) first'.format(lab_name))

    if code == 0 and output:

        for file in output.splitlines():
            exiting_lab_name = os.path.basename(os.path.dirname(file))
            if exiting_lab_name in lab_name or lab_name in exiting_lab_name:
                certificate_file = file
                break
        else:
            certificate_file = output.splitlines()[0]
    else:
        msg = 'failed to fetch cert-file from build server, tried path:{}, server:{}'.format(
            search_path, from_server)
        LOG.warn(msg)
        return -1, msg

    LOG.info('found cert-file on build server, trying to scp to current active controller\ncert-file:{}'.format(
        certificate_file))

    scp_cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {} sysadmin@{}:{}'.format(
        certificate_file, lab_info.get_lab_floating_ip(), save_cert_to)

    ssh_to_server.send(scp_cmd)
    timeout = 60
    output_index = ssh_to_server.expect([ssh_to_server.prompt, Prompt.PASSWORD_PROMPT], timeout=timeout)
    if output_index == 2:
        ssh_to_server.send('yes')
        output_index = ssh_to_server.expect([ssh_to_server.prompt, Prompt.PASSWORD_PROMPT], timeout=timeout)
    if output_index == 1:
        ssh_to_server.send(HostLinuxCreds.get_password())
        output_index = ssh_to_server.expect(timeout=timeout)

    assert output_index == 0, "Failed to scp files"

    exit_code = ssh_to_server.get_exit_code()
    assert 0 == exit_code, "scp not fully succeeded"

    ssh_to_server.close()

    copied_cert_file = os.path.join(save_cert_to, os.path.basename(certificate_file))

    ssh_client.exec_cmd('ls -l {}; mv {} {}.bk'.format(copied_cert_file, copied_cert_file, copied_cert_file))
    return 0, copied_cert_file + '.bk'


def verify_cert_file(ssh_client, certificate_file, expect_existing=False):
    returned_code, result = ssh_client.exec_cmd('test -e {}'.format(certificate_file), fail_ok=True)
    if returned_code != 0:
        message = 'certificate file does not exist as expected, file:{}'.format(certificate_file)
        LOG.info(message)
        assert not expect_existing, message

    else:
        message = 'Https certificate is still existing, it should be removed, file:{}, output:{}'.format(
            certificate_file, result)
        LOG.error(message)
        assert expect_existing, message


def remove_cert_from_tpm(ssh_client,
                         cert_file=SecurityPath.DEFAULT_CERT_PATH,
                         alt_cert_file=SecurityPath.ALT_CERT_PATH,
                         check_first=True,
                         fail_ok=False):
    return install_uninstall_cert_into_tpm(ssh_client,
                                           installing=False,
                                           cert_file=cert_file,
                                           alt_cert_file=alt_cert_file,
                                           check_first=check_first,
                                           fail_ok=fail_ok)


def prepare_cert_file(con_ssh,
                      primary_cert_file=SecurityPath.DEFAULT_CERT_PATH, alt_cert_file=SecurityPath.ALT_CERT_PATH):
    check_cmd = 'test -e {}'.format(primary_cert_file)
    return_code, result = con_ssh.exec_cmd(check_cmd, fail_ok=True)
    if return_code != 0:
        LOG.info('no certificate file found at:{}, code:{}, output:{}'.format(
            os.path.dirname(primary_cert_file), return_code, result))
        LOG.info('searching alternative location:{}'.format(alt_cert_file))

        check_cmd = 'test -e {}'.format(alt_cert_file)
        return_code, result = con_ssh.exec_cmd(check_cmd, fail_ok=True)
        if return_code != 0:
            message = 'no certificate file neither at specified location nor alternative path,' + \
                'specified:{}, alternative path:{}, code:{}, output:{}'.format(
                    primary_cert_file, alt_cert_file, return_code, result)

            LOG.warn(message)
            return_code, result = fetch_cert_file(con_ssh)
            if return_code != 0 or not result:
                skip(message)
            return result

        else:
            primary_cert_file = alt_cert_file

    cert_file_to_use = os.path.join(os.path.dirname(primary_cert_file), '.bk-' + time.strftime('%Y%m%d-%H%M%S'))

    LOG.info('copy certificate file to ' + cert_file_to_use)
    return_code, result = con_ssh.exec_sudo_cmd('cp -L {} {}'.format(primary_cert_file, cert_file_to_use))

    assert return_code == 0, 'Failed to copy certificate file for testing'

    LOG.info('OK, found certificate file:{}'.format(primary_cert_file))

    return cert_file_to_use


def store_cert_into_tpm(ssh_client,
                        cert_file=SecurityPath.DEFAULT_CERT_PATH,
                        alt_cert_file=SecurityPath.ALT_CERT_PATH,
                        pem_password=None,
                        check_first=True,
                        fail_ok=False):
    return install_uninstall_cert_into_tpm(ssh_client,
                                           cert_file=cert_file,
                                           alt_cert_file=alt_cert_file,
                                           pem_password=pem_password,
                                           check_first=check_first,
                                           installing=True,
                                           fail_ok=fail_ok)


def get_cert_id(output):
    pat = re.compile(cert_id_line)
    for line in output.splitlines():
        m = re.match(pat, line)
        if m and len(m.groups()) >= 1:
            return m.group(1)

    LOG.warn('No certificate id found from output:' + output)

    return ''


def timeout_it(max_wait=900, wait_per_loop=10, passing_codes=(0,),
               failing_codes=(-999,), fail_on_empty=True):

    def wrapped(func):

        @functools.wraps(func)
        def insider(*args, **kwargs):
            rc = 0
            end_time = time.time() + max_wait

            while time.time() < end_time:
                code = rc = func(*args, **kwargs)

                if not rc:
                    if fail_on_empty:
                        return -1, rc
                else:
                    if isinstance(rc, tuple) or isinstance(rc, list):
                        code = rc[0]

                    if code in passing_codes or code == passing_codes:
                        return rc
                    elif code in failing_codes or code == failing_codes:
                        return rc
                    else:
                        LOG.info('result:{}, continue to check'.format(rc))

                time.sleep(wait_per_loop)

            else:
                LOG.info('TIMEOUT after {} seconds, the last output: {}'.format(max_wait, rc))
                return rc

        return insider

    return wrapped


@timeout_it(max_wait=180)
def get_cert_info(cert_id, con_ssh=None):
    LOG.info('check the status of the current certificate')
    cmd = 'certificate-show ' + cert_id
    output = cli.system(cmd, ssh_client=con_ssh, fail_ok=False)[1]
    if output:
        table = table_parser.table(output)
        if table:
            actual_id = table_parser.get_value_two_col_table(table, 'uuid')
            actual_type = table_parser.get_value_two_col_table(table, 'certtype')
            actual_details = table_parser.get_value_two_col_table(table, 'details')
            actual_states = ''
            if not actual_details:
                # CGTS-9529
                LOG.fatal('No details in output of certificate-show')
                LOG.fatal('Ignore it until the known issue CGTS-9529 fixed, output:' + output)
                # assert False, 'No details in output of certificate-show'
            else:
                LOG.debug('details from output of certificate-show: {}'.format(actual_details))
                actual_states = eval(actual_details)
                LOG.debug('states: {}'.format(actual_states))
                return 0, actual_id, actual_type, actual_states

            LOG.info('')
            return 1, actual_id, actual_type, actual_states
    else:
        LOG.info('no "details" in output')

    return 2, '', '', ''


def get_current_cert(con_ssh=None):
    LOG.info('query certificates information of the system')
    cmd = 'certificate-list'
    output = cli.system(cmd, ssh_client=con_ssh, fail_ok=False)[1]
    if output:
        table = table_parser.table(output)
        if table:
            cert_id, cert_type = table_parser.get_columns(table, ['uuid', 'certtype'])[0]
            return cert_id, cert_type
    return 0, ''


def get_tpm_status(con_ssh):
    cert_id, cert_type = get_current_cert(con_ssh=con_ssh)
    if cert_type == tpm_modes['enabled'] and cert_id:
        return 0, cert_id, cert_type

    return 1, cert_id, cert_type


def install_uninstall_cert_into_tpm(ssh_client,
                                    cert_file=None,
                                    alt_cert_file=None,
                                    pem_password=None,
                                    check_first=True,
                                    installing=True,
                                    fail_ok=False):

    if check_first:
        rc, cert_id, cert_type = get_tpm_status(ssh_client)
        if installing and rc == 0:
            msg = 'TPM is already configured, skip the installation test, current TPM:{}, type:{}'.format(
                cert_id, cert_type)
            skip(msg)
        elif not installing and rc != 0:
            msg = 'TPM is NOT configured, skip the uninstall test'
            skip(msg)

    cert_file_to_test = prepare_cert_file(ssh_client, primary_cert_file=cert_file, alt_cert_file=alt_cert_file)

    cmd = 'certificate-install '
    msg = ''
    if installing:
        expected_mode = tpm_modes['enabled']
        cmd += ' -m ' + expected_mode
        msg += '-enabling/install certificate into TPM'

    else:  # if expected_mode == 'ssl':
        expected_mode = tpm_modes['disabled']
        cmd += ' -m ' + expected_mode
        msg += '-unisntall certificate from TPM'

    if pem_password is not None and installing:
        msg += ', with password:' + pem_password
    else:
        msg += ', without any password'

    cmd += ' ' + cert_file_to_test

    rc, output = cli.system(cmd, fail_ok=True)
    if 0 == rc:
        LOG.debug('-succeeded:' + msg + ', cmd: ' + cmd + ', output:' + output)
        cert_id = get_cert_id(output)
        LOG.info('current cert-id is:' + cert_id)

        if installing:
            status = 'tpm-config-applied'
        else:
            status = ''

        rc = wait_for_tmp_status(cert_id, ssh_client=ssh_client, expected_status=status)[0]

        return rc, msg

    else:
        LOG.debug('-failed:' + msg + ', cmd: ' + cmd)
        assert fail_ok, 'msg:' + msg + ', cmd:' + cmd

        return -1, msg


@timeout_it(max_wait=900, wait_per_loop=60)
def wait_for_tmp_status(cert_id, ssh_client=None, expected_status=''):
    rc, actual_id, actual_mode, actual_states = get_cert_info(cert_id, con_ssh=ssh_client)
    LOG.info('auctual_id={}, actual_mode={}, actual_states={}'.format(actual_id, actual_mode, actual_states))

    controllers = system_helper.get_controllers(con_ssh=ssh_client)
    if expected_status == 'tpm-config-applied':
        for h in controllers:
            if h not in actual_states['state'] or actual_states['state'][h] != expected_status:
                return 1, '{} is not in expected status: {}'.format(h, expected_status)

        return 0, 'all controllers:{} are in expected status:{}'.format(controllers, expected_status)

    elif rc != 0:
        return 0, 'no detailed information as expected'

    return 1, 'did not get expected status, continue to wait'


def check_changes(expected_changes, actual_changes, expected=True):
    expected_changes = sorted(expected_changes)
    actual_changes = sorted(actual_changes.splitlines())
    if len(actual_changes) <= len(expected_changes):
        error_message = 'Fail, actual changes do not match expected.\n\tactual:\n{}\nexpected:\n{}'.format(
            actual_changes, expected_changes)

        LOG.info(error_message)
        return error_message

    prefix = '<' if expected else '>'

    error_message = ''
    i, j = 0, 0
    while i < len(actual_changes) and j < len(expected_changes):
        line = actual_changes[i]
        if line.strip() and line.startswith(prefix):
            line = line[2:].strip()
            rule = expected_changes[j]
            if re.match(rule, line):
                i += 1
                j += 1

            else:
                error_message += 'Mismatch: expecting:{}, actual:{}\n'.format(rule, line)
                LOG.warn(error_message)
                i += 1
        else:
            i += 1

    return error_message


def verify_configuration_changes(expected=True, connection=None):
    global file_changes

    error_messages = []
    for service, info in file_changes.items():

        for file_path, changes in info.items():
            backup_file = os.path.join(conf_backup_dir, os.path.basename(file_path))
            rc, output = connection.exec_sudo_cmd('diff -b ' + file_path + ' ' + backup_file)
            if rc == 1:

                error_message = check_changes(changes, output, expected=expected)
                if error_message:
                    LOG.error('Failed, ' + error_message)
                    error_messages.append(error_message)

            elif rc == 0:
                error_message = 'Fail, No change for file:{}, rc:{}, output:{}'.format(file_path, rc, output)
                LOG.info(error_message)
                error_messages.append(error_message)
            else:
                error_message = 'Failed, rc:{}, output:{}, '.format(rc, output)
                error_messages.append(error_message)
                LOG.error(error_message)

    assert len(error_messages) == 0, 'Failed with errors:' + '\n'.join(error_messages)
    return True


@mark.parametrize('swact_first', [
    param(False, marks=mark.p1),
    param(True, marks=mark.p1)
])
def test_enable_tpm(swact_first):
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Check if TPM is already configured')
    code, cert_id, cert_type = get_tpm_status(con_ssh)

    if code == 0:
        LOG.info('TPM already configured on the lab, cert_id:{}, cert_type:{}'.format(cert_id, cert_type))

        LOG.tc_step('disable TPM first in order to test enabling TPM')
        code, output = remove_cert_from_tpm(con_ssh, fail_ok=False, check_first=False)
        assert 0 == code, 'failed to disable TPM'
        time.sleep(30)

        LOG.info('Waiting alarm: out-of-config cleaned up')
        system_helper.wait_for_alarm_gone(EventLogID.CONFIG_OUT_OF_DATE)

    else:
        LOG.info('TPM is NOT configured on the lab')
        LOG.info('-code:{}, cert_id:{}, cert_type:{}'.format(code, cert_id, cert_type))

    if swact_first:
        LOG.tc_step('Swact the active controller as instructed')

        if len(system_helper.get_controllers()) < 2:
            LOG.info('Less than 2 controllers, skip swact')
        else:
            host_helper.swact_host(fail_ok=False)
            copy_config_from_local(con_ssh, local_conf_backup_dir, os.path.join(SYSADMIN_HOME, conf_backup_dir))

    LOG.tc_step('Install HTTPS Certificate into TPM')
    code, output = store_cert_into_tpm(con_ssh,
                                       check_first=False,
                                       fail_ok=False,
                                       pem_password=HostLinuxCreds.get_password())
    assert 0 == code, 'Failed to instll certificate into TPM, cert-file'

    LOG.info('OK, certificate is installed into TPM')

    LOG.info('Wait the out-of-config alarm cleared')
    system_helper.wait_for_alarm_gone(EventLogID.CONFIG_OUT_OF_DATE)

    LOG.tc_step('Verify the configurations changes for impacted components, expecting all changes exit')
    verify_configuration_changes(expected=True, connection=con_ssh)


@timeout_it(max_wait=300)
def copy_config_from_local(connection, local_dir, dest_dir):
    LOG.info('copy configs from local to active controller')
    connection.exec_sudo_cmd('rm -rf ' + dest_dir)
    dest_ip = system_helper.get_oam_values()['oam_floating_ip']
    common.scp_from_local(local_dir, dest_ip, dest_path=dest_dir, is_dir=True)
    rc, output = connection.exec_sudo_cmd('stat ' + dest_dir)
    if rc != 0:
        LOG.info('Failed to scp file from local to the active controller:{}'.format(output))

    return rc


@mark.parametrize('swact_first', [
    param(False, marks=mark.p1),
    param(True, marks=mark.p1)
])
def test_disable_tpm(swact_first):
    ssh_client = ControllerClient.get_active_controller()

    LOG.tc_step('Check if TPM is already configured')
    code, cert_id, cert_type = get_tpm_status(ssh_client)

    if code == 0:
        LOG.info('TPM is configured on the lab')

        if swact_first:
            LOG.tc_step('Swact the active controller as instructed')
            if len(system_helper.get_controllers()) < 2:
                LOG.info('Less than 2 controllers, skip swact')
            else:
                host_helper.swact_host(fail_ok=False)
                copy_config_from_local(ssh_client, local_conf_backup_dir, os.path.join(SYSADMIN_HOME, conf_backup_dir))

        LOG.tc_step('Disabling TPM')
        code, output = remove_cert_from_tpm(ssh_client, fail_ok=False, check_first=False)
        assert 0 == code, 'failed to disable TPM'

        LOG.info('Wait the out-of-config alarm cleared')
        system_helper.wait_for_alarm_gone(EventLogID.CONFIG_OUT_OF_DATE)

        LOG.tc_step('Verify the configurations changes for impacted components, DO NOT expect any of the changes')
        verify_configuration_changes(expected=False, connection=ssh_client)

    else:
        LOG.info('TPM is NOT configured on the lab, skip the test')
        skip('TPM is NOT configured on the lab, skip the test')
