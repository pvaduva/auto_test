###
# TC2196 Verify that alarm can be deleted using CLI
###
import re

from utils import cli, table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG

from consts.cgcs import UUID
from consts.auth import Tenant

from keywords import system_helper


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
    alarm_id = '300.005'
    LOG.tc_step("Create an critical alarm with id {}".format(alarm_id))

    cmd = "fmClientCli -c '### ###{}###set###system.vm###host=compute-0.vm=$i### ###critical###Automation test" \
          "###processing-error###cpu-cycles-limit-exceeded### ###True###True###'".format(alarm_id)
    ssh_client = ControllerClient.get_active_controller()
    cmd_output = ssh_client.exec_cmd(cmd, fail_ok=False)[1]

    LOG.tc_step("Check generated alarm is shown in system alarm-list")
    uuid = re.findall(pattern=UUID, string=cmd_output)[0]

    alarms_tab = system_helper.get_alarms_table(uuid=True)
    assert uuid in table_parser.get_column(alarms_tab, 'uuid')
    assert alarm_id in table_parser.get_column(alarms_tab, 'alarm id')

    # delete alarm
    LOG.tc_step("Execute alarm-delete command to delete the alarm created above")
    exit_code, cmd_output = cli.system('alarm-delete', uuid, auth_info=Tenant.ADMIN, fail_ok=True)
    assert exit_code == 0, "Expected system alarm-delete to execute successfully but failed with error: " \
                           "{}".format(cmd_output)

    post_alarms_tab = system_helper.get_alarms_table(uuid=True)
    assert uuid not in table_parser.get_column(post_alarms_tab, 'uuid')
    assert alarm_id not in table_parser.get_column(post_alarms_tab, 'alarm id')