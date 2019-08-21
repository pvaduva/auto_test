import time
import traceback
import os
from threading import Thread
import itertools
import re
import pexpect

from ..utils import ssh
from ..helper import installer_log
from ..helper import vm_file_management


loading_done = False  # used by the precessing bar


def wait_for_boot(node, node_name, max_time_out=1800):
    """
    Monitor the virtual machine boot status, terminates when time out or boot finished

    :param node: Pexpect spawn of 'virsh console node_name'
    :param node_name:
    :param max_time_out:
    :return: A boolean type indicates if the boot succeeded
    """
    installer_log.log_debug_msg("wait for node: {} to boot".format(node_name))
    try:
        node.expect_exact('login:', timeout=max_time_out)
        return True
    except pexpect.ExceptionPexpect:
        traceback.print_exc()
        return False


def login(node, node_name, var_dict, is_first_login=False):
    """
    Login to the virtual machine

    :param node: Pexpect spawn of 'virsh console node_name'
    :param node_name:
    :param var_dict: Variable dictionary
    :param is_first_login: A boolean type indicates if it's first time login
    :return: A boolean type indicates if login succeeded
    """
    installer_log.log_debug_msg("login to {}, first time = {}".format(node_name, is_first_login))
    try:
        if is_first_login:
            node.sendline(var_dict['vm_os_name'])
            node.expect_exact('Password:')
            node.sendline(var_dict['vm_os_name'])
            node.expect_exact('UNIX password:')
            node.sendline(var_dict['vm_os_name'])
            node.expect_exact('New password:')
            node.sendline(var_dict['vm_os_password'])
            node.expect_exact('new password:')
            node.sendline(var_dict['vm_os_password'])

        else:
            node.sendline(var_dict['vm_os_name'])
            node.expect_exact('Password:')
            node.sendline(var_dict['vm_os_password'])

        node.expect_exact(':~$')
        return True
    except pexpect.ExceptionPexpect:
        traceback.print_exc()
        return False


def get_external_connectivity(node, node_name, var_dict):
    """
    Setting up external connectivity after virtual machine just booted

    :param node: Pexpect spawn of 'virsh console node_name'
    :param node_name:
    :param var_dict: Variable dictionary
    :return: A boolean type indicates if login succeeded
    """
    installer_log.log_debug_msg("setting up external connectivity for node {}".format(node_name))
    try:
        node.sendline('sudo ip address add {}/24 dev {}'.format(var_dict['vm_ip_addr'],
                                                                var_dict['vm_interface_name']))
        time.sleep(1)
        node.expect_exact('Password:', timeout=30)
        node.sendline(var_dict['vm_os_password'])
        time.sleep(1)
        node.expect_exact(':~$')
        node.sendline('sudo ip link set up dev {}'.format(var_dict['vm_interface_name']))
        time.sleep(1)
        node.expect_exact(':~$')
        node.sendline('sudo ip route add default via {} dev {}'
                      .format(var_dict['vm_ip_route'], var_dict['vm_interface_name']))
        time.sleep(1)
        node.expect_exact(':~$')
        return True
    except pexpect.ExceptionPexpect:
        traceback.print_exc()
        return False


def select_kernel_option(controller_0, var_dict):
    """
    Select the boot options when booting controller-0

    :param controller_0: Pexpect spawn of 'virsh console controller_0_name'
    :param var_dict: Variable dictionary
    :return: A boolean type indicates if login succeeded
    """
    if 'plex' in var_dict['system_mode']:
        controller_0.send("\033[B")  # down arrow
        time.sleep(1)
        if var_dict['low_latency'] == 'True':
            controller_0.send("\033[B")
            time.sleep(1)
        controller_0.sendline('')
        time.sleep(1)
    else:
        controller_0.sendline('')
        time.sleep(1)

    controller_0.sendline('')
    time.sleep(1)

    if var_dict['extended_security'] == 'True':
        controller_0.send("\033[B")
        time.sleep(1)
    controller_0.sendline('')
    time.sleep(1)
    try:
        controller_0.expect_exact('ready', timeout=30)
        return True
    except pexpect.ExceptionPexpect:
        traceback.print_exc()
        return False


def run_ansible_playbook(node, node_name, command, max_time_out=1800):
    """
    Run ansible playbook, terminates when detecting 'failed=.'

    :param node: Pexpect spawn of 'virsh console node_name'
    :param node_name:
    :param command: A string that should be able to run correct ansible playbook
                    Since there is no value check about the correctness of the command
                    it will likely reach time out if the command is not correct
    :param max_time_out:
    :return: A boolean type indicates if login succeeded
    """
    installer_log.log_debug_msg("run ansible playbook with \n{}\non node {}".
                                format(command, node_name))

    try:
        node.sendline(command)
        node.expect('failed=.', timeout=max_time_out)
        if 'failed=0' in node.after:
            return True
        else:
            return False
    except pexpect.ExceptionPexpect:
        traceback.print_exc()
        return False


def get_system_host_list(var_dict):
    """
    Get the output of system host-list through ssh connection.

    :param var_dict:
    :return: The output of the ssh connection. Could be empty if the node is not active
    """
    return ssh.ssh_command(var_dict['vm_ip_addr'], var_dict['vm_os_name'],
                           var_dict['vm_os_password'],
                           'source /etc/platform/openrc && system host-list')


def wait_till_controller_0_available(var_dict, max_time_out=600):
    """
    Wait till the controller-0 is unlocked, enabled and available

    :param var_dict:
    :param max_time_out:
    :return: A boolean type indicates if controller-0 is ready
    """
    wait_counter = 0
    while wait_counter < max_time_out / 20:
        installer_log.log_debug_msg("wait 20 sec to get controller-0 state")
        time.sleep(20)
        output = get_system_host_list(var_dict)
        if len(re.findall('controller-0.*unlocked.*enabled.*available', output)) == 1:
            return True
        wait_counter = wait_counter + 1
    return False


def wait_till_other_nodes_configured(var_dict, num_of_other_nodes, max_time_out=600):
    """
    When using deployment manager to install multi-node system, after controller-0
    is ready, all the other nodes will be configure first, and on the output of 'system host-list'
    other node will be shown as locked, disabled and offline status
    Once all other nodes shown in the output of 'system host-list', the installer will start all
    other nodes one by one
    :param var_dict:
    :param num_of_other_nodes: Number of all nodes except controller-0
    :param max_time_out:
    :return: A boolean type indicates if other nodes is configured
    """
    wait_counter = 0
    while wait_counter < max_time_out / 20:
        installer_log.log_debug_msg('wait 20 sec to check nodes states')
        time.sleep(20)
        output = get_system_host_list(var_dict)
        if len(re.findall('locked.*disabled.*offline', output)) == num_of_other_nodes:
            return True
        wait_counter = wait_counter + 1
    return False


def wait_till_all_nodes_available(var_dict, num_of_total_nodes, max_time_out=4800):
    """
    Wait till all nodes in unlocked, enabled and available in the output of 'system host-list'

    :param var_dict:
    :param num_of_total_nodes:
    :param max_time_out:
    :return: A boolean type indicates if all nodes are ready
    """
    wait_counter = 0
    while wait_counter < max_time_out / 30:
        # print('wait 30 sec to check nodes states')
        time.sleep(30)
        output = get_system_host_list(var_dict)
        if len(re.findall('unlocked.*enabled.*available', output)) == num_of_total_nodes:
            # check the state again after 10 sec to make sure the states are stable
            time.sleep(10)
            output = get_system_host_list(var_dict)
            if len(re.findall('unlocked.*enabled.*available', output)) == num_of_total_nodes:

                return True
        wait_counter = wait_counter + 1
    return False


def check_kubectl(controller_0, controller_0_name, var_dict, num_of_total_nodes, max_time_out=600):
    """
    After all nodes ready in the output of 'system host-list', check on kubectl to see if all
    nodes are ready

    :param controller_0:
    :param controller_0_name:
    :param var_dict:
    :param num_of_total_nodes:
    :param max_time_out:
    :return: A boolean type indicates if all nodes are ready
    """
    installer_log.log_debug_msg("checking kubectl hosts status {}".format(controller_0_name))
    wait_counter = 0
    while wait_counter < max_time_out / 30:
        time.sleep(30)
        try:
            controller_0.sendline('clear')
            controller_0.sendline('kubectl get hosts -n {}'.format(var_dict['namespace']))
            controller_0.expect_exact('kubectl get hosts -n {}\r\n'.format(var_dict['namespace']))
            controller_0.expect_exact('\r\ncontroller-0:~$')
            output = controller_0.before
            if len(re.findall('unlocked.*enabled.*available.*true', output)) == num_of_total_nodes:
                controller_0.sendline('clear')
                controller_0.sendline('kubectl get nodes')
                controller_0.expect_exact('kubectl get nodes\r\n')
                controller_0.expect_exact('\r\ncontroller-0:~$')
                output = controller_0.before
                if output.count('Ready') == num_of_total_nodes:
                    return True
        except Exception:
            pass
        wait_counter = wait_counter + 1
    return False


def start_vm(node_name):
    """
    Start the virtual machine with node name

    :param node_name:
    :return:
    """
    child = ''
    try:
        child = pexpect.spawn('virsh start {}'.format(node_name), encoding='utf-8')
        child.expect_exact('started')
        installer_log.log_debug_msg('{} started'.format(node_name))
        return True
    except:
        installer_log.log_debug_msg('failed to start {}'.format(node_name))
        return False
    finally:
        if child:
            child.close()


def monitor_node_booting(node_name, log_path):
    """
    Monitor the boot output and unlock output on nodes other than controller-0
    This function is used in a thread

    :param node_name:
    :param log_path: Path to store boot output
    :return:
    """
    child = ''
    log_file = ''
    try:
        log_file = open(log_path, 'w+')

        child = pexpect.spawn('virsh console {}'.format(node_name), encoding='utf-8')
        child.logfile = log_file
        if wait_for_boot(child, node_name):
            if wait_for_boot(child, node_name, 3600):
                # wait for nodes to be unlocked
                return True
            else:
                installer_log.log_error_msg('Timeout when getting login page for unlocking node')
                installer_log.log_error_msg(traceback.format_exc())
        else:
            installer_log.log_error_msg('Timeout when getting login page for installing node')
            installer_log.log_error_msg(traceback.format_exc())
            return False
    except Exception:
        installer_log.log_error_msg('error when monitoring node booting output')
        installer_log.log_error_msg(traceback.format_exc())
        return False
    finally:
        if child and log_file:
            child.close()
            log_file.close()


def run_lab_setup(node, node_name, max_time_out=7200):
    """
    Preparing and running lab_setup.sh after all nodes are ready

    :param node:
    :param node_name:
    :param max_time_out:
    :return: A boolean type indicates if lab_setup.sh finished successfully
    """
    installer_log.log_debug_msg("apply stx-openstack on node {}".format(node_name))

    try:
        node.sendline('mkdir ~/images')
        node.sendline('echo $?')
        node.expect_exact('0')

        node.sendline('')

        node.sendline('chmod +x ./lab_setup.sh')
        node.sendline('echo $?')
        node.expect_exact('0')

        tail = 'a script from auto-installer finished'

        node.sendline('cp ~/tis-centos-guest.img ~/images && ./lab_setup.sh ; echo {}'.format(tail))
        node.expect_exact(tail, timeout=max_time_out)
        if 'fail' in node.before:
            return False
        return True

    except pexpect.ExceptionPexpect:
        traceback.print_exc()
        return False


def update_ip(node, node_name, var_dict):
    """
    Check if the external ip for the vm changed after vm rebooting

    :param node:
    :param node_name:
    :param var_dict:
    :return: A boolean type indicates if the function finished without error
    """
    installer_log.log_debug_msg("updating ip on node {}".format(node_name))

    try:
        node.sendline("ifconfig {} | grep mask | awk '{{print $2}}' | cut -f2 -d:".
                      format(var_dict['vm_interface_name']))
        # used double curly brace to print literally curly brace when using string.format()
        node.expect('[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}')
        if node.after != var_dict['vm_ip_addr']:
            installer_log.log_debug_msg('vm ip address changed from {} to {}'.
                                        format(var_dict['vm_ip_addr'], node.after))
            var_dict['vm_ip_addr'] = node.after
        return True
    except pexpect.ExceptionPexpect:
        # traceback.print_exc()
        return False


def processing_bar():
    """
    A rotating processing bar showing that the program is still running

    :return:
    """
    global loading_done
    pool = itertools.cycle(['-', '\\', '|', '/'])
    for item in pool:
        if loading_done:
            print('\rLoading Finished !')
            return
        else:
            time.sleep(0.1)
            print('\rLoading...{}'.format(item), flush=True, end='')


def deploy_system(nodes_list, var_dict):
    """
    Main control flow of installing the system

    :param nodes_list:
    :param var_dict:
    :return: A boolean type indicates if the installation succeeded
    """
    global loading_done  # used for the processing bar

    installer_log.log_step(3, False)
    nodes_dict = dict.fromkeys(nodes_list)
    controller_0_name = ''

    for node_name in nodes_list:
        if '-controller-0' in node_name:
            controller_0_name = node_name
            nodes_list.remove(node_name)
            break

    controller_0_consolelog = open(os.path.join(var_dict['base_log_dir'],
                                                var_dict['time_stamp'], '{}_console_output.log'
                                                .format(controller_0_name)), 'w+')

    controller_0 = pexpect.spawn('virsh console {}'.format(controller_0_name), encoding='utf-8')
    time.sleep(10)
    controller_0.logfile = controller_0_consolelog
    nodes_dict[controller_0_name] = controller_0
    if not select_kernel_option(controller_0, var_dict):
        installer_log.log_info_msg('sth went wrong when '
                                   'selecting kernel option for booting controller-0')
        return False

    loading_bar = Thread(target=processing_bar, daemon=True)
    loading_bar.start()

    if not wait_for_boot(controller_0, controller_0_name):
        loading_done = True
        loading_bar.join()
        installer_log.log_info_msg('sth went wrong when booting controller-0')
        return False

    loading_done = True
    loading_bar.join()
    installer_log.log_step(3, True)
    installer_log.log_step(4, False)

    if not login(controller_0, controller_0_name, var_dict, True):
        installer_log.log_info_msg('sth went wrong when login in controller-0 for the first time')
        return False

    if not get_external_connectivity(controller_0, controller_0_name, var_dict):
        installer_log.log_info_msg('sth went wrong when '
                                   'getting external connectivity for controller-0')
        return False

    if not vm_file_management.send_files_controller_0(var_dict):
        installer_log.log_info_msg('sth went wrong when sending files to controller-0')
        return False

    if not vm_file_management.populate_templates(controller_0, controller_0_name,
                                                 nodes_list, var_dict):
        installer_log.log_info_msg('sth went wrong when populating templates')
        return False

    installer_log.log_step(4, True)
    installer_log.log_step(5, False)
    loading_done = False
    loading_bar = Thread(target=processing_bar, daemon=True)
    loading_bar.start()

    if not run_ansible_playbook(controller_0, controller_0_name,
                                'ansible-playbook lab-install-playbook.yaml '
                                '-e "@local-install-overrides.yaml"'):

        loading_done = True
        loading_bar.join()

        installer_log.log_info_msg('sth went wrong when running ansible playbook')
        return False

    loading_done = True
    loading_bar.join()
    installer_log.log_step(5, True)
    installer_log.log_step(6, False)
    loading_done = False
    loading_bar = Thread(target=processing_bar, daemon=True)
    loading_bar.start()

    controller_0.sendline('source /etc/platform/openrc && watch -n 10 system host-list')
    #  This is to prevent the vm from auto-logout. can also replace it with exit

    if not wait_for_boot(controller_0, controller_0_name, 3600):

        loading_done = True
        loading_bar.join()

        installer_log.log_info_msg('sth went wrong when waiting for unlocking controller-0')
        return False

    loading_done = True
    loading_bar.join()
    installer_log.log_step(6, True)
    installer_log.log_step(7, False)
    loading_done = False
    loading_bar = Thread(target=processing_bar, daemon=True)
    loading_bar.start()

    if not login(controller_0, controller_0_name, var_dict):
        loading_done = True
        loading_bar.join()
        installer_log.log_info_msg('sth went wrong when '
                                   'login in controller-0 after unlocking controller-0')
        return False

    if not update_ip(controller_0, controller_0_name, var_dict):

        loading_done = True
        loading_bar.join()

        installer_log.log_info_msg('sth went wrong when '
                                   'updating vm ip after unlocking controller-0')
        return False

    if not wait_till_controller_0_available(var_dict):

        loading_done = True
        loading_bar.join()

        installer_log.log_info_msg('sth went wrong when '
                                   'waiting controller-0 to be available after unlocking')
        return False

    thread_list = []

    if var_dict['system_mode'] != 'simplex':
        if not wait_till_other_nodes_configured(var_dict, len(nodes_list)):

            loading_done = True
            loading_bar.join()

            installer_log.log_info_msg('sth went wrong when waiting other nodes to be configured')
            return False

        for node_name in nodes_list:
            if not start_vm(node_name):
                loading_done = True
                loading_bar.join()
                installer_log.log_info_msg('sth went wrong when starting vm {}'.format(node_name))
                return False

            log_path = os.path.join(var_dict['base_log_dir'], var_dict['time_stamp'],
                                    '{}_console_output.log'.format(node_name))

            t = Thread(target=monitor_node_booting, args=(node_name, log_path,), daemon=True)
            thread_list.append(t)
            t.start()

        if not wait_till_all_nodes_available(var_dict, len(nodes_list)+1):

            loading_done = True
            loading_bar.join()

            installer_log.log_info_msg('sth went wrong when waiting all nodes to be available')
            return False

    try:  # In case auto-logout. If it is simplex system, this login will fail
        login(controller_0, controller_0_name, var_dict)
    except Exception:
        pass
    if not check_kubectl(controller_0, controller_0_name, var_dict, len(nodes_list)+1):

        loading_done = True
        loading_bar.join()

        installer_log.log_info_msg('sth went wrong when check_nodes status on kubectl')
        return False

    loading_done = True
    loading_bar.join()
    installer_log.log_step(7, True)

    for t in thread_list:
        if t.is_alive():
            installer_log.log_error_msg('All nodes are ready in Main Thread, '
                                        'but a thread that monitors nodes booting is still running')
            installer_log.log_error_msg(traceback.format_exc())

    installer_log.log_step('lab_setup.sh', False)
    loading_done = False
    loading_bar = Thread(target=processing_bar, daemon=True)
    loading_bar.start()

    if not run_lab_setup(controller_0, controller_0_name):
        loading_done = True
        loading_bar.join()
        installer_log.log_info_msg('sth went wrong when running lab_setup.sh')
        return False
    loading_done = True
    loading_bar.join()
    installer_log.log_step('lab_setup.sh', True)
    installer_log.log_info_msg("All done! {} installed successfully"
                               .format(var_dict['system_mode']))
    controller_0_consolelog.close()
    return True

