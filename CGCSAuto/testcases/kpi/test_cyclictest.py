
import os
import re
import time
import random

from pytest import mark, fixture, skip
from consts import build_server, filepaths
from consts.auth import HostLinuxCreds, SvcCgcsAuto
from consts.proj_vars import ProjVar
from consts.cgcs import Prompt
from utils import cli, table_parser, lab_info
from utils.ssh import ControllerClient, SSHFromSSH
from utils.tis_log import LOG
from keywords import common, host_helper, system_helper, patching_helper, glance_helper, nova_helper, vm_helper


CYCLICTEST_EXE = '/folk/svc-cgcsauto/cyclictest/cyclictest'
LOCAL_DIR = '/home/wrsroot/cyclictest/'
HISTGRAM_FILE = 'hist-file'
SHELL_FILE = 'runcyclictest.sh'
RESULT_FILE = 'result'
RUN_LOG = 'runlog'
INCLUDING_RATIO = 0.999999
SKIP_PLATFORM_CPU = True
SKIP_AVS_CPU = False
RT_GUEST_PATH = '/localdisk/loadbuild/jenkins/CGCS_5.0_Guest-rt/CGCS_5.0_RT_Guest/latest_tis-centos-guest-rt.img'
# ./cyclictest -S -p99 -n -m -d0 -H 20 -D 3600
# CYCLICTEST_OPTS_TPMLATE = r'{program} -S -p {priority} -n -m -d {distance} -H {histofall} -l {loops}'

TEST_LOG_DIR = '~/AUTOMATION_LOGS'

cyclictest_conf = {
    'smp': '',
    'priority': 99,
    'nanosleep': '',
    'mlock': '',
    'distance': 0,
    # 'histofall': 20,
    'histofall': 40,
    'histfile': os.path.join(LOCAL_DIR, HISTGRAM_FILE),
    'duration': 30,
    # 'duration': 90,
    # 'duration': 1800,
    # 'duration': 3600,
    # 'duration': 7200,
}

script_file_template = '''
( rm -rf {local_path}/*.txt && \
touch {start_file} && \
{program} &> {run_log} && \
touch {end_file} ) < /dev/null > /dev/null &
'''
runglog_format = r'''^T:\s*(\d+)\s.* Min:\s*(\d+)\s* Act:\s*(\d+)\s* Avg:\s*(\d+)\s* Max:\s*(\d+)'''
result1_len = 5
histfile_format = r'''^\d+(\s+\d+)+\s*'''

testable_hypervisors = {}


@fixture(scope='session', autouse=True)
def prepare_test_session():
    suitable_targets = _check_test_conditions()
    if not suitable_targets:
        skip('Not suitable for cyclictest')
    else:
        _prepare_files()

    return suitable_targets


def get_columns(table, wanted_headers):
    if not isinstance(wanted_headers, list) and not isinstance(wanted_headers, set):
        wanted_headers = [wanted_headers]

    all_headers = table['headers']
    if not set(wanted_headers).issubset(all_headers):
        LOG.error('Unknown column:{}'.format(
            list(set(all_headers) - set(wanted_headers)) + list(set(wanted_headers) - set(all_headers)))
        )
        return []

    selected_column_positions = [i for i, header in enumerate(all_headers) if header in wanted_headers]
    results = []
    for row in table['values']:
        results.append([row[i] for i in selected_column_positions])

    return results


def get_cpu_info(host):
    output = cli.openstack('hypervisor show ' + host, source_admin_=True)
    table = table_parser.table(output)
    cpu_info = table_parser.get_value_two_col_table(table, 'cpu_info')

    cpu_table = system_helper.get_host_cpu_list_table(host)
    thread_ids = get_columns(cpu_table, ['thread'])
    num_threads = len(set(ids[0] for ids in thread_ids))
    LOG.info('per_core_threads:{}'.format(num_threads))

    core_function = get_columns(cpu_table, ['log_core', 'assigned_function'])

    non_vm_cores = {}
    for core, assigned in core_function:
        if assigned != 'VMs' and assigned != 'Shared':
            if assigned in non_vm_cores:
                non_vm_cores[assigned].append(int(core))
            else:
                non_vm_cores[assigned] = [int(core)]

    LOG.info('TODO: non_vm_cores={}'.format(non_vm_cores))
    return eval(cpu_info), num_threads, non_vm_cores, len(core_function)


