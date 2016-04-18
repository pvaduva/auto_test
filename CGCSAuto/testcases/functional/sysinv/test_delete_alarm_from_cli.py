###
# Verify that alarm can be deleted using CLI
###

from pytest import fixture, mark, skip

from utils import cli
from utils.ssh import ControllerClient
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3
from consts.timeout import CLI_TIMEOUT

'''


'''


def test_delete_alarm():

    # create an alarm using fmClientCli

    # fmClientCli -c "### ###600.005###alarm###system.vm###host=compute-0.vm=$i### ###critical###'oam' port
    # ###processing-error###cpu-cycles-limit-exceeded### ###True###True###"
    cmd = "fmClientCli -c '### ###600.005###alarm###system.vm###host=compute-0.vm=$i### ###critical###'oam' port" \
          "###processing-error###cpu-cycles-limit-exceeded### ###True###True###'"

    ssh_client = ControllerClient.get_active_controller()
    LOG.tc_step("Create an critical alarm 600.005")
    exit_code, cmd_output = ssh_client.exec_cmd(cmd, err_only=False, expect_timeout=CLI_TIMEOUT)
    uuid = cmd_output.split('\n')[2]

    # delete alarm
    LOG.tc_step("Execute alarm-delete command to delete the alarm created above")
    exit_code, cmd_output = cli.system('alarm-delete', uuid, auth_info=Tenant.ADMIN, fail_ok=True)
    assert exit_code == 0, "Expected system alarm-delete to execute successfully but failed with error: " \
                           "{}".format(cmd_output)
