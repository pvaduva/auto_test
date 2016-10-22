#!/usr/bin/env python3.4

'''
install_system.py - Installs Titanium Server load on specified configuration.

Copyright (c) 2015-2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
'''

'''
modification history:
---------------------
27apr16,amf  small footprint: handle drbd data-sync and custom configs
08mar16,mzy  Inserting steps for storage lab installation
25feb16,amf  Inserting steps for small footprint installations
22feb16,mzy  Add sshpass support
18feb16,amf  Adding doc strings to each function
02dec15,kav  initial version
'''

import os
import re
import copy
import time
import tempfile
import threading
import getpass
import textwrap
import argparse
import configparser
from constants import *
from utils.ssh import SSHClient
import utils.log as logutils
from utils.common import create_node_dict, vlm_reserve, vlm_findmine, \
    vlm_exec_cmd, find_error_msg, get_ssh_key, wr_exit
from utils.classes import Host
import utils.wr_telnetlib as telnetlib
from install_cumulus import Cumulus_TiS, create_cumulus_node_dict

"""----------------------------------------------------------------------------
Global definitions
----------------------------------------------------------------------------"""

LOGGER_NAME = os.path.splitext(__name__)[0]
log = logutils.getLogger(LOGGER_NAME)
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PUBLIC_SSH_KEY = None
USERNAME = getpass.getuser()
PASSWORD = None
controller0 = None


def parse_args():
    ''' Get commandline options. '''

    parser = argparse.ArgumentParser(formatter_class=\
                                     argparse.RawTextHelpFormatter,
                                     add_help=False, prog=__file__,
                                     description="Script to install Titanium"
                                     " Server load on specified configuration.")
    node_grp = parser.add_argument_group('Nodes')

    node_grp.add_argument('--controller', metavar='LIST',
                          help="Comma-separated list of VLM barcodes"
                          " for controllers")
    #TODO: Removed required here, this should be mutually-exclusive with running
    #      small_footprint. Need to add logic in the parser or outside of it
    #      to check if small_footprint option is used,
    #      ignore --compute and --storage
    #      Logic is required otherwise if the same barcode is specified as both
    #      controller and compute, it will try to get reserved twice and fail
    node_grp.add_argument('--compute', metavar='LIST',
                          help="Comma-separated list of VLM barcodes"
                          " for computes. Ignored if --tis-on-tis option"
                          " is specified")
    node_grp.add_argument('--storage', metavar='LIST',
                          help="Comma-separated list of VLM barcodes"
                          " for storage nodes. Ignored if --tis-on-tis"
                          " options is specified")

    lab_grp = parser.add_argument_group("Lab setup")


    lab_grp.add_argument('--tuxlab', dest='tuxlab_server',
                         choices=TUXLAB_SERVERS,
                         default=DEFAULT_TUXLAB_SERVER,
                         help="Tuxlab server with controller-0 feed directory"
                         "\n(default: %(default)s)")

    #TODO: This option is not being referenced in code. Add logic to
    #      exit after config_controller unless this option is specified
    #      or modify this option to be "skip_lab_setup" so that it skips
    #      lab_setup.sh if specified. Either way option needs to be used somehow
    lab_grp.add_argument('--run-lab-setup', dest='run_lab_setup',
                         action='store_true', help="Run lab setup")

    #TODO: Have an if for this and say it is not supported yet
    lab_grp.add_argument('--small-footprint', dest='small_footprint',
                         action='store_true', help="Run installation"
                         " as small footprint. Not applicable"
                         " for ts-on-tis install")

    lab_grp.add_argument('--tis-on-tis', dest='tis_on_tis', action='store_true',
                         help=" Run installation for Cumulus TiS on TiS. ")

    lab_grp.add_argument('--cumulus-userid', dest='cumulus_userid',
                         help="Tenant's linux login userid in Cumulus "
                         "Server. This is mandatory if --tis-on-tis is "
                         "specified.")

    lab_grp.add_argument('--cumulus-password', metavar='CUMULUS_PASSWORD',
                         dest='cumulus_password', help="Tenant's login "
                         "password to Cumulus Server.")

    # This option is valid only for small footprint option (--small-feetprint)
    #  that are bootable from USB.
    #
    # Burn boot image into USB if controller-0 is accessible, otherwise
    # the lab is booted from the existing USB image,
    # if one is plugged-in.
    #
    lab_grp.add_argument('--burn-usb', dest='burn_usb',
                         action='store_true',
                         help="Burn boot image into USB before install. Valid"
                         " only with --small-footprint option")


    # Add a flag to identify a wrl linux install
    lab_grp.add_argument('--host-os', dest='host_os',
                         choices=HOST_OS, default=DEFAULT_HOST_OS,
                         help="Centos or wrlinux based install")

    #TODO: Custom directory path is not supported yet. Need to add code
    #      to rsync files from custom directory path on local PC to controller-0
    #      Can use rsync exec_cmd(...) in common.py to do the transfer locally
    parser.add_argument('lab_config_location', help=textwrap.dedent('''\
                        Specify either:\n\n
                        (a) Directory for lab listed under:
                            -> cgcs/extras.ND/lab/yow/
                            e.g.: cgcs-ironpass-1_4\n
                        or\n
                        (b) Custom directory path accessible by "--build-server"
                            for lab config files\n
                        Option (a): For installation of existing lab
                                    Directory contains config files:
                                        -> system_config
                                        -> hosts_bulk_add.xml
                                        -> lab_setup.conf
                        Option (b): Intended for large office.
                                    Directory path contains:
                                        -> system_config
                                        -> hosts_bulk_add.xml'''))
    bld_grp = parser.add_argument_group("Build server and paths")
    bld_grp.add_argument('--build-server', metavar='SERVER',
                         dest='bld_server', choices=BLD_SERVERS,
                         default=DEFAULT_BLD_SERVER,
                         help="Titanium Server build server"
                         " host name\n(default: %(default)s)")
    bld_grp.add_argument('--bld-server-wkspce', metavar='DIR_PATH',
                         dest='bld_server_wkspce',
                         default="/localdisk/loadbuild/jenkins",
                         help="Directory path to build server workspace"
                         "\n(default: %(default)s)")
    bld_grp.add_argument('--tis-blds-dir', metavar='DIR',
                         dest='tis_blds_dir',
                         default="CGCS_3.0_Centos_Build",
                         help='Directory under "--bld-server-wkspce"'
                         " containing directories for Titanium Server loads"
                         "\n(default: %(default)s)")
    bld_grp.add_argument('--tis-bld-dir', metavar='DIR',
                         dest='tis_bld_dir', default=LATEST_BUILD_DIR,
                         help='Specific directory under "--tis-blds-dir"'
                         " containing Titanium Server load"
                         " \n(default: %(default)s)")
    bld_grp.add_argument('--guest-bld-dir', metavar='DIR',
                         dest='guest_bld_dir',
                         default="CGCS_3.0_Guest_Daily_Build",
                         help='Directory under "--bld-server-wkspce"'
                         " containing directories for guest images"
                         "\n(default: %(default)s)")
    bld_grp.add_argument('--patch-dir-paths', metavar='LIST',
                         dest='patch_dir_paths',
                         help=textwrap.dedent('''\
                         Comma-separated list of directory paths accessible by
                         "--build-server" containing patches\n
                         e.g.: for 15.05 patch testing, the following paths
                         would be specified:
                             -> /folk/cgts/patches-to-verify/ZTE/'
                             -> /folk/cgts/patches-to-verify/15.05'
                             -> /folk/cgts/rel-ops/Titanium-Server-15/15.05'''))
    bld_grp.add_argument('--email-address', metavar='EMAILADDRESS',
                         dest='email_address',
                         default=None,
                         help="Comma-separated list of email addresses to which"
                              " lab install status notification is sent"
                         "\n(default: %(default)s)")

    other_grp = parser.add_argument_group("Other options:")
    other_grp.add_argument('--output-dir', metavar='DIR_PATH',
                           dest='output_dir', help="Directory path"
                           " for output logs")
    other_grp.add_argument('--log-level', dest='log_level',
                           choices=logutils.LOG_LEVEL_NAMES, default='DEBUG',
                           help="Logging level (default: %(default)s)")
    other_grp.add_argument('--password', metavar='PASSWORD', dest='password',
                           help="User password")
    other_grp.add_argument('-h', '--help', action='help',
                           help="Show this help message and exit")

    args = parser.parse_args()
    if not args.tis_on_tis and args.controller is None:
        parser.error('--controller is required')
    if args.tis_on_tis and args.cumulus_userid is None:
        parser.error('--cumulus-userid is required if --tis-on-tis used.')
    return args

