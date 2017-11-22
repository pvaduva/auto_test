
import os
import time

from pytest import skip, fixture, mark

from consts import build_server
from consts.auth import HostLinuxCreds, SvcCgcsAuto
from consts.cgcs import Prompt
from consts.filepaths import SecurityPath, BuildServerPath
from consts.proj_vars import ProjVar

from utils import cli, lab_info, table_parser
from utils.ssh import ControllerClient, SSHFromSSH
from utils.tis_log import LOG

from keywords import system_helper, keystone_helper, host_helper


fmt_password = r'{password}'

expected_install = (
    ('Password: ', fmt_password),
    ('Enter password for the CA-Signed certificate file \[Enter <CR> for no password\]', fmt_password),
    ('Enter \[sudo\] password for wrsroot', fmt_password),
    ('Installing certificate file ', ''),
    ('WARNING, Installing an invalid or expired certificate', ''),
    ('OK to Proceed\? \(yes/NO\)', 'yes'),
    ('In {mode} mode...', ''),
    ('WARNING, For security reasons, the original certificate', ''),
    ('OK to Proceed\? \(yes/NO\)', 'yes'),
    ('Configuring TPM on all enabled controller hosts...', ''),
    ('Auditing TPM configuration state...', ''),
    ('^done$', ''),
)


@fixture(scope='session', autouse=True)
def check_lab_status():
    if not keystone_helper.is_https_lab():
        skip('Non-HTTPs lab, skip the test.')


def fetch_cert_file(ssh_client, search_path=None):

    save_cert_to = os.path.dirname(SecurityPath.ALT_CERT_PATH)

    code, output = ssh_client.exec_cmd('mkdir -p {}'.format(save_cert_to), fail_ok=True)
    if code != 0:
        msg = 'failed to create path for certificate files:{}, error:'.format(save_cert_to, output)
        LOG.warn(msg)
        return code, msg

    from_server = build_server.DEFAULT_BUILD_SERVER['ip']
    prompt = '\[{}@.* \~\]\$'.format(SvcCgcsAuto.USER)
    ssh_to_server = SSHFromSSH(ssh_client, from_server, SvcCgcsAuto.USER, SvcCgcsAuto.PASSWORD, initial_prompt=prompt)
    ssh_to_server.connect(retry=5)

    if search_path is None:
        search_path = os.path.join(BuildServerPath.DEFAULT_HOST_BUILD_PATH, BuildServerPath.CONFIG_LAB_REL_PATH)

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

    scp_cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {} wrsroot@{}:{}'.format(
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


def check_after_tpm_operation(ssh_client, certificate_file=SecurityPath.DEFAULT_CERT_PATH, to_enable=True):

    expecting_status = 'enabled' if to_enable else 'disabled'
    LOG.info('Check TPM/system states after {} TPM'.format('enabling' if to_enable else 'disabling'))

    wait_cert_in_tpm(ssh_client=ssh_client, expecting_status=expecting_status)

    verify_cert_file(ssh_client, certificate_file, expect_existing=False)


def check_tpm_states(state, ssh_client=None, expecting_state='tpm-config-applied', not_in_state_ok=False):

    if not state:
        assert not_in_state_ok, 'No controllers is TPM state:{}'.format(expecting_state)
        return 1

    controllers = system_helper.get_controllers(con_ssh=ssh_client)
    count_out_of_state = 0

    for controller in controllers:
        if state[controller].lower() != expecting_state:
            LOG.error('TPM is not in state:{} for controller:{}'.format(expecting_state, controller))
            count_out_of_state += 1

    if count_out_of_state > 0:
        message = 'total {} out of {} controllers NOT in expected state:{}'.format(count_out_of_state,
                                                                               len(controllers),
                                                                               expecting_state)
        LOG.info('state:{}'.format(state))
        assert not_in_state_ok, message

        return count_out_of_state

    else:
        LOG.info('all controllers are in state:{}'.format(expecting_state))
        return 0


def wait_cert_in_tpm(ssh_client=None, expecting_status='any', wait_gap=5, empty_output_count=2, timeout=300):
    check_count = 0
    wait_till = time.time() + timeout

    show_cmd = 'tpmconfig-show'

    while time.time() < wait_till:
        time.sleep(wait_gap)

        check_count += 1

        return_code, result = cli.system(show_cmd, ssh_client=ssh_client, rtn_list=True, fail_ok=False)

        if result:
            table = table_parser.table(result)
            uuid = table_parser.get_value_two_col_table(table, 'uuid')
            tpm_path = table_parser.get_value_two_col_table(table, 'tpm_path')
            state = eval(table_parser.get_value_two_col_table(table, 'state'))
            LOG.debug('output:{}, code:{}\n'.format(table, return_code))

            expecting_state = 'tpm-config-applied'
            count_not_in_state = check_tpm_states(state,
                                                  ssh_client=ssh_client,
                                                  expecting_state=expecting_state,
                                                  not_in_state_ok=True)
            if count_not_in_state == 0:
                assert expecting_status != 'disabled', \
                    'TPM applied on all controllers but expecting them be DISABLED,\n{}'.format(result)

                return 0, {'uuid': uuid, 'tpm_path': tpm_path, 'state': state}

            LOG.debug('{} controllers are not in expecting state:{}, keep waiting and checking, output:\n{}'.format(
                count_not_in_state, expecting_state, result))

        else:
            message = 'TPM is disabled (No TPM configured), empty output from CMD:' + show_cmd
            LOG.debug(message)

            if check_count > empty_output_count:
                assert expecting_status != 'enabled', message

                return 1, {}

    else:
        assert False, \
            'TPM state is not stabilized (enabled + applied nor disabled) after checking {} times in {} seconds'.format(
                check_count, timeout)


def remove_cert_from_tpm(ssh_client,
                         cert_file=SecurityPath.DEFAULT_CERT_PATH,
                         alt_cert_file=SecurityPath.ALT_CERT_PATH,
                         check_first=True,
                         fail_ok=False):
    return __install_uninstall_cert_into_tpm(ssh_client,
                                             installing=False,
                                             cert_file=cert_file,
                                             alt_cert_file=alt_cert_file,
                                             check_first=check_first,
                                             fail_ok=fail_ok)


def prepare_cert_file(con_ssh, primary_cert_file = SecurityPath.DEFAULT_CERT_PATH, alt_cert_file = SecurityPath.ALT_CERT_PATH):
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
                        check_first=True,
                        fail_ok=False):
    return __install_uninstall_cert_into_tpm(ssh_client,
                                             cert_file=cert_file,
                                             alt_cert_file=alt_cert_file,
                                             check_first=check_first,
                                             installing=True,
                                             fail_ok=fail_ok)


def __install_uninstall_cert_into_tpm(ssh_client,
                                      cert_file=None,
                                      alt_cert_file=None,
                                      check_first=True,
                                      installing=True,
                                      fail_ok=False):

    if check_first:
        code, output = wait_cert_in_tpm(ssh_client)
        if installing and code == 0:
            msg = 'TPM is already configured, skip the installation test, current TPM status:{}'.format(output)
            skip(msg)
        elif not installing and not output:
            msg = 'TPM is NOT configured, skip the uninstall test'
            skip(msg)

    cert_file_to_test = prepare_cert_file(ssh_client, primary_cert_file=cert_file, alt_cert_file=alt_cert_file)

    settings = {'mode': 'TPM' if installing else 'regular', 'password': HostLinuxCreds.get_password()}
    expected_outputs = [expected.format(**settings) for expected, _ in expected_install]
    expected_outputs += [Prompt.CONTROLLER_PROMPT, Prompt.ADMIN_PROMPT]
    total_outputs = len(expected_outputs)

    user_inputs = [input.format(**settings) for _, input in expected_install]
    total_inputs = len(user_inputs)

    LOG.info('cert-file:{}'.format(cert_file_to_test))

    cmd = 'sudo https-certificate-install --cert {} {}'.format(cert_file_to_test, '--tpm' if installing else '')
    ssh_client.send(cmd)

    for _ in range(total_outputs):
        index = ssh_client.expect(blob_list=expected_outputs, timeout=60)

        if 0 <= index < total_inputs:
            output = expected_outputs[index]

            if output.strip() == 'done':
                LOG.info('CLI completed, output:{}, index:{}'.format(output, index))
                break
            else:
                to_send = user_inputs[index]
                if to_send:
                    ssh_client.send(to_send)

        elif total_inputs <= index < len(expected_outputs):
            output = expected_outputs[index]
            LOG.info('CLI completed, output:{}, index:{}'.format(output, index))
            break

        else:
            LOG.error('failed to execute CLI:{}'.format(cmd))
    else:
        msg = 'CLI:{} failed'.format(cmd)
        LOG.info(msg)
        assert fail_ok, msg

        return 1, msg

    msg = 'CLI:{} successfully executed'.format(cmd)
    LOG.info(msg)

    check_after_tpm_operation(ssh_client, certificate_file=cert_file_to_test, to_enable=installing)

    return 0, msg


@mark.parametrize(('swact_first'), [
    mark.p1(False),
    mark.p1(True)
])
def test_enable_tpm(swact_first):
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Check if TPM is already configured')
    code, tpm_info = wait_cert_in_tpm(con_ssh)

    if code == 0 and tpm_info:
        LOG.info('TPM already configured on the lab')

        LOG.tc_step('disable TPM first in order to test enabling TPM')
        code, output = remove_cert_from_tpm(con_ssh, fail_ok=False, check_first=False)
        assert 0 == code, 'failed to disable TPM'

    else:
        LOG.info('TPM is NOT configured on the lab')

    if swact_first:
        LOG.tc_step('Swact the active controller as instructed')
        num_controllers = len([c for c in system_helper.get_controllers()])
        if num_controllers < 2:
            LOG.info('Less than 2 controllers, skip swact')
        else:
            host_helper.swact_host(fail_ok=False)

    LOG.tc_step('Install HTTPS Certificate into TPM')
    store_cert_into_tpm(con_ssh, fail_ok=False)


@mark.parametrize(('swact_first'), [
    mark.p1(False),
    mark.p1(True)
])
def test_disable_tpm(swact_first):
    ssh_client = ControllerClient.get_active_controller()

    LOG.tc_step('Check if TPM is configured')
    code, tpm_info = wait_cert_in_tpm(ssh_client)

    if code == 0 and tpm_info:
        LOG.info('TPM is configured on the lab')

        if swact_first:
            LOG.tc_step('Swact the active controller as instructed')
            num_controllers = len([c for c in system_helper.get_controllers()])
            if num_controllers < 2:
                LOG.info('Less than 2 controllers, skip swact')
            else:
                host_helper.swact_host(fail_ok=False)

        LOG.tc_step('disable TPM first in order to test enabling TPM')
        code, output = remove_cert_from_tpm(ssh_client, fail_ok=False, check_first=False)
        assert 0 == code, 'failed to disable TPM'

    else:
        LOG.info('TPM is NOT configured on the lab, skip the test')
        skip('TPM is NOT configured on the lab, skip the test')
