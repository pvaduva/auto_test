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

import smtplib
from email.mime.text import MIMEText

log = getLogger(__name__)


# TODO: Would be nice to have a common function which can perform an
#      action on a node (e.g. lock, unlock)
#      It would take parameter host_name and action='unlock', say by default

# TODO: Decide if functions should return 1 instead of sys.exit(1)

def create_node_dict(nodes, personality):
    """Get attributes of each node through VLM and create Host object for
    the node

    Read .ini file for necessary information not provided by VLM:
    telnet_login_prompt, nic, and web console


    The data is read into a dictionary which is used to create a Host object
    for the node.

    Return dictionary of node names mapped to their respective Host objects.
    """
    # Reserve the nodes so their telnet information can be collected
    # Unreserve first to close any telnet sessions
    vlm_unreserve(nodes)
    vlm_reserve(nodes, note=INSTALLATION_RESERVE_NOTE)

    nodes_info = vlm_getattr(nodes)
    node_dict = {}
    config = configparser.ConfigParser()
    for i in range(0, len(nodes_info)):
        try:
            local_path = os.path.dirname(__file__)
            node_filepath = os.path.join(local_path, '..',
                                         NODE_INFO_DIR, '%s.ini' % nodes[i])
            node_file = open(node_filepath, 'r')
            config.read_file(node_file)
        except Exception:
            msg = 'Failed to read \"{}\"'.format(node_filepath)
            log.exception(msg)

            wr_exit()._exit(1, msg)

        node_info_dict = {}
        for section in config.sections():
            for opt in config.items(section):
                key, value = opt
                node_info_dict[section + '_' + key] = value

        name = personality + "-{}".format(i)
        node_info_dict['name'] = name
        node_info_dict['personality'] = personality
        node_info_dict['host_ip'] = nodes_info[i]['IP Address']
        node_info_dict['telnet_ip'] = nodes_info[i]['Terminal Server']
        node_info_dict['host_name'] = nodes_info[i]['Target Alias']
        node_info_dict['telnet_port'] = str(2000 + int(nodes_info[i]['Terminal Server Port']))
        node_info_dict['barcode'] = nodes_info[i]['Target ID']
        node_dict[name] = Host(**node_info_dict)

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
    return (rc, output.decode('utf-8', 'ignore'))


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
            msg = "Failed to create public ssh key for current user"
            log.error(msg)
            wr_exit()._exit(1, msg)

    ssh_key = exec_cmd(GET_PUBLIC_SSH_KEY_CMD.format(ssh_key_fpath).split())[1]
    return ssh_key


def vlm_reserve(barcodes, note=None):
    total_barcodes = []
    # number of targets we can reserve in VLM at once
    n = 5
    if isinstance(barcodes, str):
        barcodes = [barcodes]
    chunks = [barcodes[i:i + n] for i in range(0, len(barcodes), n)]
    action = VLM_RESERVE
    for chunk in chunks:
        print(chunk)
        cmd = [VLM, action, "-t"]
        # convert chunk to strings
        [cmd.append(barcode) for barcode in chunk]
        reserve_note_params = []
        if note is not None:
            # reserve_note_params = ["-n", note]
            reserve_note_params = ["-n", '"{}"'.format(note)]
            cmd += reserve_note_params
            print("This is cmd: %s" % cmd)
            # reserved_barcodes = exec_cmd(cmd)
            reserved_barcodes = exec_cmd(cmd)[1]
            if not reserved_barcodes or "Error" in reserved_barcodes:
                msg = "Failed to reserve target(s): " + str(chunk)
                log.error(msg)
                wr_exit()._exit(1, msg)

        total_barcodes.extend(reserved_barcodes.split())
    if any(barcode not in total_barcodes for barcode in barcodes):
        msg = "Only reserved {} of {}".format(total_barcodes, barcodes)
        msg += ". Remaining barcode(s) are already reserved"
        log.error(msg)
        wr_exit()._exit(1, msg)


def vlm_unreserve(barcodes):
    log.info("Target(s) nodes: {}".format(str(barcodes)))
    reservedbyme = vlm_findmine()
    for bc in barcodes:
        if bc in reservedbyme:
            vlm_exec_cmd(VLM_UNRESERVE, bc)


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
            wr_exit()._exit(1, "Failed to get attributes for target(s): {}".format(barcodes))

        for line in output.splitlines():
            if line:
                attr, val = re.split("\s*:\s+", line)[0:2]
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
        msg = "Failed to {} target {}. Target is not reserved by user".format(action, barcode)
        log.error(msg)
        wr_exit()._exit(1, msg)
    else:
        cmd = [VLM, action, "-t", barcode]
        output = exec_cmd(cmd)[1]
        if output != "1":
            msg = 'Failed to execute "{}" on target'.format(barcode)
            log.error(msg)
            wr_exit()._exit(1, msg)


class wr_exit(object):
    class _wr_exit():
        """Exit utility.

        Wr_Exit contains various attributes  such exit status, error messages and methods
        for  Email notification of lab install status before exit.
        """

        def __init__(self):

            self.status = 0
            self.email_server = None
            self.email_subject = None
            self.email_from = None
            self.email_to = None
            self.status_msg = ''
            self.lab_name = ''
            self.executed_steps = []
            self.lab_barcodes = []

        def _set_email_attr(self, **kwargs):
            for key in kwargs:
                setattr(self, key, kwargs[key])

        def _exit(self, status, msg=None):

            if status == 2 or status == 0:
                log.info(msg)

            if status is not 0:
                self._dump_executed_steps()

            # Unreserve targets on exit
            if len(self.lab_barcodes) > 0:
                log.info("Unreserving targets")
                vlm_unreserve(self.lab_barcodes)

            else:
                install_vars_filename = self.lab_name + INSTALL_VARS_FILE_EXT
                file_path = os.path.join(INSTALL_VARS_TMP_PATH, install_vars_filename)
                if os.path.exists(file_path):
                    os.remove(file_path)

            # check if we need to send email
            if self.email_to is not None:
                _msg = ''
                if status is not 0:
                    self.email_subject += " failed"
                    _msg += self.lab_name + "\n" + EMAIL_ERROR_MSG + msg
                else:
                    self.email_subject += " completed"
                    _msg += self.lab_name + "\n" + msg
                self._send_email(_msg)

            sys.exit(status)

        def _send_email(self, msg):
            msg_body = MIMEText(msg)
            msg_body['subject'] = self.email_subject
            msg_body['From'] = self.email_from
            msg_body['To'] = self.email_to
            s = smtplib.SMTP(self.email_server)
            s.send_message(msg_body)
            s.quit()

        def _dump_executed_steps(self):
            executed_steps_filename = self.lab_name + INSTALL_EXECUTED_STEPS_FILE_EXT
            executed_steps_path = os.path.join(INSTALL_VARS_TMP_PATH, executed_steps_filename)
            if os.path.exists(executed_steps_path):
                os.remove(executed_steps_path)
            file = open(executed_steps_path, 'w')
            os.chmod(executed_steps_path, 0o777)
            if len(self.executed_steps) > 0:
                for step in self.executed_steps:
                    file.write("{}\n".format(step))
                log.info(RESUME_INSTALL_MSG)
            file.close()

        def _add_executed_step(self, step):
            self.executed_steps.append(step)

    instance = None

    def __new__(cls):
        if not wr_exit.instance:
            wr_exit.instance = wr_exit._wr_exit()
        return wr_exit.instance

    def __getattr__(self, name):
        return getattr(self.instance, name)

    def __setattr__(self, name):
        return setattr(self.instance, name)


class install_step(object):

    def __init__(self, name, rank, lab_types):
        self.name = name
        self.rank = rank
        self.lab_types = list(lab_types)
        self.step_full_name = "Step{}_{}".format(rank, name)

    def is_step_valid(self, lab_type):
        return (lab_type in self.lab_types)

