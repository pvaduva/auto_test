"""
This module provides helper functions for sw-manager commands
"""

import time

from utils import cli, exceptions
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.cgcs import OrchestStrategyPhase, OrchStrategyKey, OrchStrategyState
from consts.timeout import OrchestrationPhaseTimeout, HostTimeout
from consts.auth import Tenant


PHASE_COMPLETION_CHECK_INTERVAL = 20


def create_strategy(orchestration, controller_apply_type="serial", storage_apply_type="serial",
                    compute_apply_type="serial", max_parallel_computes=0, instance_action="stop-start",
                    alarm_restrictions="strict", wait_for_completion=True, timeout=None, conn_ssh=None, fail_ok=False):
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
        (3, err_msg) - strtegy build completed but with failed state


    """
    if orchestration is None:
        raise ValueError("The orchestration type must be specified: choices are 'patch' or 'upgrade'")

    args_dict = {
        '--storage-apply-type': storage_apply_type,
        '--compute-apply-type': compute_apply_type,
        '--max-parallel-compute-hosts': str(max_parallel_computes) if max_parallel_computes >= 2 else '',
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
    rc, output = cli.sw_manager(cmd, args, ssh_client=conn_ssh,  fail_ok=fail_ok, rtn_list=True)
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
            #timeout = OrchestStrategyPhases.PHASE_COMPLETION_TIMOUT[OrchestStrategyPhases.BUILD]
            timeout = OrchestrationPhaseTimeout.BUILD

        if not wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.BUILD, timeout,
                                              conn_ssh=conn_ssh)[0]:
            msg = "The {} strategy created failed build: {}".format(orchestration, output)
            LOG.warn(msg)
            if fail_ok:
                return 2, msg
            else:
                raise exceptions.OrchestrationError(msg)

    # get values of the created strategy
    results = get_current_strategy_values(orchestration)

    if OrchestStrategyPhase.BUILD != results['current-phase']:

        msg = "Unexpected {} strategy phase= {} encountered. A 'build' phase was expected. "\
            .format(orchestration, results["current-phase"])
        LOG.warn(msg)
        if fail_ok:
            return 3, msg
        else:
            raise exceptions.OrchestrationError(msg)

    if "failed" in results["state"]:
        msg = "The {} strategy  'failed' in build phase; reason = {}".format(orchestration, results["build-reason"])
        LOG.warn(msg)
        if fail_ok:
            return 3, msg
        else:
            raise exceptions.OrchestrationError(msg)

    LOG.info("Create {} strategy completed successfully: {}".format(orchestration, results))
    return 0, results


def apply_strategy(orchestration, wait_for_completion=True, timeout=None, conn_ssh=None, fail_ok=False):
    """
    applies an orchestration strategy
    Args:
        orchestration (str): indicates the orchestration strategy type. Choices are  patch or upgrade
        wait_for_completion:
        timeout:

        conn_ssh:
        fail_ok:

    Returns (tupble):
        (0, dict) - success  strategy applied successfully
        (1, output) - CLI command rejected
        (2, err_msg) - Timeout before the strategy is fully applied
        (3, err_msg) - Strategy apply failed

    """
    if orchestration is None:
        raise ValueError("The orchestration type (choices are 'patch' or 'upgrade') must be specified")

    strategy_values = get_current_strategy_values(orchestration)

    cmd = ''

    if orchestration is "patch":
        cmd += "patch-strategy apply"
    elif orchestration is "upgrade":
        cmd += "upgrade-strategy apply"

    rc, output = cli.sw_manager(cmd, '', ssh_client=conn_ssh,  fail_ok=fail_ok, rtn_list=True)

    if rc != 0:
        msg = " CLI command {} rejected: {}".format(cmd, output)
        LOG.warn(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.OrchestrationError(msg)

    if wait_for_completion:
        if timeout is None:
            timeout = OrchestrationPhaseTimeout.APPLY

        if not wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.APPLY, timeout=timeout,
                                              conn_ssh=conn_ssh, fail_ok=True)[0]:
            msg = "The {} strategy apply phase failed to complete within the specified timeout={}."\
                .format(orchestration, timeout)
            LOG.warn(msg)
            if fail_ok:
                return 2, msg
            else:
                raise exceptions.OrchestrationError(msg)

    # get values of the applied strategy
    results = get_current_strategy_values(orchestration)

    if len(results) == 0:
        msg = "Fail to access the created {} strategy after build completion: {}".format(orchestration, output)
        LOG.warn(msg)
        if fail_ok:
            return 2, msg
        else:
            raise exceptions.OrchestrationError(msg)

    if OrchestStrategyPhase.APPLY != results[OrchStrategyKey.CURRENT_PHASE]:

        msg = "Unexpected {} strategy phase= {} encountered. A 'build' phase was expected. "\
            .format(orchestration, results["current-phase"])
        LOG.warn(msg)
        if fail_ok:
            return 3, msg
        else:
            raise exceptions.OrchestrationError(msg)

    if "failed" in results[OrchStrategyKey.APPLY_RESULT]:
        msg = "The {} strategy  'failed' in apply phase; reason = {}"\
            .format(orchestration, results[OrchStrategyKey.ABORT_REASON])
        LOG.warn(msg)
        if fail_ok:
            return 3, msg
        else:
            raise exceptions.OrchestrationError(msg)

    LOG.info("apply {} strategy completed successfully: {}".format(orchestration, results))
    return 0, results


def delete_strategy(orchestration, conn_ssh=None, abort=True, fail_ok=False):
    """
    Deletes an orchestration strategy
    Args:
        orchestration (str): indicates the orchestration strategy type. Choices are  patch or upgrade

        conn_ssh:
        fail_ok:

    Returns (tupble):
        (0, dict) - success  strategy applied successfully
        (1, output) - CLI command rejected
        (2, err_msg) - Timeout before the strategy is fully applied
        (3, err_msg) - Strategy apply failed

    """
    if orchestration is None:
        raise ValueError("The orchestration type (choices are 'patch' or 'upgrade') must be specified")
    cmd = ''
    if orchestration is "patch":
        cmd += "patch-strategy "
    elif orchestration is "upgrade":
        cmd += "upgrade-strategy "


    strategy_values = get_current_strategy_values(orchestration)
    if len(strategy_values) > 0:

        startegy_state = strategy_values[OrchStrategyKey.STATE] if OrchStrategyKey.STATE in strategy_values else None
        if startegy_state and startegy_state in [OrchStrategyState.APPLYING, OrchStrategyState.BUILDING, OrchStrategyState.BUILDING]:
            if abort:
                cli.sw_manager(cmd + "abort", '', ssh_client=conn_ssh,  fail_ok=fail_ok, rtn_list=True)
                wait_strategy_phase_completion(orchestration, OrchestStrategyPhase.ABORT)
            else:
                msg = " In correct phase cannot be aborted: {}"
                LOG.warn(msg)
                if fail_ok:
                    return 1, msg
                else:
                    raise exceptions.OrchestrationError(msg)


        rc, output = cli.sw_manager(cmd + "delete", '', ssh_client=conn_ssh,  fail_ok=fail_ok, rtn_list=True)

        if rc != 0:
            msg = " CLI command {} rejected: {}".format(cmd, output)
            LOG.warn(msg)
            if fail_ok:
                return 1, msg
            else:
                raise exceptions.OrchestrationError(msg)
        LOG.info("{} : {}".format(output, orchestration))
    else:
        LOG.info("No {} strategy available".format(orchestration))

    return 0, None


def get_current_strategy_values(orchestration, conn_ssh=None):
    """
    Gets orchestration strategy values
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
        cmd += "patch-strategy show"
    else:
        cmd += "upgrade-strategy show"
    try:
        rc,  output = cli.sw_manager(cmd,  ssh_client=conn_ssh, fail_ok=True)
    except:
        time.sleep(20)
        if not conn_ssh._is_connected(fail_ok=True):
            conn_ssh.connect(retry=True)
            ControllerClient.set_active_controller(ssh_client=conn_ssh)
        rc,  output = cli.sw_manager(cmd,  ssh_client=conn_ssh, fail_ok=True)

    rtn = {}
    if rc == 0 and output is not None and ('strategy-uuid' in [tr.strip() for tr in output.split(':')]):
        lines = output.splitlines()
        for line in lines:
            pairs = line.split(':')
            rtn[pairs[0].strip()] = pairs[1].strip()
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

    Returns:
        bool  true/false
        error msg  in case of timeout

    """

    if orchestration is None:
        raise ValueError("The orchestration type (choices are 'patch' or 'upgrade') must be specified")
    if orchestration is not "patch" and orchestration is not "upgrade":
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
        if not conn_ssh._is_connected(fail_ok=True):
            ## ssh connection is lost. Controllers may swact in path application.
            time.sleep(30)
            conn_ssh.connect(retry=True, retry_timeout=HostTimeout.SWACT-30)
            ControllerClient.set_active_controller(conn_ssh)
            time.sleep(60)
            cli.source_openrc_file(conn_ssh, Tenant.ADMIN, '/etc/nova/openrc')
            end_time = end_time + HostTimeout.SWACT

        output = get_current_strategy_values(orchestration, conn_ssh=conn_ssh)
        if len(output) > 0:
            if output[OrchStrategyKey.CURRENT_PHASE] == OrchestStrategyPhase.ABORT:
                msg = "{} strategy {} phase was aborted before specified time: {}"\
                    .format(orchestration, current_phase, output)
                LOG.warn(msg)
                if fail_ok:
                    return False, msg
                else:
                    raise exceptions.OrchestrationError(msg)

            phase_completion = output['current-phase-completion']
            if phase_completion != prev_phase_completion:
                LOG.info("Orchestration current phase completion is at {}".format(phase_completion))
                prev_phase_completion = phase_completion

            if phase_completion == '100%':
                return True, None
            else:
                time.sleep(check_interval)
    else:
        msg = "{} strategy {} phase was not completed in specified time: {}"\
            .format(orchestration, current_phase, output)
        LOG.warn(msg)
        if fail_ok:
            return False, msg
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
    results = get_current_strategy_values(orchestration, conn_ssh=conn_ssh)
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
    results = get_current_strategy_values(orchestration)

    uuid = results[OrchStrategyKey.STRATEGY_UUID] \
        if OrchStrategyKey.STRATEGY_UUID in results else None
    LOG.info("{} strategy uuid = {}".format(orchestration, uuid))
    return uuid
