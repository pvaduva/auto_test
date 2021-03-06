"""
This module provides helper functions for sw-manager commands
"""

import time

from utils import cli, exceptions
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.stx import OrchestStrategyPhase, OrchStrategyKey, OrchStrategyState
from consts.timeout import OrchestrationPhaseTimeout, HostTimeout
from keywords import common


PHASE_COMPLETION_CHECK_INTERVAL = 20
IGNORED_ALARM_IDS = ['200.001', '700.004', '900.001', '900.005', '900.101']


def create_strategy(orchestration, controller_apply_type=None, storage_apply_type=None,
                    compute_apply_type=None, max_parallel_computes=0, instance_action=None,
                    alarm_restrictions=None, wait_for_completion=True, timeout=None, conn_ssh=None, fail_ok=False):
    """
    Creates a orchestration strategy
    Args:
        orchestration (str): indicates the orchestration strategy type. Choices are  patch or upgrade
        controller_apply_type (str): Valid only for patch orchestration. indicates how the strategy is applied on
            controllers: serial/parallel/ignore.  Default is serial
        storage_apply_type (str): indicates how the strategy is applied on storage hosts. Choices are: serial/parallel/
                                    ignore. Default is serial
        compute_apply_type (str): indicates how the strategy is applied on computes hosts. Choices are: serial/parallel/
                                    ignore.  'parallel' is valid only for patch orchestration. Default is serial.
        max_parallel_computes(int):  indicates the maximum compute hosts to apply strategy in parallel
        instance_action (str): valid only for patch orchestration. Indicates what action to perform on instances.
            Choices are migrate or stop-start. The default is to stop-start
        alarm_restrictions(str): indicates how to handle alarm restrictions based on the management affecting statuses.
            Choices are strict or relaxed. Default is strict.
        wait_for_completion:
        timeout:
        conn_ssh:
        fail_ok:

    Returns: tuple (rc, dict/msg)
        (0, dict) - success
        (1, output) - CLI reject
        (2, err_msg) - strategy build completion timeout
        (3, err_msg) - strategy build completed but with failed state

    """
    if orchestration is None:
        raise ValueError("The orchestration type must be specified: choices are 'patch' or 'upgrade'")

    args_dict = {
        '--storage-apply-type': storage_apply_type,
        '--compute-apply-type': compute_apply_type,
        '--max-parallel-compute-hosts': max_parallel_computes if max_parallel_computes >= 2 else None,
        '--alarm-restrictions': alarm_restrictions,
    }

    cmd = ''
    if orchestration is "patch":
        cmd += "patch-strategy create"
        args_dict['--controller-apply-type'] = controller_apply_type
        args_dict['--instance-action'] = instance_action
    elif orchestration is "upgrade":
        cmd += "upgrade-strategy create"
    else:
        raise exceptions.OrchestrationError("Invalid orchestration type (choices are 'patch' or 'upgrade') specified")

    args = ''
    for key, val in args_dict.items():
        if val is not None and val != '':
            args += ' {} {}'.format(key, val)

    LOG.info("Creating {} orchestration strategy with arguments: {} {}".format(orchestration, cmd, args))
    rc, output = cli.sw_manager(cmd, args, ssh_client=conn_ssh, fail_ok=fail_ok)
    LOG.info("Verifying if the {} orchestration strategy is created".format(orchestration))
    if rc != 0:
        msg = "Create {} strategy failed: {}".format(orchestration, output)
        LOG.warn(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.OrchestrationError(msg)

    if 'strategy-uuid' not in [tr.strip() for tr in output.split(':')]:
        msg = "The {} strategy not created: {}".format(orchestration, output)
        LOG.warn(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.OrchestrationError(msg)

    if wait_for_completion:
        if timeout is None:
            timeout = OrchestrationPhaseTimeout.BUILD

        if not wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.BUILD, timeout, conn_ssh=conn_ssh)[0]:
            msg = "The {} strategy created failed build: {}".format(orchestration, output)
            if fail_ok:
                LOG.warning(msg)
                return 2, msg
            else:
                raise exceptions.OrchestrationError(msg)

    # get values of the created strategy
    results = get_current_strategy_info(orchestration, conn_ssh=conn_ssh)

    if OrchestStrategyPhase.BUILD != results['current-phase']:

        msg = "Unexpected {} strategy phase= {} encountered. A 'build' phase was expected. "\
            .format(orchestration, results["current-phase"])
        if fail_ok:
            LOG.warning(msg)
            return 3, msg
        else:
            raise exceptions.OrchestrationError(msg)

    if "failed" in results["state"]:
        msg = "The {} strategy  'failed' in build phase; reason = {}".format(orchestration, results["build-reason"])
        if fail_ok:
            LOG.warning(msg)
            return 3, msg
        else:
            raise exceptions.OrchestrationError(msg)

    LOG.info("Create {} strategy completed successfully: {}".format(orchestration, results))
    return 0, results


def apply_strategy(orchestration, timeout=OrchestrationPhaseTimeout.APPLY, conn_ssh=None, fail_ok=False):
    """
    applies an orchestration strategy
    Args:
        orchestration (str): indicates the orchestration strategy type. Choices are  patch or upgrade
        timeout (int):

        conn_ssh:
        fail_ok:

    Returns (tuple):
        (0, <actual_states>(dict)) - success  strategy applied successfully
        (1, <std_err>) - CLI command rejected
        (2, <actual_states>(dict)) - Strategy apply failed

    """
    if orchestration not in ('patch', 'upgrade'):
        raise ValueError("The orchestration type (choices are 'patch' or 'upgrade') must be specified")

    # strategy_values = get_current_strategy_values(orchestration)
    if orchestration is "patch":
        cmd = "patch-strategy apply"
    else:
        cmd = "upgrade-strategy apply"

    rc, output = cli.sw_manager(cmd, ssh_client=conn_ssh, fail_ok=fail_ok)

    if rc != 0:
        return 1, output

    res, results = wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.APPLY, timeout=timeout,
                                                  conn_ssh=conn_ssh, fail_ok=True)
    if not res:
        c_phase = results[OrchStrategyKey.CURRENT_PHASE]
        c_compl = results['current-phase-completion']

        if c_phase == OrchestStrategyPhase.APPLY and int(c_compl.strip()[:-1]) > 50:
            LOG.warning('current-phase-completion > 50%, extend wait time for {} strategy to apply'.
                        format(orchestration))
            res, results = wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.APPLY, timeout=timeout,
                                                          conn_ssh=conn_ssh, fail_ok=True)
    if not res:
        msg = "{} strategy failed to apply. Current state: {}".format(orchestration, results[OrchStrategyKey.STATE])
        LOG.warn(msg)
        if fail_ok:
            return 2, results
        else:
            raise exceptions.OrchestrationError(msg)

    if results[OrchStrategyKey.STATE] != OrchStrategyState.APPLIED or \
            results[OrchStrategyKey.APPLY_RESULT] != 'success':
        raise exceptions.OrchestrationError('{} strategy not in applied state after completion'.format(orchestration))

    LOG.info("apply {} strategy completed successfully: {}".format(orchestration, results))
    return 0, results


