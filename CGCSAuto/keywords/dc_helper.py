#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import time
import copy

from utils import cli, exceptions, table_parser
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.auth import Tenant, HostLinuxUser
from consts.proj_vars import ProjVar
from consts.timeout import DCTimeout
from consts.filepaths import SysLogPath
from keywords import system_helper, nova_helper


def get_subclouds(field='name', name=None, avail=None, sync=None, mgmt=None, deploy=None,
                  auth_info=Tenant.get('admin_platform', 'RegionOne'), con_ssh=None, source_openrc=None):
    """
    Getting subclouds info
    Args:
        field:
        name:
        avail:
        sync:
        mgmt:
        auth_info:
        con_ssh:
        source_openrc:

    Returns:

    """

    # auth_info = Tenant.get('admin', 'SystemController')
    LOG.info("Auth_info: {}".format(auth_info))
    table_ = table_parser.table(
        cli.dcmanager('subcloud list', ssh_client=con_ssh, auth_info=auth_info, source_openrc=source_openrc)[1])
    arg_dict = {'name': name, 'availability': avail, 'sync': sync, 'management': mgmt, 'deploy status': deploy}
    kwargs = {key: val for key, val in arg_dict.items() if val is not None}
    subclouds = table_parser.get_values(table_, target_header=field, **kwargs)

    # Filter out the Subclouds that are not in the lab.py file
    filtered_subclouds = [_cloud for _cloud in subclouds if _cloud in ProjVar.get_var('LAB')]

    return filtered_subclouds


def get_subcloud_status(subcloud, field='availability', auth_info=Tenant.get('admin_platform', 'RegionOne'), con_ssh=None,
                        source_openrc=None):
    """

    Args:
        subcloud:
        field:
        auth_info:
        con_ssh:
        source_openrc:

    Returns:

    """

    LOG.info("Auth_info: {}".format(auth_info))
    table_ = table_parser.table(
        cli.dcmanager('subcloud list', ssh_client=con_ssh, auth_info=auth_info, source_openrc=source_openrc)[1])
    arg_dict = {'name': subcloud}
    kwargs = {key: val for key, val in arg_dict.items() if val is not None}
    status = table_parser.get_values(table_, target_header=field, **kwargs)
    return status[0]


def _manage_unmanage_subcloud(subcloud=None, manage=False, check_first=True, fail_ok=False, con_ssh=None,
                              auth_info=Tenant.get('admin_platform', 'RegionOne'), source_openrc=False):

    """
    Manage/Unmanage given subcloud(s)
    Args:
        subcloud:
        manage:
        check_first:
        fail_ok:

    Returns:

    """
    operation = 'manage' if manage else 'unmanage'
    expt_state = '{}d'.format(operation)
    if not subcloud:
        subcloud = [ProjVar.get_var('PRIMARY_SUBCLOUD')]
    elif isinstance(subcloud, str):
        subcloud = [subcloud]

    subclouds_to_update = list(subcloud)
    if check_first:
        subclouds_in_state = get_subclouds(mgmt=expt_state, con_ssh=con_ssh, auth_info=auth_info)
        subclouds_to_update = list(set(subclouds_to_update) - set(subclouds_in_state))
        if not subclouds_to_update:
            LOG.info("{} already {}. Do nothing.".format(subcloud, expt_state))
            return -1, []

    LOG.info("Attempt to {}: {}".format(operation, subclouds_to_update))
    failed_subclouds = []
    for subcloud_ in subclouds_to_update:
        code, out = cli.dcmanager('subcloud ' + operation, subcloud_, ssh_client=con_ssh, fail_ok=True,
                                  auth_info=auth_info, source_openrc=source_openrc)

        if code > 0:
            failed_subclouds.append(subcloud_)

    if failed_subclouds:
        err = "Failed to {} {}".format(operation, failed_subclouds)
        if fail_ok:
            LOG.info(err)
            return 1, failed_subclouds
        raise exceptions.DCError(err)

    LOG.info("Check management status for {} after dcmanager subcloud {}".format(subclouds_to_update, operation))
    mgmt_states = get_subclouds(field='management', name=subclouds_to_update, auth_info=auth_info, con_ssh=con_ssh)
    failed_subclouds = [subclouds_to_update[i] for i in range(len(mgmt_states)) if mgmt_states[i] != expt_state]
    if failed_subclouds:
        raise exceptions.DCError("{} not {} after dcmanger subcloud {}".format(failed_subclouds, expt_state, operation))

    return 0, subclouds_to_update


