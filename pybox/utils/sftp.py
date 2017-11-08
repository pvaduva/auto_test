#!/usr/bin/python3

import getpass
import os
import paramiko
import time

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

    privatekeyfile = os.path.expanduser('/folk/tmather/.ssh/id_rsa')
    mykey = paramiko.RSAKey.from_private_key_file(privatekeyfile)
    username = getpass.getuser()

    print("Connecting to server {} with username {}".format(remote_host, username))

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password='Oliverthekitty1')
    sftp_client = ssh_client.open_sftp()
    print("Sending file from {} to {}".format(source, destination))
    LOG.info("Sending file from {} to {}".format(source, destination))
    sftp_client.get(source, destination)
    print("Done")    
    sftp_client.close()
    ssh_client.close()


def sftp_send(source, remote_host='10.10.10.2', destination='/home/wrsroot/'):
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

    print("Connecting to server {} with username {}".format(remote_host, username))

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password=password)
    sftp_client = ssh_client.open_sftp()

    print("Sending file from {} to {}".format(source, destination))
    LOG.info("Sending file from {} to {}".format(source, destination))
    sftp_client.put(source, destination)
    print("Done")    
    sftp_client.close()
    ssh_client.close()
    
    
def send_dir(source, remote_host='10.10.10.2', destination='/home/wrsroot/'):
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

    print("Connecting to server {} with username {}".format(remote_host, username))
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password=password)
    sftp_client = ssh_client.open_sftp()
    print("Sending files {}".format(os.listdir(source)))
    path = ''
    for items in os.listdir(source):
        path=source+items
        if os.path.isfile(path):
            if items.endswith('.img'):
                remote_path=destination+'images/'+items
                LOG.info("Sending file from {} to {}".format(path, remote_path))
                print('Sending {} to {}'.format(path, remote_path))
                sftp_client.put(path, remote_path)
                
            else:
                remote_path=destination+items
                LOG.info("Sending file from {} to {}".format(path, remote_path))
                print('Sending {} to {}'.format(path, remote_path))
                sftp_client.put(path, remote_path)
    print("Done")
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
    # privatekeyfile = os.path.expanduser('/folk/tmather/.ssh/id_rsa')
    # mykey = paramiko.RSAKey.from_private_key_file(privatekeyfile)
    print("Connecting to server {} with username {}".format(remote_host, username))
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, password='Oliverthekitty1')
    sftp_client = ssh_client.open_sftp()
    print(sftp_client.listdir(source))
    path = ''
    for items in sftp_client.listdir(source):
        path=source+items
        local_path = destination + items
        try:
            if patch:
                if path.endswith('.patch'):
                    LOG.info("Sending file from {} to {}".format(path, local_path))
                    print('Sending {} to {}'.format(path, local_path))
                    old_file = sftp.stat(path).st_size
                    print(old_file)
                    sftp_client.get(path, local_path)
            else:
                print('Sending {} to {}'.format(path, local_path))
                sftp_client.get(path, local_path)
        except IOError:
            print("Cannot transfer {}".format(path))
    print("Done")
    sftp_client.close()
    ssh_client.close()