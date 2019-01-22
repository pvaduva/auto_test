import os
import random
import re
import time

from pytest import fixture, skip, mark

from consts.auth import HostLinuxCreds, SvcCgcsAuto, Tenant
from consts.build_server import DEFAULT_BUILD_SERVER
from consts.cgcs import FlavorSpec, GuestImages
from consts.filepaths import WRSROOT_HOME
from consts.kpi_vars import CyclicTest
from consts.proj_vars import ProjVar
from keywords import common, host_helper, system_helper, patching_helper, glance_helper, nova_helper, vm_helper
from utils import cli, table_parser
from utils.clients.ssh import ControllerClient
from utils.clients.local import LocalHostClient
from utils.kpi import kpi_log_parser
from utils.tis_log import LOG

CYCLICTEST_EXE = '/folk/svc-cgcsauto/cyclictest/cyclictest'
CYCLICTEST_DIR = '/home/wrsroot/cyclictest/'
HISTOGRAM_FILE = 'hist-file'
SHELL_FILE = 'runcyclictest.sh'
RESULT_FILE = 'result'
RUN_LOG = 'runlog'
INCLUDING_RATIO = 0.999999

# RT_GUEST_PATH = '/localdisk/loadbuild/jenkins/CGCS_5.0_Guest-rt/CGCS_5.0_RT_Guest/latest_tis-centos-guest-rt.img'
RT_GUEST_PATH = '/localdisk/loadbuild/jenkins/CGCS_6.0_RT_Guest/latest_tis-centos-guest-rt.img'
BUILD_SERVER = DEFAULT_BUILD_SERVER['ip']

# ./cyclictest -S -p99 -n -m -d0 -H 20 -D 3600
# CYCLICTEST_OPTS_TEMPLATE = r'{program} -S -p {priority} -n -m -d {distance} -H {histofall} -l {loops}'
cyclictest_params = {
    'smp': '',
    'priority': 99,
    'nanosleep': '',
    'mlock': '',
    'distance': 0,
    'histofall': 20,
    'histfile': '{}/{}'.format(CYCLICTEST_DIR, HISTOGRAM_FILE),
    # 'duration': 30,
    'duration': 3600,
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


@fixture(scope='module', autouse=True)
def disable_remote_cli(request):
    if ProjVar.get_var('REMOTE_CLI'):
        ProjVar.set_var(REMOTE_CLI=False)
        ProjVar.set_var(USER_FILE_DIR=WRSROOT_HOME)

        def revert():
            ProjVar.set_var(REMOTE_CLI=True)
            ProjVar.set_var(USER_FILE_DIR=ProjVar.get_var('TEMP_DIR'))
        request.addfinalizer(revert)


@fixture(scope='session')
def prepare_test_session():
    suitable_targets = get_suitable_hypervisors()
    if not suitable_targets:
        skip('Not suitable for cyclictest')

    LOG.fixture_step('Make sure the executable of cyclictest exist, download if not')
    local_path = common.scp_from_test_server_to_active_controller(CYCLICTEST_EXE, CYCLICTEST_DIR)
    LOG.info('cyclictest has been copied to the active controller:{}'.format(local_path))

    return suitable_targets


@fixture(scope='module')
def get_rt_guest_image():
    LOG.info('Scp guest image from the build server')
    con_ssh = ControllerClient.get_active_controller()
    img_path_on_tis = '{}/{}'.format(GuestImages.IMAGE_DIR, GuestImages.IMAGE_FILES['tis-centos-guest-rt'][2])

    if not con_ssh.file_exists(img_path_on_tis):
        con_ssh.scp_on_dest(source_user=SvcCgcsAuto.USER, source_ip=BUILD_SERVER, source_path=RT_GUEST_PATH,
                            dest_path=img_path_on_tis, source_pswd=SvcCgcsAuto.PASSWORD)

    return img_path_on_tis


@fixture(scope='function')
def get_hypervisor():
    global testable_hypervisors

    LOG.fixture_step('Chose a hypervisor to run from suitable computes:{}'.format(testable_hypervisors.keys()))
    candidates = [h for h in testable_hypervisors
                  if (not testable_hypervisors[h]['for_host_test'] and not testable_hypervisors[h]['for_vm_test'])]

    if not candidates:
        skip("No host left for test")

    hypervisor = random.choice(candidates)
    LOG.info("Host chosen: {}".format(hypervisor))
    return hypervisor


def get_cpu_info(hypervisor):
    output = cli.openstack('hypervisor show ' + hypervisor, auth_info=Tenant.get('admin'))
    table = table_parser.table(output)
    cpu_info = table_parser.get_value_two_col_table(table, 'cpu_info')

    cpu_table = system_helper.get_host_cpu_list_table(hypervisor)
    thread_ids = table_parser.get_columns(cpu_table, ['thread'])
    num_threads = len(set(ids[0] for ids in thread_ids))
    LOG.info('per_core_threads:{}'.format(num_threads))

    core_function = table_parser.get_columns(cpu_table, ['log_core', 'assigned_function'])

    non_vm_cores = {}
    for core, assigned in core_function:
        if assigned != 'Applications':   # and assigned != 'Shared':
            if assigned in non_vm_cores:
                non_vm_cores[assigned].append(int(core))
            else:
                non_vm_cores[assigned] = [int(core)]

    LOG.info('non_vm_cores={}'.format(non_vm_cores))
    return eval(cpu_info), num_threads, non_vm_cores, len(core_function)


def get_suitable_hypervisors():
    """
    Get low latency hypervisors with HT-off

    TODO: following settings should checked, but most of them cannot be easily done automatically
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
    # Fan Profile = Performance:

    """
    global testable_hypervisors

    LOG.fixture_step('Check if the lab meets conditions required by this test case')
    hypervisors = host_helper.get_hypervisors()

    for hypervisor in hypervisors:
        personality, subfunc = host_helper.get_hostshow_values(hypervisor, ('personality', 'subfunctions'),
                                                               rtn_list=True)
        personalities = subfunc + personality
        if not personalities or 'lowlatency' not in personalities:
            continue

        cpu_info, num_threads, non_vm_cores, num_cores = get_cpu_info(hypervisor)
        if cpu_info and 'topology' in cpu_info and cpu_info['topology']['threads'] == 1:
            if num_threads != 1:
                LOG.warn('conflicting info: num_threads={}, while cpu_info.threads={}'.format(
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
            LOG.warning('hypervisor:{} has HT-on, ignore it'.format(hypervisor))

    return testable_hypervisors.keys()


def fetch_results_from_target(target_ssh, target_host, active_con_name=None, run_log=None, hist_file=None,
                              is_guest=False):
    """
    Copy results from target hypervisor or vm to active controller, then to local automation dir
    Args:
        target_ssh (SSHClient): hypervisor or vm ssh client
        target_host (str): hypervisor that runs the cyclictest or host of the vm that runs the cyclictest
        active_con_name (str): active controller name, used if is_guest=False.
        run_log (str): runlog path on target
        hist_file (str):  histfile path on target
        is_guest (bool): whether target is hypervisor or vm

    Returns (tuple): (<local_runlog_path> (str), <local_histlog_path> (str))

    """
    LOG.info('Fetch results')
    cyclictest_dir = os.path.dirname(run_log) if run_log else CYCLICTEST_DIR

    con_ssh = ControllerClient.get_active_controller()

    user = HostLinuxCreds.get_user()
    password = HostLinuxCreds.get_password()

    if not run_log:
        run_log = '{}/{}-{}*.txt'.format(cyclictest_dir, RUN_LOG, target_host)
        run_log = target_ssh.exec_cmd('ls {}'.format(run_log), fail_ok=False)[1]

    if not hist_file:
        hist_file = '{}/{}-{}*.txt'.format(cyclictest_dir, HISTOGRAM_FILE, target_host)
        hist_file = target_ssh.exec_cmd('ls {}'.format(hist_file), fail_ok=False)[1]

    target_ssh.exec_sudo_cmd('chmod -R 755 {}/*.txt'.format(cyclictest_dir))
    if not target_host == active_con_name:
        LOG.info("Copy results from target to active controller: {}".format(CYCLICTEST_DIR))
        dest_ip = con_ssh.host if is_guest else active_con_name
        target_ssh.scp_on_source(source_path=cyclictest_dir + '/*.txt', dest_path=CYCLICTEST_DIR, dest_ip=dest_ip,
                                 dest_user=user, dest_password=password, timeout=1800)

        LOG.info("Remove results files from target after scp to active controller")
        target_ssh.exec_cmd('rm -rf {}/*.txt'.format(cyclictest_dir))
        if not is_guest:
            LOG.info("Exit target hypervisor to return to active controller")
            target_ssh.close()

    LOG.info('scp from the active controller to local:{}'.format(cyclictest_dir))
    local_dest_path = '{}/cyclictest/'.format(ProjVar.get_var('LOG_DIR'))
    os.makedirs(local_dest_path, exist_ok=True)

    common.scp_from_active_controller_to_localhost('{}/*.txt'.format(CYCLICTEST_DIR),
                                                   dest_path=local_dest_path,
                                                   src_user=user,
                                                   src_password=password,
                                                   timeout=1800,
                                                   )
    local_run_log = os.path.join(local_dest_path, os.path.basename(run_log))
    assert os.path.isfile(local_run_log), 'Failed to fetch run log:{}'.format(run_log)

    local_hist_file = os.path.join(local_dest_path, os.path.basename(hist_file))
    assert os.path.isfile(local_hist_file), 'Failed to fetch hist-file:{}'.format(hist_file)

    LOG.info("Remove results files from active controller after scp to localhost")
    con_ssh.exec_cmd('rm -f {}/*.txt'.format(cyclictest_dir))

    return local_run_log, local_hist_file


def _calculate_runlog(run_log, cores_to_ignore=None):
    """
    Get Average latency for the cores that need to be measured
    Args:
        run_log (str): local run log path
        cores_to_ignore (list|None): cores to exclude from the calculation, such as non-rt-cores for vm, and
            non-VMs-function cores on hypervisor

    Returns:

    """
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

    LOG.info('result1:{}'.format(result1))

    if not cores_to_ignore:
        cores_to_ignore = []
    averages = [int(data[2]) for tid, data in result1.items() if tid not in cores_to_ignore]
    average = sum(averages) / len(averages)
    LOG.info('Average latency: {} usec'.format(average))
    with open(os.path.join(os.path.dirname(run_log), RESULT_FILE + '-host.txt'), 'a+') as f:
        f.write('Average latency: \t{} usec\n'.format(average))

    return average


def _calculate_histfile(hist_file, num_cores, cores_to_ignore=None):
    global cyclictest_params

    LOG.info('Calculate results from hist-file')
    num_item = num_cores + 2
    pattern2 = re.compile(histfile_format)

    result2 = {}
    totals = []
    overflows = []
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
                else:
                    m = re.match('^# Histogram Overflows:\s+((\d+\s+)*\d+)\s*$', line)
                    if m and len(m.groups()) == 2:
                        overflows = [int(n) for n in m.group(1).split()]
                        overflows = overflows[:-1]

    if not cores_to_ignore:
        cores_to_ignore = []
    LOG.info('ignore cpu:{}'.format(cores_to_ignore))

    accumulated = [[d for i, d in enumerate(result2[0]) if i not in cores_to_ignore]]
    total_count = sum([t for i, t in enumerate(totals) if i not in cores_to_ignore])
    total_count += sum([t for i, t in enumerate(overflows) if i not in cores_to_ignore])
    LOG.info('total={}'.format(total_count))

    time_slots = len(list(result2.keys()))
    LOG.info("Time slots: {}".format(time_slots))
    slot = 0
    for slot in range(1, time_slots):
        prev_counts = accumulated[slot-1]

        vm_cpu_counts = [hit for i, hit in enumerate(result2[slot]) if i not in cores_to_ignore]
        accumulated.append([hit + prev_counts[i] for i, hit in enumerate(vm_cpu_counts)])

        LOG.info('accumulated[{}]:{}'.format(slot, accumulated[slot]))

        if (sum(accumulated[slot]) * 1.0 / total_count) > INCLUDING_RATIO:
            LOG.info('Reach threshold:{} at {} usec, {}'.format(
                INCLUDING_RATIO*100, slot, sum(accumulated[slot]) * 1.0 / total_count))
            break
        else:
            LOG.info('usec:{}, sum till this sec:{}'.format(slot, sum(accumulated[slot])))
            LOG.info('total:{}, {}%'.format(total_count, sum(accumulated[slot]) / total_count * 100))
        LOG.info('')
    else:
        LOG.info('Wrong data in histfile:{}'.format(hist_file))

    LOG.info('{} percentile: {} usec'.format(INCLUDING_RATIO*100, slot))
    with open(os.path.join(os.path.dirname(hist_file), RESULT_FILE + '-host.txt'), 'a+') as f:
        f.write('{} percentile latency: \t{} usec\n'.format(INCLUDING_RATIO*100, slot))

    return slot


def calculate_results(run_log, hist_file, cores_to_ignore, num_cores):

    if isinstance(cores_to_ignore, int):
        cores_to_ignore = [cores_to_ignore]

    average_latency = _calculate_runlog(run_log, cores_to_ignore=cores_to_ignore)
    most_latency = _calculate_histfile(hist_file, cores_to_ignore=cores_to_ignore, num_cores=num_cores)

    return average_latency, most_latency


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


def run_cyclictest(target_ssh, program, target_hypervisor, settings=None, cyclictest_dir=CYCLICTEST_DIR):
    LOG.tc_step('On target: {}, run program: {}'.format(target_hypervisor, program))

    if settings is None or not isinstance(settings, dict):
        actual_settings = cyclictest_params
    else:
        actual_settings = settings

    start_time = time.strftime("%Y-%m-%d-%H-%M-%S")
    run_log = '{}/{}-{}-{}.txt'.format(cyclictest_dir, RUN_LOG, target_hypervisor, start_time)
    hist_file = '{}/{}-{}-{}.txt'.format(cyclictest_dir, HISTOGRAM_FILE, target_hypervisor, start_time)
    actual_settings['histfile'] = hist_file
    start_file = os.path.join(cyclictest_dir, 'start-{}.txt'.format(start_time))
    end_file = os.path.join(cyclictest_dir, 'end-{}.txt'.format(start_time))

    options = ' '.join(('--' + key + ' ' + str(value) for key, value in actual_settings.items()))
    cmd = program + ' ' + options

    LOG.info('-create a temporary shell file to run CYCLICTEST')
    script_file = os.path.join(cyclictest_dir, SHELL_FILE)
    script_file_content = script_file_template.format(local_path=cyclictest_dir,
                                                      start_file=start_file,
                                                      end_file=end_file,
                                                      program=cmd,
                                                      run_log=run_log)

    target_ssh.exec_cmd('echo "{}" > {}'.format(script_file_content, script_file))

    LOG.info('-make the temporary script executable')
    target_ssh.exec_cmd('chmod +x {} ; cat {}'.format(script_file, script_file))

    time.sleep(60)
    LOG.info('-run script:{}'.format(script_file))
    target_ssh.exec_sudo_cmd('nohup ' + script_file, fail_ok=False)
    duration = actual_settings.get('duration', 60)

    _wait_for_results(target_ssh,
                      run_log=run_log,
                      hist_file=hist_file,
                      start_file=start_file,
                      end_file=end_file,
                      duration=duration)

    return run_log, hist_file


def create_rt_vm(hypervisor):
    global testable_hypervisors
    LOG.tc_step('Create/get glance image using rt guest image')
    image_id = glance_helper.get_guest_image(guest_os='tis-centos-guest-rt', cleanup='module')

    vcpu_count = 4
    non_rt_core = 0
    LOG.tc_step('Create a flavor with specified cpu model, cpu policy, realtime mask, and 2M pagesize')
    flavor_id, storage_backing = nova_helper.create_flavor(ram=1024, vcpus=vcpu_count, root_disk=2,
                                                           storage_backing='local_image')[1:3]
    cpu_info = dict(testable_hypervisors[hypervisor]['cpu_info'])
    extra_specs = {
        FlavorSpec.VCPU_MODEL: cpu_info['model'],
        FlavorSpec.CPU_POLICY: 'dedicated',
        FlavorSpec.CPU_REALTIME: 'yes',
        FlavorSpec.CPU_REALTIME_MASK: '^{}'.format(non_rt_core),
        FlavorSpec.MEM_PAGE_SIZE: 2048,
    }
    nova_helper.set_flavor_extra_specs(flavor_id, **extra_specs)

    LOG.tc_step('Boot a VM with rt flavor and image on the targeted hypervisor: {}'.format(hypervisor))
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source='image', source_id=image_id, vm_host=hypervisor,
                              cleanup='function')[1]
    return vm_id, vcpu_count, non_rt_core


def prep_test_on_host(target_ssh, target, file_path, active_controller_name, cyclictest_dir=CYCLICTEST_DIR):
    LOG.tc_step("Copy cyclictest executable to target if not already exist: {}".format(target))
    target_ssh.exec_cmd('mkdir -p {}; rm -f {}/*.*'.format(cyclictest_dir, cyclictest_dir))

    dest_path = '{}/{}'.format(cyclictest_dir, os.path.basename(file_path))
    if not target_ssh.file_exists(dest_path):
        LOG.info('Copy CYCLICTEST to selected host {}:{}'.format(target, dest_path))
        target_ssh.scp_on_dest(HostLinuxCreds.get_user(), active_controller_name, dest_path=dest_path,
                               source_path=file_path, source_pswd=HostLinuxCreds.get_password())

        LOG.info('Check if CYCLICTEST was copied to target host')
        assert target_ssh.file_exists(dest_path), \
            'Failed to find CYCLICTEST executable on target host after copied'

        LOG.info('-successfully copied to {}:{}'.format(target, file_path))


@mark.kpi
def test_kpi_cyclictest_hypervisor(collect_kpi, prepare_test_session, get_hypervisor):
    if not collect_kpi:
        skip("KPI only test.  Skip due to kpi collection is not enabled")

    global testable_hypervisors
    chosen_hypervisor = get_hypervisor
    cpu_info = testable_hypervisors[chosen_hypervisor]
    cpu_info['for_host_test'] = True

    LOG.info('Hypervisor chosen to run cyclictest: {}'.format(chosen_hypervisor))
    active_controller_name = system_helper.get_active_controller_name()
    program = os.path.join(os.path.abspath(CYCLICTEST_DIR), os.path.basename(CYCLICTEST_EXE))
    LOG.debug('program={}'.format(program))

    with host_helper.ssh_to_host(chosen_hypervisor) as target_ssh:
        prep_test_on_host(target_ssh, chosen_hypervisor, program, active_controller_name)
        run_log, hist_file = run_cyclictest(target_ssh, program, target_hypervisor=chosen_hypervisor)

        LOG.info("Process and upload test results")
        local_run_log, local_hist_file = fetch_results_from_target(target_ssh=target_ssh, target_host=chosen_hypervisor,
                                                                   active_con_name=active_controller_name,
                                                                   run_log=run_log, hist_file=hist_file)

    non_vm_cores = sum(list(cpu_info['non_vm_cores'].values()), [])
    num_cores = cpu_info['num_cores']
    avg_val, six_nines_val = calculate_results(run_log=local_run_log, hist_file=local_hist_file,
                                               cores_to_ignore=non_vm_cores, num_cores=num_cores)

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=CyclicTest.NAME_HYPERVISOR_AVG,
                              kpi_val=six_nines_val, uptime=15, unit=CyclicTest.UNIT)
    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=CyclicTest.NAME_HYPERVISOR_6_NINES,
                              kpi_val=six_nines_val, uptime=15, unit=CyclicTest.UNIT)