def _check_test_conditions():
    global testable_hypervisors

    LOG.fixture_step('Check if the lab meets conditions required by this test case')
    hypervisors = host_helper.get_hypervisors()

    for hypervisor in hypervisors:
        personalities = patching_helper.get_personality(hypervisor)
        if not personalities or 'lowlatency' not in personalities:
            continue

        cpu_info, num_threads, non_vm_cores, num_cores = get_cpu_info(hypervisor)

        if cpu_info and 'topology' in cpu_info and cpu_info['topology']['threads'] == 1:
            if num_threads != 1:
                LOG.warn('conflicting infor: num_threads={}, while cpu_info.threads={}'.format(
                    num_threads, cpu_info['topology']['threads']))
            testable_hypervisors[hypervisor] = {
                'personalities': personalities,
                'cpu_info': cpu_info,
                'non_vm_cores': non_vm_cores,
                'num_cores': num_cores,
                'for_host_test': False,
                'for_vm_test': False,
            }
        else:
            LOG.warning('hypervisor:{} is Hyperthreading, ignore it'.format(hypervisor))

    # TODO: more check should be done, including the following setting should be on the target, which however
    # some cannot be easily done automatically
    # Processor Configuration
    # Hyper-Threading = Disabled
    # Power & Performance
    # Policy = Performance
    # Workload = Balanced
    # P-States
    # SpeedStep = Enabled
    # Turbo Boost = Enabled
    # Energy Efficient Turbo = Disabled
    # C-States
    # CPU C-State = Disabled
    # Acoustic and Performance
    # Fan Profile = Performance

    return testable_hypervisors.keys()


def _prepare_files():
    LOG.fixture_step('Make sure the executable of cyclictest exiting, download if not')
    local_path = common.scp_from_test_server_to_active_controller(CYCLICTEST_EXE, LOCAL_DIR)

    LOG.info('cyclictest has been copied to the active controller:{}'.format(local_path))


def _fetch_results(con_target, run_log=None, hist_file=None, active_controller=None):
    LOG.info('Fetch results')

    con_target.scp_on_source(os.path.dirname(run_log) + '/*.txt',
                             HostLinuxCreds.get_user(),
                             active_controller.host,
                             LOCAL_DIR,
                             HostLinuxCreds.get_password(), timeout=1800)

    LOG.info('Close connection to the hypervisor')
    con_target.close()

    assert active_controller.file_exists(run_log), 'Failed to fetch run log to the active controller'
    assert active_controller.file_exists(hist_file), 'Failed to fetch hist_file to the active controller'

    LOG.info('scp from the active controller to local:{}'.format(LOCAL_DIR))
    user = HostLinuxCreds.get_user()
    password = HostLinuxCreds.get_password()
    dest_path = ProjVar.get_var('LOG_DIR') or TEST_LOG_DIR

    common.scp_from_active_controller(os.path.join(os.path.dirname(run_log), '*.txt'),
                                      dest_path=dest_path,
                                      src_user=user,
                                      src_password=password
                                      )
    local_run_log = os.path.join(dest_path, os.path.basename(run_log))
    assert os.path.isfile(local_run_log), 'Failed to fetch run log:{}'.format(run_log)

    local_hist_file = os.path.join(dest_path, os.path.basename(hist_file))
    assert os.path.isfile(local_hist_file), 'Failed to fetch hist-file:{}'.format(hist_file)

    os.rename(local_hist_file, local_hist_file + '.bk')
    os.rename(local_run_log, local_run_log + '.bk')
    os.system('rm -f {}/*.txt'.format(os.path.dirname(local_hist_file)))
    os.rename(local_hist_file + '.bk', local_hist_file)
    os.rename(local_run_log + '.bk', local_run_log)

    return local_run_log, local_hist_file


def _calculate_runlog(run_log, hypervisor_info):
    LOG.info('Calculate and report the results')

    result1 = {}
    pattern1 = re.compile(runglog_format)
    with open(run_log) as f:
        for line in f:
            m = re.match(pattern1, line)
            if m and len(m.groups()) == result1_len:
                cur_tid, cur_min, cur_act, cur_avg, cur_max = m.groups()
                result1[cur_tid] = (cur_min, cur_act, cur_avg, cur_max)
            else:
                pass
                # LOG.info('illformated, ignore:\n{}'.format(line))

    LOG.info('result1:{}'.format(result1))

    non_vm_cores = hypervisor_info['non_vm_cores']
    averages = [int(data[2]) for tid, data in result1.items()
                if tid not in non_vm_cores['Platform'] and
                tid not in non_vm_cores['vSwitch']
                ]
    average = sum(averages) / len(averages)
    LOG.info('Average latency: {} usec'.format(average))
    with open(os.path.join(os.path.dirname(run_log), RESULT_FILE + '-host.txt'), 'a+') as f:
        f.write('\nAverage latency: {} usec\n'.format(average))

    return {'average': average}


def _calculate_histfile(hist_file, hypervisor_info):
    global cyclictest_conf

    LOG.info('Calculate results from hist-file')
    num_item = hypervisor_info['num_cores'] + 2
    pattern2 = re.compile(histfile_format)

    result2 = {}
    totals = []
    with open(hist_file) as f:
        for line in f:
            m = re.match(pattern2, line)
            if m:
                numbers = line.split()
                if len(numbers) == num_item:
                    result2[int(numbers[0])] = [int(n) for n in numbers[1:-1]]
            else:
                m = re.match('^# Total:\s+((\d+\s+)*\d+)\s*$', line)
                if m and len(m.groups()) == 2:
                    totals = [int(n) for n in m.group(1).split()]
                    totals = totals[:-1]
    ignore_ids = []
    if SKIP_PLATFORM_CPU:
        ignore_ids += hypervisor_info['non_vm_cores']['Platform']
    if SKIP_AVS_CPU:
        ignore_ids += hypervisor_info['non_vm_cores']['vSwitch']

    LOG.info('TODO: ignore cpu:{}'.format(ignore_ids))

    accumlated = [[d for i, d in enumerate(result2[0]) if i not in ignore_ids]]
    total_count = sum([t for i, t in enumerate(totals) if i not in ignore_ids])
    LOG.info('TODO: total={}'.format(total_count))

    time_slots = len(result2.keys())
    slot = 0
    for slot in range(1, time_slots):
        LOG.info('\nTODO:us:{}'.format(slot))
        prev_counts = accumlated[slot-1]
        LOG.info('TODO: prev_sums:{}'.format(prev_counts))
        LOG.info('TODO: ignore cpu:{}'.format(ignore_ids))

        vm_cpu_counts = [hit for i, hit in enumerate(result2[slot]) if i not in ignore_ids]
        accumlated.append([hit + prev_counts[i] for i, hit in enumerate(vm_cpu_counts)])

        LOG.info('accumlated[{}]:{}'.format(slot, accumlated[slot]))

        if (sum(accumlated[slot]) * 1.0 / total_count) > INCLUDING_RATIO:
            LOG.info('Reach shreashold:{} at {} usec, {}'.format(
                INCLUDING_RATIO*100, slot, sum(accumlated[slot]) * 1.0 / total_count))
            break
        else:
            LOG.info('TODO: default to: sums[sec]={}'.format(accumlated[slot]))
            LOG.info('usec:{}, sum till this sec:{}'.format(slot, sum(accumlated[slot])))
            LOG.info('total:{}, {}%'.format(total_count, sum(accumlated[slot]) / total_count * 100))
        LOG.info('')
    else:
        LOG.info('Wrong data in histfile:{}'.format(hist_file))

    LOG.info('{}% percentage: {} usec'.format(INCLUDING_RATIO*100, slot))
    with open(os.path.join(os.path.dirname(hist_file), RESULT_FILE + '-hotst.txt'), 'a+') as f:
        f.write('\n{}% percentage: {} usec\n'.format(INCLUDING_RATIO*100, slot))

    return {'usec_for_6nines': slot}


def _calculate_results(active_controller, run_log=None, hist_file=None, target_name=None):
    global testable_hypervisors

    average_latency = _calculate_runlog(run_log, testable_hypervisors[target_name])
    most_lanency = _calculate_histfile(hist_file, testable_hypervisors[target_name])

    return average_latency, most_lanency


def _report_results(active_controller, results):
    LOG.info('Report results')


def _process_results(con_target, run_log=None, hist_file=None, active_controller=None):
    LOG.tc_step('Process results')
    results = _calculate_results(active_controller, run_log=run_log, hist_file=hist_file, target_name=con_target.host)

    _report_results(active_controller, results)


def _wait_for_results(con_target, run_log=None, hist_file=None, duration=60, start_file=None, end_file=None):
    wait_per_checking = max(duration / 20, 120)

    LOG.tc_step('Check the results every {} seconds'.format(wait_per_checking))
    time.sleep(10)
    LOG.info('Check if started to run')
    if start_file:
        for _ in range(5):
            if con_target.file_exists(start_file):
                LOG.info('running')
                break
            time.sleep(2)
        else:
            assert False, 'Not even started?'

    total_timeout = min(duration + 120, 4000)
    end_time = time.time() + total_timeout
    cmd_timeout = max(int(duration / 20), 90)

    while time.time() < end_time:

        if con_target.file_exists(end_file):
            LOG.info('Run completed on {} !!!'.format(con_target.host))
            cmd = 'tail -n 30 {} {}; echo'.format(run_log, hist_file)
            cmd_timeout = max(int(duration/3), 900)
            output = con_target.exec_cmd(cmd, expect_timeout=cmd_timeout)[1]
            LOG.info('\n{}\n'.format(output))
            return True

        else:
            LOG.info('Running ... on ' + con_target.host)
            output = con_target.exec_cmd('tail {}; echo'.format(run_log), expect_timeout=cmd_timeout)[1]
            LOG.info('\n{}\n'.format(output))

        time.sleep(wait_per_checking)

    else:
        LOG.info('Timeout when running on target')
        assert False, 'Timeout when running on target after {} seconds'.format(total_timeout)


def _run_cyclictest(con_target, program, target_host=None, settings=None, active_controller=None):
    LOG.tc_step('On target:{}, run program:{}'.format(target_host, program))

    if settings is None or not isinstance(settings, dict):
        actual_settings = cyclictest_conf
    else:
        actual_settings = settings

    start_time = time.strftime("%Y-%m-%d-%H-%M-%S")
    hist_file = actual_settings.get('histfile', None) + start_time + '.txt'
    actual_settings['histfile'] = hist_file
    run_log = os.path.join(LOCAL_DIR, RUN_LOG) + start_time + '.txt'
    start_file = os.path.join(LOCAL_DIR, 'start-{}.txt'.format(start_time))
    end_file = os.path.join(LOCAL_DIR, 'end-{}.txt'.format(start_time))

    options = ' '.join(('--' + key + ' ' + str(value) for key, value in actual_settings.items()))
    cmd = program + ' ' + options

    LOG.info('-create a temporary shell file to run CYCLICTEST')
    script_file = os.path.join(LOCAL_DIR, SHELL_FILE)
    script_file_content = script_file_template.format(local_path=LOCAL_DIR,
                                                     start_file=start_file,
                                                     end_file=end_file,
                                                     program=cmd,
                                                     run_log=run_log)

    con_target.exec_cmd('echo "{}" > {}'.format(script_file_content, script_file))

    LOG.info('-make the temporary script executable')
    con_target.exec_cmd('chmod +x {} ; cat {}'.format(script_file, script_file))

    LOG.info('-run script:{}'.format(script_file))
    con_target.exec_sudo_cmd('nohup ' + script_file, fail_ok=False)
    duration = actual_settings.get('duration', 60)

    _wait_for_results(con_target,
                      run_log=run_log,
                      hist_file=hist_file,
                      start_file=start_file,
                      end_file=end_file,
                      duration=duration)

    local_run_log, local_hist_file = _fetch_results(con_target,
                   run_log=run_log,
                   hist_file=hist_file,
                   active_controller=active_controller)

    _process_results(con_target, run_log=local_run_log, hist_file=local_hist_file, active_controller=active_controller)


def _cyclictest_on_hypervisor():
    global testable_hypervisors

    LOG.tc_step('Randomly pick one hypervisor to test, {}'.format(testable_hypervisors))

    hypervisors = host_helper.get_hypervisors(state='up', status='enabled')
    LOG.debug('-all up/enabled hypervisors:{}'.format(hypervisors))

    activie_controller = ControllerClient.get_active_controller()

    active_controller_name = activie_controller.host

    candidates = [h for h in testable_hypervisors
                  if not testable_hypervisors[h]['for_host_test'] and not testable_hypervisors[h]['for_vm_test']]

    chosen_hypervisor = random.choice(candidates)
    testable_hypervisors[chosen_hypervisor]['for_host_test'] = True

    # chosen_hypervisor = 'controller-1'
    LOG.info('OK, randomly selected hypervisor:{} to test on'.format(chosen_hypervisor))

    program = os.path.join(os.path.abspath(LOCAL_DIR), os.path.basename(CYCLICTEST_EXE))
    LOG.debug('program={}'.format(program))

    if active_controller_name == chosen_hypervisor:
        con_target = activie_controller
        chosen_hypervisor = system_helper.get_active_controller_name()
        LOG.info('The chosen hypervisor is happened the same as the active controller')
    else:
        LOG.tc_step('Connect to the target hypervisor:{}'.format(chosen_hypervisor))
        inital_prompt = chosen_hypervisor.strip() + r':\~\$'
        con_target = SSHFromSSH(activie_controller,
                                chosen_hypervisor,
                                HostLinuxCreds.get_user(),
                                HostLinuxCreds.get_password(),
                                initial_prompt=inital_prompt)
        con_target.connect(retry=2, timeout=60)
        LOG.info('OK, connected to the target hypervisor:{}'.format(chosen_hypervisor))

        con_target.exec_cmd('rm -rf {}; mkdir {}'.format(LOCAL_DIR, LOCAL_DIR))

        LOG.tc_step('Copy CYCLICTEST to selected hypervisor {}:{}'.format(chosen_hypervisor, program))

        activie_controller.flush()
        con_target.scp_on_dest(HostLinuxCreds.get_user(), active_controller_name,
                               program, program, HostLinuxCreds.get_password())

        LOG.info('Check if CYCLICTEST was copied to target hypervisor')
        assert con_target.file_exists(program), \
            'Failed to find CYCLICTEST executable on target hypervisor after copied'

        LOG.info('-successfully copied to {}:{}'.format(chosen_hypervisor, program))

    _run_cyclictest(con_target, program,
                    target_host=chosen_hypervisor,
                    active_controller=activie_controller)


def _get_rt_guest_image(remote_path=RT_GUEST_PATH, remote=None):
    LOG.info('Scp guet image from the build server')
    active_controller = ControllerClient.get_active_controller()
    remote = remote or build_server.DEFAULT_BUILD_SERVER['ip']
    prompt = '\[{}@.* \~\]\$'.format(SvcCgcsAuto.USER)
    time_stamp = time.strftime("%Y-%m-%d-%H-%M-%S")
    local_path = os.path.join(LOCAL_DIR, 'rt-guest-image_' + time_stamp)
    active_controller.exec_cmd('mkdir ' + local_path)
    assert patching_helper.is_dir(local_path)

    local_image_file = os.path.join(local_path, os.path.basename(remote_path))

    ssh_to_server = SSHFromSSH(active_controller, remote, SvcCgcsAuto.USER, SvcCgcsAuto.PASSWORD, initial_prompt=prompt)
    try:
        ssh_to_server.connect(retry=5)
        scp_cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {} wrsroot@{}:{}'.format(remote_path,
            lab_info.get_lab_floating_ip(), local_image_file)

        ssh_to_server.send(scp_cmd)
        timeout = 60
        output_index = ssh_to_server.expect([ssh_to_server.prompt, Prompt.PASSWORD_PROMPT], timeout=timeout)
        if output_index == 2:
            ssh_to_server.send('yes')
            output_index = ssh_to_server.expect([ssh_to_server.prompt, Prompt.PASSWORD_PROMPT], timeout=timeout)
        if output_index == 1:
            ssh_to_server.send(HostLinuxCreds.get_password())
            output_index = ssh_to_server.expect(timeout=timeout)

        assert output_index == 0, "Failed to scp files from {}:{} to the active controller".format(remote, remote_path)
    finally:
        ssh_to_server.close()

    if patching_helper.is_file(local_image_file):
        LOG.info('real-time guest image is download from {} to the active controller: {}'.format(
            remote, local_image_file))
    else:
        assert False, 'Failed to download file:{} from server:{}'.format(remote_path, remote)

    return local_image_file