def delete_strategy(orchestration, check_first=True, fail_ok=False, conn_ssh=None):
    """
    Deletes an orchestration strategy
    Args:
        orchestration (str): indicates the orchestration strategy type. Choices are  patch or upgrade
        conn_ssh:
        check_first (bool): Check if strategy exits, if so, check if strategy is still in-progress, if so, abort it
        fail_ok:

    Returns (tuple):
        (-1, "No strategy available. Do nothing.")
        (0, "<orch_type> orchestration strategy deleted successfully.")
        (1, <std_err>)  # CLI command rejected

    """
    if orchestration is None:
        raise ValueError("The orchestration type (choices are 'patch' or 'upgrade') must be specified")
    cmd = ''
    if orchestration is "patch":
        cmd += "patch-strategy "
    elif orchestration is "upgrade":
        cmd += "upgrade-strategy "

    strategy_info = get_current_strategy_info(orchestration, conn_ssh=conn_ssh)
    if check_first:
        if not strategy_info:
            msg = "No strategy available. Do nothing."
            LOG.info(msg)
            return -1, msg

        if strategy_info.get(OrchStrategyKey.INPROGRESS, None) == 'true':
            LOG.info("Strategy in progress. Abort.")
            strategy_state = strategy_info[OrchStrategyKey.STATE]
            if strategy_state in (OrchStrategyState.APPLYING, OrchStrategyState.BUILDING, OrchStrategyState.INITIAL):
                cli.sw_manager(cmd, 'abort', ssh_client=conn_ssh, fail_ok=False)
                wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.ABORT)
            elif strategy_state == OrchStrategyState.ABORTING:
                wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.ABORT)

    rc, output = cli.sw_manager(cmd, 'delete', ssh_client=conn_ssh, fail_ok=fail_ok)

    if rc != 0:
        return 1, output

    post_strategy_info = get_current_strategy_info(orchestration, conn_ssh=conn_ssh)
    if post_strategy_info:
        raise exceptions.OrchestrationError("{} strategy still exists after deletion: {}".
                                            format(orchestration, post_strategy_info))

    msg = "{} orchestration strategy deleted successfully.".format(orchestration)
    LOG.info(msg)
    return 0, msg


def get_current_strategy_info(orchestration, conn_ssh=None):
    """
    Gets orchestration strategy values
    Args:
        orchestration (str):
        conn_ssh:

    Returns: dict of strategy values

    """

    if orchestration not in ("patch", "upgrade"):
        raise ValueError("Invalid orchestration type (choices are 'patch' or 'upgrade') specified")

    if not conn_ssh:
        conn_ssh = ControllerClient.get_active_controller()

    cmd = ''
    if orchestration is "patch":
        cmd += "patch-strategy show"
    else:
        cmd += "upgrade-strategy show"
    try:
        output = cli.sw_manager(cmd, ssh_client=conn_ssh, fail_ok=False)[1]
    except:
        time.sleep(20)
        if not conn_ssh.is_connected():
            conn_ssh.connect(retry=True)
        output = cli.sw_manager(cmd, ssh_client=conn_ssh, fail_ok=False)[1]

    rtn = {}
    if 'No strategy available' in output:
        return rtn

    for line in output.splitlines():
        k, v = line.strip().split(sep=':', maxsplit=1)
        rtn[k.strip()] = v.strip()

    return rtn


def wait_strategy_phase_completion(orchestration, current_phase, timeout=None, conn_ssh=None, fail_ok=False):
    """
    Waits until the orchestration strategy phase is completed
    Args:
        orchestration (str): - indicates the orchestration type. possible values: upgrade or patch
        current_phase (str): - indicates the current phase of the orchestration. Possible values: build, apply or abort
        timeout (int): - indicates the timeout value to wait for the current phase to complete
        conn_ssh:
        fail_ok:

    Returns (tuple):
        (True, <strategy info>(dict))
        (False, <strategy info>(dict))


    """

    if orchestration is None:
        raise ValueError("The orchestration type (choices are 'patch' or 'upgrade') must be specified")
    elif orchestration is not "patch" and orchestration is not "upgrade":
        raise ValueError("Invalid orchestration type (choices are 'patch' or 'upgrade') specified")

    if not validate_current_strategy_phase(orchestration, current_phase):
        raise exceptions.OrchestrationError("Current {} strategy phase does not match the specified phase={}"
                                            .format(orchestration, current_phase))
    check_interval = PHASE_COMPLETION_CHECK_INTERVAL
    if timeout is not None and timeout < PHASE_COMPLETION_CHECK_INTERVAL:
        timeout = PHASE_COMPLETION_CHECK_INTERVAL
    else:
        if timeout is None:
            if current_phase == OrchestStrategyPhase.BUILD:
                timeout = OrchestrationPhaseTimeout.BUILD
            elif current_phase == OrchestStrategyPhase.APPLY:
                timeout = OrchestrationPhaseTimeout.APPLY
                check_interval = 40
            else:
                timeout = OrchestrationPhaseTimeout.ABORT

    end_time = time.time() + timeout

    output = None
    prev_phase_completion = "0%"

    if conn_ssh is None:
        conn_ssh = ControllerClient.get_active_controller()

    while time.time() < end_time:
        if not conn_ssh.is_connected():
            # ssh connection is lost. Controllers may swact in path application.
            time.sleep(30)
            conn_ssh.connect(retry=True, retry_timeout=HostTimeout.SWACT-30)
            time.sleep(60)
            end_time = end_time + HostTimeout.SWACT

        output = get_current_strategy_info(orchestration, conn_ssh=conn_ssh)
        if output:
            if current_phase == OrchestStrategyPhase.ABORT:
                if output[OrchStrategyKey.STATE] == OrchStrategyState.ABORT_TIMEOUT:
                    msg = '{} strategy abort timed out. Stop waiting for completion.'.format(orchestration)
                    if fail_ok:
                        LOG.warning(msg)
                        return False, output
                    else:
                        raise exceptions.OrchestrationError(msg)

            elif output[OrchStrategyKey.CURRENT_PHASE] == OrchestStrategyPhase.ABORT:
                msg = "{} strategy {} phase is aborted. Stop waiting for completion."\
                    .format(orchestration, current_phase)
                if fail_ok:
                    LOG.warn(msg)
                    return False, output
                else:
                    raise exceptions.OrchestrationError(msg)

            phase_completion = output['current-phase-completion']
            if phase_completion != prev_phase_completion:
                LOG.info("Orchestration current phase completion is at {}".format(phase_completion))
                prev_phase_completion = phase_completion

            if phase_completion == '100%':
                return True, output
            else:
                time.sleep(check_interval)
    else:
        msg = "{} strategy {} phase did not complete within automation timeout {}seconds. Current status: {}"\
            .format(orchestration, current_phase, timeout, output)
        if fail_ok:
            LOG.warn(msg)
            return False, output
        else:
            raise exceptions.OrchestrationError(msg)


