#!/usr/bin/env python3.4

'''
common.py - Common utilities.

Copyright (c) 2015-2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
    
    
modification history:
---------------------
22feb16,amf  Using the full path for the node data file
02dec15,kav  initial version
'''


from constants import *
from .log import getLogger, print_step
from .classes import Host
import sys
import os
import re
import subprocess
import configparser
import pexpect

log = getLogger(__name__)

#TODO: Decide if functions should return 1 instead of sys.exit(1)

def create_node_dict(nodes, personality):
    """Read .ini file for each node and create Host object for the node.

    The data in the .ini file is read into a dictionary which is used to
    create a Host object for the node.

    Return dictionary of node names mapped to their respective Host objects.
    """
    node_dict = {}
    i = 0
    
    for node in nodes:
        config = configparser.ConfigParser()
        try:
            local_path = os.path.dirname(__file__)
            node_filepath = os.path.join(local_path, '..',
                                         NODE_INFO_DIR, '%s.ini' % node)
            node_file = open(node_filepath, 'r')
            config.read_file(node_file)
        except Exception:
            log.exception('Failed to read \"{}\"'.format(node_filepath))
            sys.exit(1)

        node_info_dict = {}
        for section in config.sections():
            for opt in config.items(section):
                key, value = opt
                node_info_dict[section + '_' + key] = value
        name = personality + "-{}".format(i)
        node_info_dict['name'] = name
        node_info_dict['personality'] = personality
        node_info_dict['barcode'] = node

        node_dict[name]=Host(**node_info_dict)
        i += 1

    print_step(personality + " nodes:")
    for key, value in sorted(node_dict.items()):
        value.print_attrs()
        print()

    return node_dict

def remove_markers(str):
    return str.translate({ord(OPEN_MARKER): '', ord(CLOSE_MARKER): ''})

def find_error_msg(str, msg="error"):
    if re.search(msg, str, re.IGNORECASE):
        found_error_msg = True
    else:
        found_error_msg = False
    return found_error_msg

def pexpect_exec_cmd(cmd, tmout=10, event_dict=None):
    """Run cmd on localhost using pexpect.run.

    pexpect.run supports sending a dictionary of patterns and responses as
    events if specified.

    Return return code and output from command.
    """
    log.info(cmd)
    (output, rc) = pexpect.run(cmd, timeout=tmout, withexitstatus=1,
                               events=event_dict)
    return (rc, output.decode('utf-8','ignore'))

def exec_cmd(cmd, show_output=True):
    rc = 0
    log.info(" ".join(cmd))
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, universal_newlines=True)
    except subprocess.CalledProcessError as ex:
        rc = ex.returncode
        output = ex.output
    output = output.rstrip()
    if output and show_output:
        log.info("Output:\n" + output)
    log.info("Return code: " + str(rc))
    return (rc, output)

def get_ssh_key():
    ssh_key_fpath = os.path.expanduser(SSH_KEY_FPATH)
    if not os.path.isfile(ssh_key_fpath):
        print("CMD = " + CREATE_PUBLIC_SSH_KEY_CMD.format(ssh_key_fpath))
        if exec_cmd(CREATE_PUBLIC_SSH_KEY_CMD)[0] != 0:
            log.error("Failed to create public ssh key for current user")
            sys.exit(1)
    ssh_key = exec_cmd(GET_PUBLIC_SSH_KEY_CMD.format(ssh_key_fpath).split())[1]
    return ssh_key

def vlm_reserve(barcodes, note=None):
    total_barcodes = []
    # number of targets we can reserve in VLM at once
    n = 5
    if isinstance(barcodes, str):
        barcodes = [barcodes]
    chunks = [barcodes[i:i+n] for i in range(0,len(barcodes), n)]
    action = VLM_RESERVE
    for chunk in chunks:
        print(chunk)
        cmd = [VLM, action, "-t"]
        # convert chunk to strings
        [cmd.append(barcode) for barcode in chunk]
        reserve_note_params = []
        if note is not None:
            #reserve_note_params = ["-n", note]
            reserve_note_params = ["-n", '"{}"'.format(note)]
            cmd += reserve_note_params
            print("This is cmd: %s" % cmd)
            #reserved_barcodes = exec_cmd(cmd)
            reserved_barcodes = exec_cmd(cmd)[1]
            if not reserved_barcodes or "Error" in reserved_barcodes:
                log.error("Failed to reserve target(s): " + str(chunk))
                sys.exit(1)
        total_barcodes.extend(reserved_barcodes.split())
    if any(barcode not in total_barcodes for barcode in barcodes):
        msg = "Only reserved {} of {}".format(total_barcodes, barcodes)
        msg += ". Remaining barcode(s) are already reserved"
        log.error(msg)
        sys.exit(1)

def vlm_getattr(barcodes):
    attr_values = []
    if isinstance(barcodes, str):
        barcodes = [barcodes]
    for barcode in barcodes:
        attr_dict = {}
        cmd = [VLM, VLM_GETATTR, "-t"]
        cmd.append(barcode)
        cmd.append("all")
        output = exec_cmd(cmd)[1]
        if not output or "Error" in output:
            log.error("Failed to get attributes for target(s): {}".format(barcodes))
            sys.exit(1)
        for line in output.splitlines():
            if line:
                attr, val = re.split("\s*:\s+", line)
                attr_dict[attr] = val
        attr_values.append(attr_dict)
    return attr_values

def vlm_findmine():
    cmd = [VLM, VLM_FINDMINE]
    output = exec_cmd(cmd)[1]
    if re.search("\d+", output):
        reserved_targets = output.split()
        msg = "Target(s) reserved by user: {}".format(str(reserved_targets))
    else:
       msg = "User has no reserved target(s)"
       reserved_targets = []
    log.info(msg)
    return reserved_targets

def vlm_exec_cmd(action, barcode):
    if action not in VLM_CMDS_REQ_RESERVE:
        msg = '"{}" is an invalid action.'.format(action)
        msg += " Valid actions: {}".format(str(VLM_CMDS_REQ_RESERVE))
        log.error(msg)
        return 1
    elif barcode not in vlm_findmine():
        log.error("Failed to {} target {}. Target is not reserved by user".format(action, barcode))
        sys.exit(1)
    else:
        cmd = [VLM, action, "-t", barcode]
        output = exec_cmd(cmd)[1]
        if output != "1":
            log.error('Failed to execute "{}" on target'.format(barcode))
            sys.exit(1)
