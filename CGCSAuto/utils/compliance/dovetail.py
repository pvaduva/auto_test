#!/usr/bin/env python3
#
# Copyright (c) 2017 Wind River Systems, Inc.
#
#       The right to copy, distribute, modify or otherwise make use
#       of this software may be licensed only pursuant to the terms
#       of an applicable Wind River license agreement.
#
#       modification history
#       01nov17 spapinea Created
#
# Description:
# This modules handles OPNFV divetail test execution, from Jenkins server
# It will: take dovetail server arguments for login + Test List in csv format
# Connect to Test server, run pre-checks, run test list, collect logs and store them to
# Jenkins server

import pexpect
import argparse

from utils.jenkins_utils.create_log_dir import create_test_log_dir
from utils.clients.ssh import SSHClient

SERVER_PROMPT = '$'
DOCKER_PROMPT = '#'
LOG_DIR = "/home/opnfv/dovetail/results/"
LOG_FILE = "dovetail.log"
LOCAL_DIR = "/home/opnfv/dovetail"


def connect_host(host, username, password):
    global ssh_client

    try:
        ssh_client = SSHClient(host=host, user=username, password=password,
                               initial_prompt=SERVER_PROMPT)
        ssh_client.connect()
        # check if Docker exists on functest_host, if not, SSH will throw exception
        ssh_client.send("which docker", flush=True)
        ssh_client.expect("/usr/bin/docker", timeout=10)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: Wrong Host, Docker is not installed !")


def start_dovetail_docker():
    cmd = "source /home/opnfv/dovetail/pre_config/env_config.sh"
    try:
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(timeout=120)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: docker cannot be accessed !")

    cmd = "docker run --privileged=true -it \
            -e DOVETAIL_HOME=/home/opnfv/dovetail \
            -v /home/opnfv/dovetail/:/home/opnfv/dovetail/ \
            -v /var/run/docker.sock:/var/run/docker.sock opnfv/dovetail:ovp.1.0.0 /bin/bash"
    try:
        ssh_client.set_prompt(DOCKER_PROMPT)
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(timeout=120)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: docker cannot be accessed !")


def run_test(test_parameter):
    cmd = "dovetail run " + test_parameter  + " > /tmp/test_run.log"
    ssh_client.send(cmd, flush=True)
    # ensure that the Docker prompt string cannot be seen in LOG output !!!
    try:
        ssh_client.expect(timeout=7200, searchwindowsize=20)
    except Exception as e:
        ssh_client.send_control()
        ssh_client.expect(searchwindowsize=5)
        print(str(e))
        print("ERROR in Test: dovetail test has timed out !")

    cmd = "cp /tmp/test_run.log " + LOG_DIR
    ssh_client.send(cmd, flush=True)
    # ensure that the Docker prompt string cannot be seen in LOG output !!!
    try:
        ssh_client.expect(timeout=7200, searchwindowsize=20)
    except Exception as e:
        ssh_client.send_control()
        ssh_client.expect(searchwindowsize=5)
        print(str(e))
        print("ERROR in Test: dovetail test has timed out !")


def get_dovetail_logs(hostname, username, password, log_directory):
    to_host = hostname + ':'
    to_user = username + '@'

    source = to_user + to_host + LOG_DIR + "/*"
    scp_cmd = ' '.join(['scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r', source,
                        log_directory]).strip()
    try:
        var_child = pexpect.spawn(scp_cmd)
        i = var_child.expect(["password:", pexpect.EOF])

        if i == 0:
            var_child.sendline(password)
            var_child.expect(pexpect.EOF)
        elif i == 1:
            print ("Got connection timeout")
            pass
    except Exception as e:
        print(e)


def close_test():
    ssh_client.close()


if __name__ == "__main__":

    try:
        # example to run program from command line:
        # dovetail.py yow-spapinea-lx-vm1 opnfv Li69nux*  "--testarea mandatory" --local_log_directory /tmp
        parser = argparse.ArgumentParser()
        parser.add_argument("host")
        parser.add_argument("username")
        parser.add_argument("password")
        parser.add_argument("test_parameter")
        parser.add_argument("--local_log_directory", type=str, default='/sandbox/AUTOMATION_LOGS/')
        args = parser.parse_args()

        host, username, password = args.host, args.username, args.password
        test_parameter, local_log_directory = args.test_parameter, args.local_log_directory

        local_dir = create_test_log_dir("dovetail", local_log_directory)
        # connect to Server 
        print ("\n\n###########################################\n")
        print ("Dovetail test run starts...\n")
        connect_host(host, username, password)
        print ("connect to test server {} successfully.\n". format(host))
        start_dovetail_docker()
        print ("dovetail docker is started\n")
        run_test(test_parameter)
        print ("test run is done!\n")
        
        close_test()
        get_dovetail_logs(host, username, password, local_dir)
        print ("Log files are collected @yow-cgcs-test.wrs.com:/sandbox/AUTOMATION_LOGS/dovetail/\n")
    except Exception as e:
        print(str(e))
        print("ERROR in Test: TESTCASE FAILED !")