def get_current_strategy_phase(orchestration, conn_ssh=None):
    """
    Gets the current strategy phase for the specified orchestration ( upgrade or patch)
    Args:
        orchestration:
        conn_ssh:

    Returns (str):  current phase ( build, apply or abort)

    """
    results = get_current_strategy_info(orchestration, conn_ssh=conn_ssh)
    return results[OrchStrategyKey.CURRENT_PHASE]\
        if OrchStrategyKey.CURRENT_PHASE in results else None


def validate_current_strategy_phase(orchestration, expected_phase, conn_ssh=None):
    """
    Validates the current expected phase
    Args:
        orchestration:
        expected_phase:
        conn_ssh:

    Returns (bool):  True if valid otherwise return False

    """

    if not OrchestStrategyPhase.validate(phase=expected_phase):
        LOG.warn("The specified orchestration strategy phase='{}' is not valid phase. Valid phases are: {}"
                 .format(expected_phase, [OrchestStrategyPhase.BUILD,
                                          OrchestStrategyPhase.ABORT,
                                          OrchestStrategyPhase.APPLY]))
        return False

    current_phase = get_current_strategy_phase(orchestration, conn_ssh=conn_ssh)

    if current_phase is not None and current_phase == expected_phase:
        LOG.info("Current orchestration strategy phase is {} as expected".format(current_phase))
        return True
    else:
        LOG.warn("Current orchestration strategy phase='{}' does not match with expected phase='{}'"
                 .format(current_phase, expected_phase))
        return False


def get_current_strategy_uuid(orchestration):
    """
    Gets the current strategy uuid
    Args:
        orchestration (str): - indicates the orchestration type ( upgrade or patch)

    Returns (str): the uuid of the current orchestration strategy or None if the strategy does not exist

    """
    results = get_current_strategy_info(orchestration)

    uuid = results[OrchStrategyKey.STRATEGY_UUID] \
        if OrchStrategyKey.STRATEGY_UUID in results else None
    LOG.info("{} strategy uuid = {}".format(orchestration, uuid))
    return uuid


