#!/usr/bin/env python3.4

"""
install_system.py - Installs Titanium Server load on specified configuration.

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
"""

import pdb

import os
import sys
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
from utils.common import create_node_dict, vlm_reserve, vlm_exec_cmd, find_error_msg, get_ssh_key
from utils.classes import Host
import utils.wr_telnetlib as telnetlib

LOGGER_NAME = os.path.splitext(__name__)[0]
SCRIPT_DIR = os.path.dirname(__file__)
PUBLIC_SSH_KEY = None
USERNAME = None
PASSWORD = None

def parse_args():
    parser = argparse.ArgumentParser(formatter_class=\
                                     argparse.RawTextHelpFormatter,
                                     add_help=False, prog=__file__,
                                     description="Script to install Titanium"
                                     " Server load on specified configuration.")
    node_grp = parser.add_argument_group('Nodes')
    node_grp.add_argument('--controller', metavar='LIST', required=True,
                          help="Comma-separated list of VLM barcodes"
                          " for controllers")
    #TODO: Removed required here, this should be mutually-exclusive with running small footprint
    node_grp.add_argument('--compute', metavar='LIST',
                          help="Comma-separated list of VLM barcodes"
                          " for computes")
    node_grp.add_argument('--storage', metavar='LIST',
                          help="Comma-separated list of VLM barcodes"
                          " for storage nodes")

    lab_grp = parser.add_argument_group("Lab setup")
    lab_grp.add_argument('--tuxlab', dest='tuxlab_server',
                         choices=TUXLAB_SERVERS,
                         default=DEFAULT_TUXLAB_SERVER,
                         help="Tuxlab server with controller-0 feed directory"
                         "\n(default: %(default)s)")
    lab_grp.add_argument('--run-lab-setup', dest='run_lab_setup',
                           action='store_true', help="Run lab_setup.sh")

    #TODO: Have an if for this and say it is not supported yet
    lab_grp.add_argument('--small-footprint', dest='small_footprint',
                           action='store_true',help="Run installation"
                           " as small footprint")

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
                         dest='bld_server',choices=BLD_SERVERS,
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
                         default="CGCS_2.0_Unified_Daily_Build",
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
                         default="CGCS_2.0_Guest_Daily_Build",
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

    other_grp = parser.add_argument_group("Other options:")
    other_grp.add_argument('--output-dir', metavar='DIR_PATH',
                           dest='output_dir', help="Directory path"
                           " for output logs")
    other_grp.add_argument('--log-level', dest='log_level',
                           choices=logutils.LOG_LEVEL_NAMES, default='DEBUG',
                           help="Logging level (default: %(default)s)")
    other_grp.add_argument('--password', metavar='PASSWORD', dest='password',
                           help="User password")
    other_grp.add_argument('-h','--help', action='help',
                           help="Show this help message and exit")

    args = parser.parse_args()
    return args

def get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir, tis_bld_dir):
    load_path = "{}/{}".format(bld_server_wkspce, tis_blds_dir)

    if tis_bld_dir == LATEST_BUILD_DIR:
        cmd = "readlink " + load_path + "/" + LATEST_BUILD_DIR
        tis_bld_dir = bld_server_conn.exec_cmd(cmd, expect_pattern=TIS_BLD_DIR_REGEX)

    load_path += "/" + tis_bld_dir
    cmd = "test -d " + load_path
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        log.error("Load path {} not found".format(load_path))
        sys.exit(1)

    return load_path

def verify_custom_lab_cfg_location(lab_cfg_location):
    # Rename variable to reflect that it is a path
    lab_cfg_path = lab_cfg_location
    lab_settings_filepath = None
    found_bulk_cfg_file = False
    found_system_cfg_file = False
    found_lab_settings_file = False
    for file in os.listdir(lab_cfg_location):
        if file == SYSTEM_CFG_FILENAME:
            found_system_cfg_file = True
        elif file == BULK_CFG_FILENAME:
            found_bulk_cfg_file = True
        elif file == CUSTOM_LAB_SETTINGS_FILENAME:
             found_lab_settings_file = True
    if not (found_bulk_cfg_file and found_system_cfg_file):
        log.error('Failed to find \"{}\" or \"{}\" in {}'.format(
                  BULK_CFG_FILENAME, SYSTEM_CFG_FILENAME,
                  lab_cfg_location))
        sys.exit(1)
    if found_lab_settings_file:
        lab_settings_filepath = lab_cfg_location + "/"\
                                + CUSTOM_LAB_SETTINGS_FILENAME
    return lab_cfg_path, lab_settings_filepath

