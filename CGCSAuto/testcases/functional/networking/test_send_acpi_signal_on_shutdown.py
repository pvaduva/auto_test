from pytest import mark
from utils.tis_log import LOG
from keywords import  vm_helper


@mark.parametrize(('nova_action', 'hard'), [
     ('reboot', 'hard'),
     ('reboot', 'soft'),
     ('stop_start', None)
])
def test_send_acpi_signal_on_shutdown(nova_action, hard):
    """
    Sample test case for Boot an instance and send acpi signal on shutdown
    Test Steps:
        - Boot a vm with only mgmt interface & tenant interface
        - if hard is set reboot vm with --hard option, for stop/start there is no --hard option
        - ssh to vm & modify /etc/acpi/actions/power.sh file to log message
        - perform nova action using arg 'hard'
        - After nova action verify the message logged in '/var/log/messages'

    Teardown:
        - Delete created vm, volume

    """
    nova_action = nova_action.split('_')
    hard = 1 if 'hard' == hard else 0

    LOG.info("hard option: {}".format(hard))
    LOG.tc_step("Boot a vm")
    vm_under_test = vm_helper.boot_vm(name='send_acpi_signal_to_vm', cleanup='function')[1]

    LOG.tc_step("Modify gyest acpi file file")
    _modify_guest_acpi_file(vm_id=vm_under_test)

    kwargs = {}
    if hard == 1:
        kwargs = {'hard': True}
    for action in nova_action:
        LOG.tc_step("Perform nova action: {}".format(action))
        vm_helper.perform_action_on_vm(vm_under_test, action=action, **kwargs)

    LOG.tc_step("Verify /var/log/messages file")
    _check_log_messages(vm_id=vm_under_test, hard=hard)


def _modify_guest_acpi_file(vm_id):
    power_file = '/etc/acpi/actions/power.sh'
    text = '"POWER BUTTON WAS PRESSED: $1"'
    LOG.tc_step("Modify {} file to add line {}".format(power_file, text))
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_sudo_cmd("sed -e '3i /usr/bin/logger {}' -i {}".format(text, power_file))
        vm_ssh.exec_sudo_cmd("head -n 5 {}".format(power_file))


def _check_log_messages(vm_id, hard):
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        code, output = vm_ssh.exec_sudo_cmd('cat /var/log/messages | grep -v grep | grep "logger: POWER BUTTON"')
        LOG.info("Output: {}".format(output))
        LOG.info("Result code: {}".format(code))
        assert hard == code, "There should not be any output if reboot or stop with hard"
