import functools
import os
import re
import time
from datetime import datetime

from pytest import skip

from utils import exceptions
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG
from consts.cgcs import PatchState, PatchPattern, EventLogID
from consts.filepaths import WRSROOT_HOME
from consts.proj_vars import ProjVar, PatchingVars
from consts.auth import HostLinuxCreds
from testfixtures.recover_hosts import HostsToRecover
from keywords import host_helper, system_helper, orchestration_helper, common


LOG_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

PATCH_CMDS = {
    'apply': {
        'cmd': 'apply',
        'result_pattern': {
            r'([^ ]+) is now in the repo': 0,
            r'([^ ]+) is already in the repo': 1,
            r'There are no available patches to be applied': 2,
        },
        'error': '',
    },
    'host-install': {
        'cmd': 'host-install',
        'result_pattern': {
            r'Installation was successful.': 0,
            r'Installation rejected. Node must be locked': 1,
        }
    },
    'query': {
        'cmd': 'query',
    },
    'query-hosts': {
        'cmd': 'query-hosts',
    },
    'remove': {
        'cmd': 'remove',
        'result_pattern': {
            r'([^ ]+) has been removed from the repo': 0,
        }
    },
    'upload': {
        'cmd': 'upload',
        'result_pattern': {
            r'([^ ]+) is now available': 0,
            r'([^ ]+) is already imported. Updated metadata only': 1,
            r'Patch ([^ ]+) contains rpm ([^ ]+), which is already provided by patch ([^ ]+)': 2,
            r'RPM ([^ ])+ in ([^ ]+) must be higher version than original.*': 3,
        },
    },
    'requires': {
        'cmd': 'what-requires',
    },
    'delete': {
        'cmd': 'delete',

        'result_pattern': {
            r'([^ ]+) has been deleted': 0,
            },
    },
    'host-install-async': {
        'cmd': 'host-install-async',
    },
    'show': {
        'cmd': 'show',
    },
    'upload-dir': {
        'cmd': 'upload-dir',
        'result_pattern': {
            r'([^ ]+) is now in the repo': 0,
            r'([^ ]+) is already imported. Updated metadata only': 1
        },
    },
}

PATCH_ALARM_ID = '900.001'

IMPACTED_PROCESS_INVC_NOVA = ['nova-conductor', 'nova-scheduler', 'nova-consoleauth']
BASE_LOG_DIR = '/var/log'
LOG_RECORDS = {
    'upload': {
        'patching.log': [
            r'sw-patch-controller-daemon.*INFO: Importing patches: (.+)'
        ],
    },
    'delete': {
        'patching.log': [
            r'sw-patch-controller-daemon.*INFO: (.+) .*has been deleted'
        ]
    }
}

IMPACTS_ON_SYSTEM = {
    'INSVC_NOVA': {
        'processes': ['nova-scheduler', 'nova-conductor', 'nova-consoleauth'],
        'log_record': r'Starting (\w+) node \(version (.*)\)'
    }
}


def get_log_records(action='upload', con_ssh=None, start_time=None, max_lines=100, fail_if_not_found=False):
    LOG.info('Searching logs for: "{}" starting: "{}"'.format(action, start_time))

    action = action.lower()
    logs = []
    if action in LOG_RECORDS and LOG_RECORDS[action]:
        record_patterns = LOG_RECORDS[action]

        commands = []
        for log_file, patterns in record_patterns.items():
            log_file = os.path.join(BASE_LOG_DIR, log_file)
            search_command = '\egrep -H \'{}\' {} 2>/dev/null | tail -n {}'.format(
                r'\|'.join(patterns), log_file, max_lines)
            commands.append(search_command)

        code, output = run_cmd(';'.join(commands), con_ssh=con_ssh, fail_ok=fail_if_not_found)
        assert 0 == code or not fail_if_not_found, \
            'Failed to find in logs:\n{}\n'.format(record_patterns)

        if 0 != code or not output.strip():
            LOG.info('No logs found for action: "{}"'.format(action))
            return {}

        start_timestamp = datetime.strptime(start_time, LOG_DATETIME_FORMAT) if start_time else None

        for line in output.splitlines():
            if not line.strip():
                continue

            try:
                log_file = os.path.basename(line.split(':')[0])
                patch_pattern = record_patterns[log_file][0]

                patch_files = re.search(patch_pattern, line).group(1).strip().split(',')
                patches = [os.path.basename(file).split(os.path.extsep)[0] for file in patch_files]

                time_stamp = datetime.strptime(':'.join(line.split(':')[1:4]), LOG_DATETIME_FORMAT)

                if not start_timestamp or time_stamp >= start_timestamp:
                    logs.append((patches, log_file, time_stamp, line))

            except IndexError as e:
                LOG.warning('ill-formatted log line:\n"{}"\n{}\n'.format(line, e))

            except Exception as e:
                LOG.warning('unknown log line:\n"{}"\n{}\n'.format(line, e))
    else:
        LOG.warning('Not yet support searching log entries for action: "{}"'.format(action))
        return []

    assert logs or not fail_if_not_found, \
        'Failed to find log records for "{}", \nlogs={}, '.format(action, logs)

    return logs


def check_log_records(action='upload',
                      expected_patches=None,
                      con_ssh=None,
                      start_time=None,
                      fail_if_not_found=False):

    if not expected_patches and action != 'host_install':
        LOG.info('No expected log entries to check for "applied" or "removed"')
        return True, []

    max_lines = 100
    if expected_patches and isinstance(expected_patches, list):
        max_lines = max(max_lines, len(expected_patches)*10)
        
    logs = get_log_records(action=action,
                           start_time=start_time,
                           max_lines=max_lines,
                           fail_if_not_found=True,
                           con_ssh=con_ssh)

    if expected_patches:
        patches_logged = []
        for log in logs:
            patches_logged += log[0]

        all_logged = True
        if not patches_logged:
            LOG.info('No log records found for: "{}" after: "{}"'.format(action, start_time))
            assert not fail_if_not_found, 'No log records found for: "{}" after: "{}"'.format(action, start_time)
            return False, patches_logged

        if set(patches_logged) < set(expected_patches):
            LOG.warning('No all patches logged, expecting:"{}", actual:"{}"'.format(
                set(expected_patches), set(patches_logged)))
            LOG.warning('Missed log files:\n{}\n'.format(set(expected_patches) - set(patches_logged)))
            LOG.warning('Differences: \n{}\n'.format(set(expected_patches) ^ set(patches_logged)))
            all_logged = False

        return all_logged, patches_logged

    else:
        return False, []


