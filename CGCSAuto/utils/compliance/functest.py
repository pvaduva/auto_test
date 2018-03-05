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
# This modules handles OPNFV Functest test execution, from Jenkins server
# It will: take Functest server arguments for login + Test List in csv format
# Connect to Test server, run pre-checks, run test list, collect logs and store them to
# Jenkins server

import pexpect
import argparse

from utils.jenkins_utils.create_log_dir import create_functest_log_dir
from utils.ssh import SSHClient

FUNCTEST_SERVER_PROMPT = '$'
FUNCTEST_DOCKER_PROMPT = ':~#'
FUNCTEST_LOG_DIR = "/home/opnfv/functest/results/"
FUNCTEST_LOG_FILE = "functest.log"
FUNCTEST_LOCAL_DIR = "/home/opnfv/functest"

# Create Functest dictionary with all suites requested by Greg Waines, with maximum expected time for completion

FUNCTEST_TESTS_MAXDURATION = {"all": 28800, "connection_check": 900, "api_check": 1200, "snaps_health_check": 900,
                              "vping_ssh": 900, "tempest_smoke_serial": 3600,
                              "rally_sanity": 3600, "refstack_defcore": 3600, "snaps_smoke": 3600,
                              "tempest_full_parallel": 14400, "rally_full": 14400}


def build_functest_dict(functest_tuple):
    local_dict = {}
    for item in functest_tuple:
        if item in FUNCTEST_TESTS_MAXDURATION.keys():
            local_dict[item] = FUNCTEST_TESTS_MAXDURATION[item]

    return local_dict


def connect_functest(functest_host, username, password):
    global ssh_client

    try:
        ssh_client = SSHClient(host=functest_host, user=username, password=password,
                               initial_prompt=FUNCTEST_SERVER_PROMPT)
        ssh_client.connect()
        # check if Docker exists on functest_host, if not, SSH will throw exception
        ssh_client.send("which docker", flush=True)
        ssh_client.expect("/usr/bin/docker", timeout=10)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: Wrong functest Host, Docker is not installed !")


def check_functest():
    try:
        ssh_client.exec_cmd(cmd="docker ps", blob="FunctestContainer", get_exit_code=False, fail_ok=False)
        ssh_client.set_prompt(FUNCTEST_DOCKER_PROMPT)
        ssh_client.send("docker exec -ti FunctestContainer bash", flush=True)
        ssh_client.expect(timeout=120)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest docker cannot be accessed !")


def run_connection_check():
    # ensure that Functest can call all base API, otherwise no need to continue
    try:
        ssh_client.exec_cmd(cmd="functest testcase run connection_check", blob="functest - INFO - connection_check OK",
                            expect_timeout=120, get_exit_code=False, fail_ok=False)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest connection_check failed !")


def run_test_loop(functest_dict):
    # run functest test suite - will ensure that suite exists on server, before running
    # maybe add a field in TestList, such as max Guard Timer for execution by test suite
    # so, the timeout for expect does not have to be the same for each suite

    for test, maxduration in functest_dict.items():
        cmd = "functest testcase run " + test
        ssh_client.send(cmd, flush=True)
        # ensure that the Docker prompt string cannot be seen in LOG output !!!
        try:
            # catching exception, to allow FOR loop to continue. May need to halt
            # unresponsive Test Suite by sending a "CTRL-C" character
            ssh_client.expect(timeout=maxduration, searchwindowsize=20)
        except Exception as e:
            ssh_client.send_control()
            ssh_client.expect(searchwindowsize=5)
            print(str(e))
            print("ERROR in Test: Functest ", test, " has timed out !")


def delete_functest_logs():
    # this will cleanup all files inside Docker container, using ssh connection to Functest host
    try:
        logfile = FUNCTEST_LOG_DIR + FUNCTEST_LOG_FILE
        cmd = "rm " + logfile
        ssh_client.exec_cmd(cmd=cmd, get_exit_code=False)

        cmd = "touch " + logfile
        ssh_client.exec_cmd(cmd=cmd, get_exit_code=False)

        list = ['refstack', 'tempest', 'rally']
        for i in list:
            cmd = "rm  " + FUNCTEST_LOG_DIR + i + "/*"
            ssh_client.exec_cmd(cmd=cmd, get_exit_code=False)

    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest timeout to delete logs")


def collect_functest_logs():
    # don't forget to set expected prompt, before exiting from Docker Container !!!
    try:

        ssh_client.send_control()
        ssh_client.expect(searchwindowsize=5)

        ssh_client.set_prompt(FUNCTEST_SERVER_PROMPT)
        ssh_client.send("exit", flush=True)
        ssh_client.expect(timeout=60, fail_ok=True, searchwindowsize=5)

        logfile = FUNCTEST_LOG_DIR + FUNCTEST_LOG_FILE
        cmd = "ls " + logfile
        cmd_return = "ls " + logfile + ": No such file"
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(cmd_return, fail_ok=True, timeout=10)

        # add cmd to delete files + sub-directories
        cmd = "rm -R " + FUNCTEST_LOG_DIR + "*"
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(timeout=20, fail_ok=True, searchwindowsize=5)

        cmd = "docker cp FunctestContainer:" + FUNCTEST_LOG_DIR + " " + FUNCTEST_LOCAL_DIR
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(timeout=20, fail_ok=True, searchwindowsize=5)

        cmd = "ls " + logfile
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(logfile, fail_ok=True, timeout=10)

    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest log collection did not worked  !")


def get_functest_logs(hostname, username, password, log_directory):
    to_host = hostname + ':'
    to_user = username + '@'

    source = to_user + to_host + FUNCTEST_LOG_DIR
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


def close_functest():
    ssh_client.close()


if __name__ == "__main__":

    try:
        # example to run program from command line:
        # functest.py yow-spapinea-lx-vm1 opnfv Li69nux*  "connection_check,api_check,rally_sanity" --local_log_directory /tmp
        parser = argparse.ArgumentParser()
        parser.add_argument("functest_host")
        parser.add_argument("username")
        parser.add_argument("password")
        parser.add_argument("functest_test_list")
        parser.add_argument("--local_log_directory", type=str, default='/sandbox/AUTOMATION_LOGS/')
        args = parser.parse_args()

        functest_host, username, password = args.functest_host, args.username, args.password
        functest_test_list, local_log_directory = args.functest_test_list, args.local_log_directory
        functest_tuple = tuple(item for item in functest_test_list.split(',') if item.strip())
        functest_dict = build_functest_dict(functest_tuple)

        local_dir = create_functest_log_dir(local_log_directory)

        # connect to functest Server and verify if Functest Docker container is running
        connect_functest(functest_host, username, password)
        check_functest()
        run_connection_check()
        delete_functest_logs()
        run_test_loop(functest_dict)
        collect_functest_logs()
        close_functest()
        get_functest_logs(functest_host, username, password, local_dir)

    except Exception as e:
        print(str(e))
        print("ERROR in Test: TESTCASE FAILED !")
