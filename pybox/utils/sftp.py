#!/usr/bin/python3

import getpass
import os
import paramiko
import time
from sys import platform
from utils.install_log import LOG


def sftp_get(source, remote_host, destination):
    """
    Get files from remote server.

    Arguments:
    - source: full path to file including the filename
    e.g. /localhost/loadbuild/jenkins/CGCS_5.0_Host/latest_build/bootimage.iso
    - Remote host: name of host to log into, 
    e.g. yow-cgts4-lx.wrs.com
    - destination: where to store the file locally: /tmp/bootimage.iso

    Note, keys must be setup for this to work.
    """
    username = getpass.getuser()
    if platform == 'win32' or platform == 'win64':
        #privatekeyfile = os.path.expanduser('C:\\Users\\{}\\.ssh\\'.format(username))
        pass
    else:
        privatekeyfile = os.path.expanduser('~/.ssh/id_rsa')
    #mykey = paramiko.RSAKey.from_private_key_file(privatekeyfile)

    LOG.info("Connecting to server {} with username {}".format(remote_host, username))

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password="Oliverthekitty1")
    sftp_client = ssh_client.open_sftp()
    LOG.info("Sending file from {} to {}".format(source, destination))
    sftp_client.get(source, destination)
    LOG.info("Done")
    sftp_client.close()
    ssh_client.close()


def sftp_send(source, remote_host='10.10.10.3', destination='/home/wrsroot/'):
    """
    Send files to remote server, usually controller-0
    args:
    - source: full path to file including the filename
    e.g. /localhost/loadbuild/jenkins/CGCS_5.0_Host/latest_build/bootimage.iso
    - Remote host: name of host to log into, controller-0 by default
    e.g. yow-cgts4-lx.wrs.com
    - destination: where to store the file locally: /tmp/bootimage.iso
    """
    username = 'wrsroot'
    password = 'Li69nux*'

    LOG.info("Connecting to server {} with username {}".format(remote_host, username))

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password=password, look_for_keys=False, allow_agent=False)
    sftp_client = ssh_client.open_sftp()


    LOG.info("Sending file from {} to {}".format(source, destination))
    sftp_client.put(source, destination)
    LOG.info("Done")
    sftp_client.close()
    ssh_client.close()
    
    
def send_dir(source, remote_host='10.10.10.3', destination='/home/wrsroot/'):
    """
    Send directory contents to remote server, usually controller-0
    Note: does not send nested directories only files.
    args:
    - source: full path to directory
    e.g. /localhost/loadbuild/jenkins/CGCS_5.0_Host/latest_build/
    - Remote host: name of host to log into, controller-0 by default
    e.g. yow-cgts4-lx.wrs.com
    - destination: where to store the file on host: /home/wrsroot/
    """
    username = 'wrsroot'
    password = 'Li69nux*'

    LOG.info("Connecting to server {} with username {}".format(remote_host, username))
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password=password, look_for_keys=False, allow_agent=False)
    sftp_client = ssh_client.open_sftp()
    path = ''
    for items in os.listdir(source):
        path = source+items
        if os.path.isfile(path):
            if items.endswith('.img'):
                remote_path = destination+'images/'+items
                LOG.info("Sending file from {} to {}".format(path, remote_path))
                sftp_client.put(path, remote_path)
            elif items.endswith('.iso'):
                pass
            else:
                remote_path = destination+items
                LOG.info("Sending file from {} to {}".format(path, remote_path))
                sftp_client.put(path, remote_path)
    LOG.info("Done")
    sftp_client.close()
    ssh_client.close()
    
    
def get_dir(source, remote_host, destination, patch=False, setup=False):
    """
    get directory contents from remote server
    Note: does not get nested directories only files.
    args:
    - source: full path to directory
    e.g. /localhost/loadbuild/jenkins/CGCS_5.0_Host/latest_build/
    - Remote host: name of host to log into, controller-0 by default
    e.g. yow-cgts4-lx.wrs.com
    - destination: where to store the files locally: e.g. /tmp/files/
    """
    username = getpass.getuser()
    if platform == 'win32' or platform == 'win64':
        #privatekeyfile = os.path.expanduser('C:\\Users\\{}\\.ssh\\'.format(username))
        pass
    else:
        privatekeyfile = os.path.expanduser('~/.ssh/id_rsa')
    # mykey = paramiko.RSAKey.from_private_key_file(privatekeyfile)
    LOG.info("Connecting to server {} with username {}".format(remote_host, username))
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password="Oliverthekitty1")
    sftp_client = ssh_client.open_sftp()
    LOG.info(sftp_client.listdir(source))
    path = ''
    for items in sftp_client.listdir(source):
        path = source+items
        local_path = destination + items
        try:
            if patch:
                if path.endswith('.patch'):
                    LOG.info("Sending file from {} to {}".format(path, local_path))
                    sftp_client.get(path, local_path)
            else:
                LOG.info('Sending {} to {}'.format(path, local_path))
                sftp_client.get(path, local_path)
        except IOError:
            LOG.error("Cannot transfer {}".format(path))
    LOG.info("Done")
    sftp_client.close()
    ssh_client.close()