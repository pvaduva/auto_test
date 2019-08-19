import traceback
from io import StringIO
from xml.dom import minidom

import pexpect

from installer.utils.ssh import sftp_send
from installer.helper import installer_log


def populate_templates(controller_0, controller_0_name, other_nodes_list, var_dict):
    """Dynamically populates the reserved keys in template files

    :param controller_0: Pexpect spawning 'virsh console prefix-system-controller-0'
    :param controller_0_name: Name of the controller-0 virtual machine
    :param other_nodes_list: A string list contains all other virtual machines' names
                             except for controller-0
    :param var_dict: Variable dictionary
    :return: A boolean type indicates if the namespace is retrieved from deployment-config.yaml
    """
    nodes_name_list = [controller_0_name]
    for node_name in other_nodes_list:
        nodes_name_list.append(node_name)

    template_dir_tuple = (var_dict['template_dir'], var_dict['replaced_template_dir'])

    if var_dict['aio.sed'].startswith(template_dir_tuple):
        installer_log.log_info_msg("generating aio.sed on {}".format(controller_0_name))
        generate_sed(controller_0, nodes_name_list, var_dict)
    else:
        installer_log.log_info_msg("aio.sed provided by the user, skipping generating on {}"
                                   .format(controller_0_name))

    if var_dict['localhost.yml'].startswith(template_dir_tuple):
        installer_log.log_info_msg("populating localhost.yml on {}".format(controller_0_name))
        populate_localhost(controller_0, var_dict)
    else:
        installer_log.log_info_msg("localhost.yml provided by the user, skipping generating on {}"
                                   .format(controller_0_name))

    if var_dict['deployment-config.yaml'].startswith(template_dir_tuple):
        installer_log.log_info_msg("generating deployment-config.yaml on {}"
                                   .format(controller_0_name))
        generate_deployment_config(controller_0, var_dict)
    else:
        installer_log.log_info_msg("skipping generating deployment-config.yaml on {}"
                                   .format(controller_0_name))

    installer_log.log_info_msg("getting namespace from deployment-config.yaml on {}"
                               .format(controller_0_name))
    try:
        # The following two lines are for clearing the pexpect buffer
        controller_0.read_nonblocking(1000000000, timeout=1)
        controller_0.sendline('echo stx-virsh-installer buffer clearing ')
        controller_0.expect_exact('stx-virsh-installer buffer clearing')
        controller_0.read_nonblocking(1000000000, timeout=1)
        controller_0.sendline('grep namespace ~/deployment-config.yaml -m 1')
        controller_0.expect(r'namespace.*:.*\n')
        var_dict['namespace'] = controller_0.after.split(':')[1].strip()
        installer_log.log_info_msg("namespace is {}".format(var_dict['namespace']))
    except Exception:
        installer_log.log_error_msg('sth went wrong when getting namespace '
                                    'from deplyment-config.yaml')
        installer_log.log_error_msg(traceback.format_exc())
        return False
    return True


def send_files_controller_0(var_dict):
    """Send all files needed for installation from host machine to controller-0 vm
        var_dict['bootimage.iso'] should already be deleted after setup()
    :param var_dict: Variable dictionary
    :return: A boolean type indicates the status of sending files
    """
    installer_log.log_debug_msg("sending filed needed for server installation to controller-0")
    try:
        destination_dir = '/home/{}'.format(var_dict['vm_os_name'])
        for fname, source_path in var_dict.items():
            if '.' not in fname:
                continue
            source = source_path
            destination = '{}/{}'.format(destination_dir, fname)
            installer_log.log_debug_msg('sending {} to {}'.format(source, destination))
            sftp_send(source, var_dict['vm_ip_addr'], destination, var_dict['vm_os_name'],
                      var_dict['vm_os_password'])
        return True
    except Exception:
        traceback.print_exc()
        return False


def populate_localhost(controller_0, var_dict):
    """Populate localhost.yaml on controller-0
        Add system_mode: duplex if system mode is not simplex
        Add admin_password: platform_password and ansible_become_pass: platform_password
    :param controller_0: Pexpect spawning 'virsh console prefix-system-controller-0'
    :param var_dict: Variable dictionary
    :return:
    """
    to_write = '\nadmin_password: {}\nansible_become_pass: {}\n'.format(var_dict['admin_password'],
                                                                        var_dict['admin_password'])
    controller_0.sendline('echo "{}" >> ~/localhost.yml'.format(to_write))
    if var_dict['system_mode'] == 'simplex':
        controller_0.sendline('sed -e "s/system_mode: duplex//g" -i ~/localhost.yml')
    else:
        controller_0.sendline('grep -qxF "system_mode: duplex" ~/localhost.yml '
                              '|| echo "system_mode: duplex" >> ~/localhost.yml')


def generate_sed(controller_0, nodes_name_list, var_dict):
    """Populate a sed file named aio.sed that has the value for reserved keys, aio.sed will be
        used to generate deployment-config.yaml
        Reservered keys are: EXTRACOMPUTE, PASSWORD_BASE64, IS_LOW_LATENCY, CONTROLLER0MAC,
        CONTROLLER1MAC,COMPUTE0MAC, COMPUTE1MAC, STORAGE0MAC, STORAGE1MAC

        Will add EXTRASTORAGE for installing extra storage nodes

    :param controller_0: Pexpect spawning 'virsh console prefix-system-controller-0'
    :param nodes_name_list: A string list that contains all the virtual machines' names
    :param var_dict: Variable dictionary
    :return:
    """
    to_write = ''
    extra_compute_prefix = 's#EXTRACOMPUTE#---'
    extra_compute_format = '\\\\\\napiVersion: starlingx.windriver.com/v1beta1' \
                           '\\\\\\nkind: Host\\\\\\nmetadata:\\\\\\n  ' \
                           'labels:\\\\\\n    controller-tools.k8s.io: \\"1.0\\"\\\\\\n' \
                           '  name: compute-{}\\\\\\n  namespace: vbox\\\\\\n' \
                           'spec:\\\\\\n  overrides:\\\\\\n    bootMAC: {}\\\\\\n' \
                           '  profile: worker-profile\\\\\\n---'
    extra_compute_suffix = '#'
    extra_compute = ''
    for node_name in nodes_name_list:
        installer_log.log_debug_msg("server name : {}".format(node_name))
        child = pexpect.spawn('virsh dumpxml {}'.format(node_name), encoding='utf-8')

        child.expect_exact(pexpect.EOF)

        doc = minidom.parse(StringIO(child.before))
        child.close()
        for element in doc.getElementsByTagName('devices'):
            interface = element.getElementsByTagName('interface')[
                1]  # it should be the management network interface
            mac_addr = interface.getElementsByTagName('mac')[0].getAttribute('address')
            node_index = int(node_name[node_name.rfind('-') + 1:])
            if '-controller-0' in node_name:
                interface = element.getElementsByTagName('interface')[0]
                mac_addr = interface.getElementsByTagName('mac')[0].getAttribute('address')
                temp = 's/CONTROLLER{}MAC/{}/'.format(node_index, mac_addr)
                to_write = to_write + temp + '\n'
            elif int(node_name.split('-')[-1]) > 1:
                if '-worker-' in node_name:
                    extra_compute = extra_compute + extra_compute_format.format(
                        int(node_name.split('-')[-1]), mac_addr)
            elif '-controller-' in node_name:
                temp = 's/CONTROLLER{}MAC/{}/'.format(node_index, mac_addr)
                to_write = to_write + temp + '\n'
            elif '-worker-' in node_name:
                temp = 's/COMPUTE{}MAC/{}/'.format(node_index, mac_addr)
                to_write = to_write + temp + '\n'
            elif '-storage-' in node_name:
                temp = 's/STORAGE{}MAC/{}/'.format(node_index, mac_addr)
                to_write = to_write + temp + '\n'
    if not extra_compute:
        extra_compute = extra_compute_prefix + extra_compute_suffix
    else:
        extra_compute = extra_compute_prefix + extra_compute + extra_compute_suffix
    to_write = to_write + extra_compute + '\n'

    controller_0.sendline('echo -n {} | base64'.format(var_dict['admin_password']))
    controller_0.expect('base64\r\n.*\r\n')
    base64_pass = controller_0.after.split('base64')[1].strip()
    base64_pass = 's/PASSWORD_BASE64/{}/\n'.format(base64_pass)
    to_write = to_write + base64_pass

    if 'plex' in var_dict['system_mode']:
        if var_dict['low_latency'] == 'True':
            to_write = to_write + 's/IS_LOW_LATENCY/- lowlatency/'
        else:
            to_write = to_write + 's/IS_LOW_LATENCY//'
    installer_log.log_debug_msg(to_write)
    controller_0.sendline('echo -e "{}" > ~/aio.sed'.format(to_write))


def generate_deployment_config(controller_0, var_dict):
    """Use template file that has reserved keys based on system mode, combine it with aio.sed
       to generate deployment-config.yaml

    :param controller_0: Pexpect spawning 'virsh console prefix-system-controller-0'
    :param var_dict: Variable dictionary
    :return:
    """
    if var_dict['system_mode'] == 'simplex':
        controller_0.sendline('cat ~/aio-sx.yaml | sed  -f ~/aio.sed > ~/deployment-config.yaml')
    elif var_dict['system_mode'] == 'duplex':
        controller_0.sendline('cat ~/aio-dx.yaml | sed  -f ~/aio.sed > ~/deployment-config.yaml')
    elif var_dict['system_mode'] == 'controllerstorage':
        controller_0.sendline('cat ~/standard.yaml | sed  -f ~/aio.sed > ~/deployment-config.yaml')
    elif var_dict['system_mode'] == 'dedicatedstorage':
        controller_0.sendline('cat ~/storage.yaml | sed  -f ~/aio.sed > ~/deployment-config.yaml')





