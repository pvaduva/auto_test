import re
import os
import time
import functools
from datetime import datetime

from utils import cli
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from utils import table_parser
from keywords import host_helper, system_helper

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

LOG_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'


def get_process_info(names=None, con_ssh=None):
    """

    Args:
        names: list of process names
        con_ssh:

    Returns:

    """
    if not names:
        LOG.info('No prcocess names specified, skip')
        return []

    output = run_sudo_cmd('ps -ef | \grep "/usr/bin/python2 /bin/nova-" 2>/dev/null | \grep -v grep',
                          fail_ok=False, con_ssh=con_ssh)[1]

    process_info = []
    for line in output.splitlines():
        try:
            fields = line.split()
            user, pid, ppid = fields[0:3]
            command = fields[8]
            LOG.info('OK, found process: {} {} {} {}'.format(user, pid, ppid, command))
            process_info.append((pid, ppid, os.path.basename(command)))

        except IndexError as e:
            LOG.warn('Unknown output from "ps -ef"?: "{}"\n{}'.format(line, e))

    assert process_info, 'Failed to find nova processes'

    unique_names = set(names)
    names_found = set([p[2] for p in process_info])

    assert unique_names.issubset(names_found), \
        'Not all processes are alive on the active controller, expected: "{}", actual:"{}"'.format(names, names_found)

    return process_info


def get_nova_logs(action='APPLY', names=None, fail_on_not_found=True, start_time=None, max_lines=100, con_ssh=None):
    if action != 'APPLY':
        LOG.info('Only APPLY supported now')
        return []

    log_pattern = IMPACTS_ON_SYSTEM['INSVC_NOVA']['log_record']
    base_command = '\egrep \'{}\' {} 2>/dev/null | tail -n {}'

    start_time_stamp = datetime.strptime(start_time, LOG_DATETIME_FORMAT) if start_time else None

    log_records = []
    for name in names:
        log_name = os.path.join(BASE_LOG_DIR, 'nova', '{}.log'.format(name))
        command = base_command.format(log_pattern, log_name, max_lines)

        output = run_cmd(command, fail_ok=False, con_ssh=con_ssh)[1]

        for line in output.splitlines():
            try:
                log_time = datetime.strptime(line.split('\.')[0], LOG_DATETIME_FORMAT)

                service_name = re.search(log_pattern, line).group(1)

                if not start_time_stamp or start_time_stamp <= log_name:
                    log_records.append((service_name, log_time))

            except IndexError as e:
                LOG.warn('Unknown nova log line:"{}"\n{}'.format(line, e))
            except Exception as e:
                LOG.warn('Unknown nova log line:"{}"\n{}'.format(line, e))

    assert fail_on_not_found and not log_records, 'No nova log records found'

    LOG.info('OK, found nova log records:{}'.format(log_records))

    return log_records


def get_active_controller_state(action='APPLY',
                                patch_type='INSVC_NOVA',
                                including_logs=True,
                                start_time=None,
                                fail_on_not_found=False,
                                con_ssh=None):
    """

    Args:
        action:
        patch_type:
        including_logs:
        start_time:
        fail_on_not_found:
        con_ssh:

    Returns:

    """
    if action != 'APPLY':
        LOG.info('Only APPLY supported now')
        return []

    if patch_type in IMPACTS_ON_SYSTEM:
        process_names = list(IMPACTS_ON_SYSTEM[patch_type]['processes'])

        process_info = get_process_info(names=process_names, con_ssh=con_ssh)

        log_records = []
        if including_logs:
            log_records = get_nova_logs(action=action,
                                        names=process_names,
                                        start_time=start_time,
                                        fail_on_not_found=False,
                                        con_ssh=con_ssh)
            assert not log_records or not fail_on_not_found, 'No log records found for nova'

        return process_info, log_records

    return {}


def check_active_controller_state(action='APPLY',
                                  previous_state=None,
                                  patch_type='INSVC_NOVA',
                                  start_time=None,
                                  con_ssh=None):
    if action != 'APPLY' and patch_type != 'INSVC_NOVA':
        LOG.info('Only APPLY supported now')
        return []

    previous_processes = []
    if previous_state:
        previous_processes = previous_state[0]

    current_processes, current_logs = get_active_controller_state(patch_type='INSVC_NOVA',
                                                                  start_time=start_time,
                                                                  fail_on_not_found=True,
                                                                  con_ssh=con_ssh)
    previous_pids = set(p[0] for p in previous_processes)
    current_pids = set(p[0] for p in current_processes)
    common_process = previous_pids.intersection(current_pids)

    assert not common_process, 'Some process of name is not recreated?, previous:{}, current:{}'.format(
            previous_processes, current_processes)


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
                LOG.warn('ill-formatted log line:\n"{}"\n{}\n'.format(line, e))

            except Exception as e:
                LOG.warn('unknown log line:\n"{}"\n{}\n'.format(line, e))
    else:
        LOG.warn('Not yet support searching log entries for action: "{}"'.format(action))
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
            LOG.warn('No all patches logged, expecting:"{}", actual:"{}"'.format(
                set(expected_patches), set(patches_logged)))
            LOG.warn('Missed log files:\n{}\n'.format(set(expected_patches) - set(patches_logged)))
            LOG.warn('Differences: \n{}\n'.format(set(expected_patches) ^ set(patches_logged)))
            all_logged = False

        return all_logged, patches_logged

    else:
        return False, []


def repeat(times=5, wait_per_iter=10, expected_code=0, expected_hits=2, stop_codes=(),
           wait_first=False, show_progress=False, message='', verbose=False):

    def wrapper(func):

        @functools.wraps(func)
        def wrapped_func(*args, **kw):

            if wait_first:
                time.sleep(wait_per_iter)

            cnt = 0
            hit_cnt = 0
            output = ''
            previous_code = 0

            wait_for_check = wait_per_iter
            while cnt < times:
                cnt += 1
                code, output = func(*args, **kw)
                if code != previous_code:
                    LOG.warning('not stabilized yet: previous code: {}, current code:{}'.format(previous_code, code))
                    if hit_cnt > 0:
                        # US100411 US93673 US94532
                        LOG.error('not stabilized after hit expected-code:{} times, ' +
                                  'previous code: {}, current code:{}'.format(previous_code, code))
                    previous_code = code

                if code == expected_code:
                    hit_cnt += 1
                    LOG.info('{}: hits {} for expected code {} at iteration {}'.format(message, hit_cnt, code, cnt))
                    if hit_cnt >= expected_hits:
                        return code, output
                elif code in stop_codes:
                    LOG.info('{}: hit stop code {} at iteration {}'.format(message, stop_codes, cnt))
                    return code, output

                if verbose or (show_progress and cnt % 5 == 0):
                    LOG.info('{}: continue to wait for code {}, found code {} output {}'.format(
                        message, expected_code, code, output))

                if hit_cnt < 1 and wait_for_check < 180:
                    wait_for_check = wait_per_iter * cnt

                time.sleep(wait_for_check)
            return -1, output

        return wrapped_func

    return wrapper


def run_cmd(cmd, con_ssh=None, **kwargs):
    ssh_client = con_ssh or ControllerClient.get_active_controller()
    if isinstance(ssh_client, list):
        LOG.info('ssh_client is a LIST:{}'.format(ssh_client))
        ssh_client = ssh_client[0]

    return ssh_client.exec_cmd(cmd, **kwargs)


def run_sudo_cmd(cmd, con_ssh=None, **kwargs):
    ssh_client = con_ssh or ControllerClient.get_active_controller()
    if isinstance(ssh_client, list):
        LOG.info('ssh_client is a LIST:{}'.format(ssh_client))
        ssh_client = ssh_client[0]

    return ssh_client.exec_sudo_cmd(cmd, **kwargs)


def get_track_back(log_file='patching.log', con_ssh=None):
    command = '\grep -i "traceback" {} 2>/dev/null'.format(os.path.join(BASE_LOG_DIR, log_file))
    patching_trace_backs = run_cmd(command, con_ssh=con_ssh)[1]

    return [record.strip() for record in patching_trace_backs.splitlines()]


def check_error_states(con_ssh=None, pre_states=None, pre_trace_backs=None, no_checking=True, fail_on_error=False):
    states = get_system_patching_states(con_ssh=con_ssh)

    trace_backs = get_track_back(con_ssh=con_ssh)

    if no_checking:
        return states, trace_backs
    else:
        for tb in trace_backs:
            if tb not in pre_trace_backs:
                LOG.warn('New traceback found in patching log:{}'.format(tb))
                assert not fail_on_error, 'New traceback found:{}'.format(tb)

        alarms_tab = states['alarms']
        new_alarms = [alarm for alarm in alarms_tab if alarm not in pre_states['alarms']]

        if len([alarm for alarm in new_alarms if PATCH_ALARM_ID not in alarm]) > 0:
            LOG.warn('Unknown non-patching alarms found:\n{}'.format(new_alarms))

    return states, trace_backs


def run_patch_cmd(cmd, args='', con_ssh=None, fail_ok=False, timeout=600):

    assert cmd in PATCH_CMDS, 'Unknown patch command:<{}>'.format(cmd)

    ssh_client = con_ssh or ControllerClient.get_active_controller()
    if isinstance(ssh_client, list):
        LOG.info('ssh_client is a LIST:{}'.format(ssh_client))
        ssh_client = ssh_client[0]

    cmd_info = PATCH_CMDS.get(cmd)
    command = 'sw-patch {} {}'.format(cmd_info['cmd'], args)
    code, output = ssh_client.exec_sudo_cmd(command, fail_ok=fail_ok, expect_timeout=timeout)

    result_patterns = cmd_info.get('result_pattern')
    if not result_patterns:
        return code, output, 0

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

    return code, results, matched


def is_file(filename, con_ssh=None):
    if not filename:
        return False

    code = run_cmd('test -f {}'.format(filename), con_ssh=con_ssh, fail_ok=True)[0]

    return 0 == code


def is_dir(dirname, con_ssh=None):
    if not dirname:
        return False

    code = run_cmd('test -d {}'.format(dirname), con_ssh=con_ssh, fail_ok=False)[0]

    return 0 == code


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

    """
    if not patch_dir or not is_dir(dirname=patch_dir, con_ssh=con_ssh):
        LOG.info('Not a directory:{}'.format(patch_dir))
        return -2, []

    patch_ids_in_dir = get_patch_ids_from_dir(patch_dir=patch_dir, con_ssh=con_ssh)
    if not patch_ids_in_dir:
        LOG.info("No patch found in directory: {}".format(patch_dir))
        return -2, []

    assert check_patches_version(patch_ids_in_dir, con_ssh=con_ssh), \
        'Mismatched versions between patch files and system image load'
    patch_states = get_patches_states(con_ssh=con_ssh)[1]

    patches_to_upload = list(set(patch_ids_in_dir) - set(patch_states.keys()))

    patches_to_skip = list(set(patch_ids_in_dir) & set(patch_states.keys()))
    if len(patches_to_upload) < len(patch_ids_in_dir):
        LOG.warn('Some patches already in system: {}'.format(patches_to_skip))

    LOG.info('Patches to upload: {}'.format(patches_to_upload))
    patches_uploaded = []
    for p in patches_to_skip:
        if patch_states[p]['state'].lower() == 'available':
            patches_uploaded.append(p)

    if not patches_to_upload:
        LOG.info("All patches in dir already in system. Patches in Available state: {}".format(patches_uploaded))
        return -1, patches_uploaded
    # time_before = datetime.now()
    time_before = lab_time_now()[0]

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


def wait_for_hosts_states(expected_states=None, con_ssh=None):
    if expected_states:
        return 0, None

    for host, expected_state in expected_states.items():
        code, state = wait_host_states(host, expected_states=expected_state, con_ssh=con_ssh)
        assert 0 == code, \
            'Host:{} failed to reach state: "{}"\nactual states: "{}"'.format(host, expected_state, state)
        LOG.info('OK, host: {} reach state: {} as expected: {}'.format(host, state, expected_state))

    return 0, expected_states


def wait_for_patches_states(patch_ids, expected_states=None, con_ssh=None):
    if not patch_ids or not expected_states:
        return 0, []

    for pid in patch_ids:
        expected_state = expected_states[pid]
        LOG.info('Wait for patch: "{}" reaches states: "{}"'.format(pid, expected_state))
        code, state = wait_for_patch_state(pid, expected=[expected_state], con_ssh=con_ssh)
        assert 0 == code, \
            'Patch:{} failed to reach state: {} after apply, actual states:{}'.format(pid, expected_state, state)
    return 0, patch_ids


def delete_patches(patch_ids=None, con_ssh=None):
    LOG.info('Deleting patches: "{}"'.format(patch_ids))
    if not patch_ids:
        return []

    time_before = lab_time_now()[0]

    args = ' '.join(patch_ids)
    code, patch_info, _ = run_patch_cmd('delete', args=args, con_ssh=con_ssh)
    assert 0 == code, 'Failed to delete patch(es):{}'.format(args)

    assert check_if_patches_exist(patch_ids=patch_ids, expecting_exist=False, con_ssh=con_ssh)

    found, patches = check_log_records(action='delete',
                                       start_time=time_before,
                                       expected_patches=patch_ids,
                                       con_ssh=con_ssh)
    assert found, 'Failed to find log records for deleting patches: {}'.format(patch_ids)

    LOG.info('OK, deleted patches: "{}"'.format(patch_ids))

    return code, patch_info


def delete_patch(patch_id, con_ssh=None):
    LOG.info('deleting patch:{}'.format(patch_id))
    code, deleted_ids = delete_patches([patch_id], con_ssh=con_ssh)

    return code, deleted_ids[0]


def upload_patch_file(patch_file=None, con_ssh=None, fail_if_existing=False, attempt_to_delete=False):
    if not patch_file:
        return ''

    code, patch_info, _ = run_patch_cmd('upload', args=patch_file, con_ssh=con_ssh)
    assert code in [0, 1], 'Failed to upload patch:{}, code:{}'.format(patch_file, code)

    if 0 == code:
        LOG.info('OK, patch file: "{}" uploaded'.format(patch_file))
        return patch_info[0][0][0]

    assert not fail_if_existing,\
        'Patch:{} is already installed'.format(patch_file)

    patch_id = patch_info[0][0][0]

    if 1 == code:
        LOG.info('Already exiting, patch: "{}"'.format(patch_id))

    if attempt_to_delete:
        delete_patch(patch_info[0][0][0], con_ssh=con_ssh)

        code, patch_info, _ = run_patch_cmd('upload', args=patch_file, con_ssh=con_ssh)
        assert 0 == code, 'Failed to upload patch:{}, code:{}, after deleting existing one'.format(patch_file, code)

        assert 1 == len(patch_info), 'Failed to upload files:{}, patch-ids loaded:{}'.format(patch_file, patch_info)

        LOG.info('OK, patch file:{} is uploaded, patch-id:{}'.format(patch_file, patch_id))

    return patch_id


def upload_patch_files(files=None, con_ssh=None):
    files = files if isinstance(files, list) else []

    valid_files = []
    expected_patch_ids = []
    existing_patch_ids = get_all_patch_ids(con_ssh=con_ssh)
    expected_to_fail = []
    for file in files:
        if is_file(file, con_ssh=con_ssh):
            patch_id = get_patch_id_from_file(file)
            if not patch_id:
                LOG.warn('Failed to get PATCH ID from PATCH file:{}'.format(file))

            else:
                valid_files.append((patch_id, file))

                if patch_id in existing_patch_ids:
                    expected_to_fail.append(patch_id)
                    LOG.warn('Patch: "{}" already existing, upload again will be rejected'.format(patch_id))

                else:
                    expected_patch_ids.append(patch_id)

    if not valid_files:
        LOG.warn('No valid patch files could be uploaded: "{}"'.format(files))
        return None

    # time_before = datetime.now()
    time_before = lab_time_now()[0]

    return_ids = []
    for patch_id, patch_file in valid_files:
        # Negative testcases included: already existing PATCHes are re-uploaded again
        uploaded_id = upload_patch_file(patch_file=patch_file,
                                        fail_if_existing=(patch_id not in expected_to_fail),
                                        con_ssh=con_ssh)
        assert patch_id == uploaded_id, 'Failed to upload patch file: "{}"'.format(patch_file)
        return_ids.append(uploaded_id)

    if len(expected_patch_ids) > 0:
        if len(expected_to_fail) > 0:
            LOG.warn('Some patches files: "{}" already in system'.format(expected_to_fail))

    else:
        if len(expected_to_fail) > 0:
            LOG.warn('All patches files: "{}" already in system'.format(expected_to_fail))
        return None

    code, expected_patches = check_patches_uploaded(expected_patch_ids, con_ssh=con_ssh)

    assert 0 == code, \
        'Failed to confirm all patches were actually uploaded, checked patch ids:{}'.format(expected_patch_ids)

    uploaded, patches = check_log_records(action='upload',
                                          expected_patches=expected_patch_ids,
                                          start_time=time_before,
                                          con_ssh=con_ssh)
    assert uploaded, 'Log records for upload patch files not found:{}, output: {}'.format(files, patches)

    return tuple(return_ids)


def get_expected_patch_states(action='upload', patch_ids=None, pre_patches_states=None, con_ssh=None):
    # heuristic codes trying to figure out the next state of patches
    if not patch_ids or not pre_patches_states:
        return {}

    action = action.upper()
    expected_states = {}

    if action == 'UPLOAD':
        expected_states = {patch_id: 'Available' for patch_id in patch_ids if patch_id not in pre_patches_states}
        expected_states.update({patch_id: pre_patches_states[patch_id]['state'] for patch_id in pre_patches_states})
        return expected_states

    default_action_states = {
        'APPLY': 'Partial-Apply',
        'REMOVE': 'Partial-Remove',
        'HOST_INSTALL': 'Applied',
    }
    is_storage_lab = len(system_helper.get_storage_nodes(con_ssh=con_ssh)) > 0

    for patch_id in pre_patches_states:
        if 'FAILURE' in patch_id:
            pass

        if patch_id not in patch_ids:
            continue

        elif 'STORAGE' in patch_id and not is_storage_lab:
            if action == 'APPLY':
                # final state
                expected_states[patch_id] = 'Applied'

            elif action == 'REMOVE':
                # final state
                expected_states[patch_id] = 'Available'
        else:
            previous_state = pre_patches_states[patch_id]['state']
            if action == 'APPLY':
                if previous_state == 'Available':
                    expected_states[patch_id] = 'Partial-Apply'
                elif previous_state == 'Partial-Remove':
                    expected_states[patch_id] = 'Available'
                else:
                    LOG.warn('Cannot "{}" patch: "{}" while it is now in: "{}" states'.format(
                        action, patch_id, previous_state))

            elif action == 'REMOVE':
                if previous_state == 'Applied':
                    expected_states[patch_id] = 'Partial-Remove'
                elif previous_state == 'Partial-Apply':
                    expected_states[patch_id] = 'Available'
                else:
                    LOG.warn('Cannot "{}" patch: "{}" while it is now in: "{}" states'.format(
                        action, patch_id, previous_state))

            elif action == 'HOST_INSTALL':
                if previous_state == 'Partial-Apply':
                    expected_states[patch_id] = 'Applied'
                elif previous_state == 'Partial-Remove':
                    expected_states[patch_id] = 'Available'
                else:
                    LOG.warn('Cannot "{}" patch: "{}" while it is now in: "{}" states'.format(
                        action, patch_id, previous_state))

        if patch_id not in expected_states:
            if action in default_action_states:
                expected_states[patch_id] = default_action_states[action]
            else:
                LOG.info('Unknown patch-action: "{}"'.format(action))

    return expected_states


def get_expected_hosts_states(action, patch_ids=None, pre_hosts_states=None, pre_patches_states=None, con_ssh=None):
    if not action or not patch_ids or not pre_hosts_states or not pre_patches_states:
        LOG.warning('No action is specified')
        return 0, {}

    action = action.upper()
    if action == 'UPLOAD':
        # no impact on host states
        return 0, {}
    elif action == 'DELETE':
        # no impact on host states
        return 0, {}
    elif action == 'APPLY' or action == 'REMOVE':
        impacted_host_types = []
        reboot_required = False

        for patch_id in patch_ids:
            if '_RR_' in patch_id:
                reboot_required = True

            if '_NOVA' in patch_id:
                impacted_host_types.append('COMPUTE')
                impacted_host_types.append('CONTROLLER')

            if '_CONTROLLER' in patch_id:
                impacted_host_types.append('CONTROLLER')

            if '_COMPUTE' in patch_id:
                impacted_host_types.append('COMPUTE')

            if '_STORAGE' in patch_id:
                impacted_host_types.append('STORAGE')

            if '_ALLNODES' in patch_id:
                impacted_host_types.append('COMPUTE')
                impacted_host_types.append('CONTROLLER')
                impacted_host_types.append('STORAGE')

            if '_LARGE' in patch_id:
                reboot_required = True

        controllers, computes, storages = system_helper.get_hosts_by_personality(con_ssh=con_ssh)
        hosts_per_types = {'CONTROLLER': controllers, 'COMPUTE': computes, 'STORAGE': storages}

        expected_states = {}
        for host in pre_hosts_states:
            for host_type, hosts in hosts_per_types.items():

                if host in hosts and host_type in impacted_host_types:
                    patch_current = False

                    if not pre_hosts_states[host]['patch-current']:
                        if action == 'APPLY' \
                                and all(state['state'] == 'Partial-Remove' for state in pre_patches_states.values):
                            patch_current = True
                        elif action == 'REMOVE' \
                                and all(state['state'] == 'Partial-Apply' for state in pre_patches_states.values):
                            patch_current = True

                    expected_states[host] = {
                        'rr': reboot_required,
                        'patch-current': patch_current
                    }
        LOG.info('expected hosts states:\n{}'.format(expected_states))

        return 0, expected_states

    elif action == 'HOST-INSTALL' or action == 'HOST-INSTALL-ASYNC':
        return 0, {}

    elif action == 'REMOVE':
        return 0, {}

    return 0, {}


def apply_patches(con_ssh=None, patch_ids=None, apply_all=False, fail_if_patched=True):
    if patch_ids is None or apply_all:
        args = ' --all'
    elif any(patch_id.upper() == 'ALL' for patch_id in patch_ids):
        args = ' --all'
    else:
        args = ' '.join(patch_ids)

    pre_patches_states = get_patches_states(con_ssh=con_ssh)[1]

    pre_hosts_states = get_hosts_states(con_ssh=con_ssh)[1]

    code, patch_info = run_patch_cmd('apply', args=args, con_ssh=con_ssh)[0:2]

    applied_patch_ids = []
    for ids, rtn_code in patch_info:
        applied_patch_ids += ids

        if 0 == rtn_code:
            LOG.info('-OK patch:{} is applied'.format(ids[0]))

        elif 1 == rtn_code:
            if not fail_if_patched:
                LOG.warn('-patch:{} already applied'.format(ids[0]))
            else:
                assert 1 == rtn_code, '-patch:{} already applied'.format(ids[0])

        elif 2 == rtn_code:
            LOG.warn('-ALL patches already applied')

        else:
            LOG.warn('-patch:{} not applied for unknown reason'.format(ids or ''))

    if 0 == len(applied_patch_ids):
        LOG.warn('No patches applied, all of them were already in Apply/Partial-Apply/Partial-Remove status')

    elif set(applied_patch_ids) != set(patch_ids):
        LOG.warn('Some patch(es) failed to apply, applied patches:{}'.format(applied_patch_ids))
        LOG.warn('-attempted to apply patches:{}'.format(patch_ids))

    expected_states = get_expected_patch_states(action='APPLY',
                                                patch_ids=applied_patch_ids,
                                                pre_patches_states=pre_patches_states,
                                                con_ssh=con_ssh)
    for pid in applied_patch_ids:
        expected_state = expected_states[pid]
        LOG.info('Wait for patch: "{}" reaches states: "{}"'.format(pid, expected_state))
        code, state = wait_for_patch_state(pid, expected=[expected_state], con_ssh=con_ssh)
        assert 0 == code, \
            'Patch:{} failed to reach state: {} after apply, actual states:{}'.format(pid, expected_state, state)

    code, expected_hosts_states = get_expected_hosts_states('APPLY',
                                                            patch_ids=applied_patch_ids,
                                                            pre_hosts_states=pre_hosts_states,
                                                            pre_patches_states=pre_patches_states,
                                                            con_ssh=con_ssh)

    assert 0 == code, 'Failed to get expected states of hosts'
    LOG.info('Expected states of hosts: "{}"'.format(expected_hosts_states))

    code, output = wait_for_hosts_states(expected_states=expected_hosts_states, con_ssh=con_ssh)
    assert 0 == code, 'Failed to get expected states of hosts'

    LOG.info('OK, applied patches: "{}" and hosts in expected states'.format(patch_ids))

    return applied_patch_ids


def _patch_parser(output, delimits=None):
    results = []

    if not output:
        return results

    if not delimits:
        delimits = r'([^\s]+)\s*'

    pattern = re.compile(delimits)
    lines = list(output.splitlines())

    if 2 > len(lines):
        LOG.warn('empty Patch Output Table')
        return []

    for line in lines[2:]:
        match = pattern.findall(line)
        results.append(match)

    return results


def _query_output_parser(output):

    results = _patch_parser(output)

    return results


def get_patches_states(con_ssh=None, fail_ok=False):
    code, output = run_patch_cmd('query', con_ssh=con_ssh, fail_ok=fail_ok)[0:2]

    patch_states = _query_output_parser(output)

    patch_id_states = {}
    for patch_id, rr, release, state in patch_states:
        patch_id_states[patch_id] = {'rr': rr == 'Y', 'release': release, 'state': state}

    return code, patch_id_states


def check_if_patches_exist(patch_ids=None, expecting_exist=True, con_ssh=None):
    if not patch_ids:
        return True

    code, patch_id_states = get_patches_states(con_ssh=con_ssh, fail_ok=False)

    if not patch_id_states:
        if expecting_exist:
            assert 'No patches in the system, while {} are expected'.format(patch_ids)

    for patch_id in patch_ids:
        if expecting_exist:
            assert patch_id in patch_id_states, \
                'Patch: {} was NOT uploaded as expected'.format(patch_id)
        else:
            assert patch_id not in patch_id_states, \
                'Patch: {} EXISTING, it should be deleted/not-uploaded'.format(patch_id)

    return True


def get_patches_in_state(expected_states=None, con_ssh=None):
    states = get_patches_states(con_ssh=con_ssh, fail_ok=False)[1]

    if not expected_states:
        return list(states.keys())

    if not isinstance(expected_states, list) and not isinstance(expected_states, tuple):
        expected_states = [expected_states]

    return [patch for patch in states if states[patch]['state'] in expected_states]


def get_patch_states(patch_ids, con_ssh=None, not_existing_ok=True, fail_ok=False):
    states = get_patches_states(con_ssh=con_ssh, fail_ok=fail_ok)[1]

    if not not_existing_ok:
        assert set(patch_ids).issubset(states.keys()), 'Some patches not found'

    return {patch_id: states[patch_id] for patch_id in patch_ids if patch_id in states}


def get_patch_state(patch_id, con_ssh=None):
    patch_id_states = get_patches_states(con_ssh=con_ssh)[1]

    return patch_id_states[patch_id]


def __get_patch_ids(con_ssh=None, expected_states=None):
    _, states = get_patches_states(con_ssh=con_ssh)

    if expected_states is None:
        return list(states.keys())
    else:
        return [patch_id for patch_id in states if states[patch_id]['state'] in expected_states]


def get_partial_applied(con_ssh=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=('Partial-Apply', ))


def get_partial_removed(con_ssh=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=('Partial-Remove', ))


def get_available_patches(con_ssh=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=('Available', ))


def get_all_patch_ids(con_ssh=None, expected_states=None):
    return __get_patch_ids(con_ssh=con_ssh, expected_states=expected_states)


def parse_patch_detail(patch_id, output=''):
    LOG.info('parse_patch_detail: output={}'.format(output))
    lines = output.splitlines()
    start_line = 0
    cnt = 0
    for line in lines:
        # LOG.info('part1 line={}'.format(line))
        if re.match('{}:'.format(patch_id), line):
            start_line = cnt
        cnt += 1

    rpms = []
    for line in lines[start_line+1:]:
        # LOG.info('\n\npart2 line={}\n\n'.format(line))
        if re.match(r'\s*[^\s]*\.rpm', line):
            rpms.append(line.strip())

    return rpms


def get_patch_content(patch_id, con_ssh=None, fail_if_not_exists=True):
    code, output, _ = run_patch_cmd('show', args=patch_id, con_ssh=con_ssh, fail_ok=not fail_if_not_exists)

    assert -1 != code or fail_if_not_exists, 'Patch is not existing'
    LOG.info('get_patch_content: output:{} code={}'.format(output, code))

    rpms = parse_patch_detail(patch_id, output)
    LOG.info('RPM in patch:{} rpms={}'.format(patch_id, rpms))

    return rpms


@repeat(times=6, wait_first=True, message='wait_for_patch_state()')
def wait_for_patch_state(patch_id, expected=('Available',), con_ssh=None):
    state = get_patch_state(patch_id, con_ssh=con_ssh)

    if state['state'] in expected:
        return 0, ''
    else:
        return 1, state


@repeat(times=6, wait_first=True, message='waiting for multiple patches in states:')
def wait_for_patch_states(patch_ids, expected=None, con_ssh=None):
    if not patch_ids:
        return 0, ''

    states = get_patch_states(patch_ids, con_ssh=con_ssh)

    for pid in states.keys():
        if pid not in patch_ids:
            continue
        if states[pid]['state'] != expected[pid]:
            LOG.info('Patch not in expected status, expected: "{}", actual: "{}"'.format(
                expected, states[pid]['state']))
            return 1, states

    return 0, ''


def get_hosts_states(con_ssh=None, fail_ok=False):
    _, output, _ = run_patch_cmd('query-hosts', fail_ok=fail_ok, con_ssh=con_ssh)

    states = _patch_parser(output)

    return 0, {h: {'ip': ip, 'patch-current': pc == 'Yes', 'rr': rr == 'Yes', 'release': release, 'state': state}
               for h, ip, pc, rr, release, state in states}


def get_host_state(host, con_ssh=None):
    _, hosts_states = get_hosts_states(con_ssh=con_ssh)

    return hosts_states.get(host)


def get_hosts_in_states(con_ssh=None, expected_states=None):
    _, states = get_hosts_states(con_ssh=con_ssh)

    LOG.info("hosts states:{}".format(states))
    if expected_states is None:
        return list(states.keys())

    # return [host for host in states if states[host]['state'] in expected_states]
    hosts = []
    for host, state in states.items():
        if all(item in state.items() for item in expected_states.items()):
            hosts.append(host)

    if not hosts:
        LOG.warn('no hosts fund in state: "{}", actual states:"{}"'.format(expected_states, states))
    return hosts


def get_hosts_in_idle(con_ssh=None):
    ready_states = {'patch-current': True, 'rr': False, 'state': 'idle'}
    return get_hosts_in_states(con_ssh=con_ssh, expected_states=ready_states)


def get_personality(host, con_ssh=None):
    table_ = table_parser.table(cli.system('host-show', host, ssh_client=con_ssh))
    subfunc = table_parser.get_value_two_col_table(table_, 'subfunctions')

    personality = table_parser.get_value_two_col_table(table_, 'personality')

    return subfunc + personality


@repeat(times=10, wait_first=True, expected_hits=2, message='wait_for_host_state')
def wait_for_host_state(host, expected, con_ssh=None):
    host_state = get_host_state(host, con_ssh=con_ssh)

    if host_state['state'] == expected:
        return 0, host_state
    else:
        return 1, host_state


@repeat(times=1000, wait_first=True, expected_hits=2, message='wait_for_hosts_states')
def wait_host_states(host, expected_states, con_ssh=None):
    host_state = get_host_state(host, con_ssh=con_ssh)

    for state in expected_states.keys():
        if state not in host_state or expected_states[state] != host_state[state]:
            return 1, host_state
    return 0, host_state


@repeat(times=10, expected_hits=2, wait_per_iter=20, verbose=True, message='waiting for patches in expected status')
def wait_patch_states(patch_ids, expected_states=('Available',), con_ssh=None, fail_on_not_found=False):
    if not patch_ids:
        LOG.warn('No patches to check?')
        return -1, 'No patches to check?'

    cur_patch_states = get_patches_states(con_ssh=con_ssh)[1]
    for patch_id in patch_ids:
        if patch_id in cur_patch_states:
            state = cur_patch_states[patch_id]['state']
            if state not in expected_states:
                LOG.info('at least one Patch:{} is not in expected states:{}, actual state:{}'.format(
                    patch_id, expected_states, cur_patch_states[patch_id]))
                return 1, [patch_id]
        else:
            LOG.info('Patch:{} is not in the system')
            if fail_on_not_found:
                LOG.error('Patch:{} is not loaded in the system'.format(patch_id))
                return -1, [patch_id]

    return 0, patch_ids


def check_patches_uploaded(patch_ids, prev_patch_states=None, con_ssh=None):
    if not patch_ids:
        return 0, []

    if prev_patch_states:
        LOG.info('previous states:{}'.format(prev_patch_states))

    prev_patch_states = prev_patch_states or {}
    for patch_id in patch_ids:
        if patch_id in prev_patch_states:
            prev_state = prev_patch_states[patch_id]
            LOG.warn('Patch already in system, Patch id:{} status:{}'.format(
                patch_id, prev_state
            ))
            if 'Available' != prev_state['state']:
                msg = 'Patch already in system but not in "Available" status, (it is in status:"{}), '
                msg += 'fail the test in this case"'.format(prev_state['state'])
                LOG.warn(msg)
                return 1, [patch_id]

    return wait_patch_states(patch_ids, ('Available',), con_ssh=con_ssh)


@repeat(times=10, expected_hits=3, message='waiting for host to be patch-installed')
def check_host_installed(host, reboot_required=True, con_ssh=None):
    host_state = get_host_state(host, con_ssh=con_ssh)

    if host_state['state'] != 'idle':
        LOG.info('host:{} state:{}, expecting: idle'.format(host, host_state['state']))
        LOG.info('host-state:{}'.format(host_state))
        return 1, host_state

    if reboot_required != host_state['rr']:
        msg = 'host:{} is actually in status '.format(host)
        msg += 'REBOOT-REQUIRED ' if host_state['rr'] else 'IN-SERVICE '
        msg += ', while expecting it is in '
        msg += 'REBOOT-REQUIRED ' if reboot_required else 'IN-SERVICE '

        LOG.info(msg)
        LOG.info('host-state:{}'.format(host_state))
        return 1, host_state

    if not host_state['patch-current']:
        LOG.info('host-state:{}'.format(host_state))
        return 1, host_state

    return 0, ''


def host_install(host, reboot_required=True, fail_if_locked=True,
                 wait_for_state_changed=True, not_unlock=False, con_ssh=None):
    if reboot_required:
        code, msg = host_helper.lock_host(host, con_ssh=con_ssh, fail_ok=False, lock_timeout=1800, timeout=2000)
        LOG.info('lock host: rr={} patch on host={}, locking msg={}'.format(reboot_required, host, msg))
        if -1 == code:
            LOG.warn('host:{} already locked, msg:{}'.format(host, msg))
            if fail_if_locked:
                LOG.warn('-return error code')
                return code, msg
    else:
        LOG.info('no-reboot-required, install rr={} patch on host={}, no need to lock'.format(reboot_required, host))

    if wait_for_state_changed:
        code, output = run_patch_cmd('host-install', args=host, con_ssh=con_ssh, timeout=1200)[0:2]
    else:
        code, output = run_patch_cmd('host-install-async', args=host, con_ssh=con_ssh, timeout=100)[0:2]
        LOG.info('OK, asynchronous install on "{}" command sent'.format(host))

    if 0 != code:
        LOG.warn('host-install returns: code={}, output={}'.format(code, output))

    if not wait_for_state_changed and not_unlock:
        return code, {}

    if wait_for_state_changed:
        code, host_state = check_host_installed(host, reboot_required=reboot_required, con_ssh=con_ssh)
        assert 0 == code, 'Failed to install patches on host:{}, code:{}, it is in state:{}'.format(
            host, code, host_state)

    if reboot_required:
        if not wait_for_state_changed:
            expected_state = {'state': 'idle'}
            code, state = wait_host_states(host, expected_state, con_ssh=con_ssh)
            assert 0 == code, \
                'Host:{} failed to reach states, expected={}, actual={}'.format(host, expected_state, state)

        code, msg = host_helper.unlock_host(host, fail_ok=False, con_ssh=con_ssh)
        LOG.info('unlock rr={} patch on host={}, locking msg={}'.format(reboot_required, host, msg))
        if -1 == code:
            LOG.warn('unlock host:{} failed, msg:{}'.format(host, msg))

    state = None
    if wait_for_state_changed:

        expected_state = {'patch-current': True,
                          'rr': False,
                          'state': 'idle'}

        LOG.info('Wait after host-install, host into states: {}'.format(expected_state))
        code, state = wait_host_states(host, expected_state, con_ssh=con_ssh)
        assert 0 == code, \
            'Host:{} failed to reach states, expected={}, actual={}'.format(host, expected_state, state)

    return code, state


def remove_patches(patch_ids='', con_ssh=None):
    _, pre_patches_states = get_patches_states(con_ssh=con_ssh)
    expected_states = get_expected_patch_states(action='REMOVE',
                                                patch_ids=patch_ids,
                                                pre_patches_states=pre_patches_states,
                                                con_ssh=con_ssh)

    code, output, _ = run_patch_cmd('remove', args=patch_ids, con_ssh=con_ssh, fail_ok=False)

    assert 0 == code, 'Failed to remove patches:{}, \noutput {}'.format(patch_ids, output)

    patch_ids_removed = []
    for patch_ids, rtn_code in output:
        patch_ids_removed += patch_ids

    assert patch_ids_removed, \
        'Failed to remove patches:{}, \npatch_ids_removed {}'.format(patch_ids, patch_ids_removed)

    code, output = wait_for_patch_states(patch_ids, expected=expected_states, con_ssh=con_ssh)

    assert 0 == code, \
        'Patches failed to reach states, patches:{}, expected:{}, actual output:{}, code:{}'.format(
            patch_ids_removed, expected_states, output, code)

    return patch_ids_removed


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


def get_system_patching_states(con_ssh=None, fail_ok=False):
    patch_stats = get_patches_states(con_ssh=con_ssh, fail_ok=fail_ok)[1]
    hosts_stats = get_hosts_states()[1]
    alarms = system_helper.get_alarms()

    return {'host_states': hosts_stats, 'patch_states': patch_stats, 'alarms': alarms}


def match_patch_node_types(host, patch_id, con_ssh=None):
    host_type = get_personality(host, con_ssh=con_ssh)
    patch_info = parse_patch_file_name(patch_id)

    patch_type = patch_info[patch_id]['node_type'].upper()

    LOG.info('patch_type:{}, host_type:{}'.format(patch_type, host_type))

    if patch_type in ['ALLNODES', 'UNKNOWN']:
        return True

    else:
        return host_type.upper() == patch_type


def lab_time_now(con_ssh=None):

    timestamp = run_cmd('date +"%Y-%m-%dT%H:%M:%S.%N"', con_ssh=con_ssh, fail_ok=False)[1]
    with_milliseconds = timestamp.split('.')[0] + '.{}'.format(int(int(timestamp.split('.')[1]) / 1000))
    format1 = LOG_DATETIME_FORMAT + '.%f'
    parsed = datetime.strptime(with_milliseconds, format1)

    return with_milliseconds.split('.')[0], parsed