def get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir,
                  tis_bld_dir):
    ''' Get the directory path for the load that will be used in the
        lab. This directory path is typically taken as the latest build on
        the TiS build server.
    '''

    load_path = "{}/{}".format(bld_server_wkspce, tis_blds_dir)

    if tis_bld_dir == LATEST_BUILD_DIR or not tis_bld_dir:
        cmd = "readlink " + load_path + "/" + LATEST_BUILD_DIR
        tis_bld_dir = bld_server_conn.exec_cmd(cmd,
                                               expect_pattern=TIS_BLD_DIR_REGEX)

    load_path += "/" + tis_bld_dir
    cmd = "test -d " + load_path
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        msg = "Load path {} not found".format(load_path)
        log.error(msg)
        wr_exit()._exit(1, msg)

    return load_path

def verify_custom_lab_cfg_location(lab_cfg_location):
    ''' Verify that the correct configuration file is used in setting up the
        lab.
    '''

    # Rename variable to reflect that it is a path
    lab_cfg_path = lab_cfg_location
    lab_settings_filepath = None
    found_bulk_cfg_file = False
    found_system_cfg_file = False
    found_lab_settings_file = False
    for file in os.listdir(lab_cfg_location):
        cfgfile_list = CENTOS_CFGFILE_LIST + WRL_CFGFILE_LIST
        if file in cfgfile_list:
            found_system_cfg_file = True
        elif file == BULK_CFG_FILENAME:
            found_bulk_cfg_file = True
        elif file == CUSTOM_LAB_SETTINGS_FILENAME:
            found_lab_settings_file = True

    # Tell the user what files are missing
    if not found_bulk_cfg_file:
        msg = 'Failed to find {} in {}'.format(BULK_CFG_FILENAME,
                                               lab_cfg_location)
        log.error(msg)
    if not found_system_cfg_file:
        msg = 'Failed to find {} in {}'.format(cfgfile_list, lab_cfg_location)
        log.error(msg)
    if not found_lab_settings_file:
        msg = 'Failed to find {} in {}'.format(CUSTOM_LAB_SETTINGS_FILENAME,
                                               lab_cfg_location)
        log.error(msg)

    if not (found_bulk_cfg_file or found_system_cfg_file or
            found_lab_settings_file):
        log.error(msg)
        wr_exit()._exit(1, msg)

    if found_lab_settings_file:
        lab_settings_filepath = lab_cfg_location + "/"\
                                + CUSTOM_LAB_SETTINGS_FILENAME
    return lab_cfg_path, lab_settings_filepath

def verify_lab_cfg_location(bld_server_conn, lab_cfg_location, load_path, host_os):
    ''' Get the directory path for the configuration file that is used in
        setting up the lab.
    '''

    lab_settings_filepath = None
    if host_os == "wrlinux":
        lab_cfg_rel_path = LAB_YOW_REL_PATH + "/" + lab_cfg_location
        lab_cfg_path = load_path + "/" + lab_cfg_rel_path
    else:
        lab_cfg_rel_path = CENTOS_LAB_REL_PATH + "/yow/" + lab_cfg_location
        lab_cfg_path = load_path + "/" + lab_cfg_rel_path

    cmd = "test -d " + lab_cfg_path
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        msg = 'Lab config directory \"{}\" not found in {}'.format(
            lab_cfg_location, lab_cfg_path)
        log.error(msg)
        wr_exit()._exit(1, msg)

    # ~/wassp-repos/testcases/cgcs/sanityrefresh/labinstall/lab_settings/*.ini
    lab_settings_rel_path = LAB_SETTINGS_DIR + "/{}.ini".format(
        lab_cfg_location)
    lab_settings_filepath = SCRIPT_DIR + "/" + lab_settings_rel_path
    if not os.path.isfile(lab_settings_filepath):
        log.error('Lab settings filepath was not found.')
        lab_settings_filepath = None

    return lab_cfg_path, lab_settings_filepath

