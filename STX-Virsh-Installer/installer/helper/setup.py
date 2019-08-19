import os
from subprocess import check_output

from installer.utils import download_file
from installer.helper import installer_log


def setup(var_dict):
    """Download files, create virtual machines if necessary

    :param var_dict: variable dictionary
    :return: a string list of virtual machines' name
    """
    if var_dict['bootimage.iso'].startswith(var_dict['template_dir']):
        var_dict['bootimage.iso'] = os.path.join(var_dict['base_log_dir'],
                                                 var_dict['time_stamp'], 'bootimage.iso')
        if not download_file.download_file(var_dict['bootimage_url'], var_dict['bootimage.iso']):
            return False
    if var_dict['stx-openstack.tgz'].startswith(var_dict['template_dir']):
        var_dict['stx-openstack.tgz'] = os.path.join(var_dict['base_log_dir'],
                                                     var_dict['time_stamp'], 'stx-openstack.tgz')
        if not download_file.download_file(var_dict['stx_openstack_url'],
                                           var_dict['stx-openstack.tgz']):
            return False
    if var_dict['helm-charts-manifest.tgz'].startswith(var_dict['template_dir']):
        var_dict['helm-charts-manifest.tgz'] = os.path.join(
            var_dict['base_log_dir'], var_dict['time_stamp'], 'helm-charts-manifest.tgz')
        if not download_file.download_file(var_dict['helm_charts_manifest_url'],
                                           var_dict['helm-charts-manifest.tgz']):
            return False
    if var_dict['tis-centos-guest.img'].startswith(var_dict['template_dir']):
        var_dict['tis-centos-guest.img'] = os.path.join(
            var_dict['base_log_dir'], var_dict['time_stamp'], 'tis-centos-guest.img')
        if not download_file.download_file(var_dict['tis-centos-guest_url'],
                                           var_dict['tis-centos-guest.img']):
            return False
    if not var_dict['skipvm']:
        # To run the bash scripts used for set up network and virtual machines,
        # the current working directory has to be changed
        cwd = os.getcwd()
        os.chdir(var_dict['libvirt_scirpt_dir'])
        try:  # set_network.sh will return non zero exit if the network name exist
            ret = check_output([os.path.join(var_dict['libvirt_scirpt_dir'], 'setup_network.sh')])
            installer_log.log_debug_msg('output from setup_network.sh:\n{}'.format(ret))
        except Exception:
            pass
        if var_dict['vm_name_prefix']:
            ret = check_output(
                [os.path.join(var_dict['libvirt_scirpt_dir'], 'setup_configuration.sh'),
                    '-c', var_dict['system_mode'], '-i', var_dict['bootimage.iso'],
                    '-p', var_dict['vm_name_prefix'],
                    '-w', var_dict['num_of_compute'], '-s', var_dict['num_of_storage']
                 ])
        else:
            ret = check_output(
                [os.path.join(var_dict['libvirt_scirpt_dir'], 'setup_configuration.sh'),
                    '-c', var_dict['system_mode'], '-i', var_dict['bootimage.iso'],
                    '-w', var_dict['num_of_compute'], '-s', var_dict['num_of_storage']
                 ])
        installer_log.log_debug_msg('output from setup_configuration.sh:\n{}'.format(ret))
        os.chdir(cwd)  # change back to the previous current working directory

    nodes_name_list = []
    for i in range(0, int(var_dict['num_of_controller'])):
        nodes_name_list.append("{}{}-controller-{}".format(var_dict['vm_name_prefix'],
                                                           var_dict['system_mode'], i))
    for i in range(0, int(var_dict['num_of_compute'])):
        nodes_name_list.append("{}{}-worker-{}".format(var_dict['vm_name_prefix'],
                                                       var_dict['system_mode'], i))
    for i in range(0, int(var_dict['num_of_storage'])):
        nodes_name_list.append("{}{}-storage-{}".format(var_dict['vm_name_prefix'],
                                                        var_dict['system_mode'], i))
    return nodes_name_list


def cleanup(var_dict):
    """Remove the virtual machines that corresponds to the variable dictionary

    :param var_dict: variable dictionary
    :return:
    """

    # Need to change the current working directory to run the destroy virtual machines' script
    cwd = os.getcwd()
    os.chdir(var_dict['libvirt_scirpt_dir'])
    if var_dict['vm_name_prefix']:
        ret = check_output(
            [os.path.join(var_dict['libvirt_scirpt_dir'], 'destroy_configuration.sh'),
                '-c', var_dict['system_mode'],
                '-p', var_dict['vm_name_prefix'],
                '-w', var_dict['num_of_compute'], '-s', var_dict['num_of_storage']
             ])
    else:
        ret = check_output(
            [os.path.join(var_dict['libvirt_scirpt_dir'], 'destroy_configuration.sh'),
                '-c', var_dict['system_mode'],
                '-w', var_dict['num_of_compute'], '-s', var_dict['num_of_storage']
             ])
    installer_log.log_debug_msg('output from destroy_configuration.sh:\n{}'.format(ret))

    # Not destroying the network in case other virtual machines are running
    # check_output([os.path.join(var_dict['libvirt_scirpt_dir'], 'destroy_network.sh')])
    os.chdir(cwd)