def manage_subcloud(subcloud=None, check_first=True, fail_ok=False, con_ssh=None):
    """
    Manage subcloud(s)
    Args:
        subcloud (str|tuple|list):
        check_first (bool):
        fail_ok (bool):
        con_ssh(SSClient):

    Returns (tuple):
        (-1, [])                            All give subcloud(s) already managed. Do nothing.
        (0, [<updated subclouds>])          Successfully managed the give subcloud(s)
        (1, [<cli_rejected_subclouds>])     dcmanager manage cli failed on these subcloud(s)

    """
    return _manage_unmanage_subcloud(subcloud=subcloud, manage=True, check_first=check_first, fail_ok=fail_ok,
                                     con_ssh=con_ssh)


def unmanage_subcloud(subcloud=None, check_first=True, fail_ok=False, con_ssh=None):
    """
    Unmanage subcloud(s)
    Args:
        subcloud (str|tuple|list):
        check_first (bool):
        fail_ok (bool):
        con_ssh (SSHClient):

    Returns (tuple):
        (-1, [])                        All give subcloud(s) already unmanaged. Do nothing.
        (0, [<updated subclouds>])      Successfully unmanaged the give subcloud(s)
        (1, [<cli_rejected_subclouds>])     dcmanager unmanage cli failed on these subcloud(s)

    """
    return _manage_unmanage_subcloud(subcloud=subcloud, manage=False, check_first=check_first, fail_ok=fail_ok,
                                     con_ssh=con_ssh)


def wait_for_subcloud_config(func, *func_args, subcloud=None, config_name=None, expected_value=None,
                             auth_name='admin_platform', fail_ok=False, timeout=DCTimeout.SYNC,
                             check_interval=30, strict_order=True, **func_kwargs):
    """
    Wait for subcloud configuration to reach expected value
    Args:
        subcloud (str|None):
        func: function defined to get current value, which has to has parameter con_ssh and auth_info
        *func_args: positional args for above func. Should NOT include auth_info or con_ssh.
        config_name (str): such as dns, keypair, etc
        expected_value (None|str|list):
        auth_name (str): auth dict name. e.g., admin_platform, admin, tenant1, TENANT2, etc
        fail_ok (bool):
        timeout (int):
        check_interval (int):
        strict_order (bool)
        **func_kwargs: kwargs for defined func. auth_info and con_ssh has to be provided here

    Returns (tuple):
        (0, <subcloud_config>)     # same as expected
        (1, <subcloud_config>)     # did not update within timeout
        (2, <subcloud_config>)     # updated to unexpected value

    """
    if not subcloud:
        subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')

    config_name = ' ' + config_name if config_name else ''

    if expected_value is None:
        central_ssh = ControllerClient.get_active_controller(name='RegionOne')
        expected_value = func(con_ssh=central_ssh, auth_info=Tenant.get(auth_name, dc_region='RegionOne'))
    elif isinstance(expected_value, str):
        expected_value = expected_value.split(sep=',')

    if not strict_order:
        expected_value = sorted(list(expected_value))

    LOG.info("Wait for {}{} to be {}".format(subcloud, config_name, expected_value))
    if not func_kwargs.get('con_ssh', None):
        func_kwargs['con_ssh'] = ControllerClient.get_active_controller(name=subcloud)
    if not func_kwargs.get('auth_info', None):
        func_kwargs['auth_info'] = Tenant.get(auth_name, dc_region=subcloud)

    origin_subcloud_val = func(*func_args, **func_kwargs)
    subcloud_val = copy.copy(origin_subcloud_val)
    if isinstance(subcloud_val, str):
        subcloud_val = subcloud_val.split(sep=',')

    if not strict_order:
        subcloud_val = sorted(list(subcloud_val))

    end_time = time.time() + timeout + check_interval
    while time.time() < end_time:
        if subcloud_val == expected_value:
            LOG.info("{}{} setting is same as central region".format(subcloud, config_name))
            return 0, subcloud_val

        elif subcloud_val != origin_subcloud_val:
            msg = '{}{} config changed to unexpected value. Expected: {}; Actual: {}'.\
                format(subcloud, config_name, expected_value, subcloud_val)

            if fail_ok:
                LOG.info(msg)
                return 2, subcloud_val
            else:
                raise exceptions.DCError(msg)

        time.sleep(check_interval)
        subcloud_val = func(*func_args, **func_kwargs)

    msg = '{}{} config did not reach: {} within {} seconds; actual: {}'.format(subcloud, config_name, expected_value,
                                                                               timeout, subcloud_val)
    if fail_ok:
        LOG.info(msg)
        return 1, subcloud_val
    else:
        raise exceptions.DCError(msg)


def wait_for_sync_audit(subclouds, con_ssh=None, fail_ok=False, filters_regex=None, timeout=DCTimeout.SYNC):
    """
    Wait for Updating subcloud log msg in dcmanager.log for given subcloud(s)
    Args:
        subclouds (list|tuple|str):
        con_ssh:
        fail_ok:
        filters_regex: e.g., ['audit_action.*keypair', 'Clean audit.*ntp'], '\/compute'
        timeout:

    Returns (tuple):
        (True, <res_dict>)
        (False, <res_dict>)

    """
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller('RegionOne')

    if isinstance(subclouds, str):
        subclouds = [subclouds]

    LOG.info("Waiting for sync audit in dcmanager.log for: {}".format(subclouds))
    if not filters_regex:
        filters_regex = ['platform', 'patching', 'identity']
    elif isinstance(filters_regex, str):
        filters_regex = [filters_regex]

    subclouds_dict = {subcloud: list(filters_regex) for subcloud in subclouds}
    res = {subcloud: False for subcloud in subclouds}
    subclouds_to_wait = list(subclouds)
    end_time = time.time() + timeout

    expt_list = []
    for subcloud in subclouds_dict:
        expt_list += ['{}.*{}'.format(subcloud, service) for service in subclouds_dict[subcloud]]

    con_ssh.send('tail -n 0 -f {}'.format(SysLogPath.DC_ORCH))

    try:
        while time.time() < end_time:
            index = con_ssh.expect(expt_list, timeout=timeout, fail_ok=True)
            if index >= 0:
                subcloud_, service_ = expt_list[index].split('.*', maxsplit=1)
                subclouds_dict[subcloud_].remove(service_)
                expt_list.pop(index)
                if not subclouds_dict[subcloud_]:
                    subclouds_to_wait.remove(subcloud_)
                    subclouds_dict.pop(subcloud_)
                    res[subcloud_] = True
                if not subclouds_to_wait:
                    LOG.info("sync request logged for: {}".format(subclouds))
                    return True, res
            else:
                msg = 'sync audit for {} not shown in {} in {}s: {}'.format(subclouds_to_wait, SysLogPath.DC_ORCH,
                                                                            timeout, subclouds_dict)
                if fail_ok:
                    LOG.info(msg)
                    for subcloud in subclouds_to_wait:
                        res[subcloud] = False
                    return False, res
                else:
                    raise exceptions.DCError(msg)

    finally:
        con_ssh.send_control()
        con_ssh.expect()


def wait_for_subcloud_or_patch_audit(patch_audit=False, timeout=DCTimeout.SUBCLOUD_AUDIT, con_ssh=None):
    """
    Wait for next subcloud/patch audit to be triggered. Raise if not.
    subcloud online/offline or patch status should then be updated after audit.
    Args:
        patch_audit (bool): Wait for patch or subcloud audit
        timeout (int):
        con_ssh (SSHClient): central region ssh

    Returns (None):

    """
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller('RegionOne')

    con_ssh.send('tail -n 0 -f {}'.format(SysLogPath.DC_MANAGER))
    try:
        con_ssh.expect('Triggered {} audit'.format('patch' if patch_audit else 'subcloud'), timeout=timeout)
    finally:
        con_ssh.send_control()
        con_ssh.expect()


def wait_for_subcloud_dns_config(subcloud=None, subcloud_ssh=None, expected_dns=None, fail_ok=False,
                                 timeout=DCTimeout.SYNC, check_interval=30):
    """
    Wait for dns configuration to reach expected value
    Args:
        subcloud (str|None):
        subcloud_ssh (None|SSHClient):
        expected_dns (None|str|list):
        fail_ok (bool):
        timeout (int):
        check_interval (int):

    Returns (tuple):
        (0, <subcloud_dns_servers>)     # same as expected
        (1, <subcloud_dns_servers>)     # did not update within timeout
        (2, <subcloud_dns_servers>)     # updated to unexpected value

    """
    func = system_helper.get_dns_servers
    func_kwargs = {'con_ssh': subcloud_ssh} if subcloud_ssh else {}
    return wait_for_subcloud_config(subcloud=subcloud, func=func, config_name='DNS', expected_value=expected_dns,
                                    fail_ok=fail_ok, timeout=timeout, check_interval=check_interval, **func_kwargs)


def wait_for_subcloud_snmp_comms(subcloud=None, subcloud_ssh=None, expected_comms=None, fail_ok=False,
                                 timeout=DCTimeout.SYNC, check_interval=30):
    """
    Wait for dns configuration to reach expected value
    Args:
        subcloud (str|None):
        subcloud_ssh (None|SSHClient):
        expected_comms (None|str|list):
        fail_ok (bool):
        timeout (int):
        check_interval (int):

    Returns (tuple):
        (0, <subcloud_dns_servers>)     # same as expected
        (1, <subcloud_dns_servers>)     # did not update within timeout
        (2, <subcloud_dns_servers>)     # updated to unexpected value

    """
    func = system_helper.get_snmp_comms
    func_kwargs = {'con_ssh': subcloud_ssh} if subcloud_ssh else {}
    return wait_for_subcloud_config(subcloud=subcloud, func=func, config_name='SNMP Community strings',
                                    expected_value=expected_comms, fail_ok=fail_ok, timeout=timeout,
                                    check_interval=check_interval, strict_order=False, **func_kwargs)


def wait_for_subcloud_snmp_trapdests(subcloud=None, subcloud_ssh=None, expected_trapdests=None, fail_ok=False,
                                     timeout=DCTimeout.SYNC, check_interval=30):
    """
    Wait for dns configuration to reach expected value
    Args:
        subcloud (str|None):
        subcloud_ssh (None|SSHClient):
        expected_trapdests (None|str|list):
        fail_ok (bool):
        timeout (int):
        check_interval (int):

    Returns (tuple):
        (0, <subcloud_dns_servers>)     # same as expected
        (1, <subcloud_dns_servers>)     # did not update within timeout
        (2, <subcloud_dns_servers>)     # updated to unexpected value

    """
    func = system_helper.get_snmp_trapdests
    func_kwargs = {'con_ssh': subcloud_ssh} if subcloud_ssh else {}
    return wait_for_subcloud_config(subcloud=subcloud, func=func, config_name='SNMP Community strings',
                                    expected_value=expected_trapdests, fail_ok=fail_ok, timeout=timeout,
                                    check_interval=check_interval, strict_order=False, **func_kwargs)


def wait_for_subcloud_ntp_config(subcloud=None, subcloud_ssh=None, expected_ntp=None, clear_alarm=True, fail_ok=False,
                                 timeout=DCTimeout.SYNC, check_interval=30):
    """
    Wait for ntp configuration to reach expected value
    Args:
        subcloud (str|None):
        subcloud_ssh (None|SSHClient):
        expected_ntp (None|str|list):
        clear_alarm (bool)
        fail_ok (bool):
        timeout (int):
        check_interval (int):

    Returns (tuple):
        (0, <subcloud_ntp_servers>)     # same as expected
        (1, <subcloud_ntp_servers>)     # did not update within timeout
        (2, <subcloud_ntp_servers>)     # updated to unexpected value

    """
    if not subcloud:
        subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
    func_kwargs = {'auth_info': Tenant.get('admin_platform', subcloud)}
    if subcloud_ssh:
        func_kwargs['con_ssh'] = subcloud_ssh

    func = system_helper.get_ntp_servers
    res = wait_for_subcloud_config(subcloud=subcloud, func=func, config_name='NTP', expected_value=expected_ntp,
                                   fail_ok=fail_ok, timeout=timeout, check_interval=check_interval, **func_kwargs)

    if res[0] in (0, 2) and clear_alarm:
        system_helper.wait_and_clear_config_out_of_date_alarms(host_type='controller', **func_kwargs)

    return res