#TODO: Remove this as using deploy_key defined for ssh and telnetlib
def deploy_key(conn):
    ''' Set the keys used for ssh and telnet connections.
    '''

    try:
        ssh_key = (open(os.path.expanduser(SSH_KEY_FPATH)).read()).rstrip()
    except FileNotFoundError:
        log.exception("User must have a public key {} defined".format(SSH_KEY_FPATH))
        wr_exit()._exit(1, msg)
    else:
        log.info("User has public key defined: " + SSH_KEY_FPATH)

    if isinstance(conn, SSHClient):
        conn.sendline("mkdir -p ~/.ssh/")
        cmd = 'grep -q "{}" {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH)
        if conn.exec_cmd(cmd)[0] != 0:
            log.info("Adding public key to {}".format(AUTHORIZED_KEYS_FPATH))
            conn.sendline('echo -e "{}\n" >> {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH))
            conn.sendline("chmod 700 ~/.ssh/ && chmod 644 {}".format(AUTHORIZED_KEYS_FPATH))
    elif isinstance(conn, telnetlib.Telnet):
        conn.write_line("mkdir -p ~/.ssh/")
        cmd = 'grep -q "{}" {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH)
        if conn.exec_cmd(cmd)[0] != 0:
            log.info("Adding public key to {}".format(AUTHORIZED_KEYS_FPATH))
            conn.write_line('echo -e "{}\n" >> {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH))
            conn.write_line("chmod 700 ~/.ssh/ && chmod 644 {}".format(AUTHORIZED_KEYS_FPATH))

def set_network_boot_feed(barcode, tuxlab_server, bld_server_conn, load_path, host_os, output_dir):
    ''' Transfer the load and set the feed on the tuxlab server in preparation
        for booting up the lab.
    '''

    logutils.print_step("Set feed for {} network boot".format(barcode))
    tuxlab_sub_dir = USERNAME + '/' + os.path.basename(load_path)

    tuxlab_conn = SSHClient(log_path=output_dir + "/" + tuxlab_server + ".ssh.log")
    tuxlab_conn.connect(hostname=tuxlab_server, username=USERNAME,
                        password=PASSWORD)
    tuxlab_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + "/" + barcode

    if tuxlab_conn.exec_cmd("cd " + tuxlab_barcode_dir)[0] != 0:
        msg = "Failed to cd to: " + tuxlab_barcode_dir
        log.error(msg)
        wr_exit()._exit(1, msg)

    log.info("Copy load into feed directory")
    if tuxlab_conn.exec_cmd("test -d " + tuxlab_sub_dir)[0] != 0:
        feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir
        tuxlab_conn.sendline("mkdir -p " + tuxlab_sub_dir)
        tuxlab_conn.find_prompt()
        tuxlab_conn.sendline("chmod 755 " + tuxlab_sub_dir)
        tuxlab_conn.find_prompt()
        # Extra forward slash at end is required to indicate the sync is for
        # all of the contents of RPM_INSTALL_REL_PATH into the feed path
        if host_os == "centos":
            bld_server_conn.sendline("cd " + load_path)
            bld_server_conn.find_prompt()
            bld_server_conn.rsync(CENTOS_INSTALL_REL_PATH + "/", USERNAME, tuxlab_server, feed_path, ["--delete"])
            bld_server_conn.rsync("export/extra_cfgs/yow*", USERNAME, tuxlab_server, feed_path)
        else:
            bld_server_conn.rsync(load_path + "/" + RPM_INSTALL_REL_PATH + "/", USERNAME, tuxlab_server, feed_path, ["--delete"])

            bld_server_conn.sendline("cd " + load_path)
            bld_server_conn.find_prompt()

            bld_server_conn.rsync("export/extra_cfgs/yow*", USERNAME, tuxlab_server, feed_path)
            bld_server_conn.rsync(RPM_INSTALL_REL_PATH + "/boot/isolinux/vmlinuz", USERNAME, tuxlab_server, feed_path)
            bld_server_conn.rsync(RPM_INSTALL_REL_PATH + "/boot/isolinux/initrd", USERNAME, tuxlab_server, feed_path + "/initrd.img")

    else:
        log.info("Build directory \"{}\" already exists".format(tuxlab_sub_dir))

    log.info("Create new symlink to feed directory")
    if tuxlab_conn.exec_cmd("rm -f feed")[0] != 0:
        msg = "Failed to remove feed"
        log.error(msg)
        wr_exit()._exit(1, msg)

    if tuxlab_conn.exec_cmd("ln -s " + tuxlab_sub_dir + "/" + " feed")[0] != 0:
        msg = "Failed to set VLM target {} feed symlink to: " + tuxlab_sub_dir
        log.error(msg)
        wr_exit()._exit(1, msg)

    tuxlab_conn.logout()

def burn_usb_load_image(node, bld_server_conn, load_path):
    ''' Burn usb with given load image.
    '''

    logutils.print_step("Burning USB with load image from {}".format(load_path))

    # Check  if node (controller-0) is accessible.
    cmd = "ping -w {} -c 4 {}".format(PING_TIMEOUT, node.host_ip)
    if (bld_server_conn.exec_cmd(cmd, timeout=PING_TIMEOUT +
                                 TIMEOUT_BUFFER)[0] != 0):
        log.info("Node not responding. Skipping USB burning. Installing with existing USB image")
        return
    else:
        node.telnet_conn.login()

    # check if a USB is plugged in
    cmd = "ls -lrtd /dev/disk/by-id/usb*"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = "No USB found in lab node. Please plug in a usb to {}.".format(node.host_ip)
        log.info(msg)
        wr_exit()._exit(1, msg)

    cmd = "test -f " + load_path + "/" + BOOT_IMAGE_ISO_PATH
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        msg = 'Boot image iso file \"{}\" not found in {}'.format(
            load_path, BOOT_IMAGE_ISO_PATH)
        log.error(msg)
        wr_exit()._exit(1, msg)

    bld_server_conn.sendline("cd " + load_path)
    bld_server_conn.find_prompt()
    pre_opts = 'sshpass -p "{0}"'.format(WRSROOT_PASSWORD)
    bld_server_conn.rsync(BOOT_IMAGE_ISO_PATH, WRSROOT_USERNAME, node.host_ip,
                          BOOT_IMAGE_ISO_TMP_PATH, pre_opts=pre_opts)

    cmd = "test -f " + BOOT_IMAGE_ISO_TMP_PATH
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = "Boot image not found in {} : {}".format(node.host_ip, BOOT_IMAGE_ISO_TMP_PATH)
        log.info(msg)
        wr_exit()._exit(1, msg)

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S dd if=" + BOOT_IMAGE_ISO_TMP_PATH + " of=/dev/sdc bs=1M oflag=direct; sync"
    if node.telnet_conn.exec_cmd(cmd, timeout=RSYNC_TIMEOUT)[0] != 0:
        msg = 'Failed to burn Boot image iso file \"{}\"  onto USB'.format(
            BOOT_IMAGE_ISO_PATH)
        log.error(msg)
        wr_exit()._exit(1, msg)

def wipe_disk(node, output_dir):
    ''' Perform a wipedisk operation on the lab before booting a new load into
        it.
    '''

    # Until we have time to figure out how to have this fool-proof
    return

    # Only works for small footprint
    if small_footprint:
        if node.telnet_conn is None:
            node.telnet_conn = telnetlib.connect(node.telnet_ip, \
                                                int(node.telnet_port), \
                                                negotiate=node.telnet_negotiate,\
                                                vt100query=node.telnet_vt100query,\
                                                log_path=output_dir + "/"\
                                                + node.name + ".telnet.log", \
                                                debug=False)

            # Check that the node is accessible for wipedisk to run.
            # If we cannot successfully ping the interface of the node, then it is
            # expected that the login will fail. This may be due to the node not
            # being left in an installed state.
            cmd = "ping -w {} -c 4 {}".format(PING_TIMEOUT, node.host_ip)
            if (node.telnet_conn.exec_cmd(cmd, timeout=PING_TIMEOUT +
                                          TIMEOUT_BUFFER)[0] != 0):
                log.info("Node not responding. Skipping wipedisk process")
                return
            else:
                node.telnet_conn.login()

        node.telnet_conn.write_line("sudo -k wipedisk")
        node.telnet_conn.get_read_until(PASSWORD_PROMPT)
        node.telnet_conn.write_line(WRSROOT_PASSWORD)
        node.telnet_conn.get_read_until("[y/n]")
        node.telnet_conn.write_line("y")
        node.telnet_conn.get_read_until("confirm")
        node.telnet_conn.write_line("wipediskscompletely")
        node.telnet_conn.get_read_until("The disk(s) have been wiped.", WIPE_DISK_TIMEOUT)

        log.info("Disk(s) have been wiped on: " + node.name)


def wait_state(nodes, type, expected_state, sut=None, exit_on_find=False):
    ''' Function to wait for the lab to enter a specified state.
        If the expected state is not entered, the boot operation will be
        terminated.
    '''
    global controller0
    if isinstance(nodes, Host):
        nodes = [nodes]
    else:
        nodes = copy.copy(nodes)
    count = 0
    if type not in STATE_TYPE_DICT:
        msg = "Type of state can only be one of: " + \
                   str(list(STATE_TYPE_DICT.keys()))
        log.error(msg)
        wr_exit()._exit(1, msg)
    if expected_state not in STATE_TYPE_DICT[type]:
        msg = "Expected {} state can only be on one of: {}"\
                   .format(type, str(STATE_TYPE_DICT[type]))
        log.error(msg)
        wr_exit()._exit(1, msg)

    expected_state_count = 0
    sleep_secs = int(REBOOT_TIMEOUT/MAX_SEARCH_ATTEMPTS)
    node_count = len(nodes)
    while count < MAX_SEARCH_ATTEMPTS:
        output = controller0.ssh_conn.exec_cmd("source /etc/nova/openrc; system host-list")[1]
        # Remove table header and footer
        output = "\n".join(output.splitlines()[3:-1])

        if exit_on_find:
            log.info('Waiting for {} to be \"{}\"...'.format(sut, \
                      expected_state))
        else:
            node_names = [node.name for node in nodes]
            log.info('Waiting for {} to be \"{}\"...'.format(node_names, \
                      expected_state))

        # Create copy of list so that it is unaffected by removal of node
        for node in copy.copy(nodes):
            # Determine if the full table list should be searched
            if exit_on_find:
                name_search = sut
            else:
                name_search = node.name

            #TODO: Should use table_parser here instead
            match = re.search("^.*{}.*{}.*$".format(name_search, expected_state), \
                              output, re.MULTILINE|re.IGNORECASE)
            if match:
                if exit_on_find:
                    return True
                if type == ADMINISTRATIVE:
                    node.administrative = expected_state
                elif type == OPERATIONAL:
                    node.operational = expected_state
                elif type == AVAILABILITY:
                    node.availability = expected_state
                log.info("{} has {} state: {}".format(node.name, type, expected_state))
                expected_state_count += 1
                # Remove matched line from output
                output = re.sub(re.escape(match.group(0)), "", output)
                nodes.remove(node)

            # TODO: host-reboot does not fix the problem. Users need to hard reboot from
            # horizon manually until it is fixed (CGTS-3964)

        if expected_state_count == node_count:
            break
        else:
            log.info("Sleeping for {} seconds...".format(str(sleep_secs)))
            time.sleep(sleep_secs)
        count += 1
    if count == MAX_SEARCH_ATTEMPTS:
        msg = 'Waited {} seconds and {} did not become \"{}\"'.format(str(REBOOT_TIMEOUT), node_names, expected_state)
        log.error(msg)
        wr_exit()._exit(1, msg)

def get_availability_controller1():
    ## Todo: Make this generic for any node
    ''' Gets the availablity state of a node after unlock
    '''
    global controller0
    cmd = "source /etc/nova/openrc; system host-show controller-1 | awk ' / availability / { print $4}'"
    output = controller0.ssh_conn.exec_cmd(cmd)[1]
    return output

def get_system_name(bld_server_conn, lab_cfg_path):
    '''
    Args: Gets the lab system name from lab_setup.conf file
        bld_server_conn:
        lab_cfg_path:

    Returns: system name

    '''
    cmd = "grep SYSTEM_NAME " + lab_cfg_path + "/" + LAB_SETUP_CFG_FILENAME
    return bld_server_conn.exec_cmd(cmd)[1]

def bring_up(node, boot_device_dict, small_footprint, host_os, output_dir, close_telnet_conn=True):
    ''' Initiate the boot and installation operation.
    '''

    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip,
                                             int(node.telnet_port),
                                             negotiate=node.telnet_negotiate,
                                             port_login=True if node.telnet_login_prompt else False,
                                             vt100query=node.telnet_vt100query,
                                             log_path=output_dir + "/"\
                                               + node.name + ".telnet.log")

    vlm_exec_cmd(VLM_TURNON, node.barcode)
    logutils.print_step("Installing {}...".format(node.name))
    node.telnet_conn.install(node, boot_device_dict, small_footprint, host_os)
    if close_telnet_conn:
        node.telnet_conn.close()

def apply_patches(node, bld_server_conn, patch_dir_paths):
    ''' Apply any patches after the load is installed.
    '''

    patch_names = []
    pre_opts = 'sshpass -p "{0}"'.format(WRSROOT_PASSWORD)
    for dir_path in patch_dir_paths.split(","):
        if bld_server_conn.exec_cmd("test -d " + dir_path)[0] != 0:
            msg = "Patch directory path {} not found".format(dir_path)
            log.error(msg)
            wr_exit()._exit(1, msg)

        if bld_server_conn.exec_cmd("cd " + dir_path)[0] != 0:
            msg = "Failed to cd to: " + dir_path
            log.error(msg)
            wr_exit()._exit(1, msg)

        rc, output = bld_server_conn.exec_cmd("ls -1 --color=none *.patch")
        if rc != 0:
            msg = "Failed to list patches in: " + dir_path
            log.error(msg)
            wr_exit()._exit(1, msg)

        for item in output.splitlines():
            # Remove ".patch" extension
            patch_name = os.path.splitext(item)[0]
            log.info("Found patch named: " + patch_name)
            patch_names.append(patch_name)

        bld_server_conn.rsync(dir_path + "/", WRSROOT_USERNAME, node.host_ip, WRSROOT_PATCHES_DIR, pre_opts=pre_opts)

    log.info("List of patches:\n" + "\n".join(patch_names))

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = "Failed to query patches"
        log.error(msg)
        wr_exit()._exit(1, msg)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch upload-dir " + WRSROOT_PATCHES_DIR
    output = node.telnet_conn.exec_cmd(cmd)[1]
    if find_error_msg(output):
        msg = "Failed to upload entire patch directory: " + WRSROOT_PATCHES_DIR
        log.error(msg)
        wr_exit()._exit(1, msg)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    rc, output = node.telnet_conn.exec_cmd(cmd)
    if rc != 0:
        msg = "Failed to query patches"
        log.error(msg)
        wr_exit()._exit(1, msg)

    # Remove table header
    output = "\n".join(output.splitlines()[2:])
    for patch in patch_names:
        #TODO: Should use table_parser here instead
        if not re.search("^{}.*{}.*$".format(patch, AVAILABLE), output, re.MULTILINE|re.IGNORECASE):
            msg = 'Patch \"{}\" is not in list or in {} state'.format(patch, AVAILABLE)
            log.error(msg)
            wr_exit()._exit(1, msg)

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch apply --all"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = "Failed to apply patches"
        log.error(msg)
        wr_exit()._exit(1, msg)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch install-local"

    output = node.telnet_conn.exec_cmd(cmd)[1]
    #if not find_error_msg(output):
    #    msg = "Failed to install patches"
    #    log.error(msg)
    #    wr_exit()._exit(1, msg)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = "Failed to query patches"
        log.error(msg)
        wr_exit()._exit(1, msg)

    node.telnet_conn.write_line("echo " + WRSROOT_PASSWORD + " | sudo -S reboot")
    log.info("Patch application requires a reboot.")
    log.info("Controller0 reboot has started")
    #node.telnet_conn.get_read_until("Rebooting...")
    node.telnet_conn.get_read_until(LOGIN_PROMPT, REBOOT_TIMEOUT)

def wait_until_drbd_sync_complete(controller0, timeout=600, check_interval=180):
    '''
    Function for waiting until the drbd alarm is cleared
    '''

    sync_complete = False
    end_time = time.time() + timeout

    while True:
        if time.time() < end_time:
            time.sleep(15)
            cmd = "source /etc/nova/openrc; system alarm-list"
            output = controller0.ssh_conn.exec_cmd(cmd)[1]
            print('Waiting for data sync to complete')

            if not find_error_msg(output, "data-syncing"):
                print('Data sync is complete')
                sync_complete = True
                break
            time.sleep(check_interval)
        else:
            message = "FAIL: DRBD data sysnc was not completed in expected time."
            print(message)
            break

    return sync_complete

def main():

    boot_device_dict = DEFAULT_BOOT_DEVICE_DICT
    lab_settings_filepath = ""
    compute_dict = {}
    storage_dict = {}
    provision_cmds = []
    barcodes = []
    threads = []

    args = parse_args()

    global PASSWORD

    PASSWORD = args.password or getpass.getpass()
    PUBLIC_SSH_KEY = get_ssh_key()

    tis_on_tis = args.tis_on_tis
    if tis_on_tis:
        print("\nRunning Tis-on-TiS lab install ...")
        cumulus_password = args.cumulus_password or \
                           getpass.getpass("CUMULUS_PASSWORD: ")
        #lab_cfg_location = "cgcs-tis_on_tis"
        lab_cfg_location = args.lab_config_location
    else:
        # e.g. cgcs-ironpass-7_12
        lab_cfg_location = args.lab_config_location

    if not tis_on_tis:
        controller_nodes = tuple(args.controller.split(','))


    if args.compute != None:
        compute_nodes = tuple(args.compute.split(','))
    else:
        compute_nodes = None

    if args.storage != None:
        storage_nodes = tuple(args.storage.split(','))
    else:
        storage_nodes = None

    tuxlab_server = args.tuxlab_server + HOST_EXT
    run_lab_setup = args.run_lab_setup
    small_footprint = args.small_footprint
    burn_usb = args.burn_usb

    host_os = args.host_os

    bld_server = args.bld_server + HOST_EXT

    bld_server_wkspce = args.bld_server_wkspce

    tis_blds_dir = args.tis_blds_dir

    tis_bld_dir = args.tis_bld_dir

    guest_bld_dir = args.guest_bld_dir

    patch_dir_paths = args.patch_dir_paths

    if args.output_dir:
        output_dir = args.output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
    else:
        prefix = re.search("\w+", __file__).group(0) + "."
        suffix = ".logs"
        output_dir = tempfile.mkdtemp(suffix, prefix)

    log_level = args.log_level

    log_level_idx = logutils.LOG_LEVEL_NAMES.index(log_level)
    logutils.GLOBAL_LOG_LEVEL = logutils.LOG_LEVELS[log_level_idx]
    log = logutils.getLogger(LOGGER_NAME)

    logutils.print_step("Arguments:")
    if tis_on_tis:
        logutils.print_name_value("TiS-on-TiS", tis_on_tis)

    logutils.print_name_value("Logs location:", 'http://128.224.150.21/install_logs/')
    logutils.print_name_value("Lab config location", lab_cfg_location)

    if not tis_on_tis:

        logutils.print_name_value("Controller", controller_nodes)
        logutils.print_name_value("Compute", compute_nodes)
        logutils.print_name_value("Storage", storage_nodes)

        logutils.print_name_value("Run lab setup", run_lab_setup)
        logutils.print_name_value("Tuxlab server", tuxlab_server)
        logutils.print_name_value("Small footprint", small_footprint)

    logutils.print_name_value("Build server", bld_server)
    logutils.print_name_value("Build server workspace", bld_server_wkspce)
    logutils.print_name_value("TiS builds directory", tis_blds_dir)
    logutils.print_name_value("TiS build directory", tis_bld_dir)
    logutils.print_name_value("Guest build directory", guest_bld_dir)
    logutils.print_name_value("Patch directory paths", patch_dir_paths)
    logutils.print_name_value("Output directory", output_dir)
    logutils.print_name_value("Log level", log_level)

    logutils.print_name_value("Host OS", host_os)

    email_info = {}
    email_info['email_server'] = EMAIL_SERVER
    email_info['email_from'] = EMAIL_FROM
    email_info['email_to'] = args.email_address
    email_info['email_subject'] = EMAIL_SUBJECT

    installer_exit = wr_exit()
    installer_exit._set_email_attr(**email_info)

    # installed load info for email message
    installed_load_info = ''

    print("\nRunning as user: " + USERNAME + "\n")

    bld_server_conn = SSHClient(log_path=output_dir + "/" + bld_server + ".ssh.log")
    bld_server_conn.connect(hostname=bld_server, username=USERNAME,
                            password=PASSWORD)

    guest_load_path = "{}/{}".format(bld_server_wkspce, guest_bld_dir)

    load_path = get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir,
                                  tis_bld_dir)
    if os.path.isdir(lab_cfg_location):
        lab_cfg_path, lab_settings_filepath = verify_custom_lab_cfg_location(lab_cfg_location)
    else:
        lab_cfg_path, lab_settings_filepath = verify_lab_cfg_location(bld_server_conn,
                                                  lab_cfg_location, load_path,
                                                  host_os)

    if lab_settings_filepath:
        log.info("Lab settings file path: " + lab_settings_filepath)
        config = configparser.ConfigParser()
        try:
            lab_settings_file = open(lab_settings_filepath, 'r')
            config.read_file(lab_settings_file)
        except Exception:
            msg = "Failed to read file: " + lab_settings_filepath
            log.exception(msg)
            wr_exit()._exit(1, msg)

        for section in config.sections():
            try:
                provision_cmds = config.get(CFG_PROVISION_SECTION_NAME,
                                            CFG_CMD_OPT_NAME)
                log.info("Provision commands: " + str(provision_cmds))
            except (configparser.NoSectionError, configparser.NoOptionError):
                pass

            try:
                boot_device_dict = dict(config.items(CFG_BOOT_INTERFACES_NAME))
            except configparser.NoSectionError:
                pass

    # get lab name from config file
    lab_name = get_system_name(bld_server_conn, lab_cfg_path)
    if lab_name is not None:
        installer_exit.lab_name = lab_name

    if tis_on_tis:

        tis_on_tis_info = {'userid': args.cumulus_userid,
                            'password': cumulus_password,
                            'server': CUMULUS_SERVER_IP,
                            'log': log, 'bld_server_conn': bld_server_conn,
                            'load_path': load_path,
                            'guest_load_path': guest_load_path,
                            'output_dir': output_dir,
                            'lab_cfg_path': lab_cfg_path}

        cumulus = Cumulus_TiS(**tis_on_tis_info)
        
    if tis_on_tis:
        controller_dict = create_cumulus_node_dict((0, 1), CONTROLLER)
        compute_dict = create_cumulus_node_dict(range(0, cumulus.get_number_of_computes()), COMPUTE)
        storage_dict = create_cumulus_node_dict(range(0, cumulus.get_number_of_storages()), STORAGE)
    else:
        controller_dict = create_node_dict(controller_nodes, CONTROLLER)

    global controller0
    controller0 = controller_dict[CONTROLLER0]

    if compute_nodes is not None:
        compute_dict = create_node_dict(compute_nodes, COMPUTE)

    if storage_nodes is not None:
        storage_dict = create_node_dict(storage_nodes, STORAGE)

    executed = False
    if not executed:
        if str(boot_device_dict.get('controller-0')) != "USB" \
                and not tis_on_tis:
            set_network_boot_feed(controller0.barcode, tuxlab_server, bld_server_conn, load_path, host_os, output_dir)

    nodes = list(controller_dict.values()) + list(compute_dict.values()) + list(storage_dict.values())
    if not tis_on_tis:
        [barcodes.append(node.barcode) for node in nodes]

        executed = False
        if not executed:
            # Reserve the nodes via VLM
            # Unreserve first to close any opened telnet sessions.
            reservedbyme = vlm_findmine()
            barcodesAlreadyReserved = []
            for item in barcodes:
                if item in reservedbyme:
                    barcodesAlreadyReserved.append(item)
            if len(barcodesAlreadyReserved) > 0:
                for bcode in barcodesAlreadyReserved:
                    vlm_exec_cmd(VLM_UNRESERVE, bcode)

            #vlm_reserve(barcodesForReserve, note=INSTALLATION_RESERVE_NOTE)
            vlm_reserve(barcodes, note=INSTALLATION_RESERVE_NOTE)

            # Open a telnet session for controller0.
            cont0_telnet_conn = telnetlib.connect(controller0.telnet_ip,
                                                  int(controller0.telnet_port),
                                                  negotiate=controller0.telnet_negotiate,
                                                  port_login=True if controller0.telnet_login_prompt else False,
                                                  vt100query=controller0.telnet_vt100query,\
                                                  log_path=output_dir + "/" + CONTROLLER0 +\
                                                  ".telnet.log", debug=False)
            #cont0_telnet_conn.login()
            controller0.telnet_conn = cont0_telnet_conn
            if burn_usb and small_footprint:
                burn_usb_load_image(controller0, bld_server_conn, load_path)

            #TODO: Must add option NOT to wipedisk, e.g. if cannot login to any of
            #      the nodes as the system was left not in an installed state
            #TODO: In this case still need to set the telnet session for controller0
            #      so consider keeping this outside of the wipe_disk method

            # Run the wipedisk utility if the nodes are accessible
            for node in nodes:
                node_thread = threading.Thread(target=wipe_disk, name=node.name, args=(node, output_dir,))
                threads.append(node_thread)
                log.info("Starting thread for {}".format(node_thread.name))
                node_thread.start()

            for thread in threads:
                thread.join()

            # Power down all the nodes via VLM (note: this can also be done via board management control)
            for barcode in barcodes:
                vlm_exec_cmd(VLM_TURNOFF, barcode)

            # Boot up controller0
            bring_up(controller0, boot_device_dict, small_footprint, host_os, output_dir, close_telnet_conn=False)
            logutils.print_step("Initial login and password set for " + controller0.name)
            controller0.telnet_conn.login(reset=True)
    else:
        cumulus.tis_install()
        controller0.host_ip = cumulus.get_floating_ip("EXTERNALOAMC0")
        #Boot up controller0
        cumulus.launch_controller0()

    # Configure networking interfaces
    executed = False
    if not executed:
        if small_footprint and burn_usb:

            # Setup network access on the running controller0
            nic_interface = NIC_INTERFACE_CENTOS if host_os == DEFAULT_HOST_OS else NIC_INTERFACE
            cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S ip addr add " + controller0.host_ip + \
                  controller0.host_routing_prefix + " dev {}".format(nic_interface)
            if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
                log.error("Warning: Failed to add IP address: " + controller0.host_ip)

            cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S ip link set dev {} up".format(nic_interface)
            if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
                log.error("Warning: Failed to bring up {} interface".format(nic_interface))

            time.sleep(2)

            cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S route add default gw " + controller0.host_gateway
            if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
                log.error("Warning: Failed to add default gateway: " + controller0.host_gateway)

            # Ping the outside network to ensure the above network setup worked as expected
            # Sometimes the network may take upto a minute to setup. Adding a delay of 60 seconds
            # before ping
            #TODO: Change to ping at 15 seconds interval for upto 4 times
            time.sleep(60)
            cmd = "ping -w {} -c 4 {}".format(PING_TIMEOUT, DNS_SERVER)
            if controller0.telnet_conn.exec_cmd(cmd, timeout=PING_TIMEOUT + TIMEOUT_BUFFER)[0] != 0:
                msg = "Failed to ping outside network"
                log.error(msg)
                wr_exit()._exit(1, msg)

    # Open an ssh session
    cont0_ssh_conn = SSHClient(log_path=output_dir + "/" + CONTROLLER0 + ".ssh.log")
    cont0_ssh_conn.connect(hostname=controller0.host_ip, username=WRSROOT_USERNAME,
                            password=WRSROOT_PASSWORD)
    controller0.ssh_conn = cont0_ssh_conn

    controller0.ssh_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

    # Apply patches if patch dir is not none
    executed = False
    if not executed:
        if patch_dir_paths != None:
            apply_patches(controller0, bld_server_conn, patch_dir_paths)

            # Reconnect telnet session
            log.info("Found login prompt. Controller0 reboot has completed")
            cont0_telnet_conn.login()
            controller0.telnet_conn = cont0_telnet_conn

            # Reconnect ssh session
            cont0_ssh_conn.disconnect()
            cont0_ssh_conn = SSHClient(log_path=output_dir +\
                                       "/" + CONTROLLER0 + ".ssh.log")
            cont0_ssh_conn.connect(hostname=controller0.host_ip,
                                   username=WRSROOT_USERNAME,
                                   password=WRSROOT_PASSWORD)
            controller0.ssh_conn = cont0_ssh_conn

    # Download configuration files
    executed = False
    if not executed:
        pre_opts = 'sshpass -p "{0}"'.format(WRSROOT_PASSWORD)
        bld_server_conn.rsync(LICENSE_FILEPATH, WRSROOT_USERNAME,
                              controller0.host_ip,
                              os.path.join(WRSROOT_HOME_DIR, "license.lic"),
                              extra_opts="-L",
                              pre_opts=pre_opts)
        bld_server_conn.rsync(os.path.join(lab_cfg_path, "*"),
                              WRSROOT_USERNAME, controller0.host_ip,
                              WRSROOT_HOME_DIR, pre_opts=pre_opts)
        if host_os == "centos":
            scripts_path = load_path + "/" + CENTOS_LAB_REL_PATH + "/scripts/"
            bld_server_conn.rsync(os.path.join(scripts_path, "*"),
                              WRSROOT_USERNAME, controller0.host_ip,
                              WRSROOT_HOME_DIR, pre_opts=pre_opts)
            heat_path = load_path + "/" + HEAT_TEMPLATES_PATH
            bld_server_conn.rsync(os.path.join(heat_path, "*"),
                               WRSROOT_USERNAME, controller0.host_ip, \
                               WRSROOT_HEAT_DIR + "/",\
                               pre_opts=pre_opts)
        else:
            bld_server_conn.rsync(os.path.join(load_path, LAB_SCRIPTS_REL_PATH, "*"), 
                              WRSROOT_USERNAME, controller0.host_ip,
                              WRSROOT_HOME_DIR, pre_opts=pre_opts)
        bld_server_conn.rsync(os.path.join(guest_load_path, "cgcs-guest.img"),
                              WRSROOT_USERNAME, controller0.host_ip, \
                              WRSROOT_IMAGES_DIR + "/",\
                              pre_opts=pre_opts)

        if small_footprint:
            bld_server_conn.rsync(SFP_LICENSE_FILEPATH, WRSROOT_USERNAME,
                              controller0.host_ip, 
                              os.path.join(WRSROOT_HOME_DIR, "license.lic"),
                              pre_opts=pre_opts)

        cmd = 'grep -q "TMOUT=" ' + WRSROOT_ETC_PROFILE
        cmd += " && echo " + WRSROOT_PASSWORD + " | sudo -S"
        cmd += ' sed -i.bkp "/\(TMOUT=\|export TMOUT\)/d"'
        cmd += " " + WRSROOT_ETC_PROFILE
        controller0.ssh_conn.exec_cmd(cmd)
        cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
        cmd += ' sed -i.bkp "$ a\TMOUT=\\nexport TMOUT"'
        cmd += " " + WRSROOT_ETC_PROFILE
        controller0.ssh_conn.exec_cmd(cmd)
        cmd = 'echo \'export HISTTIMEFORMAT="%Y-%m-%d %T "\' >>'
        cmd += " " + WRSROOT_HOME_DIR + "/.bashrc"
        controller0.ssh_conn.exec_cmd(cmd)
        cmd = 'echo \'export PROMPT_COMMAND="date; $PROMPT_COMMAND"\' >>'
        cmd += " " + WRSROOT_HOME_DIR + "/.bashrc"
        controller0.ssh_conn.exec_cmd(cmd)
        controller0.ssh_conn.exec_cmd("source " + WRSROOT_ETC_PROFILE)
        controller0.ssh_conn.exec_cmd("source " + WRSROOT_HOME_DIR + "/.bashrc")

    # Configure the controller as required
    executed = False
    if not executed:
        # No consistency in naming of config file naming
        cfg_found = False
        if host_os == "centos":
            cfgfile_list = CENTOS_CFGFILE_LIST
        else:
            cfgfile_list = WRL_CFGFILE_LIST
        for cfgfile in cfgfile_list: 
            cfgpath = WRSROOT_HOME_DIR + "/" + cfgfile
            cmd = "test -f " + cfgpath
            if controller0.ssh_conn.exec_cmd(cmd)[0] == 0:
                cfg_found = True
                # check if HTTPS is enabled and if yes get the certification file
                cmd = " grep ENABLE_HTTPS " + cfgpath + " | awk \'{print $3}\' "
                rc, output = controller0.ssh_conn.exec_cmd(cmd)
                match = re.compile('(^\s*)Y(\s*?)$')
                if rc == 0 and match.match(output):
                    log.info("Getting certificate file")
                    bld_server_conn.rsync(CERTIFICATE_FILE_PATH,
                                          WRSROOT_USERNAME, controller0.host_ip,
                                          os.path.join(WRSROOT_HOME_DIR,
                                          CERTIFICATE_FILE_NAME),
                                          pre_opts=pre_opts)

                #cmd = "export USER=wrsroot"
                #rc, output = controller0.telnet_conn.exec_cmd(cmd)

                cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
                cmd += " config_controller --config-file " + cfgfile
                #cmd += " config_controller --default"
                #os.environ["TERM"] = "xterm"
                #rc, output = controller0.telnet_conn.exec_cmd(cmd, timeout=CONFIG_CONTROLLER_TIMEOUT)
                # Switching to ssh due to CGTS-4051
                rc, output = controller0.ssh_conn.exec_cmd(cmd, timeout=CONFIG_CONTROLLER_TIMEOUT)
                if rc != 0 or find_error_msg(output, "Configuration failed"):
                    msg = "config_controller failed"
                    log.error(msg)
                    wr_exit()._exit(1, msg)
                break

        if not cfg_found:
            msg = "Configuration failed: No configuration files found"
            log.error(msg)
            installer_exit._exit(1, msg)


    time.sleep(10)
    cmd = "source /etc/nova/openrc"
    if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to source environment")

    # Run host bulk add
    executed = False
    if not executed:
        if not tis_on_tis:
            # No consistency in naming of hosts file
            bulkfile_found = False
            for bulkfile in BULKCFG_LIST:
                bulkpath = WRSROOT_HOME_DIR + "/" + bulkfile
                cmd = "test -f " + bulkpath
                if controller0.ssh_conn.exec_cmd(cmd)[0] == 0:
                    bulkfile_found = True
                    cmd = "system host-bulk-add " + bulkfile
                    rc, output = controller0.ssh_conn.exec_cmd(cmd, timeout=CONFIG_CONTROLLER_TIMEOUT)
                    if rc != 0 or find_error_msg(output, "Configuration failed"):
                        msg = "system host-bulk-add failed"
                        log.error(msg)
                        installer_exit._exit(1, msg)
                    break

            if not bulkfile_found:
                msg = "Configuration failed: No host-bulk-add file was found."
                log.error(msg)
                installer_exit._exit(1, msg)

    # Complete controller0 configuration either as a regular host
    # or a small footprint host.
    executed = False
    if not executed:
        if small_footprint:
            cmd = './lab_setup.sh'
            if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                msg = "lab_setup failed in small footprint configuration."
                log.error(msg)
                installer_exit._exit(1, msg)

            cmd = 'source /etc/nova/openrc; system compute-config-complete'
            if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                log.error("compute-config-complete failed in small footprint configuration")
                installer_exit._exit(1, "compute-config-complete failed in small footprint configuration.")

            # The controller0 will restart. Need to login after reset is
            # complete before we can continue.

            log.info("Controller0 reset has started")
            if host_os == "wrlinux":
                controller0.telnet_conn.get_read_until("Rebooting...")
            else:
                controller0.telnet_conn.get_read_until("Restarting")

            controller0.telnet_conn.get_read_until(LOGIN_PROMPT, REBOOT_TIMEOUT)
            log.info("Found login prompt. Controller0 reset has completed")

            # Reconnect telnet session
            cont0_telnet_conn.login()
            controller0.telnet_conn = cont0_telnet_conn

            # Reconnect ssh session
            cont0_ssh_conn.disconnect()
            cont0_ssh_conn = SSHClient(log_path=output_dir +\
                                       "/" + CONTROLLER0 + ".ssh.log")
            cont0_ssh_conn.connect(hostname=controller0.host_ip,
                                   username=WRSROOT_USERNAME,
                                   password=WRSROOT_PASSWORD)
            controller0.ssh_conn = cont0_ssh_conn

            # Run lab_setup again to setup controller-1 interfaces
            cmd = './lab_setup.sh'
            if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                msg = "lab_setup failed in small footprint configuration"
                log.error(msg)
                wr_exit()._exit(1, msg)

    # Bring up other hosts
    tis_on_tis_storage = False
    executed = False
    if not executed:
        if not tis_on_tis:
            threads.clear()
            for node in nodes:
                if node.name != CONTROLLER0:
                    node_thread = threading.Thread(target=bring_up,
                                                   name=node.name,
                                                   args=(node,
                                                   boot_device_dict,
                                                   small_footprint, host_os,
                                                   output_dir))
                    threads.append(node_thread)
                    log.info("Starting thread for {}".format(node_thread.name))
                    node_thread.start()


            for thread in threads:
                thread.join()
        else:
            cumulus.launch_controller1()
            # Set controller-1 personality after virtual controller finish spawning
            time.sleep(120)
            cmd = "source /etc/nova/openrc; system host-list | grep None"
            rc, output = controller0.ssh_conn.exec_cmd(cmd)
            if rc is 0:
                cmd = "source /etc/nova/openrc; system host-update 2 " \
                      "personality=controller rootfs_device=vda boot_device=vda"
                if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                    wr_exit()._exit(1, msg)
                    msg = "Failed to set personality for controller-1"
                    log.error(msg)
            else:
                msg = "Launching controller-1 failed"
                log.error(msg)
                wr_exit()._exit(1, msg)
            
            # storages
            current_host = 3
            cumulus.launch_storages()
            storage_count = cumulus.get_number_of_storages()

            if storage_count > 0:
                tis_on_tis_storage = True
                # update osd config for lab_setup.sh
                current_osd = 'b' # /dev/vdb
                osd_string = 'OSD_DEVICES="'
                for i in range(0, storage_count):
                    osd_string += "\/dev\/vd" + current_osd + " "
                    current_osd = chr(ord(current_osd) + 1)   
                osd_string += '"'             
                cmd =  "sed -i 's/#OSD_STRING/" + osd_string + "/g' lab_setup.conf"
                rc, output = controller0.ssh_conn.exec_cmd(cmd)
                if rc is not 0:
                    msg = "Failed to update osd config for lab_setup.sh"
                    log.error(msg)
                    wr_exit()._exit(1, msg)

            time.sleep(120)
            cmd =  "source /etc/nova/openrc; system host-list | awk \'/None/ { print $2 }\'"
            rc, ids = controller0.ssh_conn.exec_cmd(cmd)
            if rc is 0:
                for i in range(0, storage_count):

                    cmd = "source /etc/nova/openrc;system host-update " + str(current_host) + " " +\
                          "personality=storage " \
                          "rootfs_device=vda boot_device=vda"

                    rc = controller0.ssh_conn.exec_cmd(cmd)[0]
                    if rc is not 0:
                        msg = "Failed to set storage personality"
                        log.error(msg)
                        wr_exit()._exit(1, msg)
                    current_host += 1
            else:
                msg = "Launching storages failed"
                log.error(msg)
                wr_exit()._exit(1, msg)            

            # computes
            cumulus.launch_computes()
            compute_count = cumulus.get_number_of_computes()

            time.sleep(120)
            cmd =  "source /etc/nova/openrc; system host-list | awk \'/None/ { print $2 }\'"
            rc, ids = controller0.ssh_conn.exec_cmd(cmd)
            if rc is 0:
                for i in range(0, compute_count):

                    cmd = "source /etc/nova/openrc;system host-update " + str(current_host) + " " +\
                          "personality=compute hostname=compute-" + str(i) + " " \
                          "rootfs_device=vda boot_device=vda"

                    rc = controller0.ssh_conn.exec_cmd(cmd)[0]
                    if rc is not 0:
                        msg = "Failed to set compute personality"
                        log.error(msg)
                        wr_exit()._exit(1, msg)
                    current_host += 1
            else:
                msg = "Launching computes failed"
                log.error(msg)
                wr_exit()._exit(1, msg)

    # STORAGE LAB INSTALL
    executed = False
    if not executed and (storage_nodes is not None or tis_on_tis_storage == True):
        log.info("Beginning lab setup procedure for storage lab")

        # Remove controller-0 from the nodes list since it's up
        nodes.remove(controller0)

        # Wait for all nodes to be online to allow lab_setup to set
        # interfaces properly
        wait_state(nodes, AVAILABILITY, ONLINE)

        # WE RUN LAB_SETUP REPEATEDLY - MOVE TO FUNC
        # Run lab setup
        lab_setup_cmd = WRSROOT_HOME_DIR + "/" + LAB_SETUP_SCRIPT
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            msg = "Failed during lab setup"
            log.error(msg)
            wr_exit()._exit(1, msg)

        # Storage nodes are online so run lab_setup again
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            msg = "Failed during lab setup"
            log.error(msg)
            wr_exit()._exit(1, msg)


        # Unlock controller-1 and then run lab_setup
        for node in nodes:
            if node.name == "controller-1":
                cmd = "source /etc/nova/openrc; system host-unlock " + node.name
                if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                    msg = "Failed to unlock: " + node.name
                    log.error(msg)
                    wr_exit()._exit(1, msg)


                # Wait for controller-1 to be available, otherwise we can't add OSDs to
                # storage nodes via lab_setup.sh if controller-1 is still degraded.
                wait_state(node, AVAILABILITY, AVAILABLE)

                if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
                    msg = "Failed during lab setup"
                    log.error(msg)
                    wr_exit()._exit(1, msg)
                nodes.remove(node)

                break

        # Unlock storage nodes
        for node in nodes:
            if node.name.startswith("storage"):
                cmd = "source /etc/nova/openrc; system host-unlock " + node.name
                if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                    msg = "Failed to unlock: " + node.name
                    log.error(msg)
                    wr_exit()._exit(1, "Failed to unlock: " + node.name)

        # Wait for storage nodes to be enabled and computes to be online before
        # running lab_setup again
        for node in nodes:
            if node.name.startswith("storage"):
                wait_state(node, OPERATIONAL, ENABLED)
            else:
                wait_state(node, AVAILABILITY, ONLINE)

        # Run lab_setup
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            msg = "Failed during lab setup"
            log.error(msg)
            wr_exit()._exit(1, "Failed during lab setup")

        # Unlock computes
        for node in nodes:
            if node.name.startswith("compute"):
                cmd = "source /etc/nova/openrc; system host-unlock " + node.name
                if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                    msg = "Failed to unlock: " + node.name
                    log.error(msg)
                    wr_exit()._exit(1, msg)

        # Wait for computes to become enabled before we run lab_setup again
        wait_state(nodes, OPERATIONAL, ENABLED)

        # Run lab_setup again
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            msg = "Failed during lab setup"
            log.error(msg)
            wr_exit()._exit(1, "Failed during lab setup")

        # Check that the computes and storage nodes are available
        wait_state(nodes, AVAILABILITY, AVAILABLE)

        # COMMON CODE TO MOVE OUT START
        # Get alarms
        cmd = "source /etc/nova/openrc; system alarm-list"
        if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
            msg = "Failed to get alarm list"
            log.error(msg)
            wr_exit()._exit(1, "Failed to get alarm list")

        # Get build info
        cmd = "cat /etc/build.info"
        rc, installed_load_info = controller0.ssh_conn.exec_cmd(cmd)
        #if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        if rc != 0:
            msg = "Failed to get build info"
            log.error(msg)
            wr_exit()._exit(1, msg)

        # Unreserve targets
        for barcode in barcodes:
            vlm_exec_cmd(VLM_UNRESERVE, barcode)

        # If we made it this far, we probably had a successful install
        log.info("Terminating storage system install")
        wr_exit()._exit(0, "Terminating storage system install.\n"
                      + installed_load_info)
        # COMMON CODE TO MOVE OUT END

    # REGULAR LAB PROCEDURE
    executed = False
    if not executed and not storage_nodes and not small_footprint and not tis_on_tis_storage:
        log.info("Beginning lab setup procedure for regular lab")

        # Remove controller-0 from the nodes list since it's up
        nodes.remove(controller0)

        # Wait for all nodes to be online to allow lab_setup to set
        # interfaces properly
        wait_state(nodes, AVAILABILITY, ONLINE)

        # Run lab setup
        lab_setup_cmd = WRSROOT_HOME_DIR + "/" + LAB_SETUP_SCRIPT
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            log.error("Failed during lab setup")
            wr_exit()._exit(1, "Failed during lab setup")

        # Run lab_setup again
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            log.error("Failed during lab setup")
            wr_exit()._exit(1, "Failed during lab setup")

        # Unlock computes and then run lab_setup
        for node in nodes:
            if node.name.startswith("compute"):
                cmd = "source /etc/nova/openrc; system host-unlock " + node.name
                if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                    log.error("Failed to unlock: " + node.name)
                    wr_exit()._exit(1, "Failed to unlock: " + node.name)

        # Wait until computes are enabled
        for node in nodes:
            if node.name.startswith("compute"):
                wait_state(node, OPERATIONAL, ENABLED)

        # Run lab_setup again
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            log.error("Failed during lab setup")
            wr_exit()._exit(1, "Failed during lab setup")

        # Unlock controller-1
        for node in nodes:
            if node.name == "controller-1":
                cmd = "source /etc/nova/openrc; system host-unlock " + node.name
                if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                    log.error("Failed to unlock: " + node.name)
                    wr_exit()._exit(1, "Failed to unlock: " + node.name)

                wait_state(node, OPERATIONAL, ENABLED)

        # Run lab_setup again
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            log.error("Failed during lab setup")
            wr_exit()._exit(1, "Failed during lab setup")

        # Check that the nodes are available
        wait_state(nodes, AVAILABILITY, AVAILABLE)

        # COMMON CODE TO MOVE OUT START
        # Get alarms
        cmd = "source /etc/nova/openrc; system alarm-list"
        if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
            log.error("Failed to get alarm list")
            wr_exit()._exit(1, "Failed to get alarm list")

        # Get build info
        cmd = "cat /etc/build.info"
        rc, installed_load_info = controller0.ssh_conn.exec_cmd(cmd)
        #if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        if rc != 0:
            log.error("Failed to get build info")
            wr_exit()._exit(1, "Failed to get build info")

        # Unreserve targets
        for barcode in barcodes:
            vlm_exec_cmd(VLM_UNRESERVE, barcode)

        # If we made it this far, we probably had a successful install
        log.info("Terminating regular system install")
        wr_exit()._exit(0, "Terminating regular system install.\n"
                      + installed_load_info)
        # COMMON CODE TO MOVE OUT END


    # Verify the nodes are up and running
    executed = False
    if not executed and small_footprint:
        #TODO: Put this in a loop
        log.info("Waiting for controller0 come online")
        wait_state(controller0, ADMINISTRATIVE, UNLOCKED)
        wait_state(controller0, OPERATIONAL, ENABLED)

        nodes.remove(controller0)

        wait_state(nodes, AVAILABILITY, ONLINE)


        cmd = "source /etc/nova/openrc; ./lab_setup.sh"
        if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
            log.error("Warning: Failed to bring up {}".\
                       format("node"))

        # unlock controller-1
        if not executed:
            for node in nodes:
                cmd = "source /etc/nova/openrc; system host-unlock " + node.name
                if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                    msg = "Failed to unlock: " + node.name
                    log.error(msg)
                    wr_exit()._exit(1, msg)

        wait_state(nodes, ADMINISTRATIVE, UNLOCKED)
        wait_state(nodes, OPERATIONAL, ENABLED)
        # Sleep to allow drdb sync to initiate
        time.sleep(60)
        wait_until_drbd_sync_complete(controller0, timeout=1800, check_interval=180)

    for node in nodes:
        cmd = "source /etc/nova/openrc; system host-if-list {} -a".format(node.name)
        if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
            msg = "Failed to get list of interfaces for node: " + node.name
            log.error(msg)
            wr_exit()._exit(1, msg)

    cmd = "source /etc/nova/openrc; system alarm-list"
    if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to get alarm list")
        wr_exit()._exit(1, msg)

    cmd = "cat /etc/build.info"
    rc, installed_load_info = controller0.ssh_conn.exec_cmd(cmd)
    #if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
    if rc != 0:
        log.error("Failed to get build info")
        wr_exit()._exit(1, msg)

    #TODO: Add unreserving of targets if you exit early for some reason
    #      This needs to be in the exception error handling for failure cases
    for barcode in barcodes:
        vlm_exec_cmd(VLM_UNRESERVE, barcode)

    wr_exit()._exit(0, "Installer completed.\n" + installed_load_info)


if __name__ == '__main__':
    main()