def verify_lab_cfg_location(bld_server_conn, lab_cfg_location, load_path):
    lab_cfg_rel_path = LAB_YOW_REL_PATH + "/" + lab_cfg_location
    lab_cfg_path = load_path + "/" + lab_cfg_rel_path
    lab_settings_filepath = None

    cmd = "test -d " + lab_cfg_path
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        log.error('Lab config directory \"{}\" not found in {}'.format(
                  lab_cfg_location, lab_cfg_rel_path))
        sys.exit(1)

    lab_settings_rel_path = LAB_SETTINGS_DIR + "/{}.ini".format(
                            lab_cfg_location)
    if os.path.isfile(lab_settings_rel_path):
        # Path is relative to current directory
        lab_settings_filepath = SCRIPT_DIR + "/" + lab_settings_rel_path

    return lab_cfg_path, lab_settings_filepath

#TODO: Remove this as using deploy_key defined for ssh and telnetlib
def deploy_key(conn):
    try:
        ssh_key = (open(os.path.expanduser(SSH_KEY_FPATH)).read()).rstrip()
    except FileNotFoundError:
        log.exception("User must have a public key {} defined".format(SSH_KEY_FPATH))
        sys.exit(1)
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

def set_network_boot_feed(barcode, tuxlab_server, bld_server_conn, load_path):
    logutils.print_step("Set feed for {} network boot".format(barcode))
    tuxlab_sub_dir = USERNAME + '/' + os.path.basename(load_path)

    tuxlab_conn = SSHClient(log_path=output_dir + "/" + tuxlab_server + ".ssh.log")
    tuxlab_conn.connect(hostname=tuxlab_server, username=USERNAME,
                        password=PASSWORD)
    tuxlab_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + "/" + barcode

    if tuxlab_conn.exec_cmd("cd " + tuxlab_barcode_dir)[0] != 0:
        log.error("Failed to cd to: " + tuxlab_barcode_dir)
        sys.exit(1)

    log.info("Copy load into feed directory")
    if tuxlab_conn.exec_cmd("test -d " + tuxlab_sub_dir)[0] != 0:
        feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir
        tuxlab_conn.sendline("mkdir -p " + tuxlab_sub_dir)
        tuxlab_conn.find_prompt()
        tuxlab_conn.sendline("chmod 755 " + tuxlab_sub_dir)
        tuxlab_conn.find_prompt()
        # Extra forward slash at end is required to indicate the sync is for
        # all of the contents of RPM_INSTALL_REL_PATH into the feed path
        bld_server_conn.rsync(load_path + "/" + RPM_INSTALL_REL_PATH + "/", USERNAME, tuxlab_server, feed_path, ["--delete"])

        bld_server_conn.sendline("cd " + load_path)
        bld_server_conn.find_prompt()

        bld_server_conn.rsync("extra_cfgs/yow*", USERNAME, tuxlab_server, feed_path)
        bld_server_conn.rsync(RPM_INSTALL_REL_PATH + "/boot/isolinux/vmlinuz", USERNAME, tuxlab_server, feed_path)
        bld_server_conn.rsync(RPM_INSTALL_REL_PATH + "/boot/isolinux/initrd", USERNAME, tuxlab_server, feed_path + "/initrd.img")
    else:
        log.info("Build directory \"{}\" already exists".format(tuxlab_sub_dir))

    log.info("Create new symlink to feed directory")
    if tuxlab_conn.exec_cmd("rm -f feed")[0] != 0:
        log.error("Failed to remove feed")
        sys.exit(1)

    if tuxlab_conn.exec_cmd("ln -s " + tuxlab_sub_dir + "/" + " feed")[0] != 0:
        log.error("Failed to set VLM target {} feed symlink to: " + tuxlab_sub_dir)
        sys.exit(1)

    tuxlab_conn.logout()

def wipe_disk(node):

    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip, int(node.telnet_port), negotiate=node.telnet_negotiate, vt100query=node.telnet_vt100query, log_path=output_dir + "/" + node.name + ".telnet.log", debug=False)
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

def wait_state(nodes, type, expected_state):
    if isinstance(nodes, Host):
        nodes = [nodes]
    else:
        nodes = copy.copy(nodes)
    count = 0
    if type not in STATE_TYPE_DICT:
        log.error("Type of state can only be one of: " + str(list(STATE_TYPE_DICT.keys())))
        sys.exit(1)
    if expected_state not in STATE_TYPE_DICT[type]:
        log.error("Expected {} state can only be on one of: {}".format(type, str(STATE_TYPE_DICT[type])))
        sys.exit(1)

    expected_state_count = 0
    sleep_secs = int(REBOOT_TIMEOUT/MAX_SEARCH_ATTEMPTS)
    node_count = len(nodes)
    while count < MAX_SEARCH_ATTEMPTS:
        output = controller0.ssh_conn.exec_cmd("system host-list")[1]
        # Remove table header and footer
        output = "\n".join(output.splitlines()[3:-1])
        node_names = [node.name for node in nodes]
        log.info('Waiting for {} to be \"{}\"...'.format(node_names, expected_state))
        # Create copy of list so that it is unaffected by removal of node
        for node in copy.copy(nodes):
            match = re.search("^.*{}.*{}.*$".format(node.name, expected_state), output, re.MULTILINE|re.IGNORECASE)
            if match:
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
        if expected_state_count == node_count:
            break
        else:
            log.info("Sleeping for {} seconds...".format(str(sleep_secs)))
            time.sleep(sleep_secs)
        count += 1
    if count == MAX_SEARCH_ATTEMPTS:
        log.error('Waited {} seconds and {} did not become \"{}\"'.format(str(REBOOT_TIMEOUT), node_names, expected_state))
        sys.exit(1)

def bring_up(node, boot_device_dict, small_footprint, close_telnet_conn=True):
    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip, int(node.telnet_port), negotiate=node.telnet_negotiate, vt100query=node.telnet_vt100query, log_path=output_dir + "/" + node.name + ".telnet.log")
    vlm_exec_cmd(VLM_TURNON, node.barcode)
    logutils.print_step("Installing {}...".format(node.name))
    node.telnet_conn.install(node, boot_device_dict, small_footprint)
    if close_telnet_conn:
        node.telnet_conn.close()

def apply_patches(node, bld_server_conn, patch_dir_paths):
    patch_names = []

    for dir_path in patch_dir_paths.split(","):
        if bld_server_conn.exec_cmd("test -d " + dir_path)[0] != 0:
            log.error("Patch directory path {} not found".format(dir_path))
            sys.exit(1)

        if bld_server_conn.exec_cmd("cd " + dir_path)[0] != 0:
            log.error("Failed to cd to: " + dir_path)
            sys.exit(1)

        rc, output = bld_server_conn.exec_cmd("ls -1 --color=none *.patch")
        if rc != 0:
            log.error("Failed to list patches in: " + dir_path)
            sys.exit(1)

        for item in output.splitlines():
            # Remove ".patch" extension
            patch_name = os.path.splitext(item)[0]
            log.info("Found patch named: " + patch_name)
            patch_names.append(patch_name)

        bld_server_conn.rsync(dir_path + "/", WRSROOT_USERNAME, node.host_ip, WRSROOT_PATCHES_DIR)

    log.info("List of patches:\n" + "\n".join(patch_names))

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to query patches")
        sys.exit(1)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch upload-dir " + WRSROOT_PATCHES_DIR
    output = node.telnet_conn.exec_cmd(cmd)[1]
    if find_error_msg(output):
        log.error("Failed to upload entire patch directory: " + WRSROOT_PATCHES_DIR)
        sys.exit(1)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    rc, output = node.telnet_conn.exec_cmd(cmd)
    if rc != 0:
        log.error("Failed to query patches")
        sys.exit(1)

    # Remove table header
    output = "\n".join(output.splitlines()[2:])
    for patch in patch_names:
        if not re.search("^{}.*{}.*$".format(patch, AVAILABLE), output, re.MULTILINE|re.IGNORECASE):
            log.error('Patch \"{}\" is not in list or in {} state'.format(patch, AVAILABLE))
            sys.exit(1)

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch apply --all"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to apply patches")
        sys.exit(1)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch install-local"

    output = node.telnet_conn.exec_cmd(cmd)[1]
    if not find_error_msg(output):
        log.error("Failed to install patches")
        sys.exit(1)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to query patches")
        sys.exit(1)

    node.telnet_conn.exec_cmd("echo " + WRSROOT_PASSWORD + " | sudo -S reboot")
    node.telnet_conn.get_read_until(LOGIN_PROMPT, REBOOT_TIMEOUT)

