#!/usr/bin/python3

import getpass
import os
import paramiko

def sftp_get(remote_path, remote_host, local_path):
    """
    Get files from remote server.

    Arguments:
    - Remote path: full path to file including the filename
    e.g. /localhost/loadbuild/jenkins/CGCS_5.0_Host/latest_build/bootimage.iso
    - Remote host: name of host to log into, 
    e.g. yow-cgts4-lx.wrs.com
    - Local path: where to store the file locally: /tmp/bootimage.iso

    Note, keys must be setup for this to work.
    """

    privatekeyfile = os.path.expanduser('~/.ssh/id_rsa')
    mykey = paramiko.RSAKey.from_private_key_file(privatekeyfile)
    username = getpass.getuser()

    print("Connecting to server {} with username {}".format(remote_host, username))

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(remote_host, username=username, pkey=mykey)
    sftp_client = ssh_client.open_sftp()

    print("Getting file: {}".format(remote_path))

    sftp_client.get(remote_path, local_path)
    sftp_client.close()
    ssh_client.close()
