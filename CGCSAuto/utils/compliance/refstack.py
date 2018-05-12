#!/usr/bin/env python3
#
# Copyright (c) 2017 Wind River Systems, Inc.
#
#       The right to copy, distribute, modify or otherwise make use
#       of this software may be licensed only pursuant to the terms
#       of an applicable Wind River license agreement.
#
#
# Description:
# This modules handles refstack test execution, from Jenkins server
# It will: take refstack server arguments for login + Test List file 
# Connect to Test server, run pre-checks, run test list, collect logs and store them to
# Jenkins server

import argparse

from utils.jenkins_utils.create_log_dir import create_test_log_dir
import pexpect
from utils.clients.ssh import SSHClient
from utils.jenkins_utils.create_log_dir import create_refstack_log_dir


TEST_SERVER_PROMPT = '$'
TEST_LOG_DIR = ""
TEST_LOCAL_DIR = ""
TEST_LIST_file = ""
TEST_MAX_TIMEOUT = 20000
TEST_LOG_FILES_LIST = ['/failing', '/test_run.log', '/[0-9]*', '/summary.txt']


def connect_test(test_host, username, password):
    global ssh_client

    try:
        ssh_client = SSHClient(host=test_host, user=username, password=password,
                               initial_prompt=TEST_SERVER_PROMPT)
        ssh_client.connect()
    except Exception as e:
        print(str(e))
        print("ERROR in Test: SSH is not connected")

def set_test_list_file(hostname, username, password, refstack_test_list):
    to_host = hostname + ':'
    to_user = username + '@'
    # copy test-list file to test server
    source = refstack_test_list
    destination = to_user + to_host + TEST_LIST_file
    scp_cmd = ' '.join(['scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r', source,
                        destination]).strip()
    try:
        var_child = pexpect.spawn(scp_cmd)
        i = var_child.expect(["password:", pexpect.EOF])
        if i == 0:
            var_child.sendline(password)
            var_child.expect(pexpect.EOF)
        elif i == 1:
            print
            "Scp test-list file to test server timeout"
            pass
    except Exception as e:
        print(e)
    # copy parse tool to test server
    source = "/folk/cgts/compliance/RefStack/parseResults.awk"
    destination = to_user + to_host + TEST_LOCAL_DIR + "/parseResults.awk"
    scp_cmd = ' '.join(['scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r', source,
                        destination]).strip()
    try:
        var_child = pexpect.spawn(scp_cmd)
        i = var_child.expect(["password:", pexpect.EOF])
        if i == 0:
            var_child.sendline(password)
            var_child.expect(pexpect.EOF)
        elif i == 1:
            print
            "Scp test-list file to test server timeout"
            pass
    except Exception as e:
        print(e)


def run_test():
    # setup refstack test environment 
    cmd = "cd " + TEST_LOCAL_DIR
    ssh_client.send(cmd, flush=True)
    try:
        ssh_client.expect(timeout=20, searchwindowsize=20)
    except Exception as e:
        ssh_client.send_control()
        ssh_client.expect(searchwindowsize=5)
        print(str(e))
        print("ERROR in Test: refsteack has timed out !")

    # run refstack test suite by giving test_list.txt 
    cmd = "source .venv/bin/activate; refstack-client test -c etc/tempest.conf -v --test-list " + TEST_LIST_file + " > " + TEST_LOG_DIR + "/test_run.log"
    ssh_client.send(cmd, flush=True)
    try:
        ssh_client.expect("JSON results saved in", timeout=TEST_MAX_TIMEOUT, searchwindowsize=200)
    except Exception as e:
        ssh_client.send_control()
        ssh_client.expect(searchwindowsize=5)
        print(str(e))
        print("ERROR in Test: refsteack run has timed out !")

    # parse the result
    cmd = "awk -f " + TEST_LOCAL_DIR + "/parseResults.awk " + TEST_LOG_DIR + "/[0-9]*" + " > " + TEST_LOG_DIR + "/summary.txt"
    ssh_client.send(cmd, flush=True)
    try:
        ssh_client.expect(timeout=60, searchwindowsize=200)
    except Exception as e:
        ssh_client.send_control()
        ssh_client.expect(searchwindowsize=5)
        print(str(e))
        print("ERROR in Test: refsteack run has timed out !")


def delete_previous_test_logs():
    for item in TEST_LOG_FILES_LIST :
        cmd = "rm " + TEST_LOG_DIR + item
        ssh_client.send(cmd, flush=True)


def get_test_logs(hostname, username, password, log_directory):
    to_host = hostname + ':'
    to_user = username + '@'
    # copy log files to test server
    for item in TEST_LOG_FILES_LIST :
        source = to_user + to_host + TEST_LOG_DIR + item
        scp_cmd = ' '.join(['scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r', source,
                        log_directory]).strip()
        try:
            var_child = pexpect.spawn(scp_cmd)
            i = var_child.expect(["password:", pexpect.EOF])
            if i == 0:
                var_child.sendline(password)
                var_child.expect(pexpect.EOF)
            elif i == 1:
                print
                "Got connection timeout"
                pass
        except Exception as e:
            print(e)


def close_test():
    ssh_client.close()


if __name__ == "__main__":

    try:
        # example to run program from command line:
        # refstack.py yow-spapinea-lx-vm1 opnfv Li69nux*  "connection_check,api_check,rally_sanity" --local_log_directory /tmp
        parser = argparse.ArgumentParser()
        parser.add_argument("test_host")
        parser.add_argument("username")
        parser.add_argument("password")
        parser.add_argument("refstack_test_list")
        parser.add_argument("--refstack_install_directory", type=str, default='/home/opnfv/refstack/refstack-client')
        #parser.add_argument("--local_log_directory", type=str, default='/sandbox/AUTOMATION_LOGS/')
        parser.add_argument("--local_log_directory", type=str, default='/tmp/AUTOMATION_LOGS/')
        args = parser.parse_args()

        test_host, username, password = args.test_host, args.username, args.password
        refstack_test_list = args.refstack_test_list
        TEST_LOCAL_DIR = args.refstack_install_directory
        local_log_directory = args.local_log_directory

        local_dir = create_test_log_dir("refstack", local_log_directory)

        TEST_LOG_DIR = TEST_LOCAL_DIR + "/.tempest/.testrepository"
        TEST_LIST_file = TEST_LOCAL_DIR + "/test-list.txt"
        # connect to test Server 
        print ("\n\n###########################################\n")
        print ("Refstack test run starts...\n")
        connect_test(test_host, username, password)
        print ("connect to test server {} successfully.\n". format(test_host))
        delete_previous_test_logs()
        print ("All previous logs were cleaned. \n")
        set_test_list_file(test_host, username, password, refstack_test_list)
        print ("test_list file is set on test server\n")
        run_test()
        print ("test run is done!\n")
        get_test_logs(test_host, username, password, local_dir)
        print ("Log files are collected @yow-cgcs-test.wrs.com:/sandbox/AUTOMATION_LOGS/refstack/\n")
        close_test()
        print ("Refstack Test run is completed.\n")
        print ("###########################################\n\n")

    except Exception as e:
        print(str(e))
        print("ERROR in Test: Refstack TEST FAILED !")
