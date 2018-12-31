import time

from utils import cli, exceptions, table_parser
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import AppStatus


def upload_app(app_name, tar_file, check_first=True, fail_ok=False, uploaded_timeout=300, con_ssh=None,
               auth_info=Tenant.get('admin')):
    """

    Args:
        app_name:
        tar_file:
        check_first
        fail_ok:
        uploaded_timeout:
        con_ssh:
        auth_info:

    Returns:

    """
    if check_first and get_apps_values(apps=app_name, con_ssh=con_ssh, auth_info=auth_info)[0]:
        msg = '{} already exists. Do nothing.'.format(app_name)
        LOG.info(msg)
        return -1, msg

    args = '{} {}'.format(app_name, tar_file)
    code, output = cli.system('application-upload', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True)
    if code > 0:
        return 1, output

    res = wait_for_apps_status(apps=app_name, status=AppStatus.UPLOADED, timeout=uploaded_timeout,
                               con_ssh=con_ssh, auth_info=auth_info, fail_ok=fail_ok)[0]
    if not res:
        return 2, "{} failed to upload".format(app_name)

    msg = '{} uploaded successfully'.format(app_name)
    LOG.info(msg)
    return 0, msg


def get_apps_values(apps, rtn_vals=('status',), con_ssh=None, auth_info=Tenant.get('admin'), rtn_dict=False):
    """
    Get applications values for give apps and fields via system application-list
    Args:
        apps:
        rtn_vals (str|list|tuple):
        con_ssh:
        auth_info:
        rtn_dict:

    Returns (list|dict):
        list of list, or
        dict with app name(str) as key and values(list) for given fields for each app as value

    """
    if isinstance(rtn_vals, str):
        rtn_vals = [rtn_vals]
    if isinstance(apps, str):
        apps = [apps]

    table_ = table_parser.table(cli.system('application-list', ssh_client=con_ssh, auth_info=auth_info))
    if not table_['values']:
        return {app:None for app in apps} if rtn_dict else [None]*len(apps)

    table_ = table_parser.row_dict_table(table_, key_header='application', lower_case=False)
    apps_vals = []
    for app in apps:
        vals_dict = table_.get(app, None)
        vals = [vals_dict[header] for header in rtn_vals] if vals_dict else None
        apps_vals.append(vals)

    if rtn_dict:
        apps_vals = {apps[i]: apps_vals[i] for i in range(len(apps))}

    return apps_vals


def get_app_show_values(app_name, fields, con_ssh=None, auth_info=Tenant.get('admin')):
    if isinstance(fields, str):
        fields = [fields]

    table_ = table_parser.table(cli.system('application-show', app_name, ssh_client=con_ssh, auth_info=auth_info),
                                combine_multiline_entry=True)
    values = [table_parser.get_value_two_col_table(table_, field=field) for field in fields]
    return values


def wait_for_apps_status(apps, status, timeout=300, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):

    if isinstance(apps, str):
        apps = [apps]
    apps_to_check = list(apps)
    check_failed = []
    end_time = time.time() + timeout

    while time.time() < end_time:
        apps_status = get_apps_values(apps=apps_to_check, rtn_vals='status', con_ssh=con_ssh, auth_info=auth_info)
        checked = []
        for i in range(len(apps_to_check)):
            app = apps_to_check[i]
            current_app_status = apps_status[i]
            if current_app_status:
                current_app_status = current_app_status[0]
            if current_app_status == status:
                checked.append(app)
            elif (status and current_app_status.endswith('ed')) or \
                    (not status and current_app_status == AppStatus.DELETE_FAILED):
                check_failed.append(app)
                checked.append(app)

        apps_to_check = list(set(apps_to_check) - set(checked))
        if not apps_to_check:
            if check_failed:
                msg = '{} failed to reach status - {}'.format(check_failed, status)
                if fail_ok:
                    LOG.info(msg)
                    return False, check_failed
                else:
                    raise exceptions.ContainerError(msg)

            return True, None

        time.sleep(5)

    check_failed += apps_to_check
    msg = '{} did not reach status {} within {}s'.format(check_failed, status, timeout)
    if fail_ok:
        LOG.info(msg)
        return False, check_failed
    raise exceptions.ContainerError(msg)


def apply_app(app_name, check_first=False, fail_ok=False, applied_timeout=300, con_ssh=None,
              auth_info=Tenant.get('admin')):

    if check_first:
        app_vals = get_apps_values(apps=app_name, con_ssh=con_ssh, auth_info=auth_info)[0]
        if app_vals and app_vals[0] == AppStatus.APPLIED:
            msg = '{} is already applied. Do nothing.'.format(app_name)
            LOG.info(msg)
            return -1, msg

    code, output = cli.system('application-apply', app_name, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True)
    if code > 0:
        return 1, output

    res = wait_for_apps_status(apps=app_name, status=AppStatus.APPLIED, timeout=applied_timeout,
                               con_ssh=con_ssh, auth_info=auth_info, fail_ok=fail_ok)[0]
    if not res:
        return 2, "{} failed to apply".format(app_name)

    msg = '{} (re)applied successfully'.format(app_name)
    LOG.info(msg)
    return 0, msg


def delete_app(app_name, check_first=True, fail_ok=False, applied_timeout=300, con_ssh=None,
               auth_info=Tenant.get('admin')):

    if check_first:
        app_vals = get_apps_values(apps=app_name, con_ssh=con_ssh, auth_info=auth_info)[0]
        if not app_vals:
            msg = '{} does not exist. Do nothing.'.format(app_name)
            LOG.info(msg)
            return -1, msg

    code, output = cli.system('application-delete', app_name, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True)
    if code > 0:
        return 1, output

    res = wait_for_apps_status(apps=app_name, status=None, timeout=applied_timeout,
                               con_ssh=con_ssh, auth_info=auth_info, fail_ok=fail_ok)[0]
    if not res:
        return 2, "{} failed to delete".format(app_name)

    msg = '{} deleted successfully'.format(app_name)
    LOG.info(msg)
    return 0, msg


def remove_app(app_name, check_first=True, fail_ok=False, applied_timeout=300, con_ssh=None,
               auth_info=Tenant.get('admin')):

    if check_first:
        app_vals = get_apps_values(apps=app_name, con_ssh=con_ssh, auth_info=auth_info)[0]
        if not app_vals or app_vals[0] in (AppStatus.UPLOADED, AppStatus.UPLOAD_FAILED):
            msg = '{} is not applied. Do nothing.'.format(app_name)
            LOG.info(msg)
            return -1, msg

    code, output = cli.system('application-remove', app_name, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True)
    if code > 0:
        return 1, output

    res = wait_for_apps_status(apps=app_name, status=AppStatus.UPLOADED, timeout=applied_timeout,
                               con_ssh=con_ssh, auth_info=auth_info, fail_ok=fail_ok)[0]
    if not res:
        return 2, "{} failed to remove".format(app_name)

    msg = '{} removed successfully'.format(app_name)
    LOG.info(msg)
    return 0, msg