
import os
import time
import random

from pytest import mark, fixture
from consts.auth import HostLinuxCreds
from consts.proj_vars import ProjVar
from utils.ssh import ControllerClient, SSHFromSSH
from utils.tis_log import LOG
from keywords import common, host_helper, system_helper


CYCLICTEST_EXE = '/folk/svc-cgcsauto/cyclictest/cyclictest'
LOCAL_DIR = '/home/wrsroot/cyclictest/'
HISTGRAM_FILE = 'hist-file'
SHELL_FILE = 'runcyclictest.sh'
RUN_LOG = 'runlog.txt'
# ./cyclictest -S -p99 -n -m -d0 -H 20 -D 3600
# CYCLICTEST_OPTS_TPMLATE = r'{program} -S -p {priority} -n -m -d {distance} -H {histofall} -l {loops}'

TEST_LOG_DIR = '~/AUTOMATION_LOGS'

cyclictest_conf = {
    'smp': '',
    'priority': 99,
    'nanosleep': '',
    'mlock': '',
    'distance': 0,
    'histofall': 20,
    'histfile': os.path.join(LOCAL_DIR, HISTGRAM_FILE),
    'duration': 3600,
    # 'duration': 60,
}

script_file_template = '''
( rm -rf {local_path}/*.txt && \
touch {start_file} && \
{program} &> {run_log} && \
touch {end_file} ) < /dev/null > /dev/null &
'''



@fixture(scope='session', autouse=True)
def prepare_files():
    LOG.fixture_step('Make sure the executable of cyclictest exiting, download if not')
    local_path = common.scp_from_test_server_to_active_controller(CYCLICTEST_EXE, LOCAL_DIR)

    LOG.info('cyclictest has been copied to the active controller:{}'.format(local_path))


def _fetch_results(con_target, run_log=None, hist_file=None, target_host=None):
    LOG.info('Fetch results')
    activie_controller = ControllerClient.get_active_controller()
    activie_controller_name = system_helper.get_active_controller_name()

    LOG.info('scp running log to local:{}'.format(LOCAL_DIR))
    user = HostLinuxCreds.get_user()
    password = HostLinuxCreds.get_password()
    file_suffix = time.strftime("%Y-%m-%d-%H-%M-%S")

    local_run_log_dir = ProjVar.get_var('log_dir')
    if not local_run_log_dir:
        local_run_log_dir = os.path.join(TEST_LOG_DIR, ProjVar.get_var('lab')['short_name'].lower(), strftime('%Y%m%d%H%M'))

    for file in (run_log, hist_file):
        LOG.info('scp hist file to local:{}'.format(LOCAL_DIR))
        con_target.scp_on_source(file, user, activie_controller_name, file + '_' + file_suffix, password, timeout=900)
        activie_controller.file_exists(run_log)
        common.scp_from_active_controller(run_log, local_run_log_dir)

    run_log = run_log + '_' + file_suffix
    hist_file = hist_file + '_' + file_suffix
    return run_log, hist_file


def _calculate_and_report_results(con_target, run_log=None, hist_file=None):
    LOG.tc_step('Calculate and report the results')


def _report_results(con_target, results):
    LOG.info('Report results')


def _process_results(con_target, run_log=None, hist_file=None, target_host=None):
    LOG.tc_step('Process results')
    _fetch_results(con_target, run_log=run_log, hist_file=hist_file, target_host=target_host)
    results = _calculate_and_report_results(con_target, run_log=run_log, hist_file=hist_file)
    _report_results(con_target, results)


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
            LOG.info('Run completed!!!')
            cmd = 'tail -n 30 {} {}; echo'.format(run_log, hist_file)
            cmd_timeout = max(int(duration/3), 900)
            output = con_target.exec_cmd(cmd, expect_timeout=cmd_timeout)[1]
            LOG.info('\n{}\n'.format(output))
            return True

        else:
            LOG.info('Running ...')
            output = con_target.exec_cmd('tail {}; echo'.format(run_log), expect_timeout=cmd_timeout)[1]
            LOG.info('\n{}\n'.format(output))

        time.sleep(wait_per_checking)

    else:
        LOG.info('Timeout when running on target')
        assert False, 'Timeout when running on target after {} seconds'.format(total_timeout)


def _run_cyclictest(con_target, program, target_host=None, settings=None):
    LOG.tc_step('On target, run program:{}'.format(program))

    if settings is None or not isinstance(settings, dict):
        actual_settings = cyclictest_conf
    else:
        actual_settings = settings

    hist_file = actual_settings.get('histfile', None)
    options = ' '.join(('--' + key + ' ' + str(value) for key, value in actual_settings.items()))

    cmd = program + ' ' + options

    run_log = os.path.join(LOCAL_DIR, RUN_LOG)
    script_file = os.path.join(LOCAL_DIR, SHELL_FILE)

    LOG.info('-create a temporary shell file to run CYCLICTEST')
    start_file = os.path.join(LOCAL_DIR, 'start.txt')
    end_file = os.path.join(LOCAL_DIR, 'end.txt')
    # create_script_file = 'rm -rf {}; echo "(rm -rf {}/*.txt && {} > {} &" > {}'.format(script_file, cmd, run_log, script_file)
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

    _process_results(con_target, run_log=run_log, hist_file=hist_file, target_host=target_host)


def _cyclictest_on_hypervisor():
    LOG.tc_step('Randomly pick one hypervisor to test')

    hypervisors = host_helper.get_hypervisors(state='up', status='enabled')
    LOG.debug('-all up/enabled hypervisors:{}'.format(hypervisors))

    activie_controller = ControllerClient.get_active_controller()

    active_controller_name = system_helper.get_active_controller_name()

    chosen_hypervisor = random.choice(hypervisors)
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

    _run_cyclictest(con_target, program, target_host=chosen_hypervisor)


def _cyclictest_inside_vm():
    pass

@mark.parametrize(
    ('where'), [
        ('on_hypervisor'),
        # ('inside_vm')
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
