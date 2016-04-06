import os

from utils import exceptions
from utils import ssh
from utils.ssh import ControllerClient
from consts.timeout import CLI_TIMEOUT
from consts.auth import Primary, Tenant


def exec_cli(cmd, sub_cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
             auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):
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
    if ssh_client is None:
        ssh_client = ControllerClient.get_active_controller()

    if auth_info is None:
        auth_info = Primary.get_primary()

    positional_args = __convert_args(positional_args)
    flags = __convert_args(flags)

    if auth_info:
        auth_args = ('--os-username {} --os-password {} --os-tenant-name {} --os-auth-url {} --os-region-name {}'.
                     format(auth_info['user'], auth_info['password'], auth_info['tenant'], auth_info['auth_url'],
                            auth_info['region']))
        flags = (auth_args + ' ' + flags).strip()

    complete_cmd = ' '.join([os.path.join(cli_dir, cmd), flags, sub_cmd, positional_args]).strip()
    exit_code, cmd_output = ssh_client.exec_cmd(complete_cmd, err_only=err_only, expect_timeout=timeout)

    # The commented code is to convert output to dictionary or list.
    # But it might be a overkill, and hides the return type.
    # if not raw_output:
    #    cmd_output = table_parser.tables(cmd_output)
    #    # return dictionary if output contains only 1 table, otherwise return a list of tables.
    #    if len(cmd_output) == 1:
    #        cmd_output = cmd_output[0]

    if fail_ok:
        if exit_code in [0, 1]:
            return exit_code, cmd_output
    elif exit_code == 0:
        if rtn_list:
            return exit_code, cmd_output
        else:
            return cmd_output

    raise exceptions.CLIRejected("CLI command failed to execute.".format(cmd_output))


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
              auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('openstack', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def system(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
           auth_info=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('system', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def heat(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
         auth_info=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('heat', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def neutron(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
            auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

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
          auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('swift', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=False, timeout=timeout, rtn_list=rtn_list)


def glance(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
           auth_info=Tenant.ADMIN, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('glance', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=False, timeout=timeout, rtn_list=rtn_list)