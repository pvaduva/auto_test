from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import system_helper, host_helper, glance_helper, common
from utils import cli, table_parser
from consts.proj_vars import ProjVar
from consts import build_server
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


def get_application(con_ssh=None, auth_info=None, fail_ok=False):

    common.scp_from_test_server_to_active_controller('/folk/cgts/users/jsun3/com.wrs.titanium.murano.examples.demo.zip', '/home/wrsroot/')

    con_ssh = ControllerClient.get_active_controller()
    # con_ssh.exec_cmd('source ./openrc.tenant1')

    output = cli.neutron('subnet-list')
    print (output)
    # if code != 0:
    #     return 1, output
    table_ = table_parser.table(output)
    mgmt_id = table_parser._get_values(table_, 'name', 'tenant1-mgmt0-subnet0', 'id')

    return mgmt_id


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


def create_env(name, mgmt_id, con_ssh=None, auth_info=None, fail_ok=False):
    """
    Create Murano Environment
    Args:
        name: Name of the env to create
        mgmt_id (str): The ID of tenant1 management subnet
        con_ssh (SSHClient):
        auth_info (dict)
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state

    Returns:
        code, msg: return code and msg

        """

    if name is None:
        raise ValueError("Murano environment name has to be specified.")

    LOG.info("Creating Murano Environment {}".format(name))
    code, output = cli.murano('environment-create --join-subnet-id {}'.format(mgmt_id), name, ssh_client=con_ssh, auth_info=auth_info,
                              fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    env_id = table_parser.get_values(table_, 'ID')

    return 0, env_id

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
    msg = "Session succesfully created session {}".format(session_id)
    return 0, msg


def add_app_to_env(env_id, session_id, image_id, con_ssh=None, auth_info=None, fail_ok=False):
    if env_id is None:
        env_id = create_env('test_env')

    if session_id is None:
        session_id = create_session(env_id)

    common.scp_from_test_server_to_active_controller('/folk/cgts/users/jsun3/com.wrs.titanium.murano.examples.demo.zip', 'home/wrsroot/')

    file = ('\n'
            '[\n'
            '    { "op": "add", "path": "/-", "value":\n'
            '        {\n'
            '            "instance": {\n'
            '                "availabilityZone": "nova",\n'
            '                "name": "xwvupifdxq27t1",\n'
            '                "image": "{}",\n'
            '                "keyname": "",\n'
            '                "flavor": "medium.dpdk",\n'
            '                "assignFloatingIp": false,\n'
            '                "?": {\n'
            '                    "type": "io.murano.resources.LinuxMuranoInstance",\n'
            '                    "id": "===id1==="\n'
            '                }\n'
            '            },\n'
            '            "name": "Titanium Murano Demo App",\n'
            '            "enablePHP": true,\n'
            '            "?": {\n'
            '                "type": "com.wrs.titanium.murano.examples.demo",\n'
            '                "id": "===id2==="\n'
            '            }\n'
            '        }\n'
            '    }\n'
            ']').format(image_id)

    con_ssh = ControllerClient.get_active_controller()
    filename = 'object_model_patch.json'
    con_ssh.exec_cmd('cat {} > {}'.format(filename, file))
    cli.murano('environment-apps-edit --session-id {} {} {}'.format(session_id, env_id, filename))

    code, output = cli.murano('environment-show {} --session-id {} --only-apps'.format(env_id, session_id))

    return code, output


def deploy_env(env_id, session_id, con_ssh=None, auth_info=None, fail_ok=False):

    code, output = cli.murano('environment-deploy {} --session-id {}'.format(env_id, session_id))

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    deploy_id = table_parser.get_values(table_, 'ID')

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
