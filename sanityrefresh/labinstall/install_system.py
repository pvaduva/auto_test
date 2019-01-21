#!/usr/bin/env python3.4

'''
install_system.py - Installs Titanium Server load on specified configuration.

Copyright (c) 2015-2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
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
import subprocess
from constants import *
from utils.ssh import SSHClient
import utils.log as logutils
from utils.common import create_node_dict, vlm_reserve, vlm_findmine, \
    vlm_exec_cmd, vlm_unreserve, find_error_msg, get_ssh_key, wr_exit, install_step
from utils.classes import Host
import utils.wr_telnetlib as telnetlib
from install_cumulus import Cumulus_TiS, create_cumulus_node_dict

"""----------------------------------------------------------------------------
Global definitions
----------------------------------------------------------------------------"""

LOGGER_NAME = os.path.splitext(__name__)[0]
log = None
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PUBLIC_SSH_KEY = None
USERNAME = getpass.getuser()
PASSWORD = None
controller0 = None
cumulus = None
lab_type = 'regular'
executed_install_steps = []


def parse_args():
    ''' Get commandline options. '''

    parser = argparse.ArgumentParser(formatter_class= \
                                         argparse.RawTextHelpFormatter,
                                     add_help=False, prog=__file__,
                                     description="Script to install Titanium"
                                     " Server load on specified configuration.")

    parser.add_argument('--lab', dest='lab_name',
                        help="Official lab name")
                        # required=True)
    parser.add_argument('--continue', dest='continue_install',
                        action='store_true', help="Continue lab install"
                        " from its last step")
    node_grp = parser.add_argument_group('Nodes')

    node_grp.add_argument('--controller', metavar='LIST',
                          help="Comma-separated list of VLM barcodes"
                          " for controllers")
    # TODO: Removed required here, this should be mutually-exclusive with running
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

    lab_grp.add_argument('--iso-install', dest='iso_install', action="store_true", default=False,
                         help="iso install flag ")

    lab_grp.add_argument('--skip-pxebootcfg', dest='skip_pxebootcfg', action="store_true", default=False,
                         help="Don't modify pxeboot.cfg if set")

    lab_grp.add_argument('--config-region', dest='config_region', action="store_true", default=False,
                         help="configure_region instead of config_controller")

    # TODO: This option is not being referenced in code. Add logic to
    #      exit after config_controller unless this option is specified
    #      or modify this option to be "skip_lab_setup" so that it skips
    #      lab_setup.sh if specified. Either way option needs to be used somehow
    lab_grp.add_argument('--run-lab-setup', dest='run_lab_setup',
                         action='store_true', help="Run lab setup")

    lab_grp.add_argument('--small-footprint', dest='small_footprint',
                         action='store_true', help="Run installation"
                                                   " as small footprint. Not applicable"
                                                   " for tis-on-tis install")

    lab_grp.add_argument('--system-mode', dest='system_mode', default='',
                         choices=['duplex-direct', 'duplex', 'simplex'],
                         help="select system mode")

    lab_grp.add_argument('--security', dest='security', default='',
                         choices=['', 'standard', 'extended'],
                         help="Install security profile")

    lab_grp.add_argument('--postinstall', choices=['True', 'False'],
                         default=True, help="Run post install scripts")

    lab_grp.add_argument('--tis-on-tis', dest='tis_on_tis', action='store_true',
                         help=" Run installation for Cumulus TiS on TiS. ")

    lab_grp.add_argument('--burn-usb', dest='burn_usb',
                         action='store_true',
                         help="Burn boot image into USB before installing from USB")

    lab_grp.add_argument('--simplex', dest='simplex',
                         action='store_true',
                         help="Simplex install")

    lab_grp.add_argument('--ovs', dest='ovs',
                         action='store_true',
                         help="Use ovs-dpdk versions of files")
    
    lab_grp.add_argument('--kubernetes', dest='kubernetes',
                         action='store_true',
                         help="Use kubernetes option in config_controller")

    lab_grp.add_argument('--lowlat', dest='lowlat',
                         action='store_true',
                         help="Low latency option for CPE and Simplex")

    lab_grp.add_argument('--boot-usb', dest='boot_usb',
                         action='store_true',
                         help="Boot using the existing load on the USB")

    lab_grp.add_argument('--iso-path', dest='iso_path', default='',
                         help='Full path to ISO')

    lab_grp.add_argument('--iso-host', dest='iso_host', default='',
                         help='Host where ISO resides')

    lab_grp.add_argument('--skip-feed', dest='skip_feed',
                         action='store_true',
                         help="Skip setup of network feed")

    lab_grp.add_argument('--host-os', dest='host_os',
                         choices=HOST_OS, default=DEFAULT_HOST_OS,
                         help="Centos or wrlinux based install")

    lab_grp.add_argument('--install-mode', dest='install_mode',
                         choices=INSTALL_MODE, default=DEFAULT_INSTALL_MODE,
                         help="Select install mode, either legacy or uefi")

    lab_grp.add_argument('--stop', dest='stop', default='99',
                         help="Integer value that represents when to stop the install\n"
                              "0 - Stop after setting up network feed\n"
                              "1 - Stop after booting controller-0\n"
                              "2 - Stop after downloading config files\n"
                              "3 - Stop after running config controller\n"
                              "4 - Stop after running host bulk add\n")

    # Grab the latest configuration files
    lab_grp.add_argument('--override', dest='override',
                         choices=['yes', 'no'], default='no',
                         help="Use the latest config files")

    lab_grp.add_argument('--banner', dest='banner',
                         choices=['before', 'after', 'no'], default='before',
                         help='Apply banner files before or after config controller')

    lab_grp.add_argument('--branding', dest='branding',
                         choices=['before', 'no'], default='before',
                         help='Apply branding files before config controller')

    lab_grp.add_argument('--wipedisk', dest='wipedisk', default=False,
                         action='store_true',
                         help="wipedisk during installation")

    # TODO: Custom directory path is not supported yet. Need to add code
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
                         dest='bld_server',
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
                         default="CGCS_5.0_Host",
                         help='Directory under "--bld-server-wkspce"'
                              " containing directories for Titanium Server loads"
                              "\n(default: %(default)s)")
    bld_grp.add_argument('--tis-bld-dir', metavar='DIR',
                         dest='tis_bld_dir', default=GA_LOAD,
                         help='Specific directory under "--tis-blds-dir"'
                              " containing Titanium Server load"
                              " \n(default: %(default)s)")
    bld_grp.add_argument('--guest-bld-dir', metavar='DIR',
                         dest='guest_bld_dir',
                         default="CGCS_5.0_Guest",
                         help='Directory under "--bld-server-wkspce"'
                              " containing directories for guest images"
                              "\n(default: %(default)s)")
    bld_grp.add_argument('--patch-dir-paths', metavar='LIST',
                         dest='patch_dir_paths',
                         default=None,
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
    if args.controller is None and not args.tis_on_tis and not args.continue_install:
        parser.error('--controller is required')
    # if args.tis_on_tis and args.cumulus_userid is None:
    #     parser.error('--cumulus-userid is required if --tis-on-tis used.')
    return args


def get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir,
                  tis_bld_dir):
    ''' Get the directory path for the load that will be used in the
        lab. This directory path is typically taken as the latest build on
        the TiS build server.
    '''
    prestage_load_path = ""
    load_path = "{}/{}".format(bld_server_wkspce, tis_blds_dir)

    TC_18_03_pattern = re.compile(TC_18_03_REGEX)
    TC_17_06_pattern = re.compile(TC_17_06_REGEX)
    TS_16_10_pattern = re.compile(TS_16_10_REGEX)
    TS_15_12_pattern = re.compile(TS_15_12_REGEX)

    
    if TC_18_03_pattern.match(tis_blds_dir):
        prestage_load_path = TC_18_03_WKSPCE
        cmd = "test -d " + prestage_load_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            msg = "Load path {} not found".format(prestage_load_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
    elif TC_17_06_pattern.match(tis_blds_dir):
        prestage_load_path = TC_17_06_WKSPCE
        cmd = "test -d " + prestage_load_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            msg = "Load path {} not found".format(prestage_load_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
    elif TS_16_10_pattern.match(tis_blds_dir):
        prestage_load_path = TS_16_10_WKSPCE
        cmd = "test -d " + prestage_load_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            msg = "Load path {} not found".format(prestage_load_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
    elif TS_15_12_pattern.match(tis_blds_dir):
        prestage_load_path = TS_15_12_WKSPCE
        cmd = "test -d " + prestage_load_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            msg = "Load path {} not found".format(prestage_load_path)
            log.error(msg)
            wr_exit()._exit(1, msg)

    # tis_bld_dir check (ga_load then latest_build)
    if tis_bld_dir == GA_LOAD or not tis_bld_dir:
        test_load_path = load_path + "/" + GA_LOAD
        cmd = "test -h " + test_load_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            log.info("GA_LOAD symlink doesn't exist for this release.  Use latest_build instead")
            test_load_path = load_path + "/" + LATEST_BUILD_DIR
            cmd = "test -h " + test_load_path
            if bld_server_conn.exec_cmd(cmd)[0] != 0:
                msg = "Build path doesn't exist: {}".format(test_load_path)
                log.error(msg)
                wr_exit()._exit(1, msg)
        cmd = "readlink " + test_load_path
        tis_bld_dir = bld_server_conn.exec_cmd(cmd, expect_pattern=TIS_BLD_DIR_REGEX)
        load_path += "/" + tis_bld_dir
    else:
        load_path = load_path + "/" + tis_bld_dir
        cmd = "test -d " + load_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            msg = "Build path doesn't exist: {}".format(load_path)
            log.error(msg)
            wr_exit()._exit(1, msg)


    return load_path, prestage_load_path


def verify_custom_lab_cfg_location(bld_server_conn, lab_cfg_location, tis_on_tis, simplex):
    ''' Verify that the correct configuration file is used in setting up the
        lab.
    '''

    # Rename variable to reflect that it is a path
    lab_cfg_path = lab_cfg_location
    lab_settings_filepath = None
    found_bulk_cfg_file = False
    found_system_cfg_file = False
    found_lab_settings_file = False
    found_lab_setup_cfg_file = False
    cfgfile_list = CENTOS_CFGFILE_LIST + WRL_CFGFILE_LIST
    exit = False

    for file in os.listdir(lab_cfg_location):
        if file in cfgfile_list:
            found_system_cfg_file = True
        elif file == BULK_CFG_FILENAME:
            found_bulk_cfg_file = True
        elif file == CUSTOM_LAB_SETTINGS_FILENAME:
            found_lab_settings_file = True
        elif file == LAB_SETUP_CFG_FILENAME:
            found_lab_setup_cfg_file = True

    if simplex:
        found_bulk_cfg_file = True

    if tis_on_tis:
        found_bulk_cfg_file = True
        found_lab_settings_file = True

    # Tell the user what files are missing
    msg = ''
    if not found_bulk_cfg_file and not tis_on_tis:
        msg += 'Failed to find {} in {}\n'.format(BULK_CFG_FILENAME, lab_cfg_location)
        exit = True

    if not found_system_cfg_file:
        msg += 'Failed to find {} in {}\n'.format(cfgfile_list, lab_cfg_location)
        exit = True

    if not found_lab_setup_cfg_file:
        msg += 'Failed to find {} in {}\n'.format(LAB_SETUP_CFG_FILENAME, lab_cfg_location)
        exit = True

    if exit:
        log.error(msg)
        msg = 'Missing required configuration files'
        wr_exit()._exit(1, msg)

    if not found_lab_settings_file:
        log.info('Settings.ini not found in {}. Will use stored values.' .format(lab_cfg_location))
        lab_cfg_location = get_settings(bld_server_conn, lab_cfg_path)
        lab_settings_filepath = SCRIPT_DIR + "/" + LAB_SETTINGS_DIR + "/" + lab_cfg_location + ".ini"
        log.info('Using lab settings file path: {}'.format(lab_settings_filepath))

    if found_lab_settings_file and not tis_on_tis:
        lab_settings_filepath = lab_cfg_location + "/" + CUSTOM_LAB_SETTINGS_FILENAME

    return lab_cfg_path, lab_settings_filepath


def verify_lab_cfg_location(bld_server_conn, lab_cfg_location, load_path, tis_on_tis, host_os, override,
                            guest_load_path, simplex):
    ''' Get the directory path for the configuration file that is used in
        setting up the lab.
    '''

    # Determine where to find configuration files, e.g. TiS_config.ini, etc.
    if load_path == TC_18_03_WKSPCE:
        lab_cfg_rel_path = TC_18_03_LAB_REL_PATH + "/yow/" + lab_cfg_location
        lab_cfg_path = load_path + "/" + lab_cfg_rel_path
    elif load_path == TC_17_06_WKSPCE:
        lab_cfg_rel_path = TC_17_06_LAB_REL_PATH + "/yow/" + lab_cfg_location
        lab_cfg_path = load_path + "/" + lab_cfg_rel_path
    elif load_path == TS_16_10_WKSPCE:
        lab_cfg_rel_path = TS_16_10_LAB_REL_PATH + "/yow/" + lab_cfg_location
        lab_cfg_path = load_path + "/" + lab_cfg_rel_path
    elif load_path == TS_15_12_WKSPCE:
        lab_cfg_rel_path = TS_15_12_LAB_REL_PATH + "/yow/" + lab_cfg_location
        lab_cfg_path = load_path + "/" + lab_cfg_rel_path

    else:
        lab_cfg_path = load_path + "/lab/yow/" + lab_cfg_location
        cmd = "test -d " + lab_cfg_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0 or override == "yes":
            lab_cfg_rel_path = CENTOS_LAB_REL_PATH + "/yow/" + lab_cfg_location
            lab_cfg_path = load_path + "/" + lab_cfg_rel_path

    cmd = "test -d " + lab_cfg_path
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        msg = 'Lab config directory {} not found in {}'.format(
            lab_cfg_location, lab_cfg_path)
        log.error(msg)
        wr_exit()._exit(1, msg)
    log.info('Using lab config directory: {}'.format(lab_cfg_path))

    # Confirm we have a valid config controller file before starting
    if host_os == "centos":
        cfgfile_list = CENTOS_CFGFILE_LIST
    else:
        cfgfile_list = WRL_CFGFILE_LIST

    cfg_found = False
    for cfgfile in cfgfile_list:
        cmd = "test -f " + lab_cfg_path + "/" + cfgfile
        if bld_server_conn.exec_cmd(cmd)[0] == 0:
            cfg_found = True
            log.info('Using config controller file: {}'.format(cfgfile))
            break

    if not cfg_found:
        msg = 'No valid config controller files found in {}'.format(lab_cfg_path)
        log.error(msg)
        wr_exit()._exit(1, msg)

    # Confirm we have a valid host_bulk_add
    if not simplex:
        bulkfile_found = False
        for bulkfile in BULKCFG_LIST:
            cmd = "test -f " + lab_cfg_path + "/" + bulkfile
            if bld_server_conn.exec_cmd(cmd)[0] == 0:
                bulkfile_found = True
                log.info('Using host bulk add file: {}'.format(bulkfile))
                break

        if not bulkfile_found and not tis_on_tis:
            msg = 'No valid host bulk add file found in {}'.format(lab_cfg_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
    # ~/wassp-repos/testcases/cgcs/sanityrefresh/labinstall/lab_settings/*.ini
    lab_settings_rel_path = LAB_SETTINGS_DIR + "/{}.ini".format(lab_cfg_location)
    lab_settings_filepath = SCRIPT_DIR + "/" + lab_settings_rel_path

    if not os.path.isfile(lab_settings_filepath):
        msg = 'Lab settings file path was not found: {}'.format(lab_settings_filepath)
        lab_settings_filepath = None
    else:
        log.info('Using lab settings file path: {}'.format(lab_settings_filepath))

    # Check the guest directory exists
    cmd = "test -d " + guest_load_path
    if bld_server_conn.exec_cmd(cmd)[0] == 0:
        log.info('Using guest directory path: {}'.format(guest_load_path))
    else:
        msg = 'Guest directory path does not exist on build server: {}'.format(guest_load_path)
        log.error(msg)
        wr_exit()._exit(1, msg)

    return lab_cfg_path, lab_settings_filepath

# TODO: Remove this as using deploy_key defined for ssh and telnetlib
def deploy_key(conn):
    ''' Set the keys used for ssh and telnet connections.
    '''

    try:
        ssh_key = (open(os.path.expanduser(SSH_KEY_FPATH)).read()).rstrip()
    except FileNotFoundError:
        log.exception("User must have a public key {} defined".format(SSH_KEY_FPATH))
        msg = 'User must have a public key {} defined".format(SSH_KEY_FPATH)'
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


def restore_pxeboot_cfg(barcode, tuxlab_server, install_output_dir):
    """
    Unlink the existing pxeboot.cfg symlink and then restore it.  This is done
    in case the file was modified for pre-R5 installs.
    """

    tuxlab_conn = SSHClient(log_path=install_output_dir + "/" + tuxlab_server + ".ssh.log")
    tuxlab_conn.connect(hostname=tuxlab_server, username=USERNAME,
                        password=PASSWORD)
    tuxlab_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + "/" + barcode

    cmd = "cd {}".format(tuxlab_barcode_dir)
    assert tuxlab_conn.exec_cmd(cmd)[0] == 0, "Failed to cd to {}".format(tuxlab_barcode_dir)

    log.info("Changing pxeboot.cfg symlink to {}".format(R5_PXEBOOT))
    cmd = "[ -f {} ]".format(R5_PXEBOOT)
    assert tuxlab_conn.exec_cmd(cmd)[0] == 0, "Failed to find a pxeboot.cfg with gpt boot options defined"
    assert tuxlab_conn.exec_cmd("unlink pxeboot.cfg")[0] == 0, "Unlink of pxeboot.cfg failed"
    cmd = "ln -s {} pxeboot.cfg".format(R5_PXEBOOT)
    assert tuxlab_conn.exec_cmd(cmd)[0] == 0, "Unable to symlink gpt pxeboot cfg"


def set_network_boot_feed(barcode, tuxlab_server, bld_server_conn, load_path, host_os, install_output_dir, tis_blds_dir,
                          skip_pxebootcfg):
    ''' Transfer the load and set the feed on the tuxlab server in preparation
        for booting up the lab.
    '''

    logutils.print_step("Set feed for {} network boot".format(barcode))
    tuxlab_sub_dir = USERNAME + '/' + os.path.basename(load_path)

    tuxlab_conn = SSHClient(log_path=install_output_dir + "/" + tuxlab_server + ".ssh.log")
    tuxlab_conn.connect(hostname=tuxlab_server, username=USERNAME,
                        password=PASSWORD)
    tuxlab_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + "/" + barcode

    cmd = "cd {}".format(tuxlab_barcode_dir)
    assert tuxlab_conn.exec_cmd(cmd)[0] == 0, "Failed to cd to {}".format(tuxlab_barcode_dir)

    log.info("Copy load into feed directory")
    feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir
    tuxlab_conn.sendline("mkdir -p " + tuxlab_sub_dir)
    tuxlab_conn.find_prompt()
    tuxlab_conn.sendline("chmod 775 " + tuxlab_sub_dir)
    tuxlab_conn.find_prompt()

    # Switch pxeboot.cfg files
    old_releases = ["TC_17.06_Host", "TS_16.10_Host", "TS_15.12_Host"]
    if tis_blds_dir.endswith('/'):
        rel = tis_blds_dir[:-1]
    else:
        rel = tis_blds_dir

    if rel in old_releases:
        pxeboot_cfgfile = PRE_R5_PXEBOOT
    else:
        pxeboot_cfgfile = R5_PXEBOOT

    if not skip_pxebootcfg:
        log.info("Changing pxeboot.cfg symlink to {}".format(pxeboot_cfgfile))
        cmd = "[ -f {} ]".format(pxeboot_cfgfile)
        assert tuxlab_conn.exec_cmd(cmd)[0] == 0, "Failed to find a file called {}".format(pxeboot_cfgfile)
        assert tuxlab_conn.exec_cmd("unlink pxeboot.cfg")[0] == 0, "Unlink of pxeboot.cfg failed"
        cmd = "ln -s {} pxeboot.cfg".format(pxeboot_cfgfile)
        assert tuxlab_conn.exec_cmd(cmd)[0] == 0, "Unable to symlink pxeboot.cfg to {}".format(pxeboot_cfgfile)

    # Extra forward slash at end is required to indicate the sync is for
    # all of the contents of RPM_INSTALL_REL_PATH into the feed path

    if host_os == "centos":
        log.info("Installing Centos load")
        bld_server_conn.sendline("cd " + load_path)
        bld_server_conn.find_prompt()
        bld_server_conn.rsync(CENTOS_INSTALL_REL_PATH + "/", USERNAME, tuxlab_server, feed_path,
                              ["--delete", "--force", "--chmod=Du=rwx"])
        bld_server_conn.rsync("export/extra_cfgs/yow*", USERNAME, tuxlab_server, feed_path)
    else:
        log.info("Installing wrlinux load")
        bld_server_conn.rsync(load_path + "/" + RPM_INSTALL_REL_PATH + "/", USERNAME, tuxlab_server, feed_path,
                              ["--delete", "--force", "--chmod=Du=rwx"])

        bld_server_conn.sendline("cd " + load_path)
        bld_server_conn.find_prompt()

        bld_server_conn.rsync("extra_cfgs/yow*", USERNAME, tuxlab_server, feed_path)
        bld_server_conn.rsync(RPM_INSTALL_REL_PATH + "/boot/isolinux/vmlinuz", USERNAME, tuxlab_server, feed_path)
        bld_server_conn.rsync(RPM_INSTALL_REL_PATH + "/boot/isolinux/initrd", USERNAME, tuxlab_server,
                              feed_path + "/initrd.img")

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


def burn_usb_load_image(install_output_dir, node, bld_server_conn, load_path, iso_path=None, iso_host=None):
    ''' Burn usb with given load image.
    '''

    if iso_host:
        logutils.print_step("Burn USB with load image from {} on host {}".format(iso_path, iso_host))
    else:
        logutils.print_step("Burning USB with load image from {}".format(load_path))

    # Check if node (controller-0) is accessible.
    time.sleep(10)
    cmd = "ping -c 4 {}".format(node.host_ip)
    rc, output = bld_server_conn.exec_cmd(cmd, timeout=PING_TIMEOUT + TIMEOUT_BUFFER)

    if rc != 0:
        msg = "Node not responding reliably.  Skipping USB burning."
        wr_exit()._exit(1, msg)
    else:
        node.telnet_conn.login()

    log.info(output)
    # Do not remove! - messes up next line (NEED TO FIX)
    cmd = "ls"
    rc, output = node.telnet_conn.exec_cmd(cmd)

    # check if a USB is plugged in
    cmd = "ls -lrtd /dev/disk/by-id/usb*"
    rc, output = node.telnet_conn.exec_cmd(cmd)
    if rc != 0:
        msg = "No USB found in lab node. Please plug in a usb to {}.".format(node.host_ip)
        log.info(msg)
        wr_exit()._exit(1, msg)
    usb_device = (output.splitlines()[0])[-3:]

    # Check if the ISO is available
    pre_opts = "sshpass -p '{0}'".format(WRSROOT_PASSWORD)
    if not iso_host:
        iso_path = load_path + "/" + BOOT_IMAGE_ISO_PATH
        cmd = "test -f " + iso_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Boot image iso file not found at {}'.format(iso_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
        bld_server_conn.rsync(iso_path, WRSROOT_USERNAME, node.host_ip, BOOT_IMAGE_ISO_TMP_PATH, pre_opts=pre_opts)
    else:
        iso_host_conn = SSHClient(log_path=install_output_dir + "/" + iso_host + ".ssh.log")
        iso_host_conn.connect(hostname=iso_host, username=USERNAME, password=PASSWORD)
        cmd = "test -f " + iso_path
        if iso_host_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Boot image iso file not found at {}'.format(iso_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
        iso_host_conn.rsync(iso_path, WRSROOT_USERNAME, node.host_ip, BOOT_IMAGE_ISO_TMP_PATH, pre_opts=pre_opts)

    # Write the ISO to USB
    cmd = "echo {} | sudo -S dd if={} of=/dev/{} bs=1M oflag=direct; sync".format(WRSROOT_PASSWORD,
                                                                                  BOOT_IMAGE_ISO_TMP_PATH,
                                                                                  usb_device)
    if node.telnet_conn.exec_cmd(cmd, timeout=RSYNC_TIMEOUT)[0] != 0:
        msg = 'Failed to burn boot image iso file \"{}\" onto USB'.format(iso_path)
        log.error(msg)
        wr_exit()._exit(1, msg)

    cmd = "rm bootimage.iso"
    rc, output = node.telnet_conn.exec_cmd(cmd)
    if rc != 0:
        msg = "Unable to delete bootimage.iso.  Please delete manually."
        log.info(msg)
        wr_exit()._exit(1, msg)


def copy_iso(install_output_dir, tuxlab_server, bld_server_conn, load_path, iso_path=None, iso_host=None,
             c0_targetId=None):
    '''
    This Function is intended to perform the following operation
    Copy latest_bootimage.iso to yow-cgcs-tuxlab, mounti it and run pxeboot_setup.sh
    '''

    # Check if node yow-cgcs-tuxlab host is accessible
    cmd = "ping -c 4 {}".format(tuxlab_server)
    rc, output = bld_server_conn.exec_cmd(cmd, timeout=PING_TIMEOUT + TIMEOUT_BUFFER)

    if rc != 0:
        msg = "Unable to ping tuxlab: {}".format(tuxlab_server)
        wr_exit()._exit(1, msg)

    ISO_TMP_PATH = "/tmp/iso/" + c0_targetId + "/" + BOOT_IMAGE_ISO

    # Check if the ISO is available
    pre_opts = "sshpass -p '{0}'".format(PASSWORD)
    if not iso_host:
        iso_path = load_path + "/" + BOOT_IMAGE_ISO_PATH
        cmd = "test -f " + iso_path
        if bld_server_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Boot image iso file not found at {}'.format(iso_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
            logutils.print_step("Starting copying ISO {} from host {}".format(tuxlab_server, iso_host))
        bld_server_conn.rsync(iso_path, USERNAME, tuxlab_server, ISO_TMP_PATH, pre_opts=pre_opts)
    else:
        iso_host_conn = SSHClient(log_path=install_output_dir + "/" + iso_host + ".ssh.log")
        iso_host_conn.connect(hostname=iso_host, username=USERNAME, password=PASSWORD)
        cmd = "test -f " + iso_path
        if iso_host_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Boot image iso file not found at {}'.format(iso_path)
            log.error(msg)
            wr_exit()._exit(1, msg)
        iso_host_conn.rsync(iso_path, USERNAME, tuxlab_server, ISO_TMP_PATH, pre_opts=pre_opts)
    # TODO: The following block should be made into a separate function
    # Now that we have the iso we need to mount it and run pxeboot_setup.sh

    logutils.print_step("Iso copy finished")
    # wr_exit()._exit(54, "done for now")


def test_state(node, attr_type, expected_state):
    '''
    Test the state of the given node
    '''

    global controller0

    rc, output = controller0.ssh_conn.exec_cmd("source /etc/nova/openrc; system host-list")
    if rc != 0:
        msg = "Failed to query hosts on system"
        log.error(msg)
        wr_exit()._exit(1, msg)

    output = "\n".join(output.splitlines()[3:-1])
    match = re.search("^.*{}.*{}.*$".format(node.name, expected_state), \
                      output, re.MULTILINE | re.IGNORECASE)
    if match:
        return True

    return False


def wait_state(nodes, attr_type, expected_state, sut=None, exit_on_find=False, fail_ok=False):
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
    #if attr_type not in STATE_TYPE_DICT:
    #    msg = "Type of state can only be one of: " + \
    #          str(list(STATE_TYPE_DICT.keys()))
    #    log.error(msg)
    #    wr_exit()._exit(1, msg)
    #if expected_state not in STATE_TYPE_DICT[attr_type]:
    #    msg = "Expected {} state can only be on one of: {}" \
    #        .format(attr_type, str(STATE_TYPE_DICT[attr_type]))
    #    log.error(msg)
    #    wr_exit()._exit(1, msg)

    expected_state_count = 0
    search_attempts = MAX_SEARCH_ATTEMPTS
    sleep_secs = int(REBOOT_TIMEOUT / MAX_SEARCH_ATTEMPTS)
    sleep_secs /= 2
    search_attempts = MAX_SEARCH_ATTEMPTS * 2
    node_count = len(nodes)
    while count < search_attempts:
        output = controller0.ssh_conn.exec_cmd("source /etc/nova/openrc; system host-list")[1]
        # Remove table header and footer
        output = "\n".join(output.splitlines()[3:-1])

        if exit_on_find:
            log.info('Waiting for {} to be \"{}\"...'.format(sut, expected_state))
        else:
            node_names = [node.name for node in nodes]
            log.info('Waiting for {} to be \"{}\"...'.format(node_names, expected_state))

        # Create copy of list so that it is unaffected by removal of node
        for node in copy.copy(nodes):
            # Determine if the full table list should be searched
            if exit_on_find:
                name_search = sut
            else:
                name_search = node.name

            # TODO: Should use table_parser here instead
            match = re.search("^.*{}.*{}.*$".format(name_search, expected_state), \
                              output, re.MULTILINE | re.IGNORECASE)
            if match:
                if exit_on_find:
                    return True
                if attr_type == ADMINISTRATIVE:
                    node.administrative = expected_state
                elif attr_type == OPERATIONAL:
                    node.operational = expected_state
                elif attr_type == AVAILABILITY:
                    node.availability = expected_state
                log.info("{} has {} state: {}".format(node.name, attr_type, expected_state))
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
    if count == search_attempts and not fail_ok:
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
    """
    Args: Gets the lab system name from lab_setup.conf file
        bld_server_conn:
        lab_cfg_path:

    Returns: system lab name

    """
    cmd = "grep SYSTEM_NAME " + lab_cfg_path + "/" + LAB_SETUP_CFG_FILENAME
    system_name = bld_server_conn.exec_cmd(cmd)[1]
    return ((system_name.split('=')[1])[5:]).replace('"', '')


def get_settings(bld_server_conn, lab_cfg_path):
    server_name = get_system_name(bld_server_conn, lab_cfg_path)
    server_name = server_name.replace('\n', '')
    server_name = server_name.replace("yow-", "")
    try:
        server_name.index("cgcs-")
    except ValueError:
        # TODO: fix in get_settings
        server_name = "cgcs-" + server_name
    # pv labs are named differently
    if len(server_name.split('-')) < 3:
        last_letter = -1
        while server_name[last_letter].isdigit():
            last_letter -= 1
        server_name = server_name[:last_letter + 1] + '-' + server_name[last_letter + 1:]
    return server_name


def bring_up(node, boot_device_dict, small_footprint, host_os, install_output_dir, close_telnet_conn=False, usb=False,
             lowlat=False, security=False, iso_install=False):
    ''' Initiate the boot and installation operation.
    '''

    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip,
                                             int(node.telnet_port),
                                             negotiate=node.telnet_negotiate,
                                             port_login=True if node.telnet_login_prompt else False,
                                             vt100query=node.telnet_vt100query,
                                             log_path=install_output_dir + "/" + node.name + ".telnet.log")

    # if USB, the node was already on for the file transfer to occur
    if usb:
        vlm_exec_cmd(VLM_TURNOFF, node.barcode)

    vlm_exec_cmd(VLM_TURNON, node.barcode)
    logutils.print_step("Installing {}...".format(node.name))
    rc = node.telnet_conn.install(node, boot_device_dict, small_footprint, host_os, usb, lowlat, security, iso_install)

    if close_telnet_conn:
        print("Closing telnet connection")
        node.telnet_conn.close()

    return rc


def apply_banner(node, banner):
    ''' Apply banner files if they exist
    '''

    log.info('Attempting to apply banner files')

    cmd = 'test -d ' + BANNER_SRC
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = 'Banner files not found for this lab'
        log.info(msg)
        return

    if banner == 'before':
        cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
        cmd += " mv {} {}".format(BANNER_SRC, BANNER_DEST)
        if node.telnet_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Unable to move banner files from {} to {}'.format(BANNER_SRC, BANNER_DEST)
            log.error(msg)
            wr_exit()._exit(1, msg)
    elif banner == 'after':
        cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
        cmd += " sudo apply_banner_customization " + BANNER_SRC
        if node.telnet_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Banner application failed'
            log.error(msg)
            wr_exit()._exit(1, msg)
        else:
            log.info('Banner files have been applied')
    else:
        log.info('Skipping banner file application')

    return


def apply_branding(node):
    ''' Apply branding files if they exist (before config controller is run)
    '''

    log.info('Attempting to apply branding files')

    cmd = 'test -d ' + BRANDING_SRC
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = 'Branding files not found for this lab'
        log.info(msg)
        return

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
    cmd += " cp -r {}/* {}".format(BRANDING_SRC, BRANDING_DEST)
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = 'Unable to move branding files from {} to {}'.format(BRANDING_SRC, BRANDING_DEST)
        log.error(msg)
        wr_exit()._exit(1, msg)

    return


def run_postinstall(node):
    """
    Run post install scripts, if they exist.
    """

    cmd = 'test -d ' + SCRIPTS_HOME
    if node.ssh_conn.exec_cmd(cmd)[0] != 0:
        msg = 'Post install scripts not found for this lab'
        log.info(msg)
        return

    cmd = 'ls -1 --color=none ' + SCRIPTS_HOME
    rc, output = node.ssh_conn.exec_cmd(cmd)
    if rc != 0:
        msg = "Failed to list scripts in: " + SCRIPTS_HOME
        log.error(msg)
        return

    for item in output.splitlines():
        msg = 'Attempting to run script {}'.format(item)
        log.info(msg)
        cmd = "chmod 755 " + SCRIPTS_HOME + "/" + item
        if node.ssh_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Unable to change file permissions'
            log.error(msg)
            wr_exit()._exit(1, msg)
        cmd = SCRIPTS_HOME + "/" + item + " " + node.host_name
        if node.ssh_conn.exec_cmd(cmd)[0] != 0:
            msg = 'Script execution failed'
            log.error(msg)
            wr_exit()._exit(1, msg)

    return


def apply_patches(node, bld_server_conn, patch_dir_paths):
    ''' Apply any patches after the load is installed.
    '''

    patch_names = []
    pre_opts = "sshpass -p '{0}'".format(WRSROOT_PASSWORD)
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

        bld_server_conn.rsync(dir_path + "/*.patch", WRSROOT_USERNAME, node.host_ip, WRSROOT_PATCHES_DIR,
                              pre_opts=pre_opts)

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
        # TODO: Should use table_parser here instead
        if not re.search("^{}.*{}.*$".format(patch, AVAILABLE), output, re.MULTILINE | re.IGNORECASE):
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
    # if not find_error_msg(output):
    #    msg = "Failed to install patches"
    #    log.error(msg)
    #    wr_exit()._exit(1, msg)
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S sw-patch query"
    if node.telnet_conn.exec_cmd(cmd)[0] != 0:
        msg = "Failed to query patches"
        log.error(msg)
        wr_exit()._exit(1, msg)

    # Remove patches
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S rm -rf " + WRSROOT_PATCHES_DIR
    output = node.telnet_conn.exec_cmd(cmd)[1]
    if find_error_msg(output):
        msg = "Failed to remove patch directory: " + WRSROOT_PATCHES_DIR
        log.error(msg)
        wr_exit()._exit(1, msg)

    node.telnet_conn.write_line("echo " + WRSROOT_PASSWORD + " | sudo -S reboot")
    log.info("Patch application requires a reboot.")
    log.info("Controller0 reboot has started")
    # node.telnet_conn.get_read_until("Rebooting...")
    node.telnet_conn.get_read_until(LOGIN_PROMPT, REBOOT_TIMEOUT)


def wait_until_alarm_clears(controller0, timeout=600, check_interval=60, alarm_id="800.001", host_os="centos", fm_alarm=False):
    '''
    Function for waiting until an alarm clears
    '''

    alarm_cleared = False
    end_time = time.time() + timeout

    log.info('Waiting for alarm {} to clear'.format(alarm_id))
    while True:
        if time.time() < end_time:
            time.sleep(15)
            if host_os == "centos":
                cmd = "source /etc/nova/openrc; system alarm-list --nowrap"
            else:
                cmd = "source /etc/nova/openrc; system alarm-list"

            if fm_alarm:
                cmd = "source /etc/nova/openrc; fm alarm-list --nowrap"
            output = controller0.ssh_conn.exec_cmd(cmd)[1]

            if not find_error_msg(output, alarm_id):
                log.info('Alarm {} has cleared'.format(alarm_id))
                alarm_cleared = True
                break
            time.sleep(check_interval)
        else:
            log.info("Alarm {} was not cleared in expected time".format(alarm_id))
            break

    return alarm_cleared


def write_install_vars(args):
    config = configparser.ConfigParser()

    lab_name = args.lab_name
    if lab_name is None or lab_name is "":
        msg = "Lab is not specified; cannot write install variables to file."
        log.error(msg)
        wr_exit()._exit(1, msg)

    install_vars_filename = lab_name + INSTALL_VARS_FILE_EXT
    file_path = os.path.join(INSTALL_VARS_TMP_PATH, install_vars_filename)

    install_vars = dict((k, str(v)) for k, v, in (vars(args)).items())

    config['INSTALL_CONFIG'] = install_vars
    if os.path.exists(file_path):
        os.remove(file_path)

    with open(file_path, "w") as install_var_file:
        os.chmod(file_path, 0o777)
        config.write(install_var_file)
        install_var_file.close()


def read_install_from_file(args):
    lab_name = args.lab_name
    if lab_name is None or lab_name is "":
        msg = "Lab is not specified; cannot read install variables from file."
        log.error(msg)
        wr_exit()._exit(1, msg)

    config = configparser.ConfigParser()
    install_vars_filename = lab_name + INSTALL_VARS_FILE_EXT
    file_path = os.path.join(INSTALL_VARS_TMP_PATH, install_vars_filename)
    install_vars = {}
    if len(config.read(file_path)) > 0:
        import ast
        install_vars = dict(config['INSTALL_CONFIG'])

        for (k, v) in install_vars.items():
            if v == 'False' or v == 'True' or v == 'None':
                install_vars[k] = ast.literal_eval(v)

        return Namespace(**install_vars)
    else:
        return None


def labInstallVars():
    args = parse_args()

    lab_name = args.lab_name

    # rc, labs = verifyLabName(args.lab_name)
    # if not rc:
    #    msg = 'Specified lab name {} is not in the supported lab names {}'.format(args.lab_name, labs)
    #    return False, msg

    if not args.continue_install:
        if lab_name is not None and lab_name is not "":
            write_install_vars(args)
        return args
    else:
        install_vars = read_install_from_file(args)
        if install_vars is not None:
            # update continue_install
            install_vars.continue_install = True

            global executed_install_steps
            executed_steps_filename = lab_name + INSTALL_EXECUTED_STEPS_FILE_EXT
            executed_steps_path = os.path.join(INSTALL_VARS_TMP_PATH, executed_steps_filename)

            if os.path.exists(executed_steps_path):
                with open(executed_steps_path) as file:
                    executed_install_steps = file.read().splitlines()

            return install_vars
        else:
            msg = "Lab Install Variable file not found."
            print(msg)
            wr_exit()._exit(1, msg)


def verifyLabName(lab_name):
    from os import walk
    filenames = next(os.walk(LAB_SETTINGS_DIR))[2]
    supported_labs = []
    for f in filenames:
        if f.endswith(".ini"):
            supported_labs.append(os.path.splitext(f)[0])

    if lab_name in supported_labs:
        return True, supported_labs
    else:
        return False, supported_labs


class Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def reserveLabNodes(barcodes):
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

    # vlm_reserve(barcodesForReserve, note=INSTALLATION_RESERVE_NOTE)
    vlm_reserve(barcodes, note=INSTALLATION_RESERVE_NOTE)


def establish_ssh_connection(_controller0, install_output_dir):
    print("Opening ssh connection")
    cont0_ssh_conn = SSHClient(log_path=install_output_dir + \
                                        "/" + CONTROLLER0 + ".ssh.log")
    cont0_ssh_conn.connect(hostname=_controller0.host_ip,
                           username=WRSROOT_USERNAME,
                           password=WRSROOT_PASSWORD)

    return cont0_ssh_conn


def open_telnet_session(_controller0, install_output_dir):
    cont0_telnet_conn = telnetlib.connect(_controller0.telnet_ip,
                                          int(_controller0.telnet_port),
                                          negotiate=_controller0.telnet_negotiate,
                                          port_login=True if _controller0.telnet_login_prompt else False,
                                          vt100query=_controller0.telnet_vt100query, \
                                          log_path=install_output_dir + "/" + CONTROLLER0 + \
                                                   ".telnet.log", debug=False)

    return cont0_telnet_conn


def setupNetworking(host_os):
    """
    Setup the network if we have a USB install or after patch installation.
    """
    # Setup network access on the running controller0
    nic_interface = controller0.host_nic if host_os == DEFAULT_HOST_OS else NIC_INTERFACE
    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S ip addr add " + controller0.host_ip + \
          HOST_ROUTING_PREFIX + " dev {}".format(nic_interface)
    if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
        log.error("Warning: Failed to add IP address: " + controller0.host_ip)

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S ip link set dev {} up".format(nic_interface)
    if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
        log.error("Warning: Failed to bring up {} interface".format(nic_interface))

    time.sleep(2)

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S route add default gw " + HOST_GATEWAY
    if controller0.telnet_conn.exec_cmd(cmd)[0] != 0:
        log.error("Warning: Failed to add default gateway: " + HOST_GATEWAY)

    # Ping the outside network to ensure the above network setup worked as expected
    # Sometimes the network may take upto a minute to setup. Adding a delay of 60 seconds
    # before ping
    # TODO: Change to ping at 15 seconds interval for upto 4 times
    time.sleep(120)
    cmd = "ping -w {} -c 4 {}".format(PING_TIMEOUT, DNS_SERVER)
    if controller0.telnet_conn.exec_cmd(cmd, timeout=PING_TIMEOUT + TIMEOUT_BUFFER)[0] != 0:
        msg = "Failed to ping outside network"
        log.error(msg)
        wr_exit()._exit(1, msg)


def bringUpController(install_output_dir, bld_server_conn, load_path, patch_dir_paths,
                      host_os, boot_device_dict, small_footprint, burn_usb,
                      tis_on_tis, boot_usb, iso_path, iso_host, lowlat,
                      security, iso_install):
    global controller0
    # global cumulus

    if not tis_on_tis:
        if controller0.telnet_conn is None:
            controller0.telnet_conn = open_telnet_session(controller0, install_output_dir)

        if burn_usb:
            burn_usb_load_image(install_output_dir, controller0, bld_server_conn, load_path, iso_path, iso_host)

        if burn_usb or boot_usb:
            usb = True
        else:
            usb = False

        # Boot up controller0
        rc = bring_up(controller0, boot_device_dict, small_footprint, host_os, install_output_dir,
                      close_telnet_conn=False, usb=usb, lowlat=lowlat, security=security, iso_install=iso_install)
        if rc != 0:
            msg = "Unable to bring up controller-0"
            wr_exit()._exit(1, msg)
        logutils.print_step("Initial login and password set for " + controller0.name)
        controller0.telnet_conn.login(reset=True)
    else:
        if cumulus:
            cumulus.tis_install()
            controller0.host_ip = cumulus.get_floating_ip("EXTERNALOAMC0")
            controller0.host_floating_ip = cumulus.get_floating_ip('EXTERNALOAMFLOAT')
            # Boot up controller0
            cumulus.launch_controller0()
        else:
            msg = "Failed to cumulus virtual controller-0"
            log.error(msg)
            wr_exit()._exit(1, msg)

    if burn_usb or boot_usb:
        setupNetworking(host_os)

    # Open an ssh session
    # Temporary workaround for timing issue where ssh fails
    time.sleep(60)

    controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)

    controller0.ssh_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

    # Apply patches if patch dir is not none

    if patch_dir_paths:
        apply_patches(controller0, bld_server_conn, patch_dir_paths)

        # Reconnect telnet session
        log.info("Found login prompt. Controller0 reboot has completed")
        controller0.telnet_conn.login()

        # Think we only need this if we burn/boot from USB
        if burn_usb or boot_usb:
            setupNetworking(host_os)

        # Reconnect ssh session
        controller0.ssh_conn.disconnect()
        controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)


def downloadLabConfigFiles(lab_type, bld_server_conn, lab_cfg_path, load_path,
                           guest_load_path, host_os, override, lab_cfg_location,
                           centos_lab_path=CENTOS_LAB_REL_PATH,
                           heat_temp_path=HEAT_TEMPLATES_PATH):
    pre_opts = "sshpass -p '{0}'".format(WRSROOT_PASSWORD)

    if cumulus:
        bld_server_conn.rsync(os.path.join(DEFAULT_WKSPCE, DEFAULT_REL,
                                           DEFAULT_BLD, centos_lab_path,
                                           "scripts", "*"),
                              WRSROOT_USERNAME, controller0.host_ip,
                              WRSROOT_HOME_DIR, pre_opts=pre_opts)
        bld_server_conn.rsync(os.path.join(DEFAULT_WKSPCE, DEFAULT_REL,
                                           DEFAULT_BLD, heat_temp_path, "*"),
                              WRSROOT_USERNAME, controller0.host_ip,
                              WRSROOT_HEAT_DIR, pre_opts=pre_opts)
    else:
        if load_path.find(TS_15_12_WKSPCE) > -1:
            bld_server_conn.rsync(os.path.join(TS_15_12_WKSPCE, TS_15_12_LAB_REL_PATH, "scripts", "*"),
                                  WRSROOT_USERNAME, controller0.host_ip,
                                  WRSROOT_HOME_DIR, pre_opts=pre_opts)
        elif load_path.find(TS_16_10_WKSPCE) > -1:
            bld_server_conn.rsync(os.path.join(TS_16_10_WKSPCE, TS_16_10_LAB_REL_PATH, "scripts", "*"),
                                  WRSROOT_USERNAME, controller0.host_ip,
                                  WRSROOT_HOME_DIR, pre_opts=pre_opts)
        elif load_path.find(TC_17_06_WKSPCE) > -1:
            bld_server_conn.rsync(os.path.join(TC_17_06_WKSPCE, TC_17_06_LAB_REL_PATH, "scripts", "*"),
                                  WRSROOT_USERNAME, controller0.host_ip,
                                  WRSROOT_HOME_DIR, pre_opts=pre_opts)
        elif load_path.find(TC_18_03_WKSPCE) > -1:
            bld_server_conn.rsync(os.path.join(TC_18_03_WKSPCE, TC_18_03_LAB_REL_PATH, "scripts", "*"),
                                  WRSROOT_USERNAME, controller0.host_ip,
                                  WRSROOT_HOME_DIR, pre_opts=pre_opts)
        else:
            rc = bld_server_conn.rsync(os.path.join(lab_cfg_path, "/../../scripts/", "*"),
                                       WRSROOT_USERNAME, controller0.host_ip,
                                       WRSROOT_HOME_DIR, pre_opts=pre_opts,
                                       allow_fail=True)

            rc1 = bld_server_conn.rsync(os.path.join(load_path, centos_lab_path, "scripts", "*"),
                                        WRSROOT_USERNAME, controller0.host_ip,
                                        WRSROOT_HOME_DIR,
                                        pre_opts=pre_opts, allow_fail=True)

            rc2 = bld_server_conn.rsync(os.path.join(load_path, "lab/scripts", "*"),
                                        WRSROOT_USERNAME, controller0.host_ip,
                                        WRSROOT_HOME_DIR,
                                        pre_opts=pre_opts, allow_fail=True)

            if 0 not in (rc, rc1, rc2):
                msg = "Unable to rsync any script files"
                log.error(msg)
                wr_exit()._exit(1, msg)

        # Grab heat templates
        heatloc1 = bld_server_conn.rsync(os.path.join(load_path, heat_temp_path, "*"),
                                         WRSROOT_USERNAME, controller0.host_ip, \
                                         WRSROOT_HEAT_DIR + "/", \
                                         pre_opts=pre_opts, allow_fail=True)

        if heatloc1 != 0:
            bld_server_conn.rsync(os.path.join(load_path, HEAT_TEMPLATES_PATH_STX, "*"),
                                  WRSROOT_USERNAME, controller0.host_ip, \
                                  WRSROOT_HEAT_DIR + "/", \
                                  pre_opts=pre_opts, allow_fail=True)


    # Grab the configuration files, e.g. TiS_config.ini_centos, etc.
    bld_server_conn.rsync(os.path.join(lab_cfg_path, "*"),
                          WRSROOT_USERNAME, controller0.host_ip,
                          WRSROOT_HOME_DIR, pre_opts=pre_opts)

    # Get the appropriate guest image
    bld_server_conn.rsync(os.path.join(guest_load_path, "cgcs-guest.img"),
                          WRSROOT_USERNAME, controller0.host_ip, \
                          WRSROOT_IMAGES_DIR + "/", \
                          pre_opts=pre_opts, allow_fail=True)

    bld_server_conn.rsync(os.path.join(guest_load_path, "latest_tis-centos-guest.img"),
                          WRSROOT_USERNAME, controller0.host_ip, \
                          WRSROOT_IMAGES_DIR + "/tis-centos-guest.img", \
                          pre_opts=pre_opts, allow_fail=True)

    bld_server_conn.rsync(os.path.join(guest_load_path, "tis-centos-guest.img"),
                          WRSROOT_USERNAME, controller0.host_ip, \
                          WRSROOT_IMAGES_DIR + "/tis-centos-guest.img", \
                          pre_opts=pre_opts, allow_fail=True)

    # Get licenses
    if load_path.find(TS_15_12_WKSPCE) > -1:
        if lab_type == "regular" or lab_type == "storage":
            license = LICENSE_FILEPATH_R2
        else:
            license = SFP_LICENSE_FILEPATH_R2
            
    elif load_path.find(TS_16_10_WKSPCE) > -1:
        if lab_type == "regular" or lab_type == "storage":
            license = LICENSE_FILEPATH_R3
        else:
            license = SFP_LICENSE_FILEPATH_R3

    elif load_path.find(TC_17_06_WKSPCE) > -1:
        if lab_type == "regular" or lab_type == "storage":
            license = LICENSE_FILEPATH_R4
        elif lab_type == "cpe":
            license = SFP_LICENSE_FILEPATH_R4
        elif lab_type == "simplex":
            license = SIMPLEX_LICENSE_FILEPATH_R4
        else:
            license = SFP_LICENSE_FILEPATH_R4

    elif load_path.find(TC_18_03_WKSPCE) > -1:
        if lab_type == "regular" or lab_type == "storage":
            license = LICENSE_FILEPATH_R5
        elif lab_type == "cpe":
            license = SFP_LICENSE_FILEPATH_R5
        elif lab_type == "simplex":
            license = SFP_LICENSE_FILEPATH_R5
        else:
            license = SIMPLEX_LICENSE_FILEPATH_R5

    else:
        if lab_type == "regular" or lab_type == "storage":
            license = LICENSE_FILEPATH
        elif lab_type == "cpe":
            license = SFP_LICENSE_FILEPATH
        elif lab_type == "simplex" and "R3" in load_path:
            license = SFP_LICENSE_FILEPATH
        else:
            license = SIMPLEX_LICENSE_FILEPATH

    bld_server_conn.rsync(license, WRSROOT_USERNAME,
                          controller0.host_ip,
                          os.path.join(WRSROOT_HOME_DIR, "license.lic"),
                          pre_opts=pre_opts)

    if host_os == "centos":
        wrsroot_etc_profile = WRSROOT_ETC_PROFILE
    else:
        wrsroot_etc_profile = WRSROOT_ETC_PROFILE_LEGACY

    cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"
    cmd += " sed -i.bkp 's/TMOUT=900/TMOUT=0/g' " + wrsroot_etc_profile
    controller0.ssh_conn.exec_cmd(cmd)
    cmd = "unset TMOUT"
    controller0.ssh_conn.exec_cmd(cmd)
    cmd = 'echo \'export HISTTIMEFORMAT="%Y-%m-%d %T "\' >>'
    cmd += " " + WRSROOT_HOME_DIR + "/.bashrc"
    controller0.ssh_conn.exec_cmd(cmd)
    cmd = 'echo \'export PROMPT_COMMAND="date; $PROMPT_COMMAND"\' >>'
    cmd += " " + WRSROOT_HOME_DIR + "/.bashrc"
    controller0.ssh_conn.exec_cmd(cmd)
    controller0.ssh_conn.exec_cmd("source " + WRSROOT_HOME_DIR + "/.bashrc")


def setupHeat(bld_server_conn):
    # Check if the /home/wrsroot/.heat_resources file exists
    heat_resources_path = WRSROOT_HOME_DIR + HEAT_RESOURCES
    cmd = "test -f " + heat_resources_path
    rc, output = controller0.ssh_conn.exec_cmd(cmd)
    if rc != 0:
        log.info("{} not found.  Skipping heat setup.".format(heat_resources_path))
        return
    cmd = "test -f /home/wrsroot/.this_didnt_work"
    rc, output = controller0.ssh_conn.exec_cmd(cmd)
    if rc == 0:
        log.info("Skipping heat setup")
        return

    # Check if /home/wrsroot/create_resource_stacks.sh exists
    stack_create_script = WRSROOT_HOME_DIR + STACK_CREATE_SCRIPT
    cmd = "test -f " + stack_create_script
    rc, output = controller0.ssh_conn.exec_cmd(cmd)
    if rc != 0:
        log.info("{} not found.  Skipping heat setup.".format(stack_create_script))
        return

    # Create the resource stacks
    # Check if /home/wrsroot/create_resource_stacks.sh exists
    cmd = WRSROOT_HOME_DIR + "./" + STACK_CREATE_SCRIPT
    rc, output = controller0.ssh_conn.exec_cmd(cmd)
    if rc != 0:
        msg = "Failure when creating resource stacks"
        log.error(msg)
        wr_exit()._exit(1, msg)

    # Check expected resources are created
    for yaml_file in YAML:
        yaml_path = WRSROOT_HOME_DIR + yaml_file
        cmd = "test -f " + yaml_file
        rc, output = controller0.ssh_conn.exec_cmd(cmd)
        if rc != 0:
            msg = "Expected file {} not found".format(yaml_file)
            log.error(msg)
            wr_exit()._exit(1, msg)

    # Check /home/wrsroot/launch_stacks.sh exists
    stack_launch_script_path = WRSROOT_HOME_DIR + STACK_LAUNCH_SCRIPT
    cmd = "test -f " + stack_launch_script_path
    rc, output = controller0.ssh_conn.exec_cmd(cmd)
    if rc != 0:
        msg = "Expected file {} not found".format(stack_launch_script_path)
        log.error(msg)
        wr_exit()._exit(1, msg)

    # Temp workaround since permissions in git don't allow execution
    cmd = "chmod 755 " + stack_launch_script_path
    rc, output = controller0.ssh_conn.exec_cmd(cmd)

    # Run launch_stacks.sh lab_setup.conf
    cmd = stack_launch_script_path + " lab_setup.conf"
    rc, output = controller0.ssh_conn.exec_cmd(cmd)
    if rc != 0:
        msg = "Heat stack launch failed"
        log.error(msg)
        wr_exit()._exit(1, msg)


def configureController(bld_server_conn, host_os, install_output_dir, banner,
                        branding, config_region, kubernetes):
    # Configure the controller as required
    global controller0
    if not cumulus:
        if controller0.telnet_conn is None:
            controller0.telnet_conn = open_telnet_session(controller0, install_output_dir)
            controller0.telnet_conn.login()

    # Apply banner if specified by user
    if banner == 'before' and host_os == 'centos':
        apply_banner(controller0, banner)

    # Apply branding if specified by user
    if branding != 'no' and host_os == 'centos':
        apply_branding(controller0)

    # No consistency in naming of config file naming
    pre_opts = "sshpass -p '{0}'".format(WRSROOT_PASSWORD)
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
            cmd = "export USER=wrsroot"
            if not cumulus:
                rc, output = controller0.telnet_conn.exec_cmd(cmd)
            else:
                rc, output = controller0.ssh_conn.exec_cmd(cmd)
            cmd = "echo " + WRSROOT_PASSWORD + " | sudo -S"

            if config_region:
                cmd += " config_region " + cfgfile
            elif kubernetes:
                cmd += " config_controller --kubernetes --config-file " + cfgfile
            else:
                cmd += " config_controller --config-file " + cfgfile

            os.environ["TERM"] = "xterm"
            if host_os == "centos" and not cumulus:
                rc, output = controller0.telnet_conn.exec_cmd(cmd, timeout=CONFIG_CONTROLLER_TIMEOUT)
            else:
                rc, output = controller0.ssh_conn.exec_cmd(cmd, timeout=CONFIG_CONTROLLER_TIMEOUT)
            if rc != 0 or find_error_msg(output, "Configuration failed"):
                msg = "config_controller failed"
                log.error(msg)
                wr_exit()._exit(1, msg)
            break

    if not cfg_found:
        msg = "Configuration failed: No configuration files found"
        log.error(msg)
        wr_exit()._exit(1, msg)

    # Apply banner if specified by the user
    if banner == 'after' and host_os == 'centos':
        apply_banner(controller0, banner)

    return


def bulkAddHosts():
    # Run host bulk add

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
                wr_exit()._exit(1, msg)
            break

    if not bulkfile_found:
        msg = "Configuration failed: No host-bulk-add file was found."
        log.error(msg)
        wr_exit()._exit(1, msg)


def run_labsetup(fail_ok=False):
    cmd = './lab_setup.sh'
    cmd = WRSROOT_HOME_DIR + "/" + LAB_SETUP_SCRIPT
    log.info("Running cmd: {}".format(cmd))
    controller0.ssh_conn.sendline(cmd)
    try:
        log.info("Checking for password prompt")
        controller0.ssh_conn.expect("Password:", timeout=20)
        log.info("Found lab_setup password prompt.  Sending password.")
        controller0.ssh_conn.sendline(WRSROOT_PASSWORD)
    except:
        log.info("Password prompt not found")
        pass

    log.info("Waiting for lab_setup.sh to complete")
    controller0.ssh_conn.find_prompt(LAB_SETUP_TIMEOUT)
    out = controller0.ssh_conn.get_after()
    rc = controller0.ssh_conn.get_rc()

    installer_exit = wr_exit()

    if rc != "0":
        if fail_ok:
            msg = "lab_setup returned non-zero exit code but continuing anyways."
            log.info(msg)
        else:
            msg = "lab_setup returned non-zero exit code, exiting install."
            log.error(msg)
            installer_exit._exit(1, msg)

    return


def run_cpe_compute_config_complete(host_os, install_output_dir):
    cmd = 'source /etc/nova/openrc; system compute-config-complete'
    if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("compute-config-complete failed in small footprint configuration")
        wr_exit()._exit(1, "compute-config-complete failed in small footprint configuration.")

    # The controller0 will restart. Need to login after reset is
    # complete before we can continue.

    log.info("Controller0 reset has started")
    if host_os == "wrlinux":
        controller0.telnet_conn.get_read_until("Rebooting...")
    else:
        # controller0.telnet_conn.get_read_until("Restarting")
        controller0.telnet_conn.get_read_until("Reached target Shutdown")

    controller0.telnet_conn.get_read_until(LOGIN_PROMPT, REBOOT_TIMEOUT)
    log.info("Found login prompt. Controller0 reset has completed")

    # Reconnect telnet session
    controller0.telnet_conn.login()

    # Reconnect ssh session
    controller0.ssh_conn.disconnect()
    cont0_ssh_conn = SSHClient(log_path=install_output_dir + "/" + CONTROLLER0 + ".ssh.log")
    cont0_ssh_conn.connect(hostname=controller0.host_ip,
                           username=WRSROOT_USERNAME,
                           password=WRSROOT_PASSWORD)
    controller0.ssh_conn = cont0_ssh_conn

    log.info("Waiting for controller0 come online")
    wait_state(controller0, ADMINISTRATIVE, UNLOCKED)
    wait_state(controller0, OPERATIONAL, ENABLED)


def boot_other_lab_hosts(nodes, boot_device_dict, host_os, install_output_dir,
                         small_footprint, tis_on_tis):
    # Bring up other hosts
    threads = []
    if not tis_on_tis:
        for node in nodes:
            if node.name != CONTROLLER0:
                node_thread = threading.Thread(target=bring_up,
                                               name=node.name,
                                               args=(node,
                                                     boot_device_dict,
                                                     small_footprint, host_os,
                                                     install_output_dir))
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
                msg = "Failed to set personality for controller-1"
                log.error(msg)
                wr_exit()._exit(1, msg)
        else:
            msg = "Launching controller-1 failed"
            log.error(msg)
            wr_exit()._exit(1, msg)

        # storages
        current_host = 3
        cumulus.launch_storages()
        storage_count = cumulus.get_number_of_storages()
        if cumulus.storage:
            current_osd = 'b'  # /dev/vdb
            osd_string = 'OSD_DEVICES="'
            for i in range(0, storage_count):
                osd_string += "\/dev\/vd" + current_osd + " "
                current_osd = chr(ord(current_osd) + 1)
            osd_string += '"'
            cmd = "sed -i 's/#OSD_STRING/" + osd_string + "/g' lab_setup.conf"
            rc, output = controller0.ssh_conn.exec_cmd(cmd)
            if rc is not 0:
                msg = "Failed to update osd config for lab_setup.sh"
                log.error(msg)
                wr_exit()._exit(1, msg)

        time.sleep(120)
        cmd = "source /etc/nova/openrc; system host-list | awk \'/None/ { print $2 }\'"
        rc, ids = controller0.ssh_conn.exec_cmd(cmd)
        if rc is 0:
            for i in range(0, storage_count):

                cmd = "source /etc/nova/openrc;system host-update " + str(current_host) + " " + \
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

        time.sleep(60)
        cmd = "source /etc/nova/openrc; system host-list | awk \'/None/ { print $2 }\'"
        rc, ids = controller0.ssh_conn.exec_cmd(cmd)
        if rc is 0:
            for i in range(0, compute_count):

                cmd = "source /etc/nova/openrc;system host-update " + str(current_host) + " " + \
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


def unlock_node(nodes, selection_filter=None, wait_done=True):
    _unlock_nodes = []
    if selection_filter is not None:
        for node in nodes:
            if selection_filter in node.name:
                _unlock_nodes.append(node)
    else:
        _unlock_nodes = list(nodes)

    if len(_unlock_nodes) > 0:
        for node in _unlock_nodes:
            cmd = "source /etc/nova/openrc; system host-unlock " + node.name
            if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
                msg = "Failed to unlock: " + node.name
                log.error(msg)
                wr_exit()._exit(1, msg)

        if wait_done:
            wait_state(_unlock_nodes, AVAILABILITY, AVAILABLE)


def do_next_install_step(_lab_type, step):
    global executed_install_steps
    if step.is_step_valid(_lab_type):
        if step.step_full_name in executed_install_steps:
            msg = "Install step {} is already executed".format(step.step_full_name)
            log.info(msg)
            return False
        else:
            msg = "Executing install step {} for {} lab".format(step.step_full_name, lab_type)
            logutils.print_step(msg)
            # log.info(msg)
            return True
    else:
        return False


def set_install_step_complete(step):
    global executed_install_steps
    if step.step_full_name not in executed_install_steps:
        executed_install_steps.append(step.step_full_name)

        msg = "Install step {} complete".format(step.step_full_name)
        log.info(msg)
    else:
        msg = "****Install step {} already present in executed step list".format(step.step_full_name)
        log.info(msg)


def main():
    boot_device_dict = DEFAULT_BOOT_DEVICE_DICT
    lab_settings_filepath = ""
    compute_dict = {}
    storage_dict = {}
    provision_cmds = []
    barcodes = []
    threads = []

    args = labInstallVars()

    lab_name = args.lab_name

    global PASSWORD
    global PUBLIC_SSH_KEY
    global lab_type
    global executed_install_steps
    global log
    global cumulus

    PASSWORD = args.password or getpass.getpass()
    PUBLIC_SSH_KEY = get_ssh_key()

    tis_on_tis = args.tis_on_tis
    if tis_on_tis:
        print("\nRunning Tis-on-TiS lab install ...")
        # cumulus_password = args.cumulus_password or \
        #                    getpass.getpass("CUMULUS_PASSWORD: ")

        lab_cfg_location = args.lab_config_location
    else:
        # e.g. cgcs-ironpass-7_12
        lab_cfg_location = args.lab_config_location

    if not tis_on_tis:
        controller_nodes = tuple(args.controller.split(','))

    if args.compute != None and args.compute != "":
        compute_nodes = tuple(args.compute.split(','))
    else:
        compute_nodes = None
        lab_type = 'cpe'

    if args.storage != None and args.storage != "":
        storage_nodes = tuple(args.storage.split(','))
        lab_type = 'storage'
    else:
        storage_nodes = None

    # tuxlab_server = args.tuxlab_server + HOST_EXT
    tuxlab_server = args.tuxlab_server
    run_lab_setup = args.run_lab_setup
    small_footprint = args.small_footprint
    system_mode = args.system_mode
    postinstall = args.postinstall
    burn_usb = args.burn_usb
    boot_usb = args.boot_usb
    iso_host = args.iso_host
    iso_path = args.iso_path
    simplex = args.simplex
    lowlat = args.lowlat
    skip_feed = args.skip_feed
    host_os = args.host_os
    stop = args.stop
    override = args.override
    banner = args.banner
    wipedisk = args.wipedisk
    security = args.security
    ovs = args.ovs
    kubernetes = args.kubernetes

    branding = args.branding
    fm_alarm = False

    if args.bld_server != "":
        bld_server = args.bld_server
    else:
        bld_server = "yow-cgts4-lx"

    if args.bld_server_wkspce != "":
        bld_server_wkspce = args.bld_server_wkspce
    else:
        bld_server = "/localdisk/loadbuild/jenkins"

    if args.tis_blds_dir != "":
        tis_blds_dir = args.tis_blds_dir
    else:
        tis_blds_dir = "CGCS_5.0_Host"

    if args.tis_bld_dir != "":
        tis_bld_dir = args.tis_bld_dir
    else:
        tis_bld_dir = GA_LOAD

    if args.guest_bld_dir != "":
        guest_bld_dir = args.guest_bld_dir
    else:
        guest_bld_dir = "CGCS_5.0_Guest"

    patch_dir_paths = args.patch_dir_paths
    iso_install = args.iso_install
    skip_pxebootcfg = args.skip_pxebootcfg
    config_region = args.config_region

    continue_install = args.continue_install

    if iso_host and iso_path and not iso_install:
        burn_usb = True
    elif (iso_host and not iso_path) or (iso_path and not iso_host):
        msg = "Both iso-host and iso-path must be specified"
        log.info(msg)
        wr_exit()._exit(1, msg)

    if simplex:
        small_footprint = True
        lab_type = 'simplex'

    # Don't bother setting up the feed if we want to boot from USB
    if burn_usb or boot_usb:
        skip_feed = True

    install_output_dir = None
    if args.output_dir:
        output_dir = args.output_dir
        if re.match('.*/\d+/?$', output_dir):
            install_output_dir = output_dir
    else:
        prefix = re.search("\w+", __file__).group(0) + "."
        suffix = ".logs"
        output_dir = tempfile.mkdtemp(suffix, prefix)

    if not install_output_dir:
        # create subdir only if not already supplied
        install_timestr = time.strftime("%Y%m%d-%H%M%S")
        install_output_dir = os.path.join(output_dir, install_timestr)

    os.makedirs(install_output_dir, exist_ok=True)

    log_level = args.log_level

    log_level_idx = logutils.LOG_LEVEL_NAMES.index(log_level)
    logutils.GLOBAL_LOG_LEVEL = logutils.LOG_LEVELS[log_level_idx]
    log = logutils.getLogger(LOGGER_NAME)

    if continue_install:
        log.info("Resuming install for lab {}".format(lab_name))

    logutils.print_step("Arguments:")
    logutils.print_name_value("LAB Name", lab_name)
    logutils.print_name_value("Resume Install", continue_install)

    if tis_on_tis:
        logutils.print_name_value("TiS-on-TiS", tis_on_tis)

    logutils.print_name_value("Lab config location", lab_cfg_location)

    if not tis_on_tis:
        logutils.print_name_value("Controller", controller_nodes)
        logutils.print_name_value("Compute", compute_nodes)
        logutils.print_name_value("Storage", storage_nodes)

        logutils.print_name_value("Run lab setup", run_lab_setup)
        logutils.print_name_value("Tuxlab server", tuxlab_server)
        logutils.print_name_value("Is iso_install", iso_install)
        logutils.print_name_value("Small footprint", small_footprint)
        logutils.print_name_value("Skip pxeboot cfg", skip_pxebootcfg)

    logutils.print_name_value("Build server", bld_server)
    logutils.print_name_value("Build server workspace", bld_server_wkspce)
    logutils.print_name_value("TiS builds directory", tis_blds_dir)
    logutils.print_name_value("TiS build directory", tis_bld_dir)
    logutils.print_name_value("Guest build directory", guest_bld_dir)
    logutils.print_name_value("Patch directory paths", patch_dir_paths)
    logutils.print_name_value("Output directory", install_output_dir)
    logutils.print_name_value("Log level", log_level)
    logutils.print_name_value("Host OS", host_os)
    logutils.print_name_value("Stop", stop)
    logutils.print_name_value("Override", override)
    logutils.print_name_value("Banner", banner)
    logutils.print_name_value("wipedisk", wipedisk)
    logutils.print_name_value("Branding", branding)
    logutils.print_name_value("Skip feed", skip_feed)
    logutils.print_name_value("Boot USB", boot_usb)
    logutils.print_name_value("Burn USB", burn_usb)
    logutils.print_name_value("ISO Host", iso_host)
    logutils.print_name_value("ISO Path", iso_path)
    logutils.print_name_value("Simplex", simplex)
    logutils.print_name_value("Security", security)
    logutils.print_name_value("Low Lat", lowlat)
    logutils.print_name_value("OVS", ovs)
    logutils.print_name_value("Kubernetes", kubernetes)
    logutils.print_name_value("Run Postinstall Scripts", postinstall)
    logutils.print_name_value("Run config_region instead of config_controller", config_region)

    email_info = {}
    email_info['email_server'] = EMAIL_SERVER
    email_info['email_from'] = EMAIL_FROM
    email_info['email_to'] = args.email_address
    email_info['email_subject'] = EMAIL_SUBJECT

    installer_exit = wr_exit()
    installer_exit._set_email_attr(**email_info)
    installer_exit.executed_steps = executed_install_steps

    # installed load info for email message
    installed_load_info = ''

    # Set security parameter for USB installs (assuming we're not installing an
    # other release)
    older_rel = ['TC_17.06_Host/', 'TC_17.06_Host', 'TS_15.12_Host/',
                 'TS_15.12_Host', 'TS_16.10_Host/', 'TS_16.10_Host']

    print("\nRunning as user: " + USERNAME + "\n")

    bld_server_conn = SSHClient(log_path=install_output_dir + "/" + bld_server + ".ssh.log")
    bld_server_conn.connect(hostname=bld_server, username=USERNAME,
                            password=PASSWORD)

    guest_load_path = "{}/{}".format(bld_server_wkspce, guest_bld_dir)

    if tis_on_tis:
        guest_load_path = "{}/{}".format(DEFAULT_WKSPCE, guest_bld_dir)
    load_path, prestage_load_path = get_load_path(bld_server_conn, bld_server_wkspce, tis_blds_dir,
                                                  tis_bld_dir)
    print("This is load path: {}".format(load_path))
    print("This is prestage load path: {}".format(prestage_load_path))

    if os.path.isdir(lab_cfg_location):
        barcode_controller = args.controller
        barcode_compute = args.compute
        lab_cfg_path, lab_settings_filepath = verify_custom_lab_cfg_location(bld_server_conn, lab_cfg_location,
                                                                             tis_on_tis, simplex)
    elif prestage_load_path == "":
        lab_cfg_path, lab_settings_filepath = verify_lab_cfg_location(bld_server_conn,
                                                                      lab_cfg_location, load_path,
                                                                      tis_on_tis, host_os, override,
                                                                      guest_load_path, simplex)
    else:
        lab_cfg_path, lab_settings_filepath = verify_lab_cfg_location(bld_server_conn,
                                                                      lab_cfg_location, prestage_load_path,
                                                                      tis_on_tis, host_os, override,
                                                                      guest_load_path, simplex)

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
    if lab_name is None or lab_name is "":
        lab_name = get_system_name(bld_server_conn, lab_cfg_path)
        log.info(lab_name)
        args.lab_name = lab_name
        write_install_vars(args)

    installer_exit.lab_name = lab_name

    if tis_on_tis:
        guest_load_path = "{}/{}".format(DEFAULT_WKSPCE, guest_bld_dir)
        tis_on_tis_info = {'cumulus_userid': USERNAME,
                           'cumulus_password': PASSWORD,
                           'userid': USERNAME,
                           'password': PASSWORD,
                           'server': CUMULUS_SERVER,
                           'log': log, 'bld_server_conn': bld_server_conn,
                           'load_path': load_path,
                           'guest_load_path': guest_load_path,
                           'output_dir': install_output_dir,
                           'lab_cfg_path': lab_cfg_path}

        cumulus = Cumulus_TiS(**tis_on_tis_info)

    if tis_on_tis:
        controller_dict = create_cumulus_node_dict((0, 1), CONTROLLER)
        compute_dict = create_cumulus_node_dict(range(0, cumulus.get_number_of_computes()), COMPUTE)
        storage_dict = create_cumulus_node_dict(range(0, cumulus.get_number_of_storages()), STORAGE)
        if storage_dict:
            lab_type = 'storage'
        else:
            lab_type = 'regular'
    else:
        controller_dict = create_node_dict(controller_nodes, CONTROLLER)

    global controller0
    controller0 = controller_dict[CONTROLLER0]

    # Due to simplex labs and unofficial config ip28-30
    if len(controller_dict) > 1:
        global controller1
        controller1 = controller_dict[CONTROLLER1]

    if compute_nodes is not None:
        compute_dict = create_node_dict(compute_nodes, COMPUTE)

    if storage_nodes is not None:
        storage_dict = create_node_dict(storage_nodes, STORAGE)

    '''
    If we are doing a regular tuxlab or tuxlab2 install then set the feed
    If we find the --iso-install flag then skip the feed setup on tuxlab and/or tuxlab2
    '''
    if not skip_feed and iso_install is False:
        executed = False
        # Lab-install Step 0 -  boot controller from tuxlab or usb or cumulus
        msg = 'Set_up_network_feed'
        lab_install_step = install_step(msg, 0, ['regular', 'storage', 'cpe', 'simplex'])
        if do_next_install_step(lab_type, lab_install_step):
            # if not executed:
            if str(boot_device_dict.get('controller-0')) != "USB" \
                    and not tis_on_tis:
                set_network_boot_feed(controller0.barcode, tuxlab_server,
                                      bld_server_conn, load_path, host_os,
                                      install_output_dir, tis_blds_dir,
                                      skip_pxebootcfg)
                set_install_step_complete(lab_install_step)
    else:
        log.info('Skipping setup of network feed on tuxlab: '.format(tuxlab_server))

    '''
    If detect that --iso-install flag was set then it'll be pxeboot install from
    yow-cgcs-tuxlab setup via pxeboot_setup.sh that is packaged with the TiS ISO image
    '''
    if "yow-cgcs-tuxlab" in tuxlab_server and iso_install is True:
        log.info('Feedpoint will be setup on {}'.format(tuxlab_server))
        log.info('copying ISO to {}'.format(tuxlab_server))

        # vlm targetID of controller-0
        c0_targetId = controller_nodes[0]
        # Now we need to mount the iso as root
        # sudo mount -o loop /tmp/bootimage.iso /media/iso
        # Check if node yow-cgcs-tuxlab host is accessible
        tuxlab_conn = SSHClient(log_path=install_output_dir + "/" + tuxlab_server + ".ssh.log")
        tuxlab_conn.connect(hostname=tuxlab_server, username=USERNAME,
                            password=PASSWORD)
        tuxlab_conn.deploy_ssh_key(PUBLIC_SSH_KEY)

        cmd = "sudo rm -rf /tmp/iso/{}; mkdir -p /tmp/iso/{}; sudo chmod -R 777 /tmp/iso/".format(c0_targetId,
                                                                                                  c0_targetId)
        if tuxlab_conn.exec_cmd(cmd, )[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        copy_iso(install_output_dir, tuxlab_server, bld_server_conn, load_path, iso_path, iso_host, c0_targetId)
        log.info('Latest bootimage.iso copied')

        cmd = "sudo chmod -R 777 /tmp/iso/".format(c0_targetId)
        if tuxlab_conn.exec_cmd(cmd, )[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "sudo umount /media/iso/{}; echo if we fail we ignore it".format(c0_targetId)
        if tuxlab_conn.exec_cmd(cmd, )[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "sudo rm -rf /media/iso/{}".format(c0_targetId)
        if tuxlab_conn.exec_cmd(cmd, )[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "mkdir -p /media/iso/{}".format(c0_targetId)
        if tuxlab_conn.exec_cmd(cmd, )[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "sudo mount -o loop /tmp/iso/{}/bootimage.iso /media/iso/{}".format(c0_targetId, c0_targetId)
        if tuxlab_conn.exec_cmd(cmd, )[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "sudo mount -o remount,exec,dev /media/iso/{}".format(c0_targetId)
        if tuxlab_conn.exec_cmd(cmd)[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "sudo rm -rf /export/pxeboot/pxeboot.cfg/{}".format(c0_targetId)
        if tuxlab_conn.exec_cmd(cmd)[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "/media/iso/{}/pxeboot_setup.sh -u http://128.224.150.110/umalab/{}  -t /export/pxeboot/pxeboot.cfg/{}".format(
            c0_targetId, c0_targetId, c0_targetId)
        if tuxlab_conn.exec_cmd(cmd)[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

        cmd = "sudo umount /media/iso/{}".format(c0_targetId)
        if tuxlab_conn.exec_cmd(cmd, )[0] != 0:
            msg = "failed to execute: {}".format(cmd)
            log.error(msg)
            wr_exit()._exit(1, msg)

    nodes = list(controller_dict.values()) + list(compute_dict.values()) + list(storage_dict.values())

    # Reserve the nodes via VLM
    # Unreserve first to close any opened telnet sessions.
    if not tis_on_tis:
        pre_opts = "sshpass -p '{0}'".format(WRSROOT_PASSWORD)
        [barcodes.append(node.barcode) for node in nodes]
        installer_exit.lab_barcodes = barcodes
        vlm_unreserve(barcodes)
        vlm_reserve(barcodes, note=INSTALLATION_RESERVE_NOTE)

        # Run the wipedisk utility if the nodes are accessible
        if wipedisk:
            wiped_nodes = []
            unwiped_nodes = []
            log.info("Attempting to wipe disks")
            # Reverse the list to wipe the controllers last
            for node in reversed(nodes):
                if node.telnet_conn is None:
                    try:
                        node.telnet_conn = open_telnet_session(node, install_output_dir)
                        node.telnet_conn.login()
                    except:
                        log.info("Unable to reach {}, will proceed with next node".format(node.name))
                        unwiped_nodes.append(node.name)
                        continue
                cmd = "sudo wipedisk"
                node.telnet_conn.write_line(cmd)
                try:
                    index = node.telnet_conn.expect([b"assword:", b"re you absolutely sure?"], TELNET_EXPECT_TIMEOUT)[0]
                except EOFError:
                    msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(node.telnet_ip,
                                                                                            node.telnet_port)
                    log.exception(msg)
                    log.info("Could not wipe {}'s disk, will proceed with next node".format(node.name))
                    unwiped_nodes.append(node.name)
                    continue
                if index == -1:
                    log.exception("Could not read {} terminal".format(node.name))
                    log.info("Could not wipe {}'s disk, will proceed with next node".format(node.name))
                    unwiped_nodes.append(node.name)
                    continue
                elif index == 0:
                    node.telnet_conn.write(str.encode(WRSROOT_PASSWORD + '\r\n'))
                    node.telnet_conn.get_read_until("re you absolutely sure?", 10)
                cmd = "y"
                node.telnet_conn.write(str.encode(cmd + '\r\n'))
                node.telnet_conn.get_read_until("ipediskscompletely", 10)
                cmd = "wipediskscompletely"
                node.telnet_conn.write(str.encode(cmd + '\r\n'))
                log.info("wiped {}'s disk".format(node.name))
                wiped_nodes.append(node.name)
            log.info("wipedisk complete. Succesfully wiped disks on: {}".format(wiped_nodes))
            if len(unwiped_nodes) > 0:
                log.info("failed to wipe disks on: {}".format(unwiped_nodes))

        # Power down all the nodes via VLM (note: this can also be done via board management control)
        if not continue_install:
            for barcode in barcodes:
                if burn_usb and (barcode == controller0.barcode):
                    log.info("Skip power down of controller0 and power on instead")
                    vlm_exec_cmd(VLM_TURNON, barcode)
                else:
                    vlm_exec_cmd(VLM_TURNOFF, barcode)

    if stop == "0":
        wr_exit()._exit(0, "User requested stop after {}".format(msg))

    # Lab-install -  boot controller from tuxlab or usb or cumulus
    msg = 'boot_controller-0'
    lab_install_step = install_step("boot_controller-0", 1, ['regular', 'storage', 'cpe', 'simplex'])

    executed = False
    # if not executed:
    if do_next_install_step(lab_type, lab_install_step):
        bringUpController(install_output_dir, bld_server_conn, load_path, patch_dir_paths, host_os,
                          boot_device_dict, small_footprint, burn_usb,
                          tis_on_tis, boot_usb, iso_path, iso_host, lowlat,
                          security, iso_install)
        set_install_step_complete(lab_install_step)

    if stop == "1":
        wr_exit()._exit(0, "User requested stop after {}".format(msg))

    # Lab-install -  Download lab configuration files - applicable all lab types
    msg = 'Download_lab_config_files'
    lab_install_step = install_step(msg, 2, ['regular', 'storage', 'cpe', 'simplex'])

    # establish ssh connection if not connected
    if controller0.ssh_conn is None:
        controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)

    executed = False
    if do_next_install_step(lab_type, lab_install_step):
        if prestage_load_path.find(TC_18_03_WKSPCE) > -1:
            downloadLabConfigFiles(lab_type, bld_server_conn, lab_cfg_path, prestage_load_path,
                                   guest_load_path, host_os, override, lab_cfg_location,
                                   TC_18_03_LAB_REL_PATH, TC_18_03_HEAT_TEMPLATE_PATH)
        elif prestage_load_path.find(TC_17_06_WKSPCE) > -1:
            downloadLabConfigFiles(lab_type, bld_server_conn, lab_cfg_path, prestage_load_path,
                                   guest_load_path, host_os, override, lab_cfg_location,
                                   TC_17_06_LAB_REL_PATH, TC_17_06_HEAT_TEMPLATE_PATH)
        elif prestage_load_path.find(TS_16_10_WKSPCE) > -1:
            downloadLabConfigFiles(lab_type, bld_server_conn, lab_cfg_path, prestage_load_path,
                                   guest_load_path, host_os, override, lab_cfg_location,
                                   TS_16_10_LAB_REL_PATH, TS_16_10_HEAT_TEMPLATE_PATH)
        elif prestage_load_path.find(TS_15_12_WKSPCE) > -1:
            downloadLabConfigFiles(lab_type, bld_server_conn, lab_cfg_path, prestage_load_path,
                                   guest_load_path, host_os, override, lab_cfg_location,
                                   TS_15_12_LAB_REL_PATH, TS_15_12_HEAT_TEMPLATE_PATH)
        else:
            downloadLabConfigFiles(lab_type, bld_server_conn, lab_cfg_path, load_path,
                                   guest_load_path, host_os, override, lab_cfg_location)
        set_install_step_complete(lab_install_step)

    if stop == "2":
        wr_exit()._exit(0, "User requested stop after {}".format(msg))

    # Lab-install -  Configure Controller - applicable all lab types
    msg = 'Configure_controller'
    lab_install_step = install_step(msg, 3, ['regular', 'storage', 'cpe', 'simplex'])

    if do_next_install_step(lab_type, lab_install_step):
        configureController(bld_server_conn, host_os, install_output_dir, banner, branding, config_region, kubernetes)
        # controller0.ssh_conn.disconnect()
        controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)
        # Depends on when we poll whether controller0 is offline or online
        # Starting in R5 - since the controller-0 is initially in locked state after
        # running config_controller there is a special case in AIO-direct where after
        # the initial unlock controller-0 will be in degraded state (which is valid)
        # AIO-direct controller-0 will only come online when controller-1 is powered on
        # Maybe just check if not available instead
        node_offline = test_state(controller0, AVAILABILITY, OFFLINE)
        node_online = test_state(controller0, AVAILABILITY, ONLINE)
        node_degraded = test_state(controller0, AVAILABILITY, DEGRADED)
        run_config_complete = True
        if node_online or node_offline or node_degraded:
            run_config_complete = False
            if "duplex-direct" in system_mode:
                wait_state(controller0, AVAILABILITY, "degraded|online")
            else:
                wait_state(controller0, AVAILABILITY, ONLINE)
            #if "duplex-direct" in system_mode:
            #    wait_state(controller0, AVAILABILITY, DEGRADED)
            #else:
            #    wait_state(controller0, AVAILABILITY, ONLINE)

            if ovs:
                cmd = "mv {} {}".format(LAB_SETUP_OVS, LAB_SETUP_CFG_FILENAME)
                rc, output = controller0.ssh_conn.exec_cmd(cmd)
                if rc != 0:
                    msg = "Failed to override avs lab_setup.conf"
                    log.error(msg)
                    wr_exit()._exit(1, msg)

            run_labsetup()
            # Test if the node is locked before attempting an unlock
            node_locked = test_state(controller0, ADMINISTRATIVE, LOCKED)
            if node_locked:
                unlock_node(nodes, selection_filter="controller-0", wait_done=False)
            controller0.ssh_conn.disconnect()
            time.sleep(60)
            controller0.telnet_conn.get_read_until(LOGIN_PROMPT, REBOOT_TIMEOUT)
            controller0.telnet_conn.login()
            controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)
            if "duplex-direct" in system_mode:
                wait_state(controller0, AVAILABILITY, DEGRADED)
            else:
                wait_state(controller0, AVAILABILITY, AVAILABLE)
        set_install_step_complete(lab_install_step)

        time.sleep(10)

    # Reconnect ssh session
    # controller0.ssh_conn.disconnect()
    # controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)
    cmd = "source /etc/nova/openrc"
    if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to source environment")

    cmd = "system alarm-list"
    rc, out = controller0.ssh_conn.exec_cmd(cmd)
    if rc == 2:
        log.info("Use fm alarm-list instead of system alarm-list")
        fm_alarm = True
    
    if fm_alarm:
        cmd = "touch .this_didnt_work"
        rc, output = controller0.ssh_conn.exec_cmd(cmd)
        if rc != 0:
            msg = "Failed to disable heat stacks"
            log.error(msg)
            wr_exit()._exit(1, msg)

    if stop == "3":
        wr_exit()._exit(0, "User requested stop after {}".format(msg))

    # Lab-install -  Bulk hosts add- applicable all lab types
    msg = 'bulk_hosts_add'
    lab_install_step = install_step("bulk_hosts_add", 4, ['regular', 'storage', 'cpe'])

    if do_next_install_step(lab_type, lab_install_step):
        if not tis_on_tis:
            bulkAddHosts()
            set_install_step_complete(lab_install_step)

    if stop == "4":
        wr_exit()._exit(0, "User requested stop after {}".format(msg))

    # Lab-install -  Bulk hosts add- applicable all lab types

    # Complete controller0 configuration either as a regular host
    # or a small footprint host.
    # Lab-install -  Run_lab_setup - applicable cpe labs only

    if not tis_blds_dir in older_rel:
        log.info("tis_blds_dir: {} not in older_rel: {}".format(tis_blds_dir, older_rel))
        lab_install_step = install_step("run_lab_setup", 5, ['cpe', 'simplex', 'storage'])
    else:
        lab_install_step = install_step("run_lab_setup", 5, ['cpe', 'simplex'])
    if do_next_install_step(lab_type, lab_install_step):
        # lab_setup.sh only be ran when hosts are online
        # TODO: below is a hack that ignores lab_setup failure - this makes the new istalls...
        run_labsetup(fail_ok=True)
        set_install_step_complete(lab_install_step)

    # Lab-install -  Bulk hosts add- applicable all lab types
    msg = 'bulk_hosts_add'
    lab_install_step = install_step("bulk_hosts_add", 41, ['regular', 'storage', 'cpe'])

    if do_next_install_step(lab_type, lab_install_step):
        if not tis_on_tis:
            bulkAddHosts()
            set_install_step_complete(lab_install_step)

    # Lab-install - cpe_compute_config_complete - applicable cpe labs only
    # system compute-config-complete is only applicable to R3 and R4
    # SW_VERSION="16.10 and SW_VERSION="17.06
    # if tis_blds_dir in older_rel:
    if run_config_complete:
        lab_install_step = install_step("cpe_compute_config_complete", 6, ['cpe', 'simplex'])
        if do_next_install_step(lab_type, lab_install_step):
            if small_footprint:
                run_cpe_compute_config_complete(host_os, install_output_dir)
                set_install_step_complete(lab_install_step)

    # Lab-install -  Run_lab_setup - applicable cpe labs only
    lab_install_step = install_step("run_lab_setup", 7, ['cpe', 'simplex'])
    if do_next_install_step(lab_type, lab_install_step):
        if small_footprint:
            # Run lab_setup again to setup controller-1 interfaces
            run_labsetup(fail_ok=True)

            log.info("Waiting for controller0 come online")
            wait_state(controller0, ADMINISTRATIVE, UNLOCKED)
            wait_state(controller0, OPERATIONAL, ENABLED)

            set_install_step_complete(lab_install_step)

    # Heat stack changes
    if host_os != "wrlinux":
        lab_install_step = install_step("check_heat_resources_file", 8, ['simplex'])
        if do_next_install_step(lab_type, lab_install_step):
            setupHeat(bld_server_conn)
            set_install_step_complete(lab_install_step)

    # Bring up other hosts
    tis_on_tis_storage = False
    # Lab-install -  boot_other_lab_hosts - applicable all labs
    msg = "boot_other_lab_hosts"
    lab_install_step = install_step(msg, 9, ['regular', 'storage', 'cpe'])
    if do_next_install_step(lab_type, lab_install_step):

        boot_other_lab_hosts(nodes, boot_device_dict, host_os, install_output_dir,
                             small_footprint, tis_on_tis)
        nodes.remove(controller0)
        if not simplex:
            time.sleep(10)
            wait_state(nodes, AVAILABILITY, ONLINE)
        set_install_step_complete(lab_install_step)

    if stop == "5":
        wr_exit()._exit(0, "User requested stop after {}".format(msg))

    # Lab-install -  run_lab_setup - applicable all labs
    lab_install_step = install_step("run_lab_setup", 10, ['regular', 'storage', 'cpe'])
    if do_next_install_step(lab_type, lab_install_step):
        log.info("Beginning lab setup procedure for {} lab".format(lab_type))

        run_labsetup()
        set_install_step_complete(lab_install_step)

    # Extra lab_setup.sh after cinder changes
    log.info("Beginning lab setup procedure for {} lab".format(lab_type))
    # Lab-install -  run_lab_setup - applicable regular and storage labs
    lab_install_step = install_step("run_lab_setup", 11, ['regular', 'storage'])
    if do_next_install_step(lab_type, lab_install_step):
        if lab_type is "regular" or "storage":
            # do run lab setup again
            # Run lab setup
            run_labsetup()

            set_install_step_complete(lab_install_step)

    # Unlock Controller-1
    # Lab-install -  unlock_controller1 - applicable all labs

    lab_install_step = install_step("unlock_controller1", 12, ['regular', 'storage', 'cpe'])
    if do_next_install_step(lab_type, lab_install_step):
        unlock_node(nodes, selection_filter="controller-1")
        set_install_step_complete(lab_install_step)

    # Wait until the following alarms clear
    # Service alarms (400.002) e.g directory-services, web-services, etc.
    # Configuration action is required to provision compute function (250.010)
    # drbd-sync (400.001)
    if lab_type is 'cpe':
        wait_until_alarm_clears(controller0, timeout=840, check_interval=60, alarm_id="400.002",
                                host_os=host_os, fm_alarm=fm_alarm)
        wait_until_alarm_clears(controller0, timeout=720, check_interval=60, alarm_id="250.010",
                                host_os=host_os, fm_alarm=fm_alarm)
        wait_until_alarm_clears(controller0, timeout=25200, check_interval=60, alarm_id="400.001",
                                host_os=host_os, fm_alarm=fm_alarm)

    # For storage lab run lab setup
    executed = False
    # Lab-install -  run_lab_setup - applicable storage labs
    lab_install_step = install_step("run_lab_setup", 13, ['storage'])
    if do_next_install_step(lab_type, lab_install_step):
        # if not executed:
        # do run lab setup to add osd
        run_labsetup()

        set_install_step_complete(lab_install_step)

    # Lab-install -  unlock_storages - applicable storage labs
    lab_install_step = install_step("unlock_storages", 14, ['storage'])
    if do_next_install_step(lab_type, lab_install_step):

        unlock_node(nodes, selection_filter="storage")
        storage_nodes = []
        for node in nodes:
            if "storage" in node.name:
                storage_nodes.append(node)
        wait_state(storage_nodes, OPERATIONAL, ENABLED)
        set_install_step_complete(lab_install_step)

    # After unlocking storage nodes, wait for ceph to come up
    if lab_type == 'storage':
        time.sleep(10)
        wait_until_alarm_clears(controller0, timeout=600, check_interval=60, alarm_id="800.001",
                                host_os=host_os, fm_alarm=fm_alarm)

    # Lab-install -  run_lab_setup - applicable storage labs
    lab_install_step = install_step("run_lab_setup", 15, ['storage'])
    if do_next_install_step(lab_type, lab_install_step):
        # ensure all computes are online first:
        computes = []
        for node in nodes:
            if "compute" in node.name:
                computes.append(node)
        wait_state(computes, AVAILABILITY, ONLINE)

        # do run lab setup to add osd
        run_labsetup()

        set_install_step_complete(lab_install_step)

    # Lab-install - unlock_computes - applicable storage and regular labs
    lab_install_step = install_step("unlock_computes", 16, ['regular', 'storage'])
    if do_next_install_step(lab_type, lab_install_step):
        unlock_node(nodes, selection_filter="compute")
        wait_state(nodes, OPERATIONAL, ENABLED)
        set_install_step_complete(lab_install_step)

    # Lab-install - run_lab_setup - applicable storage and regular labs
    lab_install_step = install_step("run_lab_setup", 17, ['regular', 'storage', 'cpe'])
    if do_next_install_step(lab_type, lab_install_step):
        # do run lab setup to add osd
        run_labsetup()

        set_install_step_complete(lab_install_step)

    # Heat stack changes
    if host_os != "wrlinux":
        lab_install_step = install_step("check_heat_resources_file", 18, ['cpe', 'regular', 'storage'])
        if do_next_install_step(lab_type, lab_install_step):
            setupHeat(bld_server_conn)
            if len(controller_dict) > 1:
                wait_state(controller1, AVAILABILITY, AVAILABLE)
            set_install_step_complete(lab_install_step)

    # Lab-install - swact and then lock/unlock controller-0 to complete setup
    lab_install_step = install_step("swact_lockunlock", 19, ['regular', 'storage'])
    if do_next_install_step(lab_type, lab_install_step):

        if host_os == "centos" and len(controller_dict) > 1:
            cmd = "system alarm-list --nowrap"
            if fm_alarm:
                cmd = "fm alarm-list --nowrap"
            output = controller0.ssh_conn.exec_cmd(cmd)[1]

            # Wait for degrade sysinv set to raise
            time.sleep(10)
            wait_until_alarm_clears(controller0, timeout=1200, check_interval=60, alarm_id="400.001",
                                    host_os=host_os, fm_alarm=fm_alarm)
            wait_until_alarm_clears(controller0, timeout=600, check_interval=60, alarm_id="800.001",
                                    host_os=host_os, fm_alarm=fm_alarm)

            if find_error_msg(output, "250.001"):
                log.info('Config out-of-date alarm is present')

                cmd = "system host-swact controller-0"
                rc, output = controller0.ssh_conn.exec_cmd(cmd)

                time.sleep(60)

                controller0.ssh_conn.disconnect()
                cont1_ssh_conn = SSHClient(log_path=install_output_dir + "/" + CONTROLLER1 + ".ssh.log")
                cont1_ssh_conn.connect(hostname=controller0.host_floating_ip,
                                       username=WRSROOT_USERNAME,
                                       password=WRSROOT_PASSWORD)
                controller1.ssh_conn = cont1_ssh_conn

                cmd = "source /etc/nova/openrc"
                if controller1.ssh_conn.exec_cmd(cmd)[0] != 0:
                    log.error("Failed to source environment")

                cmd = "system host-lock controller-0"
                rc, output = controller1.ssh_conn.exec_cmd(cmd)

                time.sleep(20)

                cmd = "system host-unlock controller-0"
                rc, output = controller1.ssh_conn.exec_cmd(cmd)

                # Wait until config out-of-date clears
                wait_until_alarm_clears(controller1, timeout=1200, check_interval=60, alarm_id="250.001",
                                        host_os=host_os, fm_alarm=fm_alarm)

                # Wait until sm-services are up
                wait_until_alarm_clears(controller1, timeout=600, check_interval=60, alarm_id="400.002",
                                        host_os=host_os, fm_alarm=fm_alarm)

                cmd = "system host-swact controller-1"
                rc, output = controller1.ssh_conn.exec_cmd(cmd)

                time.sleep(60)

                controller1.ssh_conn.disconnect()
                controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)

                set_install_step_complete(lab_install_step)

        # Required due to ip28-30 unsupported config
        elif host_os == "centos" and len(controller_dict) == 1:
            log.info("Skipping this step since we only have one controller")

    wait_until_alarm_clears(controller0, timeout=1200, check_interval=60, alarm_id="250.001",
                            host_os=host_os, fm_alarm=fm_alarm)

    if postinstall and host_os == "centos":
        run_postinstall(controller0)

    cmd = "source /etc/nova/openrc; system alarm-list"
    if fm_alarm:
        cmd = "source /etc/nova/openrc; fm alarm-list"
    if controller0.ssh_conn.exec_cmd(cmd)[0] != 0:
        log.error("Failed to get alarm list")

    cmd = "cat /etc/build.info"
    rc, installed_load_info = controller0.ssh_conn.exec_cmd(cmd)
    if rc != 0:
        log.error("Failed to get build info")

    if not (skip_pxebootcfg or iso_install):
        restore_pxeboot_cfg(controller0.barcode, tuxlab_server, install_output_dir)

    wr_exit()._exit(0, "Installer completed.\n" + installed_load_info)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        wr_exit()._exit(2, "Keyboard Interrupt Detected")
