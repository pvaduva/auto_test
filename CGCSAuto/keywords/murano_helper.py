#
# Copyright (c) 2016 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#


import time

from utils.tis_log import LOG
from utils import cli, table_parser, exceptions
from utils.clients.ssh import ControllerClient
from consts.auth import Tenant, HostLinuxUser
from keywords import system_helper, host_helper


def enable_disable_murano(enable=True, enable_disable_agent=False,
                          fail_ok=False, con_ssh=None,
                          auth_info=Tenant.get('admin')):
    """
    Enable/Disable Murano service and murano agent on the system
    Args:
        enable: True/False, True for enable, false for disable
        enable_disable_agent: Ture/False, true for the same action as enable
            above
        fail_ok: whether return False or raise exception when some services
            fail to reach enabled-active state
        con_ssh (SSHClient):
        auth_info (dict)

    Returns:
        code, msg: return code and msg

        """

    # enable Murano

    if enable:
        msg = "Enabled Murano Service Successfully"
        ret, out = system_helper.enable_service('murano', con_ssh=con_ssh,
                                                auth_info=auth_info,
                                                fail_ok=fail_ok)

        if ret == 1:
            return 1, out

        if enable_disable_agent:
            ret, out = system_helper.create_service_parameter(
                service="murano", section="engine", name="disable_murano_agent",
                value="false", modify_existing=True)
            if ret != 0:
                return 1, out
    else:
        msg = "Disabled Murano Service Successfully"
        ret, out = system_helper.disable_service('murano', con_ssh=con_ssh,
                                                 auth_info=auth_info,
                                                 fail_ok=fail_ok)

        if ret == 1:
            return 1, out

        if enable_disable_agent:
            ret, out = system_helper.create_service_parameter(
                service="murano", section="engine",
                name="disable_murano_agent", value="true", modify_existing=True)
            if ret != 0:
                return 1, out

    if ret == 0 and system_helper.get_host_values(
            'controller-0', 'config_status')[0] == 'Config out-of-date':
            # need to lock/unlock standby and swact lock/unlock
        ret, out = host_helper.lock_unlock_controllers(alarm_ok=True)
        if ret == 1:
            return 1, out

    else:
        msg = "Failed to enable/disable Murano service"

    return 0, msg


def enable_disable_murano_agent(enable=True, con_ssh=None,
                                auth_info=Tenant.get('admin')):
    """
    Enable/Disable Murano service and murano agent on the system
    Args:
        enable: True/False, True for enable, false for disable
        con_ssh (SSHClient):
        auth_info (dict)

    Returns:
        code, msg: return code and msg

        """

    # enable Murano
    msg = "Enabled Murano Service Successfully"
    if enable:
        ret, out = system_helper.create_service_parameter(
            service="murano", section="engine",
            name="disable_murano_agent",
            value="false", modify_existing=True,
            con_ssh=con_ssh)

    else:
        ret, out = system_helper.create_service_parameter(
            service="murano", section="engine",
            name="disable_murano_agent",
            value="true", modify_existing=True,
            con_ssh=con_ssh)

    if ret != 0:
        return 1, out

    if system_helper.get_host_values('controller-0', 'config_status',
                                     con_ssh=con_ssh, auth_info=auth_info)[0] \
            == 'Config out-of-date':
            # need to lock/unlock standby and swact lock/unlock
        ret, out = host_helper.lock_unlock_controllers()
        if ret != 0:
            return 1, out
    else:
        msg = "Failed to enable/disable Murano engine"

    return 0, msg


def import_package(pkg, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Import Murano package
    Args:
        pkg: package name to import (full path)
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some
            services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if pkg is None:
        raise ValueError("Package name has to be specified.")

    LOG.info("Importing Murano package {}".format(pkg))
    code, output = cli.openstack('package import --exists-action u', pkg,
                                 ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info)

    if code > 0:
        return 1, output

    table_ = table_parser.table(output)
    pkg_id = table_parser.get_values(table_, 'ID')
    return 0, pkg_id


def import_bundle(bundle, is_public=False, con_ssh=None, auth_info=None,
                  fail_ok=False):
    """
    Import Murano bundle
    Args:
        bundle: name of the bundle (full path)
        is_public: flag to set
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some
            services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if bundle is None:
        raise ValueError("Murano bundle name has to be specified.")

    LOG.info("Importing Murano bundle {}".format(bundle))
    args = bundle if not is_public else '--is-public {}'.format(bundle)
    code, output = cli.openstack('bundle import', args, ssh_client=con_ssh,
                                 fail_ok=fail_ok, auth_info=auth_info)

    if code > 0:
        return 1, output

    table_ = table_parser.table(output)
    pkg_id = table_parser.get_value_two_col_table(table_, 'id')
    return 0, pkg_id


def get_package_list(header='ID', pkgid=None, name=None, fqn=None,
                     author=None, active=None, is_public=None,
                     pkg_type=None, version=None, auth_info=Tenant.get('admin'),
                     con_ssh=None, strict=True,
                     regex=None, **kwargs):
    """

    Args:
        header:
        pkgid
        name:
        fqn:
        author:
        active:
        is_public:
        pkg_type:
        version:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns: list

    """

    table_ = table_parser.table(cli.openstack('package list',
                                              ssh_client=con_ssh,
                                              auth_info=auth_info)[1])
    args_temp = {
        'ID': pkgid,
        'Name': name,
        'FQN': fqn,
        'Author': author,
        'Active': active,
        'Is Public': is_public,
        'Type': pkg_type,
        'Version': version
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict,
                                   regex=regex, **kwargs)


def delete_bundle(bundle_id, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Delete murano bundle
    Args:
        bundle_id: Bundle id to delete
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some
            services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if bundle_id is None:
        raise ValueError("Murano bundle id has to be specified.")

    LOG.info("Deleting Murano bundle {}".format(bundle_id))
    code, output = cli.openstack('bundle delete', bundle_id, ssh_client=con_ssh,
                                 fail_ok=fail_ok, auth_info=auth_info)

    if code > 0:
        return 1, output

    table_ = table_parser.table(output)
    pkg_id = table_parser.get_value_two_col_table(table_, 'id')
    return 0, pkg_id


def delete_package(package_id, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Delete Murano package
    Args:
        package_id: package id to delete
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some
            services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if package_id is None:
        raise ValueError("Murano package name has to be specified.")

    LOG.info("Deleting Murano bundle {}".format(package_id))
    code, output = cli.openstack('package delete', package_id,
                                 ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info)
    if code > 0:
        return 1, output

    return 0, "package {} deleted successfully".format(package_id)


def create_env(name, mgmt_net_id=None, mgmt_subnet_id=None, con_ssh=None,
               auth_info=None, fail_ok=False):
    """
    Create Murano Environment
    Args:
        name: Name of the env to create
        mgmt_subnet_id (str): The ID of tenant1 management subnet
        mgmt_net_id (str): The ID of tenant1 management net
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some
            services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if name is None:
        raise ValueError("Murano environment name has to be specified.")

    LOG.info("Creating Murano Environment {}".format(name))

    args = ''
    if mgmt_subnet_id:
        args = " --join-subnet-id {}".format(mgmt_subnet_id)
    elif mgmt_net_id:
        args = " --join-net-id {}".format(mgmt_net_id)

    args = '{} {}'.format(args, name)
    code, output = cli.openstack("environment create", args, ssh_client=con_ssh,
                                 fail_ok=fail_ok, auth_info=auth_info)
    if code > 0:
        return 1, output

    table_ = table_parser.table(output)
    env_id = table_parser.get_values(table_, 'ID')
    if len(env_id) > 0:
        return 0, env_id[0]
    else:
        msg = "Fail to get the murano environment id"
        LOG.info(msg)
        if fail_ok:
            return 2, msg
        else:
            raise exceptions.MuranoError(msg)


def create_session(env_id, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Create a Murano Session
    Args:
        env_id:
        con_ssh:
        auth_info:
        fail_ok:

    Returns:

    """

    if env_id is None:
        raise ValueError("Murano env id has to be specified.")

    LOG.info("Creating a Murano Session in Environment {}".format(env_id))
    code, output = cli.openstack('environment session create', env_id,
                                 ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info)

    if code > 1:
        return 1, output

    table_ = table_parser.table(output)
    session_id = table_parser.get_value_two_col_table(table_, 'id')
    if session_id != '':
        msg = "Session successfully created session {}".format(session_id)
        LOG.info(msg)
        return 0, session_id
    else:
        msg = "Fail to get Session id: {}".format(output)
        LOG.info(msg)
        if fail_ok:
            return 2, msg
        else:
            raise exceptions.MuranoError(msg)


def deploy_env(env_id, session_id, con_ssh=None, auth_info=None, fail_ok=False):

    code, output = cli.openstack('environment deploy --session-id {} {}'.
                                 format(session_id, env_id), ssh_client=con_ssh,
                                 fail_ok=fail_ok, auth_info=auth_info)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    deploy_id = table_parser.get_value_two_col_table(table_, 'id')
    if not deploy_id:
        msg = "Fail to get the deploy id; session-id {}; environment " \
              "id {}".format(session_id, env_id)
        if fail_ok:
            return 2, msg
        else:
            raise exceptions.MuranoError(msg)

    return 0, deploy_id


def delete_env(env_id, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Delete Murano Environment
    Args:
        env_id: Id of the env to create
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some
            services fail to reach enabled-active 12state

    Returns:
        code, msg: return code and msg

        """

    if not env_id:
        raise ValueError("Murano env id has to be specified.")

    LOG.info("Deleting Murano Environment {}".format(env_id))
    code, output = cli.openstack('environment delete', env_id,
                                 ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info)
    if code > 0:
        return 1, output

    return 0, "Env {} Deleted Successfully".format(env_id)


def import_package_from_repo(pkg, repo, con_ssh=None, auth_info=None,
                             fail_ok=False):
    """
    Import Murano package from repo
    Args:
        pkg: package name to import (full path)
        repo: repo url
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some
            services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if repo is None:
        raise ValueError("Repo URL has to be specified.")
    elif pkg is None:
        raise ValueError("Package name has to be specified.")

    args = "--murano-repo-url {} {}".format(repo, pkg)

    LOG.info("Importing Murano package {}".format(pkg))
    code, output = cli.openstack('package import', args, ssh_client=con_ssh,
                                 fail_ok=fail_ok, auth_info=auth_info)
    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    pkg_id = table_parser.get_values(table_, 'ID')
    return 0, pkg_id


def get_environment_status(env_id,  con_ssh=None):
    """

    Args:
        env_id:
        con_ssh:

    Returns:

    """
    return get_environment_list_table(header="Status", env_id=env_id,
                                      con_ssh=con_ssh).pop()


def wait_for_environment_status(env_id, status, timeout=180, check_interval=6,
                                fail_ok=False):
    """
     Waits for the  Murano environment deployment status

     Args:
         env_id:
         status:
         timeout:
         check_interval
         fail_ok:

     Returns:

     """
    end_time = time.time() + timeout
    if not status:
        raise ValueError("Expected deployment state(s) has to be specified "
                         "via keyword argument states")
    if isinstance(status, str):
        status = [status]

    status_match = False
    act_status, prev_status = None, None
    while time.time() < end_time:
        act_status = get_environment_status(env_id)
        if act_status != prev_status:
            LOG.info("Current Murano environment deploy status = "
                     "{}".format(act_status))
            prev_status = act_status

        if act_status in status:
            status_match = True
            break
        time.sleep(check_interval)
    msg = "Environment id {} did not reach {} status  within specified " \
          "time ".format(env_id, status)
    if status_match:
        return True, act_status
    else:
        LOG.warning(msg)
        if fail_ok:
            return False, act_status
        else:
            raise exceptions.MuranoError(msg)


def wait_for_environment_delete(env_id, timeout=300, check_interval=6,
                                fail_ok=False):
    """
     Waits for the  Murano environment delete completes

     Args:
         env_id:
         timeout:
         check_interval
         fail_ok

     Returns:

     """
    end_time = time.time() + timeout
    if not env_id:
        raise ValueError("Environment id  has to be specified ")

    status_match = False
    while time.time() < end_time:
        ids = get_environment_list_table()
        if env_id not in ids:
            status_match = True
            break
        time.sleep(check_interval)
    msg = "Fail to delete environment {}  within the specified time ".format(
        env_id)
    if status_match:
        return True, None
    else:
        if fail_ok:
            LOG.warning(msg)
            return False, msg
        else:
            raise exceptions.MuranoError(msg)


def get_environment_list_table(header='ID', env_id=None, name=None,
                               status=None, created=None, updated=None,
                               auth_info=Tenant.get('admin'), con_ssh=None,
                               strict=True, regex=None, **kwargs):
    """
    Get enviroment_list through murano command
    Args:
        header: 'ID' (default value)
        env_id:
        name:
        status:
        created:
        updated:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(
        cli.openstack('environment list --all-tenants', ssh_client=con_ssh,
                      auth_info=auth_info)[1])
    args_temp = {
        'ID': env_id,
        'Name': name,
        'Status': status,
        'Created': created,
        'Updated': updated
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex,
                                   **kwargs)


def edit_environment_object_mode(env_id, session_id=None,
                                 object_model_file=None,
                                 delete_file_after=False, con_ssh=None,
                                 auth_info=None, fail_ok=False):
    """
    Edits environment's object model. The object_model_file must be in format:
    [ { "op": "add", "path": "/-",
    "value": { ... your-app object model here ... } }, { "op": "replace",
    "path": "/0/?/name", "value": "new_name" }, ]

    Args:
        env_id:
        session_id:
        object_model_file (str):
        delete_file_after:
        con_ssh:
        auth_info:
        fail_ok:

    Returns:

    """

    if env_id is None:
        raise ValueError("Environment ID has to be specified.")
    if object_model_file is None:
        raise ValueError("The object_model_file  has to be specified.")
    if session_id is None:
        raise ValueError("The session_id  has to be specified.")

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    filename = 'object_model_patch.json'
    con_ssh.exec_cmd('cat >{} <<EOL\n{}\nEOL'.format(
        filename, object_model_file))

    rc = con_ssh.exec_cmd("test -f " + HostLinuxUser.get_home() + filename)[0]
    if rc != 0:
        msg = "Fail to save the object model file {}".format(
            HostLinuxUser.get_home() + filename)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.MuranoError(msg)

    code, output = cli.openstack('environment apps edit',
                                 '--session-id {} {} {}'.format(
                                     session_id, env_id, filename),
                                 ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info)
    if code > 0:
        return 1, output

    code, output = cli.openstack('environment show',
                                 '--session-id {} --only-apps {}'.format(
                                     session_id, env_id),
                                 ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info)
    if code > 0:
        msg = "Fail to display environment's object model; ID = {}; " \
              "session id = {}: {}"\
            .format(env_id, session_id, output)
        LOG.warning(msg)
        return 2, msg

    if delete_file_after:
        con_ssh.exec_cmd("rm -f " + HostLinuxUser.get_home() + filename)

    return code, output
