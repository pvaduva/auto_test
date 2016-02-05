#!/usr/bin/env python3.4

"""
collect_logs.py - Collects logs.

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
"""

import sys
import os
import argparse
import getpass
import socket
from utils.ssh import SSHClient
from constants import *

#TODO: Make --dest_ip optional and if specified make --path and --jira mutually exclusive options that are required if --dest_ip is specified
def parse_args():
    parser = argparse.ArgumentParser(formatter_class=\
                                     argparse.RawTextHelpFormatter,
                                     add_help=False, prog=__file__,
                                     description="Script to collect logs.")
    parser.add_argument('--src_ip', required=True,
                          help="Floating IP address")
    parser.add_argument('--dest_ip', required=True,
                        default=socket.gethostbyname(DEFAULT_BLD_SERVER + HOST_EXT),
                        help="Destination IP address")
    parser.add_argument('--path', help="Destination path to scp logs to")
    parser.add_argument('--jira', help="JIRA identifier to create destination folder with under " + JIRA_LOGS_DIR + " on " + DEFAULT_BLD_SERVER)
    parser.add_argument('-h','--help', action='help',
                           help="Show this help message and exit")

    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_args()

    src_ip = args.src_ip
    dest_ip = args.dest_ip
    jira_id = args.jira

    if jira_id:
        logs_dir = JIRA_LOGS_DIR + "/" + jira_id
    else:
        logs_dir = args.path

    if dest_ip:
        user = getpass.getuser()
        passwd = getpass.getpass()

    cont0_ssh_conn = SSHClient(log_path=sys.stdout)
    cont0_ssh_conn.connect(hostname=src_ip, username=WRSROOT_USERNAME,
                            password=WRSROOT_PASSWORD)

    tarball = cont0_ssh_conn.collect_logs()
#    tarball = "/scratch/ALL_NODES_20160122.234108.tar.tgz"
    tarball = os.path.splitext(tarball)[0]+'.gz'

    dest_server_conn = SSHClient()
    dest_server_conn.connect(hostname=dest_ip,
                            username=user, password=passwd)

    ssh_key = cont0_ssh_conn.get_ssh_key()
    dest_server_conn.deploy_ssh_key(ssh_key)

    dest_server_conn.sendline("mkdir -p " + logs_dir)
    dest_server_conn.find_prompt()
    cont0_ssh_conn.rsync(tarball, user, dest_ip, logs_dir)
    dest_server_conn.sendline("chmod -R 775 " + logs_dir)
    dest_server_conn.find_prompt()

    sys.exit(0)