from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import system_helper, host_helper
from utils import cli, table_parser


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
        ret, out = host_helper.lock_unlock_controllers()
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

    if host_helper.get_hostshow_value('controller-0','config_status') == 'Config out-of-date':
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
    code, output = cli.murano('package-import', pkg, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

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

    if code == 1:
        return 1, output

    msg = "package deleted successfully"
    return 0, msg


def create_env(name, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Create Murano Environment
    Args:
        name: Name of the env to create
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if name is None:
        raise ValueError("Murano environment name has to be specified.")

    LOG.info("Creating Murano Environment {}".format(name))
    code, output = cli.murano('environment-create', name, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    env_id = table_parser.get_values(table_, 'ID')

    return 0, env_id


def delete_env(env_id, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Delete Murano Environment
    Args:
        env_id: Id of the env to create
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if env_id is None:
        raise ValueError("Murano env id has to be specified.")

    LOG.info("Deleting Murano Environment {}".format(env_id))
    code, output = cli.murano('environment-delete', env_id, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    msg = "Env Deleted Successfully"
    return 0, msg


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