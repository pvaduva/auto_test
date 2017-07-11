import re
import os
import time
import functools

from consts.timeout import HostTimeout

from utils import cli
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from utils import table_parser
from keywords import host_helper, system_helper

PATCH_CMDS = {
    'apply': {
        'cmd': 'apply',
        'result_pattern': {
            r'([^\s]+) is now in the repo': 0,
            r'([^\s]+) is already in the repo': 1,
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
            r'([^\s]+) has been removed from the repo': 0,
        }
    },
    'upload': {
        'cmd': 'upload',
        'result_pattern': {
            r'([^\s]+) is now available': 0,
            r'([^\s]+) is already imported. Updated metadata only': 1,
            r'Patch ([^\s]+) contains rpm ([^\s]+), which is already provided by patch ([^\s]+)': 2,
            r'RPM ([^\s])+ in ([^\s]+) must be higher version than original.*': 3,
        },
    },
    'requires': {
        'cmd': 'what-requires',
    },
    'delete': {
        'cmd': 'delete',

        'result_pattern': {
            r'([^\s]+) has been deleted': 0,
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
            r'([^\s]+) is now in the repo': 0,
            r'([^\s]+) is already imported. Updated metadata only': 1
        },
    },
}

PATCH_ALARM_ID = '900.001'


def repeat(times=5, wait_per_iter=3, expected_code=0, expected_hits=1, stop_codes=(),
           wait_first=False, show_progress=False, message='', verbose=False):

    def wrapper(func):

        @functools.wraps(func)
        def wrapped_func(*args, **kw):

            if wait_first:
                time.sleep(wait_per_iter)

            cnt = 0
            hit_cnt = 0
            output = ''
            while cnt < times:
                cnt += 1
                code, output = func(*args, **kw)
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

                time.sleep(wait_per_iter)

            return -1, output

        return wrapped_func

    return wrapper


def run_cmd(cmd, con_ssh=None, **kwargs):
    con_ssh = con_ssh or ControllerClient.get_active_controller()
    if isinstance(con_ssh, list):
        con_ssh = con_ssh[0]

    return con_ssh.exec_cmd(cmd, **kwargs)


def get_track_back(log_file='patching.log', con_ssh=None):
    patching_trace_backs = run_cmd('grep -i "traceback" /var/log/{} 2>/dev/null'.format(log_file), con_ssh=con_ssh)[1]
    return [record.strip() for record in patching_trace_backs.splitlines()]


def check_error_states(con_ssh=None, pre_states=None, pre_trace_backs=None, no_checking=True, fail_on_error=False):
    states = get_patching_states(con_ssh=con_ssh)

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


def run_patch_cmd(cmd, args='', con_ssh=None, fail_ok=False, timeout=120):
    assert cmd in PATCH_CMDS, 'Unknown patch comamnd:<{}>'.format(cmd)

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


def is_file(con_ssh=None, filename=''):
    if not filename:
        return False

    code = con_ssh.exec_cmd('test -f {}'.format(filename), ssh_client=con_ssh, fail_ok=True)[0]

    return 0 == code


def is_dir(con_ssh=None, dirname=''):
    if not dirname:
        return False

    code = run_cmd('test -d {}'.format(dirname), con_ssh=con_ssh, fail_ok=False)[0]

    return 0 == code


def get_expected_patch_ids(patch_dir, con_ssh=None):
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
        return [], []

    expected_patch_ids = get_expected_patch_ids(patch_dir=patch_dir, con_ssh=con_ssh)
    assert check_patches_version(expected_patch_ids, con_ssh=con_ssh), \
        'Mismatched versions between patch files and system image load'
    patch_states = get_patches_states(con_ssh=con_ssh)[1]

    if len(set(expected_patch_ids).intersection(set(patch_states.keys()))) > 0:
        LOG.warn('Some patches already uploaded into the system, \n\nto upload:\n{}, \nexisting:\n{}'.format(
            expected_patch_ids, list(patch_states.keys())
        ))

    run_patch_cmd('upload-dir', args=patch_dir, con_ssh=con_ssh)

    code, expected_patches = check_patches_uploaded(
        expected_patch_ids, prev_patch_states=patch_states, con_ssh=con_ssh)
    assert 0 == code, \
        'Failed to confirm all patches were actually uploaded, checked patch ids:{}'.format(expected_patch_ids)

    return expected_patch_ids, patch_states


def delete_patches(patch_ids=None, con_ssh=None):
    LOG.info('deleting patches:{}'.format(patch_ids))
    if not patch_ids:
        return []

    args = ' '.join(patch_ids)
    code, patch_info, _ = run_patch_cmd('delete', args=args, con_ssh=con_ssh)
    assert 0 == code, 'Failed to delete patch(es):{}'.format(args)

    return code, patch_info


def delete_patch(patch_id, con_ssh=None):
    LOG.info('deleting patch:{}'.format(patch_id))
    code, deleted_ids = delete_patches((patch_id,), con_ssh=con_ssh)

    return code, deleted_ids[0]


def upload_patch_file(con_ssh=None, patch_file=None, fail_if_existing=False):
    if not patch_file:
        return ''

    code, patch_info, _ = run_patch_cmd('upload', args=patch_file, con_ssh=con_ssh)
    assert code in [0, 1], 'Failed to upload patch:{}, code:{}'.format(patch_file, code)

    assert 1 != code or not fail_if_existing,\
        'Patch:{} is already installed'.format(patch_file)

    delete_patch(patch_info[0][0][0], con_ssh=con_ssh)

    code, patch_info, _ = run_patch_cmd('upload', args=patch_file, con_ssh=con_ssh)
    assert 0 == code, 'Failed to upload patch:{}, code:{}, after deleting existing one'.format(patch_file, code)

    patch_id = patch_info[0][0][0]

    assert 1 == len(patch_info), 'Failed to upload files:{}, patch-ids loaded:{}'.format(patch_file, patch_info)

    LOG.info('OK, patch file:{} is uploaded, patch-id:{}'.format(patch_file, patch_id))
    return patch_id


def upload_patch_files(con_ssh=None, files=(), warn_if_existing=True):
    valid_files = (f for f in files if is_file(con_ssh=con_ssh, filename=f))

    return_ids = []
    if valid_files:
        args = ' '.join(valid_files)
        code, patch_info, _ = run_patch_cmd('upload', args=args, con_ssh=con_ssh)
        assert 0 == code, 'Failed to upload files:{}'.format(files)

        for patch_ids, rtn_code in patch_info:
            if 0 != rtn_code and warn_if_existing:
                LOG.warn('-Patch already existing, patch-id={}'.format(patch_ids[0]))
            return_ids += patch_ids[0]
    else:
        assert False, 'Failed to upload files:{}, all files are invalid'.format(files)

    return tuple(return_ids)


def get_expected_post_apply_state(patch_id, pre_states, con_ssh=None):
    patch_file_info = parse_patch_file_name(patch_id)
    pre_patch_states = pre_states['patch_states']

    pre_state = pre_patch_states[patch_id]['state']
    if 'Available' != pre_state:
        LOG.warn('Patch is not in "Available" status before apply, it is in stead in status:{}'.format(
            pre_state))
        assert 'Applied' == pre_state, 'Before apply, Patch is not in "Available" nor "Applied", patch_id={}'.format(
            patch_id
        )

    expected_state = 'Partial-Apply'
    patch_node_type = patch_file_info[patch_id]['node_type']
    if patch_node_type == 'STORAGE' and len(system_helper.get_storage_nodes(con_ssh=con_ssh)) <= 0:
        expected_state = 'Applied'
    LOG.info('Post apply: expecting status:{} for patch:{}, node-type:{}'.format(
        expected_state, patch_id, patch_node_type))
    return expected_state


def apply_patches(con_ssh=None, patch_ids=(), pre_states=None, apply_all=True, fail_if_patched=True):
    if 'all' in patch_ids or apply_all:
        args = ' --all'
    else:
        args = ' '.join(patch_ids)

    pre_states = get_patching_states(con_ssh=con_ssh)
    code, patch_info, _ = run_patch_cmd('apply', args=args, con_ssh=con_ssh)
    assert 0 == code, 'Failed to apply patch:{}'.format(patch_ids)

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
            LOG.warn('-patch:{} not applied for unkown reason'.format(ids or ''))

    if 0 == len(applied_patch_ids):
        LOG.warn('No patches applied, all of them were in Apply/Partial-Apply/Partial-Remove status')
    elif set(applied_patch_ids) != set(patch_ids):
        LOG.warn('Some patch(es) failed to apply, applied patches:{}'.format(applied_patch_ids))
        LOG.warn('-attempted to apply patches:{}'.format(patch_ids))

    for pid in applied_patch_ids:
        expected_state = get_expected_post_apply_state(pid, pre_states, con_ssh=con_ssh)

        code, state = wait_for_patch_state(pid, expected=(expected_state,), con_ssh=con_ssh)
        assert 0 == code, \
            'Patch:{} failed to reach state: {} after apply, actual states:{}'.format(pid, expected_state, state)

        if state in ('Applied',):
            # this patch is probably irrelevant
            LOG.warn('Patch:{} reaches "Applied" status before installing'.format(pid))
            del applied_patch_ids[pid]

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
    LOG.info('results={}'.format(results))

    return results


def get_patches_states(con_ssh=None, fail_ok=False):
    code, output = run_patch_cmd('query', con_ssh=con_ssh, fail_ok=fail_ok)[0:2]

    patch_states = _query_output_parser(output)

    patch_id_states = {}
    for patch_id, rr, release, state in patch_states:
        patch_id_states[patch_id] = {'rr': rr == 'Y', 'release': release, 'state': state}

    return code, patch_id_states


def get_patch_states(patch_ids, con_ssh=None, not_existing_ok=True, fail_ok=False):
    states = get_patches_states(con_ssh=con_ssh, fail_ok=fail_ok)[1]

    if not not_existing_ok:
        assert set(patch_ids).issubset(states.keys()), 'Some patches not found'

    return {patch_id: states[patch_id] for patch_id in patch_ids if patch_id in states}


def get_patch_state(patch_id, con_ssh=None):
    patch_id_states = get_patches_states(con_ssh=con_ssh)[1]

    return patch_id_states[patch_id]


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
def wait_for_patch_states(patch_ids, expected=('Available',), con_ssh=None):
    states = get_patch_states(patch_ids, con_ssh=con_ssh)

    for pid in states.keys():
        if states[pid]['state'] not in expected:
            return 1, states
    return 0, ''


def get_hosts_states(con_ssh=None):
    _, output, _ = run_patch_cmd('query-hosts', con_ssh=con_ssh)

    states = _patch_parser(output)

    return 0, {h: {'ip': ip, 'patch-current': pc == 'Yes', 'rr': rr == 'Yes', 'release': release, 'state': state}
               for h, ip, pc, rr, release, state in states}


def get_host_state(host, con_ssh=None):
    _, hosts_states = get_hosts_states(con_ssh=con_ssh)

    return hosts_states.get(host)


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
def wait_for_host_states(host, expected_states, con_ssh=None):
    host_state = get_host_state(host, con_ssh=con_ssh)

    for state in expected_states.keys():
        if state not in host_state or expected_states[state] != host_state[state]:
            return 1, host_state
    return 0, host_state


@repeat(times=10, expected_hits=2, verbose=True, message='waiting for patches in expected status')
def wait_patch_states(patch_ids, expected_states=('Available',), con_ssh=None, fail_on_nonexisting=False):
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
            if fail_on_nonexisting:
                LOG.error('Patch:{} is not loaded in the system'.format(patch_id))
                return -1, [patch_id]

    return 0, patch_ids


def check_patches_uploaded(patch_ids, prev_patch_states=None, con_ssh=None):
    LOG.info('previous states:{}'.format(prev_patch_states))

    for patch_id in patch_ids:
        if patch_id in prev_patch_states:
            prev_state = prev_patch_states[patch_id]
            LOG.warn('Patch already in system, Patch id:{} status:{}'.format(
                patch_id, prev_state
            ))
            assert 'Available' == prev_state['state'], \
                'Patch already in system but not in "Avaiable" status, ' \
                '(it is in status:"{}), fail the test in this case"'.format(prev_state['state'])

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


def host_install(host, reboot_required=True, fail_if_locked=True, con_ssh=None):
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

    code, output = run_patch_cmd('host-install', args=host, con_ssh=con_ssh, timeout=900)[0:2]
    if 0 != code:
        LOG.warn('host-install returns: code={}, output={}'.format(code, output))

    code, host_state = check_host_installed(host, reboot_required=reboot_required, con_ssh=con_ssh)
    assert 0 == code, 'Failed to install patches on host:{}, code:{}, it is in state:{}'.format(host, code, host_state)

    if reboot_required:
        code, msg = host_helper.unlock_host(host, fail_ok=False, con_ssh=con_ssh)
        LOG.info('unlock rr={} patch on host={}, locking msg={}'.format(reboot_required, host, msg))
        if -1 == code:
            LOG.warn('unlock host:{} failed, msg:{}'.format(host, msg))

    expected_state = {'patch-current': True,
                      'rr': False,
                      'state': 'idle'}

    LOG.info('Wait after host-install, host into states: {}'.format(expected_state))
    code, state = wait_for_host_states(host, expected_state, con_ssh=con_ssh)
    assert 0 == code, \
        'Host:{} failed to reach states, expected={}, actual={}'.format(host, expected_state, state)

    return code, state


def remove_patches(patches='', con_ssh=None):
    code, output, _ = run_patch_cmd('remove', args=patches, con_ssh=con_ssh, fail_ok=False)
    LOG.info('args:{} output:{}'.format(patches, output))
    assert output, 'Failed to remove patches:{}, \noutput {}'.format(patches, output)

    patch_ids_remvoed = []
    for patch_ids, rtn_code in output:
        patch_ids_remvoed += patch_ids

    assert patch_ids_remvoed, \
        'Failed to remove patches:{}, \npatch_ids_remvoed {}'.format(patches, patch_ids_remvoed)

    expected_states = ('Partial-Remove', 'Available')
    code, output = wait_for_patch_states(patch_ids_remvoed, expected=expected_states, con_ssh=con_ssh)
    assert 0 == code, \
        'Patches failed to reach states, patches:{}, expected:{}, actual output:{}'.format(
            patch_ids_remvoed, expected_states, output)

    return patch_ids_remvoed


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

    build_id = run_cmd('grep BUILD_ID /etc/build.info  |grep "^BUILD_ID" |  cut -d= -f2',
                       fail_ok=False, con_ssh=con_ssh)[1]
    build_id = build_id.strip('"')
    assert file_date == build_id, \
        'Mismatched patch version and host image version, file date:{}, build id:{}'.format(file_date, build_id)

    return True


def get_patching_states(con_ssh=None, fail_ok=False):
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

