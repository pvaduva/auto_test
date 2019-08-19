import time
import traceback
import logging

import paramiko

logging.getLogger("paramiko").setLevel(logging.WARNING)


def sftp_send(source, remote_host, destination, username, password):
    """
    Send files to remote server, usually controller-0
    args:
    - source: full path to file including the filename
    e.g. /localhost/loadbuild/jenkins/CGCS_5.0_Host/latest_build/bootimage.iso
    - Remote host: name of host to log into, controller-0 by default
    e.g. yow-cgts4-lx.wrs.com
    - destination: where to store the file locally: /tmp/bootimage.iso
    """
    print("Connecting to server {} with username {}".format(remote_host, username))

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ## TODO(WEI): need to make this timeout handling better
    retry = 0
    while retry < 8:
        try:
            ssh_client.connect(remote_host, username=username, password=password,
                               look_for_keys=False, allow_agent=False)
            sftp_client = ssh_client.open_sftp()
            retry = 8
        except Exception as e:
            print("******* try again")
            retry += 1
            time.sleep(10)

    print("Sending file from {} to {}".format(source, destination))
    sftp_client.put(source, destination)
    print("Done")
    sftp_client.close()
    ssh_client.close()


def ssh_command(ip, username, password, command):
    """ Set up ssh connection with ip using username and password, execute command,
    and return the output
    :param ip: The ip address to connect
    :param username: The username for setting up ssh connection
    :param password: The password for setting up ssh connection
    :param command: The command to be executed after ssh connection set up
    :return: The output of the command in one string
    """
    client = None
    output = ''
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password)
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode('ascii')
        logging.debug('ssh command output:\n{}'.format(output))
        # print('ssh command output:\n{}'.format(output))
    except Exception:
        logging.debug('ssh error:\n{}'.format(traceback.format_exc()))
    finally:
        if client:
            client.close()
    return output
