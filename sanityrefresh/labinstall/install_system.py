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
import threading
import getpass
import textwrap
import argparse
import configparser
from constants import *
from utils.ssh import SSHClient
import utils.log as logutils
from utils.common import create_node_dict, exec_cmd, vlm_reserve, vlm_exec_cmd, find_error_msg
from utils.classes import Host
import utils.wr_telnetlib as telnetlib

LOGGER_NAME = os.path.splitext(__name__)[0]
SCRIPT_DIR = os.path.dirname(__file__)

def parse_args():
    parser = argparse.ArgumentParser(formatter_class=\
                                     argparse.RawTextHelpFormatter,
                                     add_help=False, prog=sys.argv[0],
                                     description="Script to install Titanium"
                                     " Server load on specified configuration.")
    node_grp = parser.add_argument_group('Nodes')
    node_grp.add_argument('--controller', metavar='LIST', required=True,
                          help="Comma-separated list of VLM barcodes"
                          " for controllers")
    node_grp.add_argument('--compute', metavar='LIST', required=True,
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
    lab_grp.add_argument('--small-footprint', dest='small_footprint',
                           action='store_true',help="Run installation"
                           " as small footprint")

    parser.add_argument('lab_config_location', help=textwrap.dedent('''\
                        Specify either:\n\n
                        (a) Directory for lab listed under:
                            -> cgcs/extras.ND/lab/yow/
                            e.g.: cgcs-ironpass-1_4\n
                        or\n
                        (b) Custom local directory path for lab config files\n
                        Option (a): For installation of existing lab
                                    Directory contains config files:
                                        -> system_config
                                        -> hosts_bulk_add.xml
                                        -> lab_setup.conf
                        Option (b): Intended for large office.
                                    Directory path contains:
                                        -> hosts_bulk_add.xml'''))
    bld_grp = parser.add_argument_group("Build server and paths")
    bld_grp.add_argument('--build_server', metavar='SERVER',
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
                         "--build_server" containing patches\n
                         e.g.: for 15.05 patch testing, the following paths
                         would be specified:
                             -> /folk/cgts/patches-to-verify/ZTE/'
                             -> /folk/cgts/patches-to-verify/15.05'
                             -> /folk/cgts/rel-ops/Titanium-Server-15/15.05'''))

    other_grp = parser.add_argument_group("Other options:")
    other_grp.add_argument('--output-dir', metavar='DIR_PATH',
                           dest='output_dir', default=".",
                           help="Directory path for script output files"
                           "\n(default: %(default)s)")
    other_grp.add_argument('--log-level', dest='log_level',
                           choices=logutils.LOG_LEVEL_NAMES, default='DEBUG',
                           help="Logging level (default: %(default)s)")
    other_grp.add_argument('-h','--help', action='help',
                           help="Show this help message and exit")

    args = parser.parse_args()
    return args

def get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir, tis_bld_dir):
    load_path = "{}/{}".format(bld_server_wkspce, tis_blds_dir)

    if tis_bld_dir == LATEST_BUILD_DIR:
        cmd = "readlink " + load_path + "/" + LATEST_BUILD_DIR
        regex = "\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"
        tis_bld_dir = bld_server_conn.exec_cmd(cmd, expect_pattern=regex)

    load_path += "/" + tis_bld_dir
    cmd = "test -d " + load_path
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        log.error("Load path {} not found".format(load_path))
        sys.exit(1)

    return load_path

def verify_custom_lab_cfg_location(lab_cfg_location):
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
    return lab_settings_filepath

def verify_lab_cfg_location(lab_cfg_location, bld_server_conn, load_path):
    lab_settings_filepath = None
    lab_cfg_rel_path = LAB_YOW_REL_PATH + "/" + lab_cfg_location
    lab_cfg_path = load_path + "/" + lab_cfg_rel_path

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

    return lab_settings_filepath

def deploy_key(conn):
    try:
        ssh_key = (open(os.path.expanduser(SSH_KEY_FPATH)).read()).rstrip()
    except FileNotFoundError:
        log.exception("User must have a public key {} defined".format(SSH_KEY_FPATH))
        sys.exit(1)
    else:
        log.info("User has public key defined: " + SSH_KEY_FPATH)

    conn.sendline("mkdir -p ~/.ssh/")
    cmd = 'grep -q "{}" {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH)
    if conn.exec_cmd(cmd)[0] != 0:
        log.info("Adding public key to {}".format(AUTHORIZED_KEYS_FPATH))
        conn.sendline('echo -e "{}\n" >> {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH))
        conn.sendline("chmod 700 ~/.ssh/ && chmod 644 {}".format(AUTHORIZED_KEYS_FPATH))

def set_network_boot_feed(barcode, tuxlab_server, bld_server_conn, load_path):
    tuxlab_sub_dir = SCP_USERNAME + '/' + os.path.basename(load_path)

    tuxlab_conn = SSHClient()
    tuxlab_conn.connect(hostname=tuxlab_server, username=SCP_USERNAME,
                        password=SCP_PASSWORD)
    deploy_key(tuxlab_conn)

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + "/" + barcode

    if tuxlab_conn.exec_cmd("cd " + tuxlab_barcode_dir)[0] != 0:
        log.error("Failed to cd to: " + tuxlab_barcode_dir)
        sys.exit(1)

    if tuxlab_conn.exec_cmd("test -d " + tuxlab_sub_dir)[0] != 0:
        feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir
        tuxlab_conn.sendline("mkdir -p " + tuxlab_sub_dir)
        tuxlab_conn.match_prompt()
        tuxlab_conn.sendline("chmod 755 " + tuxlab_sub_dir)
        tuxlab_conn.match_prompt()
        bld_server_conn.rsync(load_path + "/export/RPM_INSTALL/", SCP_USERNAME, tuxlab_server, feed_path, ["--delete"])

        bld_server_conn.sendline("cd " + load_path)
        bld_server_conn.match_prompt()

        bld_server_conn.rsync("extra_cfgs/yow*", SCP_USERNAME, tuxlab_server, feed_path)
        bld_server_conn.rsync("export/RPM_INSTALL/boot/isolinux/vmlinuz", SCP_USERNAME, tuxlab_server, feed_path)
        bld_server_conn.rsync("export/RPM_INSTALL/boot/isolinux/initrd", SCP_USERNAME, tuxlab_server, feed_path + "/initrd.img")
    else:
        log.info("Build directory \"{}\" already exists".format(tuxlab_sub_dir))

    tuxlab_conn.sendline("rm -f feed")
    tuxlab_conn.match_prompt()
    tuxlab_conn.sendline("ln -v -s " + tuxlab_sub_dir + " feed")
    tuxlab_conn.match_prompt()
    tuxlab_conn.logout()

def wipe_disk(node):

    if node.telnet_conn is None:
        telnet_log = open(output_dir + "/" + node.name + ".telnet.log", 'w')
        telnet_conn = telnetlib.connect(node.telnet_ip, int(node.telnet_port), negotiate=node.telnet_negotiate, vt100query=node.telnet_vt100query, logfile=telnet_log)
        telnet_conn.login()
        node.telnet_conn = telnet_conn

    node.telnet_conn.write_line("sudo -k wipedisk")
    node.telnet_conn.get_read_until(PASSWORD_PROMPT)
    node.telnet_conn.write_line(WRSROOT_PASSWORD)
    node.telnet_conn.get_read_until("\[y\/n\]")
    node.telnet_conn.write_line("y")
    node.telnet_conn.get_read_until("confirm")
    node.telnet_conn.write_line("wipediskscompletely")
    node.telnet_conn.get_read_until("The disk(s) have been wiped.")

    log.info("Disk(s) have been wiped on: " + node.name)

    #TODO: See if other telnet connections should be closed
#    if node.name != CONTROLLER0:
#        node.telnet_conn.close()

def apply_patches(node, bld_server_conn, patch_dir_paths):
    patch_names = []
    valid_states = "(Available|Partial-Apply)"

    for dir_path in patch_dir_paths.split(","):
        if bld_server_conn.exec_cmd("test -d " + dir_path)[0] != 0:
            log.error("Patch directory path {} not found".format(dir_path))
            sys.exit(1)

        if bld_server_conn.exec_cmd("cd " + dir_path)[0] != 0:
            log.error("Failed to cd to: " + dir_path)
            sys.exit(1)

        rc, output = bld_server_conn.exec_cmd("ls -1 *.patch")
        if rc != 0:
            log.error("Failed to list patches in: " + dir_path)
            sys.exit(1)

        for item in output.splitlines():
            # Remove ".patch" extension
            patch_name = os.path.splitext(item)[0]
            log.info("Found patch named: " + patch_name)
            patch_names.append(patch_name)

        bld_server_conn.rsync(dir_path + "/", WRSROOT_USERNAME, node.host_ip, PATCHES_DIR)

    log.info("List of patches:\n" + "\n".join(patch_names))
    sys.exit(0)

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to query patches")
        sys.exit(1)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch upload-dir " + PATCHES_DIR
    output = node.telnet_conn.exec_cmd(cmd)[1]
    if find_error_msg(output):
        log.error("Failed to upload entire patch directory: " + PATCHES_DIR)
        sys.exit(1)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    rc, output = node.telnet_conn.exec_cmd(cmd)
    if rc != 0:
        log.error("Failed to query patches")
        sys.exit(1)

    for patch in patch_names:
        if not re.search("{}\s+{}".format(patch, valid_states), output, re.MULTILINE):
            log.error('Patch \"{}\" is not in the patch list/not in a valid state: {}'.format(patch, valid_states))
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
    boot_devices = DEFAULT_BOOT_DEVICES
    custom_lab_setup = False
    lab_settings_filepath = ""
    storage_dict = {}
    provision_cmds = []
    user = getpass.getuser()
    barcodes = []
    threads = []

    args = parse_args()

    lab_cfg_location = args.lab_config_location

    controller_nodes = tuple(args.controller.split(','))
    compute_nodes = tuple(args.compute.split(','))

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

    output_dir = args.output_dir

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

    print("\nRunning as user: " + user + "\n")

    controller_dict = create_node_dict(controller_nodes, CONTROLLER)
    controller0 = controller_dict[CONTROLLER0]
    compute_dict = create_node_dict(compute_nodes, COMPUTE)

    if storage_nodes is not None:
        storage_dict = create_node_dict(storage_nodes, STORAGE)

    bld_server_log = open(output_dir + "/" + bld_server + ".log", 'w')
    bld_server_conn = SSHClient(logf=bld_server_log)
    bld_server_conn.connect(hostname=bld_server, username=SCP_USERNAME,
                            password=SCP_PASSWORD)

    load_path = get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir,
                              tis_bld_dir)

    if os.path.isdir(lab_cfg_location):
        custom_lab_setup = True
        lab_settings_filepath = verify_custom_lab_cfg_location(lab_cfg_location)
    else:
        lab_settings_filepath = verify_lab_cfg_location(lab_cfg_location,
                                                        bld_server_conn,
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
                boot_devices = config.items(CFG_BOOT_INTERFACES_NAME)
            except configparser.NoSectionError:
                pass

#    set_network_boot_feed(controller0.barcode, tuxlab_server, bld_server_conn, load_path)

    nodes = list(controller_dict.values()) + list(compute_dict.values()) + list(storage_dict.values())

    [barcodes.append(node.barcode) for node in nodes]

#    vlm_reserve(barcodes, note=INSTALLATION_RESERVE_NOTE)

    cont0_telnet_log = open(output_dir + "/" + CONTROLLER0 + ".telnet.log", 'w')
    cont0_telnet_conn = telnetlib.connect(controller0.telnet_ip, int(controller0.telnet_port), negotiate=controller0.telnet_negotiate, vt100query=controller0.telnet_vt100query, logfile=cont0_telnet_log)
 #   cont0_telnet_conn.login()
    controller0.telnet_conn = cont0_telnet_conn

#    for node in nodes:
#        node_thread = threading.Thread(target=wipe_disk,name=node.name,args=(node,))
#        threads.append(node_thread)
#        log.info("Starting thread for {}".format(node_thread.name))
#        node_thread.start()

#    for thread in threads:
#        thread.join()

#    for barcode in barcodes:
#        vlm_exec_cmd(VLM_TURNOFF, barcode)

    vlm_exec_cmd(VLM_TURNON, controller0.barcode)

    logutils.print_step("Installing {}...".format(controller0.name))
    cont0_telnet_conn.install(controller0, boot_devices)
    logutils.print_step("Initial login and password set for " + controller0.name)
    cont0_telnet_conn.login(reset=True)

    if patch_dir_paths != None:
        apply_patches(controller0, bld_server_conn, patch_dir_paths)

    sys.exit(0)

    cont0_ssh_log = open(output_dir + "/" + CONTROLLER0 + ".ssh.log", 'w')
    cont0_ssh_conn = SSHClient(logf=cont0_ssh_log)
    cont0_ssh_conn.connect(hostname=controller0.host_ip, username=WRSROOT_USERNAME,
                            password=WRSROOT_PASSWORD)

    deploy_key(cont0_ssh_conn)

    #TODO: Fix this, copying to the wrong dest directory and ot sure what the rsync is supposed to do? Check if some other stuff needs to be copied
#    if custom_lab_setup is False:
#        dir_path = load_path + LAB_YOW_REL_PATH
#    log.info("Executing: " + 'rsync -ave "ssh {} "'.format(RSYNC_SSH_OPTIONS) + dir_path + "/*" + " " + WRSROOT_USERNAME + "@" + host_ip + ":" + PATCHES_DIR)
#    bld_server_conn.sendline('rsync -ave "ssh {} "'.format(RSYNC_SSH_OPTIONS) + dir_path + "/*" + " " + WRSROOT_USERNAME + "@" + host_ip + ":" + PATCHES_DIR)

    #TODO: Enable this
#    exec_cmd(bld_server_conn, 'rsync -ave "ssh {}" '.format(RSYNC_SSH_OPTIONS) + LICENSE_FILEPATH + " " + WRSROOT_USERNAME + "@" + host_ip + ":" + HOME_DIR + "/license.lic")
    if custom_lab_setup is False:
        #TODO: These get defined in verify_lab_cfg_location so find a way to get them from there instead
        lab_cfg_rel_path = LAB_YOW_REL_PATH + "/" + lab_cfg_location
        lab_cfg_path = load_path + "/" + lab_cfg_rel_path
 #       bld_server_conn.rsync(lab_cfg_path + "/*", WRSROOT_USERNAME, controller0.host_ip, HOME_DIR)
    #TODO: Do else where you copy them form local directory

    #TODO: Put PASSWORD in place of li69nux
    cont0_ssh_conn.exec_cmd('grep -q "TMOUT=" ' + ETC_PROFILE + ' && echo li69nux | sudo -S sed -i.bkp "/\(TMOUT=\|export TMOUT\)/d" ' + ETC_PROFILE)
    cont0_ssh_conn.exec_cmd('echo li69nux | sudo -S sed -i.bkp "$ a\TMOUT=\\nexport TMOUT" ' + ETC_PROFILE)
    cont0_ssh_conn.exec_cmd('echo \'export HISTTIMEFORMAT="%Y-%m-%d %T "\' >> ' + HOME_DIR + "/.bashrc")
    cont0_ssh_conn.exec_cmd('echo \'export PROMPT_COMMAND="date; $PROMPT_COMMAND"\' >> ' + HOME_DIR + "/.bashrc")

    #TODO: Check return code, returns 0 on success, does it return anything else on failure? Find out
#    cont0_ssh_conn.exec_cmd("echo li69nux | sudo -S config_controller --config-file " + SYSTEM_CONFIG_FILENAME, timeout=CONFIG_CONTROLLER_TIMEOUT)

    #TODO: Check return code
    dirs = "{0}/images {0}/heat {0}/bin".format(HOME_DIR)
    cont0_ssh_conn.exec_cmd("mkdir -p " + dirs)
    cont0_ssh_conn.exec_cmd("chmod 777 " + dirs)

#TODO at end:
#    TYPE cat /etc/build.info \n
