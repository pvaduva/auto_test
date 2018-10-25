import time

from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import system_helper, host_helper, network_helper, common
from utils import cli, table_parser, exceptions
from consts.proj_vars import ProjVar
from consts.filepaths import MuranoPath, WRSROOT_HOME
from utils.clients.ssh import ControllerClient


def enable_disable_murano(enable=True, enable_disable_murano_agent=False, fail_ok=False,
                          con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Enable/Disable Murano service and murano agent on the system
    Args:
        enable: True/False, True for enable, false for disable
        enable_disable_murano_agent: Ture/False, true for the same action as enable above
        fail_ok: whether return False or raise exception when some services fail to reach enabled-active state
        con_ssh (SSHClient):
        auth_info (dict)

    Returns:
        code, msg: return code and msg

        """

    # enable Murano

    if enable:
        msg = "Enabled Murano Service Successfully"
        ret, out = system_helper.enable_murano(con_ssh=con_ssh, auth_info=auth_info)

        if ret == 1:
            return 1, out

        if enable_disable_murano_agent:
            ret, out = system_helper.create_service_parameter(service="murano",section="engine",
                                                              name="disable_murano_agent",
                                                              value="false",modify_existing=True)
            if ret != 0:
                return 1, out
    else:
        msg = "Disabled Murano Service Successfully"
        ret, out = system_helper.disable_murano(con_ssh=con_ssh, auth_info=auth_info)

        if ret == 1:
            return 1, out

        if enable_disable_murano_agent:
            ret, out = system_helper.create_service_parameter(service="murano",section="engine",
                                                              name="disable_murano_agent",
                                                              value="true",modify_existing=True)
            if ret != 0:
                return 1, out

    if ret == 0 and host_helper.get_hostshow_value('controller-0','config_status') == 'Config out-of-date':
            # need to lock/unlock standby and swact lock/unlock
        ret, out = host_helper.lock_unlock_controllers(alarm_ok=True)
        if ret == 1:
            return 1, out

    else:
        msg = "Failed to enable/disable Murano service"

    return 0, msg


def enable_disable_murano_agent(enable=True, con_ssh=None, auth_info=Tenant.ADMIN, fail_ok=False):
    """
    Enable/Disable Murano service and murano agent on the system
    Args:
        enable: True/False, True for enable, false for disable
        enable_disable_murano_agent: Ture/False, true for the same action as enable above
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    # enable Murano
    msg = "Enabled Murano Service Successfully"
    if enable:
        ret, out = system_helper.create_service_parameter(service="murano", section="engine",
                                                          name="disable_murano_agent",
                                                          value="false", modify_existing=True)

    else:
        ret, out = system_helper.create_service_parameter(service="murano", section="engine",
                                                          name="disable_murano_agent",
                                                          value="true", modify_existing=True)

    if ret != 0:
        return 1, out

    if host_helper.get_hostshow_value('controller-0', 'config_status') == 'Config out-of-date':
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
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if pkg is None:
        raise ValueError("Package name has to be specified.")

    LOG.info("Importing Murano package {}".format(pkg))
    code, output = cli.murano('package-import --exists-action u', pkg, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code != 0:
        msg = "Fail to import package {}:{}".format(pkg, output)
        if fail_ok:
            LOG.warn(msg)
            return 1, output
        else:
            raise exceptions.MuranoError(msg)

    table_ = table_parser.table(output)
    pkg_id = table_parser.get_values(table_, 'ID')
    return 0, pkg_id


def import_bundle(bundle, is_public=False, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Import Murano bundle
    Args:
        bundle: name of the bundle (full path)
        is_public: flag to set
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if bundle is None:
        raise ValueError("Murano bundle name has to be specified.")

    LOG.info("Importing Murano bundle {}".format(bundle))
    code, output = cli.murano('bundle-import', bundle, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    pkg_id = table_parser.get_value_two_col_table(table_, 'id')
    return 0, pkg_id


def get_package_list(header='ID', pkgid=None, name=None, fqn=None, author=None, active=None, is_public=None,
                           type=None, version=None, auth_info=Tenant.get('admin'), con_ssh=None, strict=True,
                           regex=None, **kwargs):
    """

    Args:
        header:
        name:
        fqn:
        author:
        active:
        is_public:
        type:
        version:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns: list

    """

    table_ = table_parser.table(cli.murano('package-list',
                                           ssh_client=con_ssh,
                                           auth_info=auth_info))
    args_temp = {
        'ID': pkgid,
        'Name': name,
        'FQN': fqn,
        'Author': author,
        'Active': active,
        'Is Public': is_public,
        'Type': type,
        'Version': version
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def delete_bundle(bundle_id, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Delete murano bundle
    Args:
        bundle_id: Bundle id to delete
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if bundle_id is None:
        raise ValueError("Murano bundle id has to be specified.")

    LOG.info("Deleting Murano bundle {}".format(bundle_id))
    code, output = cli.murano('bundle-delete', bundle_id, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code == 1:
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
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if package_id is None:
        raise ValueError("Murano package name has to be specified.")

    LOG.info("Deleting Murano bundle {}".format(package_id))
    code, output = cli.murano('package-delete', package_id, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code != 0:
        msg = "Fail to delete murano package {}:{}".format(package_id, output)
        if fail_ok:
            LOG.warn(msg)
            return 1, output
        else:
            raise exceptions.MuranoError(msg)

    return 0, "package {} deleted successfully".format(package_id)


def create_env(name, mgmt_net_id=None, mgmt_subnet_id=None, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Create Murano Environment
    Args:
        name: Name of the env to create
        mgmt_subnet_id (str): The ID of tenant1 management subnet
        mgmt_net_id (str): The ID of tenant1 management net
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if name is None:
        raise ValueError("Murano environment name has to be specified.")

    LOG.info("Creating Murano Environment {}".format(name))
    cmd = "environment-create"

    if mgmt_subnet_id:
        cmd = cmd + " --join-subnet-id {}".format(mgmt_subnet_id)
    elif mgmt_net_id:
        cmd = cmd + " --join-net-id {}".format(mgmt_net_id)

    code, output = cli.murano(cmd, name, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)
    if code == 1:
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


def create_session (env_id, con_ssh=None, auth_info=None, fail_ok=False):
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
    code, output = cli.murano('environment-session-create', env_id, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    session_id = table_parser.get_value_two_col_table(table_, 'id')
    if session_id != '':
        msg = "Session succesfully created session {}".format(session_id)
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

    code, output = cli.murano('environment-deploy {} --session-id {}'.format(env_id, session_id), rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    deploy_id = table_parser.get_value_two_col_table(table_, 'id')
    if not deploy_id:
        msg = "Fail to get the deploy id; session-id {}; environment id {}".format(session_id, env_id)
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
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active 12state

    Returns:
        code, msg: return code and msg

        """

    if env_id is None:
        raise ValueError("Murano env id has to be specified.")

    LOG.info("Deleting Murano Environment {}".format(env_id))
    code, output = cli.murano('environment-delete', env_id, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code != 0:
        msg = "Failure to delete environment id {}: {}".format(env_id, output)
        if fail_ok:
            LOG.warn(msg)
            return 1, output
        else:
            raise exceptions.MuranoError(msg)

    return 0, "Env {} Deleted Successfully".format(env_id)


def import_package_from_repo(pkg, repo, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Import Murano package from repo
    Args:
        pkg: package name to import (full path)
        repo: repo url
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if repo is None:
        raise ValueError("Repo URL has to be specified.")
    elif pkg is None:
        raise ValueError("Package name has to be specified.")

    args = ""
    args += "--murano-repo=" + repo
    args += " package-import " + pkg

    LOG.info("Importing Murano package {}".format(pkg))
    code, output = cli.murano(args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    pkg_id = table_parser.get_values(table_, 'ID')
    return 0, pkg_id


def get_environment_status(env_id,  con_ssh=None ):
    """

    Args:
        env_id:
        con_ssh:

    Returns:

    """
    return (get_environment_list_table(header="Status", env_id=env_id)).pop()


def wait_for_environment_status(env_id, status, timeout=180, check_interval=6, fail_ok=False):
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
        raise ValueError("Expected deployment state(s) has to be specified via keyword argument states")
    if isinstance(status, str):
        status = [status]

    status_match = False
    act_status, prev_status = None, None
    while time.time() < end_time:
        act_status = get_environment_status(env_id)
        if act_status != prev_status:
            LOG.info("Current Murano environment deploy status = {}".format(act_status))
            prev_status = act_status

        if act_status in status:
            status_match = True
            break
        time.sleep(check_interval)
    msg = "Environment id {} did not reach {} status  within specified time ".format(env_id,status)
    if status_match:
        return True, act_status
    else:
        LOG.warning(msg)
        if fail_ok:
            return False, act_status
        else:
            raise exceptions.MuranoError(msg)


def wait_for_environment_delete(env_id, timeout=300, check_interval=6, fail_ok=False):
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
    act_status, prev_status = None, None
    while time.time() < end_time:
        ids = get_environment_list_table()
        if env_id not in ids:
            status_match = True
            break
        time.sleep(check_interval)
    msg = "Fail to delete environment {}  within the specified time ".format(env_id)
    if status_match:
        return True, None
    else:
        if fail_ok:
            LOG.warning(msg)
            return False, msg
        else:
            raise exceptions.MuranoError(msg)



def get_environment_list_table(header='ID', env_id=None, Name=None, Status=None, Created=None, Updated=None,
                           auth_info=Tenant.get('admin'), con_ssh=None, strict=True, regex=None, **kwargs):
    """
    Get enviroment_list through murano command
    Args:
        header: 'ID' (default value)
        enviroment_id:
        Name:
        Status:
        Created:
        Updated:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.murano('environment-list --all-tenants',
                                           ssh_client=con_ssh,
                                           auth_info=auth_info))
    args_temp = {
        'ID': env_id,
        'Name': Name,
        'Status': Status,
        'Created': Created,
        'Updated': Updated
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def edit_environment_object_mode(env_id, session_id=None, object_model_file=None, delete_file_after=False, con_ssh=None,
                                 auth_info=None, fail_ok=False):
    """
    Edits environment's object model. The object_model_file must be in format:
    [ { "op": "add", "path": "/-", "value": { ... your-app object model here ... } }, { "op": "replace",
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
    con_ssh.exec_cmd('cat >{} <<EOL\n{}\nEOL'.format(filename, object_model_file))

    rc = con_ssh.exec_cmd("test -f " + WRSROOT_HOME + filename)[0]
    if rc != 0:
        msg = "Fail to save the object model file {}".format(WRSROOT_HOME + filename)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.MuranoError(msg)

    cli.murano('environment-apps-edit --session-id {} {} {}'.format(session_id, env_id, filename))

    code, output = cli.murano('environment-show {} --session-id {} --only-apps'.format(env_id, session_id),
                              rtn_list=True)
    if code != 0:
        msg = "Fail to display environment's object model; ID = {}; session id = {}: {}"\
            .format(env_id, session_id,output)
        if fail_ok:
            return 2, msg
        else:
            raise exceptions.MuranoError(msg)
    if delete_file_after:
        con_ssh.exec_cmd("rm -f " + WRSROOT_HOME + filename)

    return code, output