def get_current_strategy_details(orchestration, conn_ssh=None):
    """
    Gets orchestration strategy details when successfully applied.
    Args:
        orchestration:
        conn_ssh:

    Returns: dict of strategy values

    """

    if orchestration is None:
        raise ValueError("The orchestration type (choices are 'patch' or 'upgrade') must be specified")
    if orchestration is not "patch" and orchestration is not "upgrade":
        raise ValueError("Invalid orchestration type (choices are 'patch' or 'upgrade') specified")

    cmd = ''
    if orchestration is "patch":
        cmd += "patch-strategy show --details"
    else:
        cmd += "upgrade-strategy show --details"
    try:
        rc,  output = cli.sw_manager(cmd, ssh_client=conn_ssh, fail_ok=True)
    except:
        time.sleep(20)
        if not conn_ssh.is_connected():
            conn_ssh.connect(retry=True)
            ControllerClient.set_active_controller(ssh_client=conn_ssh)

        rc,  output = cli.sw_manager(cmd, ssh_client=conn_ssh, fail_ok=True)

    rtn = {}
    if rc == 0 and output is not None and ('strategy-uuid' in [tr.strip() for tr in output.split(':')]):
        lines = output.splitlines()
        build_phase_index = [i for i, word in enumerate(lines) if "build-phase" in word]
        apply_phase_index = [i for i, word in enumerate(lines) if "apply-phase" in word]
        strategy_lines = []
        build_phase_lines = []
        apply_phase_lines = []
        if len(build_phase_index) > 0:
            strategy_lines.extend(lines[1:build_phase_index[0]])
            if len(apply_phase_index) > 0:
                build_phase_lines.extend(lines[build_phase_index[0]:apply_phase_index[0]])
                apply_phase_lines.extend(lines[apply_phase_index[0]:])
            else:
                build_phase_lines.extend(lines[build_phase_index[0]:])
        else:
            strategy_lines.extend(lines[1:])

        strategy_values = {}
        build_phase_values = {}
        apply_phase_values = {}
        if len(strategy_lines) > 0:
            for line in strategy_lines:
                pairs = line.split(':', 1)
                strategy_values[pairs[0].strip()] = pairs[1].strip()
            rtn['strategy'] = strategy_values
        if len(build_phase_lines) > 0:
            for line in build_phase_lines:
                pairs = line.split(':')
                if pairs[0].strip() == "stages":
                    break
                build_phase_values[pairs[0].strip()] = pairs[1].strip()

            rtn['build'] = build_phase_values

        if len(apply_phase_lines) > 0:
            for line in apply_phase_lines:
                pairs = line.split(':', 1)
                if pairs[0].strip() == "stages":
                    break
                apply_phase_values[pairs[0].strip()] = pairs[1].strip()
            rtn['apply'] = apply_phase_values

    return rtn


def get_current_strategy_phase_duration(orchestration, phase, conn_ssh=None):
    """
    Gets the elapsed time in seconds to execute the specified orchestration strategy phase
    Args:
        orchestration:
        phase:
        conn_ssh

    Returns:

    """
    if orchestration not in ("patch", "upgrade"):
        raise ValueError("Invalid orchestration type (choices are 'patch' or 'upgrade') specified")

    if phase not in ("build", "apply"):
        raise ValueError("Invalid orchestration phase type (choices are 'build' or 'apply') specified")

    duration = None
    strategy_details = get_current_strategy_details(orchestration, conn_ssh=conn_ssh)
    if phase in strategy_details.keys():
        start_date_time = strategy_details[phase]["start-date-time"]
        end_date_time = strategy_details[phase]["end-date-time"]
        duration = common.get_timedelta_for_isotimes(start_date_time, end_date_time)
    return duration.seconds
