#!/usr/bin/python3

from consts.timeout import HostTimeout
from consts.env import BuildServers, Licenses, Builds, ISOPATH, SetupFiles, Lab
from utils.sftp import sftp_get
from utils import serial
from helper import host_helper


def get_lab_setup_files(stream, remote_host=BuildServers.CGTS4['ip'], release='R5', path=None, host_type='Standard'):
    """
    Retrieves necessary setup files from the host specified.
    Args:
        stream(stream): Stream to controller-0, required to put files in correct directories.
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        file_path(str): Path to setup files, if none default path to files will be used
        host_type(str): Type of host either 'AIO' or 'Standard'
    """
    file_path = []
    serial.send_bytes(stream, "mkdir /home/wrsroot/images")
    if path is None:
        if release is 'R5':
            file_path = SetupFiles.R5['setup']
            file_path.extend(Builds.R5['guest'])
            file_path.extend(Licenses.R5[host_type])
        elif release is 'R4':
            file_path = SetupFiles.R4['setup']
            file_path.extend(Builds.R4['guest'])
            file_path.extend(Licenses.R4[host_type])
        elif release is 'R3':
            file_path = SetupFiles.R3['setup']
            file_path.extend(Builds.R3['guest'])
            file_path.extend(Licenses.R3[host_type])
        elif release is 'R2':
            file_path = SetupFiles.R2['setup']
            file_path.extend(Builds.R2['guest'])
            file_path.extend(Licenses.R2[host_type])
    else:
        for items in SetupFiles.FILENAMES:
            file_path.extend(path + items)
    local_path = 'wrsroot@{}:/home/wrsroot/'.format(Lab.VBOX['controller-0_ip'])
    for items in file_path:
        print("Retrieving file from {}".format(items))
        if '.img' in items:
            sftp_get(remote_path=file_path, remote_host=remote_host,
                     local_path='wrsroot@{}:/home/wrsroot/images/tis-centos-guest.img'.format(Lab.VBOX['controller-0_ip']))
        elif '.lic'in items:
            sftp_get(remote_path=file_path, remote_host=remote_host,
                     local_path='wrsroot@{}:/home/wrsroot/licence.lic'.format(Lab.VBOX['controller-0_ip']))
        else:
            sftp_get(remote_path=file_path, remote_host=remote_host, local_path=local_path)



def run_install_scripts(stream, host_list, aio=False, storage=False):
    """
    Runs lab install.sh iterations.
    Args:
        stream(stream): Stream to controller-0
        host_list(list): list of hosts, used when running aio scripts to install controller-1 at the appropriate time
        aio(bool): Option to run the script for aio setup
        storage(bool): Option to run the script for storage setup
    """
    serial.send_bytes(stream, "chmod +x *.sh")
    if aio:
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Stopping after data interface setup.", HostTimeout.LAB_INSTALL)
        serial.send_bytes(stream, "system compute-config-complete")
        serial.expect_bytes(stream, "login:", HostTimeout.REBOOT)
        serial.send_bytes(stream, "sudo sm-dump")
        serial.expect_bytes(stream, "Password:")
        serial.send_bytes(stream, "Li69nux*")
        # ensure services are running TODO
        serial.send_bytes(stream, "./lab_setup.sh")
        # check here
        serial.send_bytes(stream, "./lab_setup.sh")
        # check here
        if 'controller-1' in host_list:
            host_helper.unlock_host(stream, 'controller-1')
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Done", HostTimeout.LAB_INSTALL)
    else:
        serial.send_bytes(stream, "source /etc/nova/openrc")
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Stopping after provider network creation.", HostTimeout.LAB_INSTALL)
        if storage:
            for hosts in host_list:
                if hosts.startswith('storage'):
                    host_helper.unlock_host(stream, hosts)
            serial.send_bytes(stream, "./lab_setup.sh")
            serial.expect_bytes(stream, "Stopping after initial storage node setup", HostTimeout.LAB_INSTALL)
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Stopping after data interface setup.", HostTimeout.LAB_INSTALL)
        for host in host_list:
            if host.statswith("compute"):
                host_helper.unlock_host(stream, host)
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Done", HostTimeout.LAB_INSTALL)


def config_controller(stream, default=True, config_file=None, backup=None, clone_iso=None,
                      restore_system=None, restore_images=None):

    """
    Configure controller-0 using optional arguments
    Args:
        stream(stream): stream to controller-0
        default(bool): Use default settings
        config_file(str): Config file to use.
        backup(str):
        clone_iso(str):
        restore_system(str):
        restore_images(str):
    """
    args_dict = {
        '--config-file': config_file,
        '--backup': backup,
        '--clone-iso': clone_iso,
        '--restore-system': restore_system,
        '--restore_images': restore_images
    }
    args = ''
    for key, value in args_dict.items():
        if value:
            args += ' {} {}'.format(key, value)
    if default:
        args += ' --default'
    serial.send_bytes(stream, "sudo config_controller {}".format(args))
    serial.expect_bytes(stream, "The following configuration will be applied:")
    serial.expect_bytes(stream, "Applying configuration")
    serial.expect_bytes(stream, "Configuration was applied", HostTimeout.LAB_CONFIG)