if __name__ == '__main__':
    boot_device_dict = DEFAULT_BOOT_DEVICE_DICT
    custom_lab_setup = False
    lab_settings_filepath = ""
    compute_dict = {}
    storage_dict = {}
    provision_cmds = []
    barcodes = []
    threads = []

    args = parse_args()

    USERNAME = getpass.getuser()
    PASSWORD = args.password or getpass.getpass()
    PUBLIC_SSH_KEY = get_ssh_key()

    lab_cfg_location = args.lab_config_location

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
    logutils.print_name_value("Lab config location", lab_cfg_location)
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

    print("\nRunning as user: " + USERNAME + "\n")

    controller_dict = create_node_dict(controller_nodes, CONTROLLER)
    controller0 = controller_dict[CONTROLLER0]

    if compute_nodes is not None:
        compute_dict = create_node_dict(compute_nodes, COMPUTE)

    if storage_nodes is not None:
        storage_dict = create_node_dict(storage_nodes, STORAGE)

    bld_server_conn = SSHClient(log_path=output_dir + "/" + bld_server + ".ssh.log")
    bld_server_conn.connect(hostname=bld_server, username=USERNAME,
                            password=PASSWORD)

    guest_load_path = "{}/{}".format(bld_server_wkspce, guest_bld_dir)

    load_path = get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir,
                              tis_bld_dir)

    if os.path.isdir(lab_cfg_location):
        custom_lab_setup = True
        lab_cfg_path, lab_settings_filepath = verify_custom_lab_cfg_location(lab_cfg_location)
    else:
        lab_cfg_path, lab_settings_filepath = verify_lab_cfg_location(bld_server_conn,
                                                        lab_cfg_location,
                                                        load_path)

    if lab_settings_filepath:
        log.info("Lab settings file path: " + lab_settings_filepath)
        config = configparser.ConfigParser()
        try:
            lab_settings_file = open(lab_settings_filepath, 'r')
            config.read_file(lab_settings_file)
        except Exception:
            log.exception("Failed to read file: " + lab_settings_filepath)
            sys.exit(1)

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

    executed = False
    if not executed:
        set_network_boot_feed(controller0.barcode, tuxlab_server, bld_server_conn, load_path)

    nodes = list(controller_dict.values()) + list(compute_dict.values()) + list(storage_dict.values())

    [barcodes.append(node.barcode) for node in nodes]

    executed = False
    if not executed:
        vlm_reserve(barcodes, note=INSTALLATION_RESERVE_NOTE)

        #TODO: Must add option NOT to wipedisk, e.g. if cannot login to any of the nodes as the system was left not in an installed state
        #TODO: IN THIS CASE STILL NEED TO SET TELNET FOR CONTROLLER0 SO PERHAPS LEAVE THIS OUTSIDE OF WIPEDISK METHOD?
        cont0_telnet_conn = telnetlib.connect(controller0.telnet_ip, int(controller0.telnet_port), negotiate=controller0.telnet_negotiate, vt100query=controller0.telnet_vt100query, log_path=output_dir + "/" + CONTROLLER0 + ".telnet.log", debug=False)
        cont0_telnet_conn.login()
        controller0.telnet_conn = cont0_telnet_conn

        for node in nodes:
            node_thread = threading.Thread(target=wipe_disk,name=node.name,args=(node,))
            threads.append(node_thread)
            log.info("Starting thread for {}".format(node_thread.name))
            node_thread.start()

        for thread in threads:
            thread.join()

        for barcode in barcodes:
            vlm_exec_cmd(VLM_TURNOFF, barcode)

        bring_up(controller0, boot_device_dict, small_footprint, close_telnet_conn=False)
        logutils.print_step("Initial login and password set for " + controller0.name)
        controller0.telnet_conn.login(reset=True)

    executed = False
    if not executed:
        if small_footprint:

            cont0_telnet_conn = telnetlib.connect(controller0.telnet_ip, int(controller0.telnet_port), negotiate=controller0.telnet_negotiate, vt100query=controller0.telnet_vt100query, log_path=output_dir + "/" + CONTROLLER0 + ".telnet.log", debug=False)
            cont0_telnet_conn.login()
            controller0.telnet_conn = cont0_telnet_conn

            cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S ip addr add " + controller0.host_ip + controller0.host_routing_prefix + " dev " + NIC_INTERFACE
            if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
                log.error("Failed to add IP address: " + controller0.host_ip)
                sys.exit(1)

            cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S ip link set dev {} up".format(NIC_INTERFACE)
            if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
                log.error("Failed to bring up {} interface".format(NIC_INTERFACE))
                sys.exit(1)

            time.sleep(2)
            cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S route add default gw " + controller0.host_gateway
            if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
                log.error("Failed to add default gateway: " + controller0.host_gateway)
                sys.exit(1)

            #TODO: Fix this, put in a loop over timeout
            cmd = "ping -w {} -c 4 {}".format(PING_TIMEOUT, DNS_SERVER)
            if controller0.telnet_conn.exec_cmd(cmd, timeout=PING_TIMEOUT + TIMEOUT_BUFFER)[0] != 0:
                log.error("Failed to ping outside network")
                sys.exit(1)

        if patch_dir_paths != None:
            controller0.telnet_conn.deploy_ssh_key(PUBLIC_SSH_KEY)
            apply_patches(controller0, bld_server_conn, patch_dir_paths)

    cont0_ssh_conn = SSHClient(log_path=output_dir + "/" + CONTROLLER0 + ".ssh.log")
    cont0_ssh_conn.connect(hostname=controller0.host_ip, username=WRSROOT_USERNAME,
                            password=WRSROOT_PASSWORD)
    controller0.ssh_conn = cont0_ssh_conn

    controller0.ssh_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

    executed = False
    if not executed:
        bld_server_conn.rsync(LICENSE_FILEPATH, WRSROOT_USERNAME, controller0.host_ip, WRSROOT_HOME_DIR + "/license.lic")
        bld_server_conn.rsync(lab_cfg_path + "/*", WRSROOT_USERNAME, controller0.host_ip, WRSROOT_HOME_DIR)
        bld_server_conn.rsync(load_path + "/" + LAB_SCRIPTS_REL_PATH + "/*", WRSROOT_USERNAME, controller0.host_ip, WRSROOT_HOME_DIR)
        # Extra forward slash at end is required to indicate it is a directory
        bld_server_conn.rsync(guest_load_path + "/cgcs-guest.img", WRSROOT_USERNAME, controller0.host_ip, WRSROOT_IMAGES_DIR + "/")

        cmd = 'grep -q "TMOUT=" ' + WRSROOT_ETC_PROFILE
        cmd += " && echo " + WRSROOT_PASSWORD + " | sudo -S"
        cmd += ' sed -i.bkp "/\(TMOUT=\|export TMOUT\)/d"'
        cmd += " " + WRSROOT_ETC_PROFILE
        cont0_ssh_conn.exec_cmd(cmd)
        cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
        cmd += ' sed -i.bkp "$ a\TMOUT=\\nexport TMOUT"'
        cmd += " " + WRSROOT_ETC_PROFILE
        cont0_ssh_conn.exec_cmd(cmd)
        cmd = 'echo \'export HISTTIMEFORMAT="%Y-%m-%d %T "\' >>'
        cmd += " " + WRSROOT_HOME_DIR + "/.bashrc"
        cont0_ssh_conn.exec_cmd(cmd)
        cmd = 'echo \'export PROMPT_COMMAND="date; $PROMPT_COMMAND"\' >>'
        cmd += " " + WRSROOT_HOME_DIR + "/.bashrc"
        cont0_ssh_conn.exec_cmd(cmd)
        cont0_ssh_conn.exec_cmd("source " + WRSROOT_ETC_PROFILE)
        cont0_ssh_conn.exec_cmd("source " + WRSROOT_HOME_DIR + "/.bashrc")

    executed = False
    if not executed:
        cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
        cmd += " config_controller --config-file " + SYSTEM_CONFIG_FILENAME
        rc, output = cont0_ssh_conn.exec_cmd(cmd, timeout=CONFIG_CONTROLLER_TIMEOUT)
        if rc != 0 or find_error_msg(output, "Configuration failed"):
            log.error("config_controller failed")
            sys.exit(1)
            
    #TODO: Add system host-if-list controller-0 -a here!
    
   
    cmd = "source /etc/nova/openrc"
    if cont0_ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to source environment")

    executed = False
    if not executed:
        #TODO: Open connection to test server, don't need to deploy key if same user as already deployed it on controller-0 connection
    #    CREATE_TEST_SERVER_CONN.rsync("/home/svc-cgcsauto/precise-server-cloudimg-amd64-disk1.img", WRSROOT_USERNAME, controller0.host_ip, WRSROOT_IMAGES_DIR + "/")

        cmd = "system host-bulk-add hosts_bulk_add.xml"
        if cont0_ssh_conn.exec_cmd(cmd)[0] != 0:
            log.error("Failed to bulk add hosts")
            sys.exit(1)

    executed = False
    if not executed:
        threads.clear()
        for node in nodes:
            if node.name != CONTROLLER0:
                node_thread = threading.Thread(target=bring_up,name=node.name,args=(node, boot_device_dict, small_footprint))
                threads.append(node_thread)
                log.info("Starting thread for {}".format(node_thread.name))
                node_thread.start()

        for thread in threads:
            thread.join()

        for node in nodes:
            cmd = "system host-if-list {} -a".format(node.name)
            if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                log.error("Failed to get list of interfaces for node: " + node.name)
                sys.exit(1)

    executed = False
    if not executed:
        #TODO: Put this in a loop
        wait_state(controller0, ADMINISTRATIVE, UNLOCKED)
        wait_state(controller0, OPERATIONAL, ENABLED)
        wait_state(controller0, AVAILABILITY, AVAILABLE)

        nodes.remove(controller0)
        wait_state(nodes, ADMINISTRATIVE, LOCKED)
        wait_state(nodes, AVAILABILITY, ONLINE)

    #TODO: Put in workaround to set TEST_PROFILES="no" in lab_setup.sh due to CGTS-3219

    lab_setup_cmd = WRSROOT_HOME_DIR + "/lab_setup.sh"

    if not executed:
        for i in range(0, 2):
            if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
                log.error("Failed during lab_setup.sh")
                sys.exit(1)

    if not executed:
        for node in nodes:
            cmd = "system host-unlock " + node.name
            if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                log.error("Failed to unlock: " + node.name)
                sys.exit(1)

        wait_state(nodes, ADMINISTRATIVE, UNLOCKED)
        wait_state(nodes, OPERATIONAL, ENABLED)
        wait_state(nodes, AVAILABILITY, AVAILABLE)

    executed = False
    if not executed:
        if controller0.ssh_conn.exec_cmd(lab_setup_cmd, LAB_SETUP_TIMEOUT)[0] != 0:
            log.error("Failed during lab_setup.sh")
            sys.exit(1)

        nodes.insert(0, controller0)
        wait_state(nodes, ADMINISTRATIVE, UNLOCKED)
        wait_state(nodes, OPERATIONAL, ENABLED)
        wait_state(nodes, AVAILABILITY, AVAILABLE)

    for node in nodes:
        cmd = "system host-if-list {} -a".format(node.name)
        if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
            log.error("Failed to get list of interfaces for node: " + node.name)
            sys.exit(1)

    cmd = "system alarm-list"
    if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to get alarm list")
        sys.exit(1)

    cmd = "cat /etc/build.info"
    if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to get build info")
        sys.exit(1)

    #TODO: MUST UNRESERVE TARGETS IF YOU EXIT EARLY FOR SOME REASON OR FAIL EARLY TOO SO NEXT TIME IT RUNS IT WILL BE ABLE TO RESERVE THEM
    #       PUT THIS INSIDE EXCEPTION ERROR HANDLING
    for barcode in barcodes:
        vlm_exec_cmd(VLM_UNRESERVE, barcode)

    #TODO: Add system alarm-list and SUDO sm-dump, etc. print-outs

    #TODO: Check return code
 #   dirs = "{0}/images {0}/heat {0}/bin".format(WRSROOT_HOME_DIR)
 #   cont0_ssh_conn.exec_cmd("mkdir -p " + dirs)
 #   cont0_ssh_conn.exec_cmd("chmod 777 " + dirs)

    sys.exit(0)

    # Run lab_setup.sh twice

    # If you have storage:
    #   Unlock controller-1 and wait for it to be unlocked and enabled
    #   Unlock storage nodes and wait for them to become enabled
    #   Run lab_setup.sh 3rd time

    # Unlock computes in parallel

    # Run lab_setup.sh 4th time


    #NOTE: When you unlock controller-0 it will have availability as "degraded" so don't check availability, instead check administrative (unlocked) and operational (enabled)


#    wait for controller-1 to go enabled <-- from Matt: Semantically you have to wait for controller-1 to be unlocked-enable before you can unlock the storage nodes.
#    (optional) if the lab has storage nodes:
#     install storage-0 and storage-1 and wait for them to go "online"
#     run lab_setup.sh <-- extra run only if you have storage
#     unlock both storage nodes and wait for them to go "enabled"

#    run lab_setup.sh <-- part of back-to-back
#    install all compute nodes
#    wait for compute nodes to go "online"
#    run lab_setup.sh <-- part of back-to-back
#    unlock all compute nodes and wait for them to go "enabled"
#    run lab_setup.sh <-- last one