def repeat(wait_per_iter=10, expected_code=0, expected_hits=2, stop_codes=(),
           wait_first=False, message='', verbose=False, default_timeout=60):

    def wrapper(func):

        @functools.wraps(func)
        def wrapped_func(*args, **kw):
            timeout = kw.get('timeout', default_timeout)

            if wait_first:
                time.sleep(wait_per_iter)

            hit_cnt = 0
            total_cnt = 0
            output = ''
            previous_code = 0

            wait_for_check = wait_per_iter
            end_time = time.time() + timeout
            while time.time() < end_time:
                code, output = func(*args, **kw)
                total_cnt += 1
                if code != previous_code:
                    LOG.info('Result changed after hitting expected-code {}/{} times. Prev code: {}, '
                             'current code:{}'.format(hit_cnt, total_cnt, previous_code, code))
                    previous_code = code

                if code == expected_code:
                    hit_cnt += 1
                    LOG.debug('{}: reached expected code {} {}/{} times'.format(message, code, hit_cnt, total_cnt))
                    if hit_cnt >= expected_hits:
                        return code, output

                elif code in stop_codes:
                    LOG.info('{}: hit stop code {} at iteration {}'.format(message, stop_codes, total_cnt))

                if verbose:
                    LOG.info('{}: continue to wait for code {}, found code {} output {}'.format(
                        message, expected_code, code, output))

                if hit_cnt < 1 and wait_for_check < 180:
                    wait_for_check = wait_per_iter * total_cnt

                time.sleep(wait_for_check)
            return -1, output

        return wrapped_func

    return wrapper


def run_cmd(cmd, con_ssh=None, **kwargs):
    LOG.debug('run cmd:' + cmd)
    if not con_ssh:
        con_name = 'RegionOne' if ProjVar.get_var('IS_DC') else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    return con_ssh.exec_cmd(cmd, **kwargs)


def get_tracebacks(log_file='patching.log', start_time=None, con_ssh=None, hosts=None):
    """

    Args:
        log_file:
        start_time:
        con_ssh:
        hosts (str|list): hosts to check

    Returns (dict): {<hostname>(str): <tracebacks>(list)}

    """
    log_path = os.path.join(BASE_LOG_DIR, log_file)
    if not con_ssh:
        con_name = 'RegionOne' if ProjVar.get_var('IS_DC') else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    results = {}
    output = common.search_log(file_path=log_path, ssh_client=con_ssh, pattern='traceback', start_time=start_time)
    hostname = con_ssh.get_hostname()
    records = [record.strip() for record in output.splitlines()]
    results[hostname] = records

    if hosts:
        if isinstance(hosts, str):
            hosts = [hosts]

        for host in hosts:
            if host == hostname:
                continue

            with host_helper.ssh_to_host(hostname=host, con_ssh=con_ssh) as host_ssh:
                host_output = common.search_log(file_path=log_path, ssh_client=con_ssh, pattern='traceback',
                                                start_time=start_time)
                results[host] = [record.strip() for record in host_output.splitlines()]

    return results


def check_no_tracebacks(start_time, con_ssh=None, hosts=None, log_file='patching.log'):
    traces_per_host = get_tracebacks(log_file=log_file, con_ssh=con_ssh, hosts=hosts, start_time=start_time)
    for host, traces in traces_per_host.items():
        assert not traces, "traceback logged in {} since {}".format(log_file, start_time)


def run_patch_cmd(cmd, args='', con_ssh=None, fail_ok=False, timeout=600, parse_output=True):

    assert cmd in PATCH_CMDS, 'Unknown patch command:<{}>'.format(cmd)
    LOG.debug('run patch cmd: ' + cmd)

    if not con_ssh:
        con_name = 'RegionOne' if ProjVar.get_var('IS_DC') else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    cmd_info = PATCH_CMDS.get(cmd)
    command = 'sw-patch {} {}'.format(cmd_info['cmd'], args)
    code, output = con_ssh.exec_sudo_cmd(command, fail_ok=fail_ok, expect_timeout=timeout)

    if not parse_output:
        return code, output

    result_patterns = cmd_info.get('result_pattern')
    if not result_patterns:
        return code, output

    results = []
    matched = 0
    for line in output.splitlines():
        for pattern, rtn_code in result_patterns.items():
            values = re.match(pattern, line)
            if values:
                if rtn_code != code:
                    code = rtn_code
                matched += 1
                results.append((values.groups(), rtn_code))

    return code, results


def get_patch_id_from_file(patch_file):
    # code, output = run_cmd('ls {}'.format(patch_file), con_ssh=con_ssh)
    # assert 0 == code, 'Failed to list patch directory:{} on the active controller'.format(patch_file)

    return os.path.basename(patch_file).rstrip('.patch').upper()


def get_patch_ids_from_dir(patch_dir, con_ssh=None):
    code, output = run_cmd('ls {}'.format(os.path.join(patch_dir, '*.patch')), con_ssh=con_ssh)
    assert 0 == code, 'Failed to list patch directory:{} on the active controller'.format(patch_dir)

    return [os.path.basename(p).rstrip('.patch') for p in output.split()]


def upload_patch_dir(patch_dir=None, con_ssh=None):
    """Upload patch(es) in the specified directory

    Args:
        patch_dir:
        con_ssh:

    Returns:
        patches uploaded (list)
    """
    if not con_ssh:
        con_name = 'RegionOne' if ProjVar.get_var('IS_DC') else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    if not patch_dir or not common.is_dir(dirname=patch_dir, ssh_client=con_ssh):
        LOG.info('Not a directory:{}'.format(patch_dir))
        return -2, []

    patch_ids_in_dir = get_patch_ids_from_dir(patch_dir=patch_dir, con_ssh=con_ssh)
    if not patch_ids_in_dir:
        LOG.info("No patch found in directory: {}".format(patch_dir))
        return -2, []

    assert check_patches_version(patch_ids_in_dir, con_ssh=con_ssh), \
        'Mismatched versions between patch files and system image load'
    patch_states = get_patches_states(con_ssh=con_ssh)

    patches_to_upload = list(set(patch_ids_in_dir) - set(patch_states.keys()))

    patches_to_skip = list(set(patch_ids_in_dir) & set(patch_states.keys()))
    if len(patches_to_upload) < len(patch_ids_in_dir):
        LOG.warning('Some patches already in system: {}'.format(patches_to_skip))

    LOG.info('Patches to upload: {}'.format(patches_to_upload))
    patches_uploaded = []
    for p in patches_to_skip:
        if patch_states[p]['state'].lower() == 'available':
            patches_uploaded.append(p)

    if not patches_to_upload:
        LOG.info("All patches in dir already in system. Patches in Available state: {}".format(patches_uploaded))
        return -1, patches_uploaded
    # time_before = datetime.now()
    time_before = common.lab_time_now(con_ssh=con_ssh)[0]

    run_patch_cmd('upload-dir', args=patch_dir, con_ssh=con_ssh)

    code, expected_patches = check_patches_uploaded(
        patches_to_upload, prev_patch_states=patch_states, con_ssh=con_ssh)
    assert 0 == code, \
        'Failed to confirm all patches were actually uploaded, checked patch ids:{}'.format(patches_to_upload)

    all_found, patches_found = check_log_records(action='upload',
                                                 expected_patches=patches_to_upload,
                                                 start_time=time_before,
                                                 con_ssh=con_ssh)
    assert all_found, \
        'Not all patch upload log entries found in log file, found for:\n"{}", while expecting:\n"{}"\n'.format(
            patches_found, patches_to_upload)
    LOG.info('Log entries were found for all patches:"{}"'.format(patches_found))

    return 0, patches_to_upload + patches_uploaded


