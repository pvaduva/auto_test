import socket
import getpass
import os
import subprocess
import re

from utils.tis_log import LOG
from consts.auth import SvcCgcsAuto
from consts.vlm import VlmAction


SSH_DIR = "~/.ssh"
SSH_KEY_FPATH = SSH_DIR + "/id_rsa"
GET_PUBLIC_SSH_KEY_CMD = "ssh-keygen -y -f {}"
CREATE_PUBLIC_SSH_KEY_CMD = "ssh-keygen -f {} -t rsa -N ''"
KNOWN_HOSTS_PATH = SSH_DIR + "/known_hosts"
REMOVE_HOSTS_SSH_KEY_CMD = "ssh-keygen -f {} -R {}"
# VLM commands and options
VLM = "/folk/vlm/commandline/vlmTool"


VLM_CMDS = [VlmAction.VLM_RESERVE, VlmAction.VLM_UNRESERVE, VlmAction.VLM_FORCE_UNRESERVE, VlmAction.VLM_TURNON,
            VlmAction.VLM_TURNOFF, VlmAction.VLM_FINDMINE, VlmAction.VLM_REBOOT]


def get_host_name():
    return socket.gethostname()


def get_host_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]


def get_user():
    return getpass.getuser()


def exec_cmd(cmd, show_output=True):
    rc = 0
    cmd = [str(i) for i in cmd]
    LOG.info(" ".join(cmd))
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, universal_newlines=True)
    except subprocess.CalledProcessError as ex:
        rc = ex.returncode
        output = ex.output
    output = output.rstrip()
    if isinstance(output, bytes):
        output = output.decode()
    output = output.strip()
    if output and show_output:
        LOG.info("Output:\n" + output)
    LOG.info("Return code: " + str(rc))
    return rc, output


def get_ssh_key():
    ssh_key_fpath = os.path.expanduser(SSH_KEY_FPATH)
    if not os.path.isfile(ssh_key_fpath):
        print("CMD = " + CREATE_PUBLIC_SSH_KEY_CMD.format(ssh_key_fpath))
        if exec_cmd(CREATE_PUBLIC_SSH_KEY_CMD)[0] != 0:
            msg = "Failed to create public ssh key for current user"
            LOG.error(msg)
            return 1, msg

    ssh_key = exec_cmd(GET_PUBLIC_SSH_KEY_CMD.format(ssh_key_fpath).split())[1]
    return ssh_key


def reserve_vlm_console(barcode, note=None):
    action = VlmAction.VLM_RESERVE
    cmd = [VLM, action, "-t", str(barcode)]
    reserve_note_params = []
    if note is not None:
        reserve_note_params = ["-n", '"{}"'.format(note)]
    cmd += reserve_note_params
    print("This is cmd: %s" % cmd)

    reserved_barcodes = exec_cmd(cmd)[1]
    if not reserved_barcodes or "Error" in reserved_barcodes:
        # check if node is already reserved by user
        port = vlm_getattr(barcode, "port")[1]
        if "TARGET_NOT_RESERVED_BY_USER" in port:
            msg = "Failed to reserve target(s): " + str(barcode)
            LOG.error(msg)
            return 1, msg
        else:
            msg = "Barcode {} reserved: {}".format(barcode, reserved_barcodes)
            LOG.info(msg)
            return 0, msg
    else:
        msg = "Barcode {} reserved: {}".format(barcode, reserved_barcodes)
        LOG.info(msg)
        return 0, msg


def force_unreserve_vlm_console(barcode):
    action = VlmAction.VLM_FORCE_UNRESERVE
    force_unreserve_cmd = [VLM, action, "-L", SvcCgcsAuto.USER, "-P", SvcCgcsAuto.VLM_PASSWORD, "-t", str(barcode)]

    reserve_note = vlm_getattr(barcode, 'reserve_note')[1]
    reserved_by_user = "TARGET_NOT_RESERVED_BY_USER" not in vlm_getattr(barcode, 'port')[1]
    if not reserve_note or reserved_by_user:
        print("Force unreserving target: {}".format(barcode))
        exec_cmd(force_unreserve_cmd)
        reserved = vlm_getattr(barcode, 'date')[1]
        if reserved:
            msg = "Failed to force unreserve target!"
            LOG.error(msg)
            return 1, msg
        else:
            msg = "Barcode {} was succesfully unreserved".format(barcode)
            LOG.info(msg)
            return 0, msg
    else:
        msg = "cannot unreserve {} as it has a reservation note: {}".format(barcode, reserve_note)
        LOG.error(msg)
        return 2, msg


def vlm_findmine():
    cmd = [VLM, VlmAction.VLM_FINDMINE]
    output = exec_cmd(cmd)[1]
    if re.search("\d+", output):
        reserved_targets = output.split(sep=' ')
        msg = "Target(s) reserved by user: {}".format(str(reserved_targets))
    else:
        msg = "User has no reserved target(s)"
        reserved_targets = []

    reserved_targets = [int(barcode) for barcode in reserved_targets]
    LOG.info(msg)

    return reserved_targets


def vlm_getattr(barcode, attr='all'):
    cmd = [VLM, 'getAttr', '-t', str(barcode), attr]
    return exec_cmd(cmd)


def vlm_exec_cmd(action, barcode, reserve=True,):
    if action not in VLM_CMDS:
        msg = '"{}" is an invalid action.'.format(action)
        msg += " Valid actions: {}".format(str(VLM_CMDS))
        raise ValueError(msg)

    if reserve:
        if int(barcode) not in vlm_findmine():
            # reserve barcode
            if reserve_vlm_console(barcode)[0] != 0:
                msg = "Failed to {} target {}. Target is not reserved by user".format(action, barcode)
                LOG.info(msg)
                return 1, msg

    cmd = [VLM, action, "-t", barcode]
    output = exec_cmd(cmd)[1]
    if output != "1":
        msg = 'Failed to execute "{}" on target {}. Output: {}'.format(action, barcode, output)
        LOG.error(msg)
        return 1, msg

    return 0, None


def ping_to_host(host_ip, count=4):
    """
    Tests connectivity to host using ping utility
    Args:
        host_ip: the ip address of host
        count: the number of pings to do before decision

    Returns:
        True if pings succeed
        False if ping fail
    """

    if host_ip is None:
        raise ValueError("Valid host ip must be provided")
    ping_cmd = ['ping', '-c', count, host_ip]

    return True if exec_cmd(ping_cmd)[0] == 0 else False
