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
# Connect to Test server, run pre-checks, run test list, collect logs
#


import argparse
import pytest

from pytest import fail

from utils import ssh
from utils.ssh import SSHClient
from utils.tis_log import LOG


#import pdb;pdb.set_trace()
FUNCTEST_SERVER_PROMPT='$'
FUNCTEST_DOCKER_PROMPT=':~#'
FUNCTEST_LOG_DIR="/home/opnfv/functest/results/"
FUNCTEST_LOG_FILE="functest.log"
FUNCTEST_LOCAL_DIR="/home/opnfv/functest"
FUNCTEST_TESTS = ('all', 'connection_check', 'api_check','snaps_health_check', 'vping_ssh', 'tempest_smoke_serial',
 'rally_sanity', 'refstack_defcore', 'snaps_smoke', 'tempest_full_parallel', 'rally_full')

# Create Functest dictionary with all suites requested by Greg Waines, with maximum expected time for completion

FUNCTEST_TESTS_MAXDURATION = {"all":28800, "connection_check":300, "api_check":900,"snaps_health_check":900, "vping_ssh":900, "tempest_smoke_serial":3600,
 "rally_sanity":1800, "refstack_defcore":1800, "snaps_smoke":1800, "tempest_full_parallel":7200, "rally_full":7200}

def build_functest_list(functestTuple):
    local_list = []
    for item in functestTuple:
        if item in FUNCTEST_TESTS:
            local_list.append(item)
    return local_list


def build_functest_dict(functestTuple):
    local_dict = {}
    for item in functestTuple:
        if item in FUNCTEST_TESTS_MAXDURATION.keys():
            local_dict[item] = FUNCTEST_TESTS_MAXDURATION[item]

    return local_dict



def connect_functest(functestHost, username, password):
    global ssh_client

    try:
        ssh_client = SSHClient(host=functestHost, user=username, password=password,
                               initial_prompt=FUNCTEST_SERVER_PROMPT)
        ssh_client.connect()
        # check if Docker exists on functestHost, if not, SSH will throw exception
        ssh_client.send("which docker")
        ssh_client.expect("/usr/bin/docker", timeout=3)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: Wrong functest Host, Docker is not installed !")


def check_functest():
    try:
        ssh_client.send("docker ps")
        ssh_client.expect("FunctestContainer")
        ssh_client.set_prompt(FUNCTEST_DOCKER_PROMPT)
        ssh_client.send("docker exec -ti FunctestContainer bash", flush=True)
        ssh_client.expect(timeout=120)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest docker cannot be accessed !")


def run_connection_check():
    # ensure that Functest can call all base API, otherwise no need to continue
    try:
        ssh_client.send("functest testcase run connection_check")
        ssh_client.expect("functest - INFO - connection_check OK", timeout=120)
    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest connection_check failed !")


def run_test_loop(functestDict):
        # run functest test suite - will ensure that suite exists on server, before running
        # maybe add a field in TestList, such as max Guard Timer for execution by test suite
        # so, the timeout for expect does not have to be the same for each suite

    for test,maxduration in functestDict.items():
        cmd = "functest testcase run " + test
        ssh_client.send(cmd,flush=True)
        # ensure that the Docker prompt string cannot be seen in LOG output !!!
        try:
            # catching exception, to allow FOR loop to continue. May need to halt
            # unresponsive Test Suite by sending a "CTRL-C" character
            ssh_client.expect(timeout=maxduration,searchwindowsize=20)
        except Exception as e:
            ssh_client.send_control()
            ssh_client.expect(searchwindowsize=5)
            print(str(e))
            print("ERROR in Test: Functest ", test, " has timed out !")


def delete_functest_logs():

    try:
        logfile = FUNCTEST_LOG_DIR + FUNCTEST_LOG_FILE
        cmd = "rm " + logfile
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(timeout=20)
        cmd = "touch " + logfile
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(timeout=20)
        cmd = "ls " + logfile
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(logfile, timeout=20)

    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest timeout to delete logs")


def collect_functest_logs():
    # don't forget to set expected prompt, before exiting from Docker Container !!!
    try:

        logfile = FUNCTEST_LOCAL_DIR + "/results/" + FUNCTEST_LOG_FILE
        ssh_client.send_control()
        ssh_client.expect(searchwindowsize=5)

        ssh_client.set_prompt(FUNCTEST_SERVER_PROMPT)
        ssh_client.send("exit", flush=True)
        ssh_client.expect(timeout=60, fail_ok=True,searchwindowsize=5)

        cmd = "ls " + logfile
        cmd_return = "ls " + logfile + ": No such file"
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(cmd_return, fail_ok=True, timeout=10)

        cmd = "docker cp FunctestContainer:" + FUNCTEST_LOG_DIR + " " + FUNCTEST_LOCAL_DIR
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(timeout=20, fail_ok=True, searchwindowsize=5)

        cmd = "ls " + logfile
        cmd_return = "ls " + logfile + ": No such file"
        ssh_client.send(cmd, flush=True)
        ssh_client.expect(logfile, fail_ok=True, timeout=10)

    except Exception as e:
        print(str(e))
        print("ERROR in Test: Functest log collection did not worked  !")



def close_functest():
    ssh_client.close()


if __name__ == "__main__":

    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("functestHost")
        parser.add_argument("username")
        parser.add_argument("password")
        parser.add_argument("functestTestList")
        args = parser.parse_args()

        functestHost, username, password, functestTestList = args.functestHost, args.username, args.password, args.functestTestList
        functestTuple = tuple(item for item in functestTestList.split(',') if item.strip())
        functestDict = build_functest_dict(functestTuple)

# connect to functest Server and verify if it is running
        connect_functest(functestHost, username, password)
        check_functest()
        run_connection_check()
        delete_functest_logs()
        run_test_loop(functestDict)
        collect_functest_logs()
        close_functest()
# after disconnecting from server, reconnect with scp to store log files to Jenkins server
        #FUTURE CODE HERE TO STORE LOGS on JENKINS

    except Exception as e:
        print(str(e))
        print("ERROR in Test: TESTCASE FAILED !")

