import os

from utils import exceptions
from utils import ssh
from utils.ssh import ControllerClient
from consts.timeout import CLI_TIMEOUT
from consts.auth import Tenant, CliAuth
from consts.proj_vars import ProjVar
from consts.openstack_cli import NEUTRON_MAP


def exec_cli(cmd, sub_cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
             auth_info=None, source_creden_=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):
    """

    Args:
        cmd: such as 'neutron'
        sub_cmd: such as 'net-show'
        positional_args: string or list.
            Single arg examples: 'arg0' or ['arg0']
            Multiple args string example: 'arg1 arg2'
            Multiple args list example: ['arg1','arg2']
        flags: string or list.
            Single arg examples: 'arg0 value0' or ['arg0 value']
            Multiple args string example: 'arg1 value1 arg2 value2 arg3'
            Multiple args list example: ['arg1 value1','arg2 value2', 'arg3']
        ssh_client:
        auth_info: (dictionary) authorization information to run cli commands.
        fail_ok:
        cli_dir:
        err_only:
        timeout:
        rtn_list:

    Returns:
        if command executed successfully: return command_output
        if command failed to execute such as authentication failure:
            if fail_ok: return exit_code, command_output
            if not fail_ok: raise exception
    """
    lab = ProjVar.get_var('LAB')
    if ssh_client is None:
        ssh_client = ControllerClient.get_active_controller()

    if auth_info is None:
        auth_info = Tenant.get_primary()

    if 'auth_url' in lab:
        Tenant._set_url(lab['auth_url'])

    positional_args = __convert_args(positional_args)
    flags = __convert_args(flags)

    if source_creden_ is None:
        source_creden_ = ProjVar.get_var('SOURCE_CREDENTIAL')

    if source_creden_:
        if source_creden_ is Tenant.TENANT2:
            cmd = "source /home/wrsroot/openrc.tenant2; " + cmd
            ssh_client.set_prompt(prompt=ssh.TENANT2_PROMPT)
        elif source_creden_ is Tenant.TENANT1:
            cmd = "source /home/wrsroot/openrc.tenant1; " + cmd
            ssh_client.set_prompt(prompt=ssh.TENANT1_PROMPT)
        else:
            cmd = "source /etc/nova/openrc; " + cmd
            ssh_client.set_prompt(prompt=ssh.ADMIN_PROMPT)
    else:
        if auth_info:
            auth_args = ('--os-username {} --os-password {} --os-project-name {} --os-auth-url {} --os-region-name {} '
                         '--os-user-domain-name Default --os-project-domain-name Default'.
                         format(auth_info['user'], auth_info['password'], auth_info['tenant'], auth_info['auth_url'],
                                auth_info['region']))

            # Add additional auth args for https lab
            if CliAuth.get_var('HTTPS'):
                if cmd == 'openstack':
                    flags += ' --os-interface internal'
                else:
                    flags += ' --os-endpoint-type internalURL'

            flags = (auth_args + ' ' + flags).strip()
    complete_cmd = ' '.join([os.path.join(cli_dir, cmd), flags, sub_cmd, positional_args]).strip()
    exit_code, cmd_output = ssh_client.exec_cmd(complete_cmd, err_only=err_only, expect_timeout=timeout,
                                                searchwindowsize=100)
    if source_creden_:
        ssh_client.set_prompt()
        ssh_client.exec_cmd("export PS1='\\u@\\h:~\\$ '")

    if fail_ok:
        if exit_code in [0, 1]:
            return exit_code, cmd_output
    elif exit_code == 0:
        if rtn_list:
            return exit_code, cmd_output
        else:
            return cmd_output

    raise exceptions.CLIRejected("CLI '{}' failed to execute. Output: {}".format(complete_cmd, cmd_output))


def __convert_args(args):
    if args is None:
        args = ''
    elif isinstance(args, list):
        args = ' '.join(str(arg) for arg in args)
    else:
        args = str(args)

    return args.strip()


def source_admin(ssh_client=None, fail_ok=False):
    """
    run 'source /etc/nova/openrc' to grant keystone admin privileges. Update the ssh_client prompt after sourcing.

    Warnings: It is discouraged to source in automation unless necessary

    Args:
        ssh_client: ssh client to send the command to
        fail_ok: whether to throw the exception upon fail to send command

    Returns: exit code (int), command output (str)

    Raises: SSHExecCommandFailed
    """
    cmd = "source /etc/nova/openrc"
    prompt = ssh.ADMIN_PROMPT
    return _source_user(ssh_client, fail_ok, cmd, prompt)


def _source_user(ssh_client, fail_ok, cmd, prompt):
    if ssh_client is None:
        ssh_client = ControllerClient.get_active_controller()
    original_prompt = ssh_client.get_prompt()
    ssh_client.set_prompt(prompt)
    exit_code, cmd_output = ssh_client.exec_cmd(cmd)
    if not exit_code == 0:
        ssh_client.set_prompt(original_prompt)
        if not fail_ok:
            raise exceptions.SSHExecCommandFailed("Failed to Source.")

    return exit_code, cmd_output


def nova(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
         auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('nova', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def openstack(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
              auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False, source_admin_=False):
    source_cred_ = Tenant.ADMIN if source_admin_ else None
    flags += ' --os-identity-api-version 3'

    return exec_cli('openstack', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, source_creden_=source_cred_)


def system(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
           auth_info=Tenant.ADMIN, source_creden_=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('system', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    source_creden_=source_creden_, err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def heat(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
         auth_info=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('heat', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def neutron(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
            auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False, convert_openstack=None,
            force_neutron=False):

    openstack_cmd = None
    if not force_neutron:
        convert_openstack = convert_openstack if openstack_cmd is not None else ProjVar.get_var('OPENSTACK_CLI')
        if convert_openstack:
            openstack_cmd = NEUTRON_MAP.get(cmd, None)

    if openstack_cmd is not None:
        return openstack(cmd=openstack_cmd, positional_args=positional_args, flags=flags,
                         ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                         err_only=err_only, timeout=timeout, rtn_list=rtn_list)

    return exec_cli('neutron', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def ceilometer(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
               auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('ceilometer', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def cinder(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
           auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('cinder', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def swift(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
          auth_info=Tenant.ADMIN, source_creden_=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('swift', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    source_creden_=source_creden_, err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def glance(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
           auth_info=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('glance', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def keystone(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
             auth_info=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False, source_admin_=False):

    source_cred_ = Tenant.ADMIN if source_admin_ else None
    return exec_cli('keystone', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, source_creden_=source_cred_)


def qemu_img(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
          auth_info=Tenant.ADMIN, source_creden_=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('qemu-img', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    source_creden_=source_creden_, err_only=err_only, timeout=timeout, rtn_list=rtn_list)
