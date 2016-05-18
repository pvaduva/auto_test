###
# TC2196 Verify that alarm can be deleted using CLI
###
import re

from utils import cli
from utils.ssh import ControllerClient
from utils import table_parser
from consts.cgcs import UUID
from consts.auth import Tenant
from consts.timeout import CLI_TIMEOUT
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper


def test_delete_alarm():
    """
    Attempt to delete system alarm with 'system alarm-delete' cli and verify it's working
    sample cli:
        fmClientCli -c "### ###600.005###alarm###system.vm###host=compute-0.vm=$i### ###critical###'oam' port
        ###processing-error###cpu-cycles-limit-exceeded### ###True###True###"
    Args:
        - Nothing

    Setup:
        - setup a sample alarm using fmClientCli command

    Test Steps:
        - delete the sample alarm with the 'system alarm-delete'
        - make sure the alarm was deleted as expected

    Teardown:
        - Nothing

    """
    # create an alarm using fmClientCli
    # TODO command outdate need new command to create alarm
    cmd = "fmClientCli -c '### ###300.005###set###system.vm###host=compute-0.vm=$i### ###critical###Automation test" \
          "###processing-error###cpu-cycles-limit-exceeded### ###True###True###'"


    ssh_client = ControllerClient.get_active_controller()
    LOG.tc_step("Create an critical alarm 300.005")
    exit_code, cmd_output = ssh_client.exec_cmd(cmd, err_only=False, expect_timeout=CLI_TIMEOUT)

    uuid = re.findall(pattern=UUID, string=cmd_output)[0]

    # delete alarm
    LOG.tc_step("Execute alarm-delete command to delete the alarm created above")
    exit_code, cmd_output = cli.system('alarm-delete', uuid, auth_info=Tenant.ADMIN, fail_ok=True)
    assert exit_code == 0, "Expected system alarm-delete to execute successfully but failed with error: " \
                           "{}".format(cmd_output)