def wait_for_hosts_patch_states(expected_states, con_ssh=None, timeout=120, fail_ok=False):

    for host, expected_state in expected_states.items():
        code, state = wait_for_host_patch_states(host, expected_states=expected_state, con_ssh=con_ssh, timeout=timeout)

        if code != 0:
            msg = 'Host:{} failed to reach state: {}; actual state: {}'.format(host, expected_state, state)
            if fail_ok:
                LOG.info(msg)
                return False
            else:
                raise exceptions.PatchError(msg)

        LOG.info('OK, host:{} reached state: {} as expected'.format(host, state))

    return True


def delete_patches(patch_ids=None, con_ssh=None):
    """
    Deletes supplied patches from software system

    Args:
        patch_ids (list)
        con_ssh

    Returns:
        delete command return string
    """
    if not patch_ids:
        LOG.info("No patches to delete. Do nothing.")
        return -1, []

    if not con_ssh:
        con_name = 'RegionOne' if ProjVar.get_var('IS_DC') else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    time_before = common.lab_time_now(con_ssh=con_ssh)[0]
    LOG.info('Deleting patches: "{}"'.format(patch_ids))
    args = ' '.join(patch_ids)
    code, patch_info = run_patch_cmd('delete', args=args, con_ssh=con_ssh)
    assert 0 == code, 'Failed to delete patch(es):{}'.format(args)

    check_if_patches_exist(patch_ids=patch_ids, expecting_exist=False, con_ssh=con_ssh)

    found, patches = check_log_records(action='delete',
                                       start_time=time_before,
                                       expected_patches=patch_ids,
                                       con_ssh=con_ssh)
    assert found, 'Failed to find log records for deleting patches: {}'.format(patch_ids)

    LOG.info('OK, deleted patches: "{}"'.format(patch_ids))

    return code, patch_ids


def upload_patches(patch_files, check_first=True, fail_ok=False, check_available=True, con_ssh=None):
    """
    Uploads single patch file
    Args:
        patch_files (str|list|tuple)
        check_first (bool)
        fail_ok
        check_available (bool): raise if check failed, even if fail_ok=True.
        con_ssh

    Returns (tuple):    return code 2 and 3 only return if fail_ok=True
        (-1, <uploaded_patches>, <already_uploaded>)   # some are already uploaded
        (0, <uploaded_patches>, [])    # uploaded successfully
        (1, <uploaded_patches>, <patches_failed_validation>)    # some patches failed validation
        (2  <uploaded_patches>, <non-exist files>)  # some patch files don't exist. check_first=False

    """
    if isinstance(patch_files, str):
        patch_files = patch_files.split(sep=' ')

    if not con_ssh:
        con_name = 'RegionOne' if ProjVar.get_var('IS_DC') else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    if check_first:
        for file_ in patch_files:
            if not common.is_file(file_, con_ssh):
                raise ValueError("{} is not a file".format(file_))

    LOG.info("sw-patch upload files: {}".format(patch_files))
    code, output = run_patch_cmd('upload', args=' '.join(patch_files), con_ssh=con_ssh, parse_output=False)

    res_dict = {
        'uploaded': (re.compile(PatchPattern.UPLOADED), []),
        'already_uploaded': (re.compile(PatchPattern.ALREADY_UPLOADED), []),
        'failed': (re.compile(PatchPattern.VALIDATE_FAILED), []),
        'no_file': (re.compile(PatchPattern.FILE_NOT_EXIST), [])

    }
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        for scenario in res_dict:
            pattern, patch_ids_ = res_dict[scenario]
            found = pattern.findall(line)
            if found:
                patch_ids_.append(found[0].strip())
                break

    uploaded = res_dict['uploaded'][1]
    already_uploaded = res_dict['already_uploaded'][1]
    failed_validate = res_dict['failed'][1]
    files_not_exist = res_dict['no_file'][1]
    total_uploaded = uploaded + already_uploaded

    processed_patches = total_uploaded + failed_validate + files_not_exist
    if len(processed_patches) != len(patch_files):
        raise exceptions.PatchError("Patch files requested to upload: {}. Processed patches: {}".
                                    format(patch_files, processed_patches))

    if code > 0:
        if failed_validate:
            msg = "Patch file validation failed: {}. ".format(failed_validate)
            rtn_code = 1
            failed_patches = failed_validate
        elif files_not_exist:
            msg = "Patch file does not exist failed: {}. ".format(files_not_exist)
            rtn_code = 2
            failed_patches = files_not_exist
        else:
            raise NotImplementedError("Scenario not handled, please add the new failure case.")

        if fail_ok:
            LOG.info(msg)
            return rtn_code, total_uploaded, failed_patches
        else:
            raise exceptions.PatchError(msg)

    if check_available:
        LOG.info("Check all uploaded or already imported patches are Available: {}".format(total_uploaded))
        post_upload_states = get_patches_states(patch_ids=total_uploaded)
        for patch, state in post_upload_states.items():
            state = state['state']
            if state != PatchState.AVAILABLE:
                raise exceptions.PatchError("Patch state is {} instead of Available: {}".format(state, patch))

    rtn_code = -1 if already_uploaded else 0
    return rtn_code, total_uploaded, already_uploaded


def get_expected_patch_states(patch_ids, pre_patches_states, action='upload', con_ssh=None):
    """
    Returns the expected patch state based on the action

    Args:
        action (str)
        patch_ids (list|str)
        pre_patches_states (dict|None)
        con_ssh

    Returns:
        expected_states (dict)
    """
    # heuristic codes trying to figure out the next state of patches
    if not patch_ids or pre_patches_states is None:
        return {}

    if isinstance(patch_ids, str):
        patch_ids = [patch_ids]

    action = action.upper()
    expected_states = {}

    default_action_states = {
        'APPLY': PatchState.PARTIAL_APPLY,
        'REMOVE': PatchState.PARTIAL_REMOVE,
        'HOST_INSTALL': PatchState.APPLIED,
    }
    is_storage_lab = system_helper.is_storage_system(con_ssh=con_ssh)

    for patch_id in patch_ids:
        if action == 'UPLOAD':
            expected_states[patch_id] = pre_patches_states[patch_id]['state'] if patch_id in pre_patches_states \
                else PatchState.AVAILABLE
        elif 'FAILURE' in patch_id and 'PREINSTALL_FAILURE' not in patch_id:
            # Use default
            pass
        elif 'STORAGE' in patch_id and not is_storage_lab:
            if action == 'APPLY':
                expected_states[patch_id] = PatchState.APPLIED
            elif action == 'REMOVE':
                expected_states[patch_id] = PatchState.AVAILABLE
        else:
            previous_state = pre_patches_states[patch_id]['state']
            if action == 'APPLY':
                if previous_state == PatchState.AVAILABLE:
                    expected_states[patch_id] = PatchState.PARTIAL_APPLY
                elif previous_state == PatchState.PARTIAL_REMOVE:
                    expected_states[patch_id] = PatchState.AVAILABLE
                else:
                    LOG.warning('Cannot "{}" patch: "{}" while it is now in: "{}" states'.format(
                        action, patch_id, previous_state))

            elif action == 'REMOVE':
                if previous_state == PatchState.APPLIED:
                    expected_states[patch_id] = PatchState.PARTIAL_REMOVE
                elif previous_state == PatchState.PARTIAL_APPLY:
                    expected_states[patch_id] = PatchState.AVAILABLE
                else:
                    LOG.warning('Cannot "{}" patch: "{}" while it is now in: "{}" states'.format(
                        action, patch_id, previous_state))

            elif action == 'HOST_INSTALL':
                if previous_state == PatchState.PARTIAL_APPLY:
                    expected_states[patch_id] = PatchState.APPLIED
                elif previous_state == PatchState.PARTIAL_REMOVE:
                    expected_states[patch_id] = PatchState.AVAILABLE
                else:
                    LOG.warning('Cannot "{}" patch: "{}" while it is now in: "{}" states'.format(
                        action, patch_id, previous_state))

        if patch_id not in expected_states:
            if action in default_action_states:
                expected_states[patch_id] = default_action_states[action]
            else:
                raise ValueError('Unknown patch-action: "{}"'.format(action))

    return expected_states


def get_expected_hosts_states(action, patch_ids, pre_hosts_states, pre_patches_states, con_ssh=None):
    """
    Returns the expected host state based on the action
    Args:
        action (string)
        patch_ids (list)
        pre_hosts_states
        pre_patches_states
        con_ssh

    Returns:
        expected_states (dict)
    """

    action = action.upper()
    if action in ('APPLY', 'REMOVE'):
        reboot_required = False

        impacted_host_types = []
        for patch_id in patch_ids:
            if '_RR_' in patch_id or '_LARGE' in patch_id:
                reboot_required = True

            if '_NOVA' in patch_id:
                impacted_host_types += ['COMPUTE', 'CONTROLLER']
            elif '_CONTROLLER' in patch_id:
                impacted_host_types += ['CONTROLLER']
            elif '_COMPUTE' in patch_id:
                impacted_host_types += ['COMPUTE']
            elif '_STORAGE' in patch_id:
                impacted_host_types += ['STORAGE']
            elif '_ALLNODES' in patch_id:
                impacted_host_types += ['COMPUTE', 'CONTROLLER', 'STORAGE']
            else:
                impacted_host_types += ['COMPUTE', 'CONTROLLER', 'STORAGE']

        impacted_host_types = list(set(impacted_host_types))
        controllers, computes, storages = system_helper.get_hostnames_per_personality(con_ssh=con_ssh, rtn_tuple=True)
        hosts_per_types = {'CONTROLLER': controllers, 'COMPUTE': computes, 'STORAGE': storages}

        expected_states = {}
        for host in pre_hosts_states:
            for host_type, hosts_ in hosts_per_types.items():
                if host in hosts_:
                    if host_type in impacted_host_types:
                        patch_current = 'No'

                        if pre_hosts_states[host]['patch-current'] == 'No':
                            if action == 'APPLY' and all(state['state'] == PatchState.PARTIAL_REMOVE
                                                         for state in pre_patches_states.values):
                                patch_current = 'Yes'
                            elif action == 'REMOVE' and all(state['state'] == PatchState.PARTIAL_APPLY
                                                            for state in pre_patches_states.values):
                                patch_current = 'Yes'

                        expected_states[host] = {
                            'rr': reboot_required,
                            'patch-current': patch_current
                        }
                    else:
                        expected_states[host] = pre_hosts_states[host]

                    # Break host type loop if host found, since same host can only exist in one host_type
                    break

        LOG.info('expected hosts states:\n{}'.format(expected_states))

        return expected_states

    else:
        LOG.info("Action {} has no impact on host patch state".format(action))
        # action in ('UPLOAD', 'DELETE') has no impact on host states
        # 'HOST-INSTALL', 'HOST-INSTALL-ASYNC' are not handled
        return {}


