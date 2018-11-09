import os

from consts.auth import Tenant
from consts.cgcs import Prompt
from consts.openstack_cli import NEUTRON_MAP
from consts.proj_vars import ProjVar
from consts.timeout import CLI_TIMEOUT
from utils import exceptions
from utils.clients.ssh import ControllerClient
from utils.clients.local import RemoteCLIClient


def exec_cli(cmd, sub_cmd, positional_args='', ssh_client=None, use_telnet=False, con_telnet=None,
             flags='', fail_ok=False, cli_dir='', auth_info=None, source_openrc=None, err_only=False,
             timeout=CLI_TIMEOUT, rtn_list=False, force_source=False):
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
        use_telnet
        con_telnet
        auth_info: (dict) authorization information to run cli commands.
        source_openrc (None|bool)
        force_source (bool): whether to source if already sourced.
            This is usually used if any env var was changed in test. such as admin password changed, etc.
        fail_ok:
        cli_dir:
        err_only:
        timeout:
        rtn_list (bool):

    Returns:
        if command executed successfully: return command_output
        if command failed to execute such as authentication failure:
            if fail_ok: return exit_code, command_output
            if not fail_ok: raise exception
    """
    if use_telnet and con_telnet is None:
        raise ValueError("No Telnet session provided")

    if auth_info is None:
        auth_info = Tenant.get_primary()

    positional_args = __convert_args(positional_args)
    flags = __convert_args(flags)

    use_remote_cli = False
    remote_cli_flag = ProjVar.get_var('REMOTE_CLI')
    if not use_telnet:
        if remote_cli_flag:
            remote_client = RemoteCLIClient.get_remote_cli_client(create_new=False)
            if remote_client:
                ssh_client = remote_client
                source_openrc = True
                use_remote_cli = True
        if not ssh_client:
            if ProjVar.get_var('IS_DC'):
                region = auth_info['region']
                ssh_name = 'central_region' if region in ('RegionOne', 'SystemController') else region
                # This may not exist if cli cmd used before DC vars are initialized
                ssh_client = ControllerClient.get_active_controller(name=ssh_name, fail_ok=True)

            if not ssh_client:
                ssh_client = ControllerClient.get_active_controller()

    if source_openrc is None:
        source_openrc = ProjVar.get_var('SOURCE_CREDENTIAL')

    if source_openrc:
        source_file = _get_rc_path(tenant=auth_info['tenant'], remote_cli=use_remote_cli)
        if use_telnet:
            cmd = 'source {}; {}'.format(source_file, cmd)
        else:
            source_openrc_file(ssh_client=ssh_client, auth_info=auth_info, rc_file=source_file, fail_ok=fail_ok,
                               remote_cli=use_remote_cli, force=force_source)
    else:
        if auth_info:
            auth_args = ("--os-username '{}' --os-password '{}' --os-project-name {} --os-auth-url {} "
                         "--os-user-domain-name Default --os-project-domain-name Default".
                         format(auth_info['user'], auth_info['password'], auth_info['tenant'], auth_info['auth_url']))

            if cmd in ('openstack', 'sw-manager'):
                flags += ' --os-interface internal'
            else:
                flags += ' --os-endpoint-type internalURL'

            # # Add additional auth args for https lab
            # if CliAuth.get_var('HTTPS'):
            #     if cmd in ['openstack', 'sw-manager']:
            #         flags += ' --os-interface internal'
            #     else:
            #         flags += ' --os-endpoint-type internalURL'
            # else:
            #     if cmd == 'sw-manager':
            #         flags += ' --os-interface internal'

            if cmd != 'dcmanager':
                region = auth_info['region']
                if cmd == 'nova' and region == 'RegionOne':
                    region = 'SystemController'
                flags += ' --os-region-name {}'.format(region)

            flags = '{} {}'.format(auth_args.strip(), flags.strip())

    complete_cmd = ' '.join([os.path.join(cli_dir, cmd), flags.strip(), sub_cmd, positional_args]).strip()

    # workaround for CGTS-10031
    if complete_cmd.startswith('dcmanager'):
        complete_cmd = complete_cmd.replace('--os-project-name', '--os-tenant-name')

    if use_telnet:
        exit_code, cmd_output = con_telnet.exec_cmd(complete_cmd, timeout=timeout)
    else:
        exit_code, cmd_output = ssh_client.exec_cmd(complete_cmd, err_only=err_only, expect_timeout=timeout,
                                                    searchwindowsize=100)
    # if source_openrc:
    #     if not use_telnet:
    #         ssh_client.set_prompt()
    #         ssh_client.exec_cmd("export PS1='\\u@\\h:~\\$ '")

    if fail_ok:
        if exit_code == 0:
            return 0, cmd_output
        elif exit_code in [1, 2]:
            return 1, cmd_output
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


def _get_rc_path(tenant, remote_cli=False):
    if remote_cli:
        openrc_path = os.path.join(ProjVar.get_var('LOG_DIR'), 'horizon', '{}-openrc.sh'.format(tenant))
    else:
        openrc_path = '/etc/nova/openrc' if 'admin' in tenant else '~/openrc.{}'.format(tenant)

    return openrc_path


def source_openrc_file(ssh_client, auth_info, rc_file, fail_ok=False, remote_cli=False, force=False):
    """
    Source to the given openrc file on the ssh client.
    Args:
        ssh_client:
        auth_info:
        rc_file:
        fail_ok:
        remote_cli (bool): Whether it is remote cli client, where openrc files are on localhost.
        force (bool): Whether to source even if already sourced.

    Returns:
        (-1, None)    # Already sourced, no action done
        (0, <cmd_output>)   # sourced to openrc file successfully
        (1, <err_output>)   # Failed to source

    """
    exit_code, cmd_output = -1, None
    user = auth_info['user']

    if force or 'keystone_{}'.format(user) not in ssh_client.prompt:
        tenant = auth_info['tenant']
        password = auth_info['password']
        new_prompt = Prompt.REMOTE_CLI_PROMPT.format(user) if remote_cli else Prompt.TENANT_PROMPT.format(user)

        cmd = 'source {}'.format(rc_file)
        ssh_client.send(cmd)
        prompts = [new_prompt]
        if remote_cli:
            prompts += ['Password for project {} as user {}:'.format(tenant, user),
                        'if you are not using HTTPS:'
                        ]
        index = ssh_client.expect(prompts, fail_ok=False)

        if index == 2:
            ssh_client.send()
            index = ssh_client.expect(prompts[0:3])
        if index == 1:
            ssh_client.send(password)
            index = ssh_client.expect(prompts[0:2])

        if index == 0:
            ssh_client.set_prompt(new_prompt)
            exit_code = ssh_client.get_exit_code()
        else:
            cmd_output = ssh_client.cmd_output
            ssh_client.send_control()
            ssh_client.expect()
            exit_code = 1

        if exit_code != 0:
            print("exit code: {}".format(exit_code))
            if not fail_ok:
                raise exceptions.SSHExecCommandFailed("Failed to Source. Output: {}".format(cmd_output))

    return exit_code, cmd_output


def nova(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
         auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False, use_telnet=False,
         con_telnet=None):

    return exec_cli('nova', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, use_telnet=use_telnet,
                    con_telnet=con_telnet)


def openstack(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
              auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False, source_openrc=False):
    flags += ' --os-identity-api-version 3'

    return exec_cli('openstack', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, source_openrc=source_openrc)


def system(cmd, positional_args='', ssh_client=None, use_telnet=False, con_telnet=None,
           flags='', fail_ok=False, cli_dir='', auth_info=Tenant.get('admin'), source_openrc=None, err_only=False,
           timeout=CLI_TIMEOUT, rtn_list=False, force_source=False, system_controller_ok=False):

    if not system_controller_ok and 'SystemController' in auth_info.get('region'):
        auth_info = auth_info.copy()
        auth_info['region'] = 'RegionOne'
    return exec_cli('system', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, use_telnet=use_telnet, con_telnet=con_telnet,
                    fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info, source_openrc=source_openrc,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, force_source=force_source)


def heat(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
         auth_info=Tenant.get('admin'), err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

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


def swift(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
          auth_info=Tenant.get('admin'), source_creden_=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('swift', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    source_openrc=source_creden_, err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def glance(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
           auth_info=Tenant.get('admin'), err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('glance', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def keystone(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
             auth_info=Tenant.get('admin'), err_only=False, timeout=CLI_TIMEOUT, rtn_list=False, source_admin_=False):

    source_cred_ = Tenant.get('admin') if source_admin_ else None
    return exec_cli('keystone', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, source_openrc=source_cred_)


def sw_manager(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
               auth_info=Tenant.get('admin'), source_creden_=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('sw-manager', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    source_openrc=source_creden_, err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def murano(cmd, positional_args='', ssh_client=None,  flags='', fail_ok=False, cli_dir='',
           auth_info=None, err_only=False, timeout=CLI_TIMEOUT, rtn_list=False):

    return exec_cli('murano', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list)


def fm(cmd, positional_args='', ssh_client=None, use_telnet=False, con_telnet=None,
       flags='', fail_ok=False, cli_dir='', auth_info=Tenant.ADMIN, source_openrc=None, err_only=False,
       timeout=CLI_TIMEOUT, rtn_list=False, force_source=False):

    # FIXME: temp workaround to maintain backward compatibility for non-STX build until TC branch is created.
    build = ProjVar.get_var('BUILD_ID')
    cmd_ = 'fm'
    if build and build != 'n/a':
        if build < '2018-08-19':
            cmd_ = 'system'
    elif 'CGCS_DEV_0034' in ProjVar.get_var('BUILD_INFO') or 'TC_DEV_0003' in ProjVar.get_var('BUILD_INFO'):
        cmd_ = 'system'

    return exec_cli(cmd_, sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, use_telnet=use_telnet, con_telnet=con_telnet,
                    fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info, source_openrc=source_openrc,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, force_source=force_source)


def dcmanager(cmd, positional_args='', ssh_client=None, flags='', fail_ok=False, cli_dir='',
              auth_info=Tenant.get('admin', dc_region='RegionOne'), err_only=False, timeout=CLI_TIMEOUT,
              rtn_list=False):
    if ssh_client is None:
        ssh_client = ControllerClient.get_active_controller('central_region')
    return exec_cli('dcmanager', sub_cmd=cmd, positional_args=positional_args, flags=flags,
                    ssh_client=ssh_client, fail_ok=fail_ok, cli_dir=cli_dir, auth_info=auth_info,
                    err_only=err_only, timeout=timeout, rtn_list=rtn_list, source_openrc=False)