@mark.kpi
def test_kpi_cyclictest_vm(collect_kpi, prepare_test_session, get_rt_guest_image, get_hypervisor, add_admin_role_func):
    if not collect_kpi:
        skip("KPI only test.  Skip due to kpi collection is not enabled")

    hypervisor = get_hypervisor
    testable_hypervisors[hypervisor]['for_vm_test'] = True
    LOG.info('Hypervisor chosen to host rt vm: {}'.format(hypervisor))

    vm_id, vcpu_count, non_rt_core = create_rt_vm(hypervisor)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    cyclictest_dir = '/root/cyclictest/'
    program = os.path.join(os.path.abspath(cyclictest_dir), os.path.basename(CYCLICTEST_EXE))
    program_active_con = os.path.join(os.path.abspath(CYCLICTEST_DIR), os.path.basename(CYCLICTEST_EXE))
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        prep_test_on_host(vm_ssh, vm_id, program_active_con, ControllerClient.get_active_controller().host,
                          cyclictest_dir=cyclictest_dir)
        run_log, hist_file = run_cyclictest(vm_ssh, program, target_hypervisor=vm_id, cyclictest_dir=cyclictest_dir)

        LOG.info("Process and upload test results")
        local_run_log, local_hist_file = fetch_results_from_target(target_ssh=vm_ssh, target_host=vm_id,
                                                                   run_log=run_log, hist_file=hist_file, is_guest=True)

    avg_val, six_nines_val = calculate_results(run_log=local_run_log, hist_file=local_hist_file,
                                               cores_to_ignore=non_rt_core, num_cores=vcpu_count)

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=CyclicTest.NAME_VM_AVG,
                              kpi_val=avg_val, uptime=15, unit=CyclicTest.UNIT)
    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=CyclicTest.NAME_VM_6_NINES,
                              kpi_val=six_nines_val, uptime=15, unit=CyclicTest.UNIT)
