#!/usr/bin/python3
import os
from consts.timeout import HostTimeout
from consts.env import BuildServers, Licenses, Builds, ISOPATH, Files, Lab
from utils.sftp import sftp_get, sftp_send, send_dir, get_dir
from utils import serial
from helper import host_helper
import logging as LOG


def get_lab_setup_files(stream, remote_host=None, release='R5', remote_path=None, local_path=None, host_type='Standard'):
    """
    Retrieves necessary setup files from the host specified. If local_path is specified the files in that directory will be collected else files will be collected from remote_host
    Args:
        stream(stream): Stream to controller-0, required to put files in correct directories.
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        file_path(str): Path to setup files, if none default path to files will be used
        host_type(str): Type of host either 'AIO' or 'Standard'
    """
    serial.send_bytes(stream, "mkdir /home/wrsroot/images")
    if local_path:
        get_lab_setup_scripts(remote_host, release, remote_path, local_path)
    else:
        get_lab_setup_scripts(remote_host, release, remote_path, local_path)
        get_licence(remote_host, release, remote_path, local_path, host_type)
        get_guest_img(stream, remote_host, release, remote_path, local_path)


def get_lab_setup_scripts(remote_host=None, release='R5', remote_path=None, local_path=None):
    """
    Retrieves lab setup scripts including tenant and admin resources.
    Args:
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        file_path(str): Path to setup files, if none default path to files will be used
        local_path(str): Path on local machine to store files for transfer to vbox
    """
    if local_path is None:
        local_path = "/folk/tmather/LabInstall/R5/"
    file_path=[]
    if remote_path is None:
        if release =='R5':
            file_path = Files.R5['setup']
        elif release == 'R4':
            file_path = Files.R4['setup']
        elif release == 'R3':
            file_path = Files.R3['setup']
        else:
            file_path = Files.R2['setup']
    files = ['lab_cleanup.sh',
          'lab_setup.sh',
          'lab_setup.conf',
          'iptables.rules',
          'lab_setup-tenant2-resources.yaml',
          'lab_setup-tenant1-resources.yaml',
          'lab_setup-admin-resources.yaml']
    i = 0
    if remote_host is not None:
        for items in file_path:
            sftp_get(source=items, remote_host=remote_host, destination=local_path + files[i])
            i += 1
    send_dir(source=local_path)


def get_licence(remote_host=None, release='R5', remote_path=None,
                local_path=None, host_type='Standard'):
    """
        Retrieves Licence from specified host and sends it to controller-0.
    Args:
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        file_path(str): Path to setup files, if none default path to files will be used
        host_type(str): Type of host either 'AIO' or 'Standard'
        local_path(str): Path on local machine to store files for transfer to vbox
    """
    if local_path is None:
        local_path = "/folk/tmather/LabInstall/R5/"
    file_path = []
    if remote_path is None:
        if release == 'R5':
            file_path = Licenses.R5[host_type]
        elif release == 'R4':
            file_path = Licenses.R4[host_type]
        elif release == 'R3':
            file_path = Licenses.R3[host_type]
        else:
            file_path = Licenses.R2[host_type]
    local_path = local_path + 'licence.lic'
    if remote_host is not None:
        sftp_get(source=file_path, remote_host=remote_host, destination=local_path)
    sftp_send(source=local_path, destination='/home/wrsroot/licence.lic')


def get_guest_img(stream, remote_host=None, release='R5', remote_path=None,
                  local_path=None):
    """
 Retrieves necessary setup files from the host specified.
    Args:
        stream(stream): Stream to controller-0, required to put files in correct directories.
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        file_path(str): Path to setup files, if none default path to files will be used
        local_path(str): Path on local machine to store files for transfer to vbox
    """
    if local_path is None:
        local_path = "/folk/tmather/LabInstall/R5/" 
    file_path = []
    if remote_path is None:
        if release == 'R5':
            file_path = Builds.R5['guest']
        elif release == 'R4':
            file_path = Builds.R4['guest']
        elif release == 'R3':
            file_path = Builds.R3['guest']
        else:
            file_path = Builds.R2['guest']      
    serial.send_bytes(stream, "mkdir /home/wrsroot/images")
    local_path = local_path + 'tis_centos_guest.img'
    if remote_host is not None:
        sftp_get(source=file_path, remote_host=remote_host, destination=local_path)
    sftp_send(source=local_path, destination="/home/wrsroot/images/tis_centos_guest.img")
    
    