def _cyclictest_inside_vm():
    global testable_hypervisors
    LOG.tc_step('Run cyclictest on VM')

    LOG.tc_step('Chose a hypervisor to run from suitable computes:{}'.format(testable_hypervisors.keys()))
    candidates = [h for h in testable_hypervisors
                  if (not testable_hypervisors[h]['for_host_test'] and not testable_hypervisors[h]['for_vm_test'])]

    hypervisor = random.choice(candidates)
    testable_hypervisors[hypervisor]['for_vm_test'] = True
    LOG.info('OK, choose hypervisor {} to run cyclictest'.format(hypervisor))

    vm_id = _create_vm(hypervisor)

    return vm_id, None

def _create_vm(hypervisor):
    global testable_hypervisors
    LOG.tc_step('Run cyclictest on VM hosted on {}'.format(hypervisor))

    LOG.tc_step('Download rt-guest')
    image_file = _get_rt_guest_image()
    LOG.tc_step('OK, image file downloaded:{}'.format(image_file))

    LOG.tc_step('Create the image with the downloaded rt-guest')
    image_name = 'img_' + os.path.splitext(os.path.basename(image_file))[0]
    image_id = glance_helper.create_image(
        source_image_file=image_file,
        name=image_name,
        public=True,
        disk_format='raw',
        container_format='bare',)[1]
    LOG.tc_step('OK, glance image created, id:{}'.format(image_id))

    LOG.tc_step('Create the flavor')
    flavor_id, storage_backing = nova_helper.create_flavor(ram=1024, vcpus=4, root_disk=2,
                                                           storage_backing= 'local_image')[1:3]
    LOG.info('OK, flavor was created, id:{}, backing:{}'.format(flavor_id, storage_backing))

    cpu_info = dict(testable_hypervisors[hypervisor]['cpu_info'])
    extra_specs = {
        'hw:cpu_model': cpu_info['model'],
        'hw:cpu_policy': 'dedicated',
        'hw:cpu_realtime': 'yes',
        'hw:cpu_realtime_mask': '^0',
        'hw:mem_page_size': 2048,
    }
    LOG.tc_step('OK, extra spec set to id:{}\n{}'.format(id, extra_specs))
    nova_helper.set_flavor_extra_specs(flavor_id, **extra_specs)
    LOG.tc_step('OK, flavor was created, id:{}, backing:{}'.format(id, storage_backing))

    LOG.tc_step('Boot the VM on the targeted hypervisor')
    # vm_id = vm_helper.boot_vm(
    #     flavor=flavor_id,
    #     source='image',
    #     source_id=image_id,
    #     vm_host=hypervisor,
    #     fail_ok=False
    # )[1]
    # return vm_id
    return None


@mark.parametrize(
    ('where'), [
        ('on_hypervisor'),
        ('inside_vm'),
        # (on_hypervisor_and_in_vm)
    ]
)
def test_cyclictest(where):
    if where.lower() == 'on_hypervisor':
        LOG.info('Run cyclictest on hypervisor')
        _cyclictest_on_hypervisor()

    elif where.lower() == 'inside_vm':
        LOG.info('Run cyclictest inside a VM')
        _cyclictest_inside_vm()

    else:
        LOG.info('Running cyclictest on:"{}" is not supported'.format(where))