def wait_for_subcloud_status(subcloud, avail=None, sync=None, mgmt=None, deploy=None, timeout=DCTimeout.SUBCLOUD_AUDIT,
                             check_interval=30, auth_info=Tenant.get('admin_platform', 'RegionOne'), con_ssh=None,
                             source_openrc=None, fail_ok=False):
    """
    Wait for subcloud status
    Args:
        subcloud:
        avail:
        sync:
        mgmt:
        timeout:
        check_interval:
        auth_info:
        con_ssh:
        source_openrc:
        fail_ok:

    Returns:

    """

    if not subcloud:
        raise ValueError("Subcloud name must be specified")

    expt_status = {}
    if avail:
        expt_status['avail'] = avail
    if sync:
        expt_status['sync'] = sync
    if mgmt:
        expt_status['mgmt'] = mgmt
    if deploy:
        expt_status['deploy'] = deploy

    if not expt_status:
        raise ValueError("At least one  expected status of the subcloud must be specified.")

    LOG.info("Wait for {} status: {}".format(subcloud, expt_status))
    end_time = time.time() + timeout + check_interval
    while time.time() < end_time:
        if get_subclouds(field='name', name=subcloud, con_ssh=con_ssh, source_openrc=source_openrc,
                         auth_info=auth_info, **expt_status):
            return 0, subcloud
        LOG.info("Not in expected states yet...")
        time.sleep(check_interval)

    msg = '{} status did not reach {} within {} seconds'.format(subcloud, expt_status, timeout)
    LOG.warning(msg)
    if fail_ok:
        return 1, msg
    else:
        raise exceptions.DCError(msg)


def wait_for_subcloud_keypair(subcloud=None, subcloud_ssh=None, expected_keypair=None, fail_ok=False,
                              timeout=DCTimeout.SYNC, check_interval=30):
    """
    Wait for dns configuration to reach expected value
    Args:
        subcloud (str|None):
        subcloud_ssh (None|SSHClient):
        expected_keypair (None|str|list):
        fail_ok (bool):
        timeout (int):
        check_interval (int):

    Returns (tuple):
        (0, <subcloud_dns_servers>)     # same as expected
        (1, <subcloud_dns_servers>)     # did not update within timeout
        (2, <subcloud_dns_servers>)     # updated to unexpected value

    """
    func = nova_helper.get_keypairs
    func_kwargs = {'con_ssh': subcloud_ssh} if subcloud_ssh else {}
    return wait_for_subcloud_config(subcloud=subcloud, func=func, config_name='Name',
                                    expected_value=expected_keypair, fail_ok=fail_ok, timeout=timeout,
                                    check_interval=check_interval, strict_order=False, **func_kwargs)



def add_subcloud(subcloud, subcloud_controller_node, system_controller_node, bootstrap_values_path,
                 deploy_play_book_path, deploy_values_path,  fail_ok=False,
                 auth_info=Tenant.get('admin_platform', 'RegionOne'),  source_openrc=None):
    """


    """
    operation = 'add'
    LOG.info("Attempt to {}: {}".format(operation, subcloud))

    if system_controller_node.ssh_conn is None:
        msg = 'No ssh connection to System Controller; Cannot add subcloud {} '.format(subcloud)
        LOG.warning(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.DCError(msg)
    subcloud_add_config_pathes = [bootstrap_values_path, deploy_play_book_path, deploy_values_path]

    if not subcloud_controller_node or not bootstrap_values_path or not deploy_play_book_path or not deploy_values_path:
        msg = "To add a subcloud all values must be specified"
        LOG.warning(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.DCError(msg)

    for file_path in subcloud_add_config_pathes:
        if system_controller_node.ssh_conn.exec_cmd("test -f {}".format(file_path))[0] != 0:
            msg = "Subcloud {} is missing config file {} ".format(subcloud, file_path)
            LOG.warning(msg)
            if fail_ok:
                return 1, msg
            else:
                raise exceptions.DCError(msg)

    args_dict = {
        '--bootstrap-address': subcloud_controller_node.host_ip,
        '--bootstrap-values': bootstrap_values_path,
        '--deploy-playbook': deploy_play_book_path,
        '--deploy-values': deploy_values_path,
        '--sysadmin-password': HostLinuxUser.get_password()
    }

    opt_args = ''
    for key, val in args_dict.items():
        if val is not None:
            opt_args += '{} {} '.format(key, val)

    rc, output = cli.dcmanager('subcloud ' + operation, opt_args, ssh_client=system_controller_node.ssh_conn,
                              fail_ok=fail_ok, auth_info=auth_info, source_openrc=source_openrc)

    if rc != 0:
        msg = "Fail to add subcloud {}: {}".format(subcloud, output)
        LOG.warning(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.DCError(msg)

    return rc, output