def apply_patches(patch_ids=None, apply_all=False, fail_ok=False, con_ssh=None, wait_for_host_state=True):
    """
    Applies supplied patch_ids to the system

        Args:
            con_ssh
            patch_ids (list|str)
            apply_all (bool)
            fail_ok (bool)
            wait_for_host_state

        Returns (tuple):
            (-1, <applied_patch_ids>)   Patch_ids are specified but all patches already applied
            (0, <applied_patch_ids>)    Patches applied successfully
            (1, <stderr>)   Given patch does not exist. fail_ok=True
            (2, [])    --all is used, but no available patch to apply. fail_ok=True
    """
    if not patch_ids and not apply_all:
        raise ValueError("Either patch_ids or apply_all has to be specified")

    if isinstance(patch_ids, str):
        patch_ids = [patch_ids]

    if patch_ids is None or apply_all:
        args = ' --all'
    elif any(patch_id.upper() == 'ALL' for patch_id in patch_ids):
        args = ' --all'
    else:
        args = ' '.join(patch_ids)

    pre_patches_states = get_patches_states(con_ssh=con_ssh)
    pre_hosts_states = get_hosts_patch_states(con_ssh=con_ssh)

    LOG.info("Apply patches: {}".format(args))
    code, output = run_patch_cmd('apply', args=args, con_ssh=con_ssh, fail_ok=fail_ok, parse_output=False)
    if code > 0:
        return 1, output

    # process return code 0 scenarios

    # --all is used but no available patch
    if 'no available patches to be applied' in output:
        msg = 'No available patch to apply.'
        if fail_ok:
            LOG.info(msg)
            return 2, []
        else:
            raise exceptions.PatchError(msg)

    # patch_ids specified, patch either applied successfully or already applied
    rtn_code = 0
    applied_patch_ids = []
    already_applied = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        patch, msg = str(line).split(sep=' ', maxsplit=1)
        applied_patch_ids.append(patch)
        if 'now in the repo' in msg:
            continue
        elif 'already in the repo' in msg:
            already_applied.append(patch)
        else:
            raise NotImplementedError("patch apply output: '{}' needs to be added to apply_patches")

    if '--all' not in args and set(applied_patch_ids) != set(patch_ids):
        raise exceptions.PatchError("Patches requested to apply: {}. Applied: {}".format(patch_ids, applied_patch_ids))

    if already_applied:
        LOG.info('Patch {} already applied'.format(already_applied))
        rtn_code = -1

    expected_states = get_expected_patch_states(action='APPLY',
                                                patch_ids=applied_patch_ids,
                                                pre_patches_states=pre_patches_states,
                                                con_ssh=con_ssh)

    LOG.info("Wait for patch states after apply patch {}: {}".format(applied_patch_ids, expected_states))
    for patch_id in applied_patch_ids:
        expected_state = expected_states[patch_id]
        code, output = wait_for_patch_states(patch_id, expected_state, con_ssh=con_ssh)
        if not 0 == code:
            raise exceptions.PatchError('Patch:{} did not reach state: {} after apply. Actual state: {}'.
                                        format(patch_id, expected_state, output[patch_id]))

    if wait_for_host_state:
        expected_hosts_states = get_expected_hosts_states('APPLY',
                                                          patch_ids=applied_patch_ids,
                                                          pre_hosts_states=pre_hosts_states,
                                                          pre_patches_states=pre_patches_states,
                                                          con_ssh=con_ssh)

        LOG.info("Wait for host patch states after apply patch: {}".format(expected_hosts_states))
        wait_for_hosts_patch_states(expected_states=expected_hosts_states, con_ssh=con_ssh, fail_ok=False)

    LOG.info('OK, patches {} applied.'.format(applied_patch_ids))
    return rtn_code, applied_patch_ids


def _patch_parser(output, delimits=None):
    results = []

    if not output:
        return results

    if not delimits:
        delimits = r'([^\s]+)\s*'

    pattern = re.compile(delimits)
    lines = list(output.splitlines())

    if 2 > len(lines):
        LOG.warning('empty Patch Output Table')
        return []

    for line in lines[2:]:
        match = pattern.findall(line)
        results.append(match)

    return results


def _query_output_parser(output):

    results = _patch_parser(output)

    return results


def get_patches_states(patch_ids=None, con_ssh=None):
    """
    Returns the states of all patches in the system
    Args:
        patch_ids (list|tuple|str)
        con_ssh

    Returns:
        (code, output) from "sw-patch query"
    """
    output = run_patch_cmd('query', con_ssh=con_ssh, fail_ok=False)[1]

    patch_states = _query_output_parser(output)

    patch_id_states = {}
    for patch_id, rr, release, state in patch_states:
        patch_id_states[patch_id] = {'rr': rr == 'Y', 'release': release, 'state': state}

    if patch_ids:
        if isinstance(patch_ids, str):
            patch_ids = (patch_ids, )
        patch_id_states = {patch: states for patch, states in patch_id_states.items() if patch in patch_ids}

    return patch_id_states


def check_if_patches_exist(patch_ids=None, expecting_exist=True, con_ssh=None):
    """
    Checks if patch exist in system

    Args:
        patch_ids (list)
        expecting_exist(bool)
        con_ssh

    Returns:
        bool
    """
    if not patch_ids:
        LOG.warning("No patch id provided.")
        return

    patch_id_states = get_patches_states(con_ssh=con_ssh)

    if expecting_exist and not patch_ids:
        assert False, 'No patches in the system, while {} are expected'.format(patch_ids)

    for patch_id in patch_ids:
        if expecting_exist:
            assert patch_id in patch_id_states, \
                'Patch: {} was NOT uploaded as expected'.format(patch_id)
        else:
            assert patch_id not in patch_id_states, \
                'Patch: {} EXISTING, it should be deleted/not-uploaded'.format(patch_id)


def get_patches_in_state(expected_states=None, con_ssh=None):
    """
    Returns the patch ids that are in specified states

        Args:
            expected_states (list|str|tuple)
            con_ssh

        Returns:
            patch_ids (list)
    """
    patches_states = get_patches_states(con_ssh=con_ssh)

    if not expected_states:
        return tuple(patches_states.keys())

    if isinstance(expected_states, str):
        expected_states = (expected_states,)

    patches = [patch for patch in patches_states if patches_states[patch]['state'] in expected_states]
    LOG.info("Patches in states {}: {}".format(expected_states, patches))
    return patches


def __get_patch_ids(con_ssh=None, expected_states=None):
    states = get_patches_states(con_ssh=con_ssh)

    if expected_states is None:
        return list(states.keys())
    else:
        return [patch_id for patch_id in states if states[patch_id]['state'] in expected_states]


def get_partial_applied(con_ssh=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=(PatchState.PARTIAL_APPLY, ))


def get_partial_removed(con_ssh=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=(PatchState.PARTIAL_REMOVE, ))


def get_available_patches(con_ssh=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=(PatchState.AVAILABLE, ))


def get_all_patch_ids(con_ssh=None, expected_states=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=expected_states)


def get_hosts_patch_states(con_ssh=None):
    _, output = run_patch_cmd('query-hosts', fail_ok=False, con_ssh=con_ssh)

    states = _patch_parser(output)

    return {host: {'ip': ip, 'patch-current': pc, 'rr': rr == 'Yes', 'release': release, 'state': state}
            for host, ip, pc, rr, release, state in states}


def get_host_patch_state(host, con_ssh=None):
    hosts_states = get_hosts_patch_states(con_ssh=con_ssh)

    return hosts_states.get(host)


def wait_for_hosts_to_check_patch_current(timeout=120):
    """
    Wait for all hosts to finish checking if they are patch current or not.

        Args:
            timeout (int

        Returns:
            0
    """
    LOG.info("Waiting for hosts to check patch-current status")
    end_time = time.time() + timeout
    while time.time() < end_time:
        hosts_states = get_hosts_patch_states()
        pending_found = False
        for host_states in hosts_states:
            if 'Pending' in hosts_states[host_states].values():
                pending_found = True

        if not pending_found:
            return 0

        time.sleep(5)

    raise exceptions.TimeoutException("Timeout reached while waiting for hosts patch-status:'pending' state")


@repeat(wait_first=True, expected_hits=2, message='wait_for_hosts_states')
def wait_for_host_patch_states(host, expected_states, con_ssh=None, timeout=120):
    """

    Args:
        host:
        expected_states:
        con_ssh:
        timeout: used in decorator

    Returns:

    """
    host_state = get_host_patch_state(host, con_ssh=con_ssh)

    for state in expected_states:
        if state not in host_state or expected_states[state] != host_state[state]:
            return 1, host_state

    return 0, host_state


@repeat(expected_hits=2, wait_per_iter=20, verbose=True, message='Waiting for patches in states', stop_codes=(-1, 2))
def wait_for_patch_states(patch_ids, expected_states=('Available',), con_ssh=None, fail_on_not_found=False,
                          timeout=120):
    """

    Args:
        patch_ids (list|str):
        expected_states:
        con_ssh:
        fail_on_not_found:
        timeout: DO NOT remove. used in decorator

    Returns:

    """
    if not patch_ids:
        LOG.warning('No patches to check?')
        return -1, []

    if isinstance(patch_ids, str):
        patch_ids = patch_ids.split(sep=' ')

    cur_patch_states = get_patches_states(con_ssh=con_ssh)
    res = {}
    for patch_id in patch_ids:
        if patch_id in cur_patch_states:
            state = cur_patch_states[patch_id]['state']
            res[patch_id] = state
            if state not in expected_states:
                LOG.info('At least one patch:{} is not in expected states: {}, actual state:{}'.format(
                    patch_id, expected_states, cur_patch_states[patch_id]))
                return 1, res
        else:
            LOG.info('Patch:{} is not in the system')
            if fail_on_not_found:
                res[patch_id] = None
                LOG.error('Patch:{} is not loaded in the system'.format(patch_id))
                return 2, res

    return 0, res


def check_patches_uploaded(patch_ids, prev_patch_states=None, con_ssh=None):
    if not patch_ids:
        return 0, []

    if prev_patch_states:
        LOG.info('previous states:{}'.format(prev_patch_states))

    prev_patch_states = prev_patch_states or {}
    for patch_id in patch_ids:
        if patch_id in prev_patch_states:
            prev_state = prev_patch_states[patch_id]
            LOG.warning('Patch already in system, Patch id:{} status:{}'.format(
                patch_id, prev_state
            ))
            if 'Available' != prev_state['state']:
                msg = 'Patch already in system but not in "Available" status, (it is in status:"{}), '
                msg += 'fail the test in this case"'.format(prev_state['state'])
                LOG.warning(msg)
                return 1, [patch_id]

    return wait_for_patch_states(patch_ids, ('Available',), con_ssh=con_ssh)


def wait_for_hosts_installed(hosts, timeout=600, check_interval=10, fail_ok=False, con_ssh=None):
    hosts_patch_states = get_hosts_patch_states(con_ssh=con_ssh)
    if not hosts:
        hosts = list(hosts_patch_states.keys())
    elif isinstance(hosts, str):
        hosts = [hosts]

    end_time = time.time() + timeout
    installed_hosts = []
    failed_hosts = []
    while time.time() < end_time:
        installed_hosts = []
        failed_hosts = []
        for host in hosts:
            host_states = hosts_patch_states[host]
            patch_current = host_states['patch-current']
            host_rr = host_states['rr']
            if patch_current == 'Failed':
                failed_hosts.append(host)
            elif patch_current == 'Yes' and not host_rr:
                installed_hosts.append(host)

        if len(installed_hosts) + len(failed_hosts) == len(hosts):
            break

        time.sleep(check_interval)
        hosts_patch_states = get_hosts_patch_states(con_ssh=con_ssh)

    rtn_code = 0
    rtn_hosts = installed_hosts
    msg = "{} are patch current".format(hosts)

    if failed_hosts:
        msg = "{} failed to install patch".format(failed_hosts)
        rtn_code = 1
        rtn_hosts = failed_hosts

    uninstalled_hosts = list(set(hosts) - set(installed_hosts) - set(failed_hosts))
    if uninstalled_hosts:
        msg = "{} hosts are not patch current after install within {} seconds".format(uninstalled_hosts, timeout)
        rtn_code = 2
        rtn_hosts = uninstalled_hosts

    if rtn_code > 0:
        if fail_ok:
            LOG.warning(msg)
        else:
            raise exceptions.PatchError(msg)
    else:
        LOG.info(msg)
    return rtn_code, rtn_hosts


def wait_for_host_installed(host, timeout=600, check_interval=10, fail_ok=False, con_ssh=None):
    """
    Verifies the specified host is finished installing the patch.

        Args:
            host (str)
            timeout (int)
            check_interval (int)
            fail_ok (bool)
            con_ssh

        Returns:
            0, host_state (dict)
    """
    LOG.info("Waiting for {} to reach patch-current and idle state".format(host))

    host_state = {}
    end_time = time.time() + timeout
    while time.time() < end_time:
        host_state = get_host_patch_state(host, con_ssh=con_ssh)

        if host_state['state'] == 'idle':
            if host_state['patch-current']:
                LOG.info("{} reached patch-current and idle state".format(host))
                return 0, host_state

        time.sleep(check_interval)

    if fail_ok:
        return 1, host_state
    else:
        raise exceptions.TimeoutException("Timed out while waiting for {} to reach patch-current and idle state. "
                                          "Current states: {}".format(host, host_state))