def get_patches(cont0_stream, local_path=None, remote_host=None):
    """
    Retrieves patches from remote_host or localhost if remote_host is None
    """

    serial.send_bytes(cont0_stream, "mkdir /home/wrsroot/patches")
    if local_path is None:
        local_path = '/folk/tmather/patches/'
    remote_path = '/home/wrsroot/patches/'
    if remote_host is not None:
        get_dir(Files.PATCHES['R5'], remote_host, local_path, True)
        send_dir(local_path, destination=remote_path)
    else:
        send_dir(local_path, '10.10.10.2', remote_path)
    

def get_config_file(local_path=None, remote_host=None, release='R5'):
    """
    Retrieves config file from remote host if specified or localhost if None.
    Sends file to cont0    
    """
    if local_path is None:
        local_path = '/folk/tmather/patches/TiS_config.ini_centos'
    remote_path = '/home/wrsroot/TiS_config.ini_centos'
    #TODO: fix for other releases.
    if remote_host is not None:
        if release == 'R5':
            sftp_get(Files.R5['config'], remote_host, local_path)
        elif release == 'R4':
            sftp_get(Files.R4['config'], remote_host, local_path)
        elif release == 'R3':
            sftp_get(Files.R3['config'], remote_host, local_path)
        else:
            sftp_get(Files.R2['config'], remote_host, local_path)
    sftp_send(local_path, '10.10.10.2', remote_path)
    
    
def check_services(stream):
    """
    Checks to see if sm services are running.
    Args:
        stream(stream): Stream to active controller
    """
    serial.send_bytes(stream, "source /etc/nova/openrc")
    serial.expect_bytes(stream, "active controller")

    print("Cannot activate keystone admin credentials")
    serial.send_bytes(stream, "sudo sm-dump")
    serial.expect_bytes(stream, "assword:")
    serial.send_bytes(stream, "Li69nux*")
    serial.expect_bytes(stream, "Failed")#check this
    print("Not all services were not activated successfully")
         

def run_install_scripts(stream, host_list, aio=False, storage=False):
    """
    Runs lab install.sh iterations. Currently does not support Simplex systems
    Args:
        stream: Stream to controller-0
        host_list: list of hosts, used when running aio scripts to install controller-1 at the appropriate time
        aio: Option to run the script for aio setup
        storage: Option to run the script for storage setup
    """
    serial.send_bytes(stream, "chmod +x *.sh")
    LOG.info("Starting lab install.")
    if aio:
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Stopping after data interface setup.",  timeout=HostTimeout.LAB_INSTALL)
        LOG.info("Running system compute-config-complete, installation will resume once controller-0 reboots and services are active")
        serial.send_bytes(stream, "system compute-config-complete")
        serial.expect_bytes(stream, "login:",  timeout=HostTimeout.REBOOT)
        serial.send_bytes(stream, "sudo sm-dump")
        serial.expect_bytes(stream, "Password:")
        serial.send_bytes(stream, "Li69nux*")
        check_services(stream)
        LOG.info("Services active, continuing install")
        serial.send_bytes(stream, "./lab_setup.sh")
        # check here
        if 'controller-1' in host_list:
            LOG.info("Installing controller-1")
            host_helper.install_host(stream, 'controller-1', 'controller', 2)
        serial.send_bytes(stream, "./lab_setup.sh")
        # check here

        if 'controller-1' in host_list:
            LOG.info("Unlocking Controller-1")
            host_helper.unlock_host(stream, 'controller-1')
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Done", timeout=HostTimeout.LAB_INSTALL)
        LOG.info("Completed install successfully.")
    else:
        serial.send_bytes(stream, "source /etc/nova/openrc")
        serial.send_bytes(stream, "./lab_setup.sh")

        serial.expect_bytes(stream, "Stopping after provider network creation.",  timeout=HostTimeout.LAB_INSTALL)
        if storage:
            for hosts in host_list:
                if hosts.startswith('storage'):
                    LOG.info("Unlocking {}".format(hosts))
                    host_helper.unlock_host(stream, hosts)
            serial.send_bytes(stream, "./lab_setup.sh")
            serial.expect_bytes(stream, "Stopping after initial storage node setup",  timeout=HostTimeout.LAB_INSTALL)
            LOG.info("Competed storage node unlock")
        LOG.info("Re-running lab_setup.sh")
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Stopping after data interface setup.", HostTimeout.LAB_INSTALL)
        for host in host_list:
            LOG.info("Unlocking {}".format(host))
            if host.statswith("compute"):
                host_helper.unlock_host(stream, host)
        serial.send_bytes(stream, "./lab_setup.sh")
        serial.expect_bytes(stream, "Done", HostTimeout.LAB_INSTALL)
        LOG.info("Completed lab install.")


def config_controller(stream, default=True, release='R5', config_file=None, backup=None, clone_iso=None,
                      restore_system=None, restore_images=None, remote_host=None):
    # TODO: add support for custom configs
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
    if config_file:
        get_config_file(config_file, remote_host, release)
            
    serial.send_bytes(stream, "sudo config_controller {}".format(args), timeout=HostTimeout.LAB_CONFIG)
    #serial.expect_bytes(stream, "The following configuration will be applied:")
    #serial.expect_bytes(stream, "Applying configuration")
    #serial.expect_bytes(stream, "Configuration was applied")
    #TODO: Check for return code for sent commands in send_bytes instead

def install_patches_before_config(stream):
    """
    Installs patches before controller_config has been run.
    Args:
        stream(stream): Stream to controller-0
    """
    serial.send_bytes(stream, 'sudo sw-patch upload-dir /home/wrsroot/patches')
    serial.expect_bytes(stream, 'Password')
    serial.send_bytes(stream, 'Li69nux*')
    serial.send_bytes(stream, 'sudo sw-patch apply --all')
    serial.send_bytes(stream, "sudo sw-patch install-local")
    serial.expect_bytes(stream, "installation is complete")
    serial.send_bytes(stream, 'sudo reboot')
    serial.expect_bytes(stream, 'login:', HostTimeout.REBOOT)
    host_helper.login(stream)


def install_patches_on_nodes(stream, host_list, patch_dir='/home/wrsroot/patches/'):
    """
    Installs patches on nodes in host_list
    """

    for items in host_list:
        serial.send_bytes(stream, 'sudo sw-patch upload-dir {}'.format(patch_dir))
        serial.send_bytes(stream, 'sudo sw-patch apply --all')
        host_helper.lock_host(stream, items)
        serial.send_bytes(stream, "sw-patch host-install-async {}".format(items))
        serial.expect_bytes(stream, "Patch installation request sent to {}".format(items))


def remove_patches(stream, host_list, patch_dir='/home/wrsroot/patches/'):
    """
    removes patches from nodes in host_list
    """
    for items in os.listdir(patch_dir):
        serial.send_bytes(stream, 'sw-patch remove {}'.format(items))
        # serial.expect_bytes(stream, "")
        serial.send_bytes(stream, "sw-patch query-hosts")
        serial.send_bytes(stream, 'system host-unlock {}'.format(items))
        serial.expect_bytes(stream, 'login:', HostTimeout.CONTROLLER_UNLOCK)
        
        
def delete_patches(stream, host_list, patch_dir='/home/wrsroot/patches/'):
    """
    Deletes patches from nodes in host_list
    """
    for items in os.listdir(patch_dir):
        serial.send_bytes(stream, 'sw-patch delete {}'.format(items))
        # serial.expect_bytes(stream, "")
        serial.send_bytes(stream, "sw-patch query-hosts")
        serial.send_bytes(stream, 'system host-unlock {}'.format(items))
        serial.expect_bytes(stream, 'login:', HostTimeout.CONTROLLER_UNLOCK)
        
        
def apply_patch(stream, patch_name, host_list):
    """
    Applies patch_name to the hosts given in host-list. 
    """
    serial.send_bytes(stream, "sw-patch apply {}".format(patch_name))
    for items in host_list:
        serial.send_bytes(stream, "sw-patch host-install-async {}".format(items))
        serial.send_bytes(stream, "sw-patch query-hosts | grep {}".format(items))
        serial.expect_bytes(stream, "")