def install_patches(async=False, remove=False, fail_ok=False, force_lock=False, con_ssh=None):
    """
    Installs patches on all impacted hosts

        Args:
            async (bool)
            remove (bool): whether to install hosts after remove. Failed-installed hosts will be installed if remove.
            con_ssh
            fail_ok
            force_lock

        Returns:
            N/A
    """
    hosts_patch_states = get_hosts_patch_states(con_ssh=con_ssh)

    install_failed_hosts = []
    installed_hosts = []
    cmd = 'host-install-async' if async else 'host-install'
    active = system_helper.get_active_controller_name(con_ssh=con_ssh)
    hosts = system_helper.get_hostnames(con_ssh=con_ssh)
    hosts.remove(active)
    hosts.append(active)
    cmd_timeout = 120 if async else 1200
    state_timeout = 1200 if async else 60
    for host in hosts:
        host_patch_states = hosts_patch_states[host]
        patch_current = host_patch_states['patch-current']
        reboot_required = host_patch_states['rr']
        if not reboot_required and patch_current == 'Yes':
            LOG.info("{} is patch-current and not reboot-required. Skip install for it.".format(host))
            continue
        elif patch_current == 'Failed':
            if not remove:
                LOG.warning("Skip install for {} due to patch-current=Failed".format(host))
                continue

        installed_hosts.append(host)
        if reboot_required:
            LOG.info("Lock reboot required host {}".format(host))
            HostsToRecover.add(host)
            host_helper.lock_host(host=host, force=force_lock, con_ssh=con_ssh, swact=True)

        if patch_current != 'Yes':
            LOG.info("{} is not patch current. Install it.".format(host))
            cmd_code, output = run_patch_cmd(cmd=cmd, args=host, fail_ok=fail_ok, timeout=cmd_timeout,
                                             con_ssh=con_ssh, parse_output=False)
            if cmd_code == 0:
                expected_states = {'patch-current': 'Yes'}
                if not reboot_required:
                    expected_states['rr'] = False

                LOG.info("Wait for {} to be patch current after install".format(host))
                res, actual = wait_for_host_patch_states(host, expected_states=expected_states, timeout=state_timeout)
                if res != 0:
                    msg = '{} patch-current is {} instead of Yes after install'.format(host, actual)
                    if fail_ok:
                        LOG.info(msg)
                        install_failed_hosts.append(host)
                    else:
                        raise exceptions.PatchError(msg)
            else:
                install_failed_hosts.append(host)

        if reboot_required:
            LOG.info("Unlock reboot required host {} and check it's patch states".format(host))
            host_helper.unlock_host(host, con_ssh=con_ssh)
            HostsToRecover.remove(host)
            if remove or host not in install_failed_hosts:
                LOG.info("Wait for {} to be 'patch-current: Yes' and 'rr: No' after unlock".format(host))
                res, actual = wait_for_host_patch_states(host, expected_states={'patch-current': 'Yes', 'rr': False},
                                                         timeout=60)

                if res != 0:
                    msg = '{} states is {} after install and unlock'.format(host, actual)
                    if fail_ok:
                        LOG.info(msg)
                        install_failed_hosts.append(host)
                    else:
                        raise exceptions.PatchError(msg)

    install_failed_hosts = list(set(install_failed_hosts))
    rtn_code = 1
    if not install_failed_hosts:
        if installed_hosts:
            LOG.info("Hosts {} installed successfully".format(installed_hosts))
            rtn_code = 0
        else:
            LOG.info("All hosts are patch-current and not reboot-required. Do nothing.")
            rtn_code = -1

    return rtn_code, installed_hosts, install_failed_hosts


def remove_patches(patch_ids, con_ssh=None, fail_ok=False):
    """
    Removes patches from system

        Args:
            patch_ids (list|tuple|str):
            con_ssh
            fail_ok (bool)

        Returns (tuple):
            (0, <removed patches>)
            (1, <fail_msg>)

    """
    patch_ids_removed = []
    pre_patches_states = get_patches_states(con_ssh=con_ssh)
    expected_states = get_expected_patch_states(action='REMOVE',
                                                patch_ids=patch_ids,
                                                pre_patches_states=pre_patches_states,
                                                con_ssh=con_ssh)

    if isinstance(patch_ids, str):
        patch_ids = patch_ids.split(sep=' ')

    code, output = run_patch_cmd('remove', args=' '.join(patch_ids), con_ssh=con_ssh, fail_ok=fail_ok)

    if code != 0:
        LOG.info("Failed to remove patches:{}, \noutput {}".format(patch_ids, output))
        return 1, output

    for patch_id, rtn_code in output:
        patch_ids_removed += patch_id

    assert sorted(patch_ids_removed) == sorted(patch_ids), \
        'Failed to remove patches:{}, \npatch_ids_removed {}'.format(patch_ids, patch_ids_removed)

    for patch in patch_ids:
        expected_state = expected_states[patch]
        code, output = wait_for_patch_states(patch, expected_state, con_ssh=con_ssh)

        if 0 != code:
            actual_state = output[patch]
            if actual_state == PatchState.PARTIAL_REMOVE and \
                    pre_patches_states[patch]['state'] == PatchState.PARTIAL_APPLY and \
                    (system_helper.get_alarms(alarm_id=EventLogID.PATCH_INSTALL_FAIL) or
                     system_helper.get_alarms(alarm_id=EventLogID.PATCH_IN_PROGRESS)):
                LOG.info("Patch install failure alarm present. Patch {} is in partial-remove state.".format(patch))
            else:
                raise exceptions.PatchError('Patch:{} did not reach state: {} after remove. Actual state: {}'.
                                            format(patch, expected_state, actual_state))

    return 0, patch_ids_removed


def parse_patch_file_name(patch_file_name):
    LOG.info('patch_file_name:{}'.format(patch_file_name))
    patch_info = {}
    name_pattern = re.compile('(20\d\d-\d\d-\d\d_\d\d-\d\d-\d\d)_(.+)')
    m = name_pattern.match(patch_file_name)
    if m and len(m.groups()) == 2:
        LOG.info('matched={}'.format(m))
        patch_date, core_name = m.groups()
        reboot_required = '_RR_' in core_name or '_INSVC_' not in core_name
        node_type = re.findall(r'.*(CONTROLLER).*|.*(COMPUTE).*|.*(STORAGE).*|.*(ALLNODES).*', core_name)
        node_type = ''.join(node_type[0]) if node_type else 'UNKNOWN'

        if node_type not in ['CONTROLLER', 'COMPUTE', 'STORAGE', 'ALLNODES']:
            node_type = 'UNKNOWN'
        negative = 'FAILURE' in core_name

        patch_info[patch_file_name] = {
            'date': str(patch_date), 'rr': reboot_required, 'node_type': node_type, 'negative': negative}

    LOG.info('patch info:{}'.format(patch_info))
    return patch_info


def check_patches_version(patch_files, con_ssh=None):
    for file in patch_files:
        if not check_patch_version(file, con_ssh=con_ssh):
            return False
    return True


def get_patch_files_info(patch_files):
    patch_file_info = {}
    for file in patch_files:
        LOG.info('file={}'.format(file))
        file_info = parse_patch_file_name(os.path.basename(file))
        patch_file_info.update(file_info)
    return patch_file_info


def check_patch_version(file_name='', con_ssh=None):
    patch_files_info = get_patch_files_info((file_name,))
    file_date = str(patch_files_info[file_name]['date'])
    if not file_date:
        LOG.info('Cannot get build-date from file name:{}'.format(file_name))
        return

    build_id = run_cmd('\grep BUILD_ID /etc/build.info 2>/dev/null | \grep "^BUILD_ID" |  cut -d= -f2',
                       fail_ok=False, con_ssh=con_ssh)[1]
    build_id = build_id.strip('"')
    assert file_date == build_id, \
        'Mismatched patch version and host image version, file date:{}, build id:{}'.format(file_date, build_id)

    return True


def get_system_patching_states(con_ssh=None):
    patch_stats = get_patches_states(con_ssh=con_ssh)
    hosts_stats = get_hosts_patch_states()
    alarms = system_helper.get_alarms()

    return {'host_states': hosts_stats, 'patch_states': patch_stats, 'alarms': alarms}


def orchestration_patch_hosts(controller_apply_type='serial', storage_apply_type='serial',
                              compute_apply_type='serial', max_parallel_computes=2, instance_action='stop-start',
                              alarm_restrictions='strict'):

    # Create patch strategy
    orchestration = 'patch'

    LOG.info("Create patch strategy  ......")
    orchestration_helper.create_strategy(orchestration, controller_apply_type=controller_apply_type,
                                         storage_apply_type=storage_apply_type, compute_apply_type=compute_apply_type,
                                         max_parallel_computes=max_parallel_computes,
                                         instance_action=instance_action, alarm_restrictions=alarm_restrictions)

    LOG.info("Apply patch strategy ......")
    orchestration_helper.apply_strategy(orchestration)

    LOG.info("Delete patch orchestration strategy ......")
    orchestration_helper.delete_strategy(orchestration)


def check_system_health(check_patch_ignored_alarms=True, fail_on_disallowed_failure=True):

    rc, failed_items = system_helper.get_system_health_query()
    if rc == 0:
        LOG.info("System health OK for patching ......")
        return 0, failed_items

    allowed_failures = ('No alarms', 'All hosts are patch current')
    disallowed_failures = list(set(failed_items) - set(allowed_failures))
    if disallowed_failures:
        if not fail_on_disallowed_failure:
            return 2, disallowed_failures
        else:
            raise exceptions.PatchError("System unhealthy. Failed items: {}".format(disallowed_failures))

    if 'All hosts are patch current' in failed_items:
        LOG.info("Some hosts are not patch current")

    if 'No alarms' in failed_items and check_patch_ignored_alarms:
        rtn = ('Alarm ID',)
        current_alarms_ids = system_helper.get_alarms(rtn_vals=rtn, mgmt_affecting=True)
        affecting_alarms = [id_ for id_ in current_alarms_ids if id_ not in
                            orchestration_helper.IGNORED_ALARM_IDS]
        if not fail_on_disallowed_failure:
            return 3, affecting_alarms
        else:
            raise exceptions.PatchError("Management affecting alarm(s) present: {}".format(affecting_alarms))

    return 1, failed_items


def download_test_patches(build_server=None, patch_dir=None, tis_dir=None, con_ssh=None):
    """
    Copy test patches from build server to active controller
    Args:
        build_server (SSHClient):
        patch_dir (str):
        tis_dir
        con_ssh
    Returns (dict):

    """
    if not tis_dir:
        tis_dir = WRSROOT_HOME + 'test_patches'

    if not build_server:
        build_server = ProjVar.get_var('BUILD_SERVER')

    build_path = ProjVar.get_var('BUILD_PATH')
    if not patch_dir:
        patch_dir = PatchingVars.get_patching_var('PATCH_DIR')
        if not patch_dir and not build_path:
            skip('patch_dir is not provided, and build path is found from /etc/build.info')

    if not build_path or not build_server:
        skip('Build path or server not found from /etc/build.info')

    if not con_ssh:
        con_name = 'RegionOne' if ProjVar.get_var('IS_DC') else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)
        if not common.is_dir(tis_dir, con_ssh):
            con_ssh.exec_cmd('mkdir -p {}'.format(tis_dir))

    with host_helper.ssh_to_build_server(bld_srv=build_server) as bs_ssh:
        if not patch_dir:
            patch_dir = common.get_symlink(bs_ssh, file_path='{}/test_patches'.format(build_path))
            if not patch_dir:
                skip('No symlink to test_patches found for load {}:{}'.format(build_server, build_path))
            PatchingVars.set_patching_var(PATCH_DIR=patch_dir)

        LOG.info("Download patch files from patch dir {}".format(patch_dir))
        dest_server = ProjVar.get_var('LAB')['floating ip']
        bs_ssh.exec_cmd("ls -1 --color=none {}/*.patch".format(patch_dir), fail_ok=False)
        pre_opts = 'sshpass -p "{}"'.format(HostLinuxCreds.get_password())
        bs_ssh.rsync(patch_dir+"/*.patch", dest_server, tis_dir, pre_opts=pre_opts, timeout=600)
        output = con_ssh.exec_cmd("ls -1  {}/*.patch".format(tis_dir), fail_ok=False)[1]

        patches = {}
        for line in output.splitlines():
            patches[os.path.splitext(os.path.basename(line))[0]] = line

        LOG.info("List of patches:\n {}".format(list(patches.keys())))

    active = con_ssh.get_hostname()
    other_controller = 'controller-0' if active == 'controller-1' else 'controller-1'
    if 0 == con_ssh.exec_cmd('nslookup {}'.format(other_controller))[0]:
        with host_helper.ssh_to_host(other_controller, con_ssh=con_ssh, timeout=10) as standby_ssh:
            if not common.is_dir(tis_dir, standby_ssh):
                standby_ssh.exec_cmd('mkdir -p {}'.format(tis_dir))

        LOG.info("rsync patch files from {} to {} with best effort".format(active, other_controller))
        con_ssh.rsync(tis_dir + "/*.patch", dest_server=other_controller, dest=tis_dir, timeout=600)

    return tis_dir, patches


def parse_test_patches(patch_ids, search_str, failure_patch=False, prefix_build_id=False, end_with_search_str=False):
    """
    Get test patch ids with given criteria.
    Notes: test will be skipped if no test patch is found
    Args:
        patch_ids (list|tuple|dict):
        search_str (str):
        end_with_search_str (bool): whether to append '$' to find patches that ends with the search_str
        failure_patch:
        prefix_build_id (bool):

    Returns (list):

    """
    if prefix_build_id:
        prefix = ProjVar.get_var('BUILD_ID') + ('_' if not search_str.startswith('_') else '')
        search_str = prefix + search_str
    if end_with_search_str:
        search_str += '$'

    if failure_patch:
        patches = [patch_ for patch_ in patch_ids if re.search(search_str, patch_) and 'FAILURE' in patch_]
    else:
        patches = [patch_ for patch_ in patch_ids if re.search(search_str, patch_) and 'FAILURE' not in patch_]

    if not patches:
        skip('test patch {} not found'.format(search_str))

    if 'A-C' in search_str:
        patches = sorted(patches)

    return patches


def get_affecting_alarms():
    current_alarms_ids = system_helper.get_alarms(mgmt_affecting=True, combine_entries=False)
    affecting_alarms = [id_ for id_ in current_alarms_ids if id_[0] not in orchestration_helper.IGNORED_ALARM_IDS]
    return affecting_alarms


def wait_for_affecting_alarms_gone(fail_ok=False):
    affecting_alarms = get_affecting_alarms()
    res = True
    if affecting_alarms:
        LOG.info("Wait for mgmt affecting alarms to be gone: {}".format(affecting_alarms))
        res, affecting_alarms = system_helper.wait_for_alarms_gone(alarms=affecting_alarms, timeout=240,
                                                                   fail_ok=fail_ok)
        if res:
            time.sleep(30)

    return res, affecting_alarms
