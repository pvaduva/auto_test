#!/usr/bin/env python3.4

'''
lab_install.py - Script to install Titanium Server software load onto lab

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

'''

'''
modification history:
---------------------
16oct15,kav  Creation
'''

import os
import sys
import threading
import traceback
import textwrap
import argparse
import configparser
import pexpect
import pdb
from pprint import pprint
#from common.logUtils import *
#from common.classes import Host

# class is in non-standard location so refine python search path 
sys.path.append(os.path.expanduser('/home/ktiwari/wassp-repos/testcases/cgcs/cgcs2.0/common/py/'))

# Fix these imports to not all use * as that is not recommended
from CLI.cli import *
from CLI.install import *
from CLI.logUtils import *
from CLI.classes import *
from CLI.constants import *

#TODO: Move these into constants.py where applicable
NODE_INFO_DIR='node_info'
LAB_SETTINGS_DIR='lab_settings'
LATEST_BUILD_DIR='latest_build'
LOG_LEVELS=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
LOGGER_NAME = os.path.splitext(os.path.basename(__file__))[0]

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
                         help="Tuxlab server with feed"
                         " directory for controller-0"
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
    other_grp.add_argument('--log-level', dest='log_level', choices=LOG_LEVELS,
                           default='DEBUG', help="Logging level (default: %(default)s)")
    other_grp.add_argument('-h','--help', action='help',
                           help="Show this help message and exit")

    args = parser.parse_args()
    return args

def prepare_for_install(node):
#    wipe_disk(node)
    exec_vlm_action(action=VLM_TURNOFF, barcodes=[node.barcode])

def create_node_dict(nodes, node_type):
    node_dict = {}
    i = 0
    
    for node in nodes:
        print('going through ' + node)
        config = configparser.ConfigParser()
        try:
            node_filepath = NODE_INFO_DIR + '/{}.ini'.format(node)
            node_file = open(node_filepath, 'r')
            config.readfp(node_file)
        except Exception:
            log.exception('Failed to read \"{}\"'.format(node_filepath))
            sys.exit(1)

        node_info_dict = {}
        for section in config.sections():
#            print('section = ' + section)
#            print ('options =' + str(config.options(section)))
            for opt in config.items(section):
                key, value = opt
                node_info_dict[section + '_' + key] = value
        name = node_type + "-{}".format(i)
        node_info_dict['name'] = name
        node_info_dict['type'] = type
        node_info_dict['barcode'] = node

        node_dict[name]=Host(**node_info_dict)
        print('Storing host: \n' + str(node_dict[name]) + "\n")
        i += 1

    return node_dict

# Expects first response to be success strings (can be ORed), last one as timeout, and
# all others as error strings
#def parse_expect_response(response, *expect_list):
#    for index in range(len(expect_list)):
#        if reponse == index:

# TODO: Find better way to map expect_list to response, possibly have another list that says if they are success or failures
    
#    print("resp = " + str(response))
#    if resp == 0:
#        log.error("Failed to cd to " + barcode_dir + ":" + error_msg)
#        sys.exit(1)

def action1():
    print("got prompt")
def action2():
    print("got error")
def action3(connection=None):
    print("got timeout")
    sys.exit(1)

def get_match(connection):
    print("match = " + connection.match.group().strip())
    return connection.match.group().strip()

#TODO: Rename this function as it is confusing
#TODO: See if you want to catch a timeout exception instead of having pexpect.TIMOUT in the event list, that way you wouldn't need a list - just have one thing to match
#Might want to use expect_list passing it a compiled list to speed things up if there will be loops
def expect(conn, dicts, exact=False):
    dicts.append({pexpect.TIMEOUT: action3})
    mylist = list(map(lambda x: list(x.keys())[0], dicts))
    try:
        if exact:
            response = conn.expect_exact(mylist)
        else:
            response = conn.expect(mylist)
    except EOFError:
        log.exception("Child has died or all output read")

    print("response = " + str(response))
#    print(list(dicts[response].values())[0])
    return list(dicts[response].values())[0](connection=conn)

def dbg(val):
    print("val: " + str(val))

#TODO: Perhaps pass timeout value other than default for expect and match prompt?
#TODO: What about moving match_prompt out of this so it is done on a case-by-case basis?
def sendline_get_rc(conn, cmd):
    conn.sendline(cmd + "; echo $?")
    rc = int(expect(conn, [ {"\r\n\d+\r\n": get_match} ])) #\r\n is required for pexpect to see end-of-line, also need to surround with newlines to avoid date-timestamp that lab machines output after each command (e.g. Fri Nov  6 20:15:15 UTC 2015) to get captured
    match_prompt(conn)
    return rc

def run_cmd(conn, cmd):
    log.info("Executing: " + cmd + "\n")
    conn.sendline(cmd)
    match_prompt(conn)
    after = get_after(conn)
    rc = get_rc(conn)
    log.info("Output:\n" + after)
    log.info("Return code: " + str(rc))
    return after

def get_rc(conn):
    conn.sendline("echo $?")
    rc = int(expect(conn, [ {"\r\n\d+\r\n": get_match} ])) #\r\n is required for pexpect to see end-of-line, also need to surround with newlines to avoid date-timestamp that lab machines output after each command (e.g. Fri Nov  6 20:15:15 UTC 2015) to get captured
    match_prompt(conn)
    return rc

# Can only use on LOCAL machine (e.g. yow-cgcs-test) as does not use ssh info provided in pxssh connection
def run_local_cmd(cmd, tmout=10):
    print("command = " + cmd)
    (command_output, rc) = pexpect.run(cmd, withexitstatus=1, timeout=tmout)
    if rc == 0:
        print("exit status is zero")
    else:
        print("exit status is not zero")
    print("command_output:\n" + command_output.decode())
    print("\nrc: " + str(rc))
    return (command_output, rc)

def set_network_boot_feed(barcode, tuxlab_server, bld_server_conn, load_path, bld_dir): #, bld_wkspce, blds_dir, bld_dir):
    tuxlab_sub_dir = SCP_USERNAME + '/' + bld_dir
    # Establish connection
    conn = Session(timeout=TIMEOUT)

    conn.connect(hostname=tuxlab_server, username=SCP_USERNAME, password=SCP_PASSWORD)
    conn.setecho(ECHO)
#    conn.logfile = sys.stdout

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + "/" + barcode
    error_msg = "No such file or directory"
    conn.sendline("cd " + tuxlab_barcode_dir)
    if not conn.prompt(): expect(conn, [ {error_msg: action2} ], exact=True)

    feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir

    dbg(feed_path)
#    conn.sendline("readlink " + feed_path)
#    expect_action_dict_list = [ {SCP_USERNAME +  "\/\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}": get_match} ]
#    feed_dir = expect(conn, expect_action_dict_list)
    rc = sendline_get_rc(conn, "test -d " + tuxlab_sub_dir)
#    conn.sendline("test -d " + tuxlab_sub_dir + "; echo $?")
#    rc = int(expect(conn, [ {"\d\r\n": get_match} ]))
    if rc != 0:
        conn.sendline("mkdir -p " + tuxlab_sub_dir)
        match_prompt(conn)
        conn.sendline("chmod 755 " + tuxlab_sub_dir)
        match_prompt(conn)
        bld_server_conn.sendline("rsync -a --delete " + load_path + "/export/RPM_INSTALL/ " + tuxlab_server + ":" + feed_path)
        match_prompt(bld_server_conn, tmout=60)#bld_server_conn.prompt(timeout=60)

        bld_server_conn.sendline("cd " + load_path)
        match_prompt(bld_server_conn)

#        pdb.set_trace()

        bld_server_conn.sendline("scp extra_cfgs/yow* " + SCP_USERNAME + "@" + tuxlab_server + ":" + feed_path)
        match_prompt(bld_server_conn, tmout=60)
        print("\nbefore =\n" + bld_server_conn.before)
        print("\n\n")
        print("\nafter =\n" + bld_server_conn.after) #TODO: Can just print the commands before and then print the after
        print("\n\n")
        bld_server_conn.sendline("scp export/RPM_INSTALL/boot/isolinux/vmlinuz " + SCP_USERNAME + "@" + tuxlab_server + ":" + feed_path)
        match_prompt(bld_server_conn, tmout=60)
        bld_server_conn.sendline("scp export/RPM_INSTALL/boot/isolinux/initrd " + SCP_USERNAME + "@" + tuxlab_server + ":" + feed_path + "/initrd.img")
        match_prompt(bld_server_conn, tmout=60)
    else:
        log.info("Build directory \"{}\" already exists".format(tuxlab_sub_dir))

    conn.sendline("rm -f feed")
    match_prompt(conn)
    conn.sendline("ln -v -s " + tuxlab_sub_dir + " feed")
    match_prompt(conn)

    #    expect_list = [PROMPT, error_msg, pexpect.TIMEOUT]
    #    response = conn.expect_exact(expect_list)

    # Terminate connection
    conn.logout()

def exec_sudo_cmd(conn, cmd):
    conn.sendline(conn, "sudo " + cmd)
    telnet_read_until(conn, PASSWORD_PROMPT, 10)
#    resp_pwd = conn.read_until(b"Password:", 10)
#    if not resp_pwd:
#        msg = "Password prompt not found"
#        log.error(msg)
#        exit(1)
    telnet_write(conn, PASSWORD)

def deploy_key(conn, host_ip):
    SSH_KEY_PATH = "~/.ssh/id_rsa.pub"
    try:
        ssh_key = (open(os.path.expanduser(SSH_KEY_PATH)).read()).rstrip()
    except FileNotFoundError:
        log.exception("User must have a public key {} defined!".format(SSH_KEY_PATH))
        sys.exit(1)

    conn.sendline("mkdir -p ~/.ssh/")
    rc = sendline_get_rc(conn, 'grep -q "{}" ~/.ssh/authorized_keys'.format(ssh_key))
    if rc != 0:
        conn.sendline('echo -e "{}\n" >> ~/.ssh/authorized_keys'.format(ssh_key))
        conn.sendline("chmod 700 ~/.ssh/ && chmod 644 ~/.ssh/authorized_keys")

def match_prompt(conn, tmout=None):
    if tmout == None:
        matched = conn.prompt()
    else:
        matched = conn.prompt(timeout=tmout)

    if not matched:
        log.error("Failed to match the prompt!")
        sys.exit(1)

def get_after(conn):
    after = conn.after
    if after is pexpect.exceptions.TIMEOUT:
        log.exception("Timeout occurred! Failed to retrieve text after executing command!")
        sys.exit(1)
    print("after === " + after)
    return "\n".join(after.splitlines()[1:-1]) # Do not include command executed or prompt string in list

def look_for_error(output):
    if re.search("error", output, re.IGNORECASE):
        log.error("Found error in output!:\n" + output)
        sys.exit(1)

def apply_patches(tn_conn, host_ip, bld_server, bld_server_conn, patch_dir_paths):

    patch_names = []
    for dir_path in patch_dir_paths.split(","):
        # check if load_path exists
        rc = sendline_get_rc(bld_server_conn, "test -d " + dir_path)
        if rc != 0:
            log.error("Patch directory path {}:{} does not exist!".format(bld_server, dir_path))
            sys.exit(1)

#        match_prompt(bld_server_conn) # <-- need to consume prompt from sendline_get_rc, DOING THIS IN THE FUNCTION ITSELF NOW
        print("command = " + "cd " + dir_path + " && ls *.patch")
        bld_server_conn.sendline("cd " + dir_path)
        match_prompt(bld_server_conn)
#        print("before = " + str(bld_server_conn.before))
#        print("after = " + str(bld_server_conn.after))
        bld_server_conn.sendline("ls -1 *.patch")
        match_prompt(bld_server_conn)
        after = get_after(bld_server_conn).splitlines()
        print("after = " + str(after))
        for item in after:
            patch_name = os.path.splitext(item)[0]
            print("patch name = " + patch_name)
            patch_names.append(patch_name)

#        bld_server_conn.prompt() # <-- can simulate timeout by adding extra unexpected prompt
# BEFORE IS EMPTY BECAUSE WAS CONSUMED BY PROMPT() CALL

    print("patches found: " + str(patch_names))

    log.info("Executing: " + 'rsync -ave "ssh -o StrictHostKeyChecking=no" ' + dir_path + "/" + " " + USERNAME + "@" + host_ip + ":" + PATCHES_DIR)
    bld_server_conn.sendline('rsync -ave "ssh -o StrictHostKeyChecking=no" ' + dir_path + "/" + " " + USERNAME + "@" + host_ip + ":" + PATCHES_DIR)
    match_prompt(bld_server_conn)
    print("\nafter =\n" + str(bld_server_conn.after)) #TODO: Can just print the commands before and then print the after

    print("executing: " + "echo " + PASSWORD + " | sudo -S sw-patch query")
    telnet_write(tn_conn, "echo " + PASSWORD + " | sudo -S sw-patch query")
    resp = telnet_read_until(tn_conn, PROMPT, 10)
    print("Output:\n" + resp)
    telnet_write(tn_conn, "echo ${PASSWORD} | sudo -S sw-patch upload-dir " + PATCHES_DIR)
    resp = telnet_read_until(tn_conn, PROMPT, 10)
    print("Output:\n" + resp)
    look_for_error(resp)

    telnet_write(tn_conn, "echo ${PASSWORD} | sudo -S sw-patch query")
    resp = telnet_read_until(tn_conn, PROMPT, 10)
    print("Output:\n" + resp)
    valid_states = "(Available|Partial-Apply)"
    for patch in patch_names:
        print("patch name = " + patch)
        if not re.search("{}\s+{}".format(patch, valid_states), resp, re.MULTILINE):
            log.error("Patch {} is not in the patch list/not in a valid state: {}".format(patch, valid_states))
            sys.exit(1)

    telnet_write(tn_conn, "echo ${PASSWORD} | sudo -S sw-patch apply --all")
    resp = telnet_read_until(tn_conn, PROMPT, 10)
    print("Output:\n" + resp)
    telnet_write(tn_conn, "echo ${PASSWORD} | sudo -S sw-patch install-local")
    resp = telnet_read_until(tn_conn, PROMPT, 10)
    print("Output:\n" + resp)
    telnet_write(tn_conn, "echo ${PASSWORD} | sudo -S sw patch-query")
    resp = telnet_read_until(tn_conn, PROMPT, 10)
    print("Output:\n" + resp)
    telnet_write(tn_conn, "echo ${PASSWORD} | sudo -S reboot")
    telnet_read_until(tn_conn, LOGIN_PROMPT, 1000)
    sys.exit(0)

    tn_conn.close()

#Con1 TYPE rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ${EXECUTOR}@${BUILDSERVER}:/folk/cwinnick/ceilometer_host_patch.1.patch ${WRSDIR}/patches\n
#Con1 TYPE rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ${EXECUTOR}@${BUILDSERVER}:/folk/cgts/patches-to-verify/15.04/TS_HP_15.04_PATCH_0001.patch ${HOME_DIR}/patches\n

def wipe_disk(node):
    print("telnet ip = " + node.telnet_ip)
    print("telnet port = " + node.telnet_port)
    conn = telnet_conn(node.telnet_ip, int(node.telnet_port))
    conn.write(b"\n")

    telnet_login(conn)

# -k option forces sudo to ask for password again
#TODO: Enhance to support not requiring password if within time limit
#        conn.write("sudo wipedisk\n")
#        try:
#            resp = conn.expect(["assword:", "\[y\/n\]"], 10)
#        except EOFError as err:
#            log.error("Error occurred!")
#        resp_index, resp_match, output = resp
#        if resp_index == 0:
#            print("resp_pwd = \n" + str(resp_match.group(0)))
#            conn.write(PASSWORD + "\n")
#            resp_wipe = conn.read_until("\[y\/n\]", 10) #\? \[y\/n\]"
#            print("resp_wipe =\n" + resp_wipe)
#        elif resp_index == 2:
#            print("resp = " + str(resp) + " Timeout occurred! Didn't find expected strings...")
#        else: #-1 Otherwise, when nothing matches, return (-1, None, text) where text is the text received so far (may be the empty string if a timeout happened).
#            print("Nothing matched")

    telnet_write(conn, "sudo -k wipedisk")
#    conn.write(b"sudo -k wipedisk\n")
    telnet_read_until(conn, PASSWORD_PROMPT, 10)
#    resp_pwd = conn.read_until(b"Password:", 10)
#    if not resp_pwd:
#        msg = "Password prompt not found"
#        log.error(msg)
#        exit(1)
    telnet_write(conn, PASSWORD)
#    conn.write(str.encode(PASSWORD + "\n"))

    resp_wipe = telnet_read_until(conn, "\[y\/n\]", 10)
    print("resp_wipe =\n" + resp_wipe)
#    resp_wipe = conn.read_until(b"\[y\/n\]", 10) #\? \[y\/n\]"
#    print("resp_wipe =\n" + resp_wipe.decode('utf-8'))

    telnet_write(conn, "y")
#    conn.write(b"y\n")
    resp_confirm = telnet_read_until(conn, "confirm", 10)
    print("resp_confirm =\n" + resp_confirm)
#    resp_confirm = conn.read_until(b"confirm:", 10)
#    print("resp_confirm =\n" + resp_confirm.decode('utf-8'))

    telnet_write(conn, "wipediskscompletely")
#    conn.write(str.encode("wipediskscompletely\n"))

    resp_final = telnet_read_until(conn, "The disk(s) have been wiped.", 10)
    print("resp_final =\n" + resp_final)
#    resp_final = conn.read_until(b"The disk(s) have been wiped.", 10)
#    print("resp_final =\n" + resp_final.decode('utf-8'))

#    conn.write(b"exit\n")
    conn.close() # Must close connection for read_all() to not hang, so it can find EOF

    #TODO: Figure out why this doens't print all output
    print(conn.read_all())

if __name__ == '__main__':
    custom_lab_setup = False
    lab_settings_filepath = ""
    node_boot_devices_dict = DEFAULT_BOOT_DEVICES

    args = parse_args()

    log = getLogger(LOGGER_NAME, args.log_level) #setLogger(log, args.log_level)

    lab_config_location = args.lab_config_location

    controller_nodes = tuple(args.controller.split(','))
    compute_nodes = tuple(args.compute.split(','))

    if args.storage != None:
        storage_nodes = tuple(args.storage.split(','))
    else:
        storage_nodes = None

    tuxlab_server = args.tuxlab_server
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

    print_step("Arguments: ")
    print_arg("Lab config location", lab_config_location)
    print_arg("Controller", controller_nodes)
    print_arg("Compute", compute_nodes)
    print_arg("Storage", storage_nodes)
    print_arg("Run lab setup", run_lab_setup)
    print_arg("Tuxlab server:", tuxlab_server)
    print_arg("Small footprint", small_footprint)
    print_arg("Build server", bld_server)
    print_arg("Build server workspace", bld_server_wkspce)
    print_arg("TiS builds directory", tis_blds_dir)
    print_arg("TiS build directory", tis_bld_dir)
    print_arg("Guest build directory", guest_bld_dir)
    print_arg("Patch directory paths", patch_dir_paths)
    print_arg("Output directory", output_dir)
    print_arg("Log level", log_level)

    controller_dict = create_node_dict(controller_nodes, CONTROLLER)
    compute_dict = create_node_dict(compute_nodes, COMPUTE)
    storage_dict = {}
    if storage_nodes is not None:
        storage_dict = create_node_dict(storage_nodes, STORAGE)

    print("telnet ip = " + controller_dict[CONTROLLER0].telnet_ip)
    print("telnet port = " + controller_dict[CONTROLLER0].telnet_port)
    conn = telnet_conn(controller_dict[CONTROLLER0].telnet_ip, int(controller_dict[CONTROLLER0].telnet_port))

    conn.write(b"\n")

    telnet_read_until(conn, PASSWORD_PROMPT, 420)

#fout = open('mylog.txt','wb')
#child.logfile = fout
#    build_server_conn.logfile = sys.stdout
#    build_server_conn.logfile_send = fout
#    build_server_conn.logfile_read = fout2

    bld_server_conn = Session(timeout=TIMEOUT)
    bld_server_conn.connect(hostname=bld_server, username=SCP_USERNAME, password=SCP_PASSWORD)
    bld_server_conn.setecho(ECHO)
#    build_server_conn.logfile = sys.stdout

#    print("telnet ip = " + controller_dict[CONTROLLER0].telnet_ip)
#    print("telnet port = " + controller_dict[CONTROLLER0].telnet_port)
#    conn = telnet_conn(controller_dict[CONTROLLER0].telnet_ip, int(controller_dict[CONTROLLER0].telnet_port))
#    conn.write(b"\n")
#    telnet_login(conn)

    load_path = "{}/{}".format(bld_server_wkspce, tis_blds_dir)
    if tis_bld_dir == LATEST_BUILD_DIR:
        bld_server_conn.sendline("readlink " + load_path + "/" + LATEST_BUILD_DIR)
        expect_action_dicts = [ {"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}": get_match} ]
        tis_bld_dir = expect(bld_server_conn, expect_action_dicts)

    load_path += "/" + tis_bld_dir
    print("load path = " + load_path)

    # check if load_path exists
    rc = sendline_get_rc(bld_server_conn, "test -d " + load_path)
    if rc != 0:
        log.error("Load path {}:{} does not exist!".format(bld_server, load_path))

    found_bulk_config_file = False
    found_lab_settings_file = False

    lab_config_path = lab_config_location
    if os.path.isdir(lab_config_path):
        custom_lab_setup = True
        for file in os.listdir(lab_config_location):
            print("file = " + file)
            if file == BULK_CONFIG_FILENAME:
                found_bulk_config_file = True
            if file == CUSTOM_LAB_SETTINGS_FILENAME:
                found_lab_settings_file = True

        if not found_bulk_config_file:
            log.error('Failed to find \"{}\" under {}'.format(BULK_CONFIG_FILENAME, lab_config_path))
        if found_lab_settings_file:
            lab_settings_filepath = lab_config_path + "/" + CUSTOM_LAB_SETTINGS_FILENAME
    else:
        lab_config_rel_path = LAB_YOW_REL_PATH + "/" + lab_config_location
        lab_config_path = load_path + "/" + lab_config_rel_path
        rc = sendline_get_rc(bld_server_conn, "test -d " + lab_config_path)
        if rc != 0:
            log.error('Lab config directory "{}" does not exist'.format(lab_config_rel_path))
            sys.exit(1)

        lab_settings_filename = LAB_SETTINGS_DIR + "/{}.ini".format(lab_config_location)
        if os.path.isfile(lab_settings_filename):
            print("found lab settings filename = " + lab_settings_filename)
            lab_settings_filepath = os.path.dirname(__file__) + "/" + lab_settings_filename

    print("lab_settings_filepath = " + lab_settings_filepath)

    #TODO: Handle special case where if lab name is PV0 - see lab_settings/yow-cgcs-pv0.ini
    if lab_settings_filepath:
        # read config file from path
        config = configparser.ConfigParser()
        try:
            lab_settings_file = open(lab_settings_filepath, 'r')
            config.read_file(lab_settings_file)
        except Exception:
            log.exception("Failed to read file " + lab_settings_file)
            sys.exit(1)

        #TODO: Read this back in labinstall.py and save this info to a dictionary
        #TODO: Define global dictionary with defaults

        try:
            node_boot_devices_dict = config.items("Boot_Devices")
        except configparser.NoSectionError:
            pass

    print(node_boot_devices_dict)

#    set_network_boot_feed(controller_dict[CONTROLLER0].barcode, tuxlab_server, bld_server_conn, load_path, tis_bld_dir) #bld_server_wkspce, tis_blds_dir, bld_dir=tis_bld_dir)

    nodes = list(controller_dict.values()) + list(compute_dict.values()) + list(storage_dict.values())

    barcodes = []
    [barcodes.append(node.barcode) for node in nodes]
    print("barcodes = " + str(barcodes))
#    res = exec_vlm_action(VLM_RESERVE, barcodes,note="Lab Installation")

    threads = []
    for node in nodes:
        print("node = " + str(node) + "\n")
#        node_thread = threading.Thread(target=prepare_for_install,name=node.name,args=(node,))
#        threads.append(node_thread)
#        log.info("Starting {}".format(node_thread.name))
#        node_thread.start()

#    for thread in threads:
#        thread.join()

    res = exec_vlm_action(VLM_REBOOT, [controller_dict[CONTROLLER0].barcode])

    print("telnet ip = " + controller_dict[CONTROLLER0].telnet_ip)
    print("telnet port = " + controller_dict[CONTROLLER0].telnet_port)
    conn = telnet_conn(controller_dict[CONTROLLER0].telnet_ip, int(controller_dict[CONTROLLER0].telnet_port))

    res = telnet_biosboot(conn, controller_dict[CONTROLLER0].name, node_boot_devices_dict)
    print("result = " + str(res))
    sys.exit(0)

    cont_conn = Session(timeout=TIMEOUT)
    cont_conn.connect(hostname=host_ip, username=USERNAME, password=PASSWORD)
    cont_conn.setecho(ECHO)

    deploy_key(cont_conn, controller_dict[CONTROLLER0].host_ip)
    if patch_dir_paths != None:
        # Closing as need to re-open it as the server will get rebooted after the patch is applied
        # Terminate connection
        cont_conn.logout()
        cont_conn.close()
        apply_patches(bld_server, bld_server_conn, patch_dir_paths)
        cont_conn = Session(timeout=TIMEOUT)
        cont_conn.connect(hostname=host_ip, username=USERNAME, password=PASSWORD)
        cont_conn.setecho(ECHO)

    if custom_lab_setup is False:
        dir_path = load_path + LAB_YOW_REL_PATH
    log.info("Executing: " + 'rsync -ave "ssh {} "'.format(RSYNC_SSH_OPTIONS) + dir_path + "/*" + " " + USERNAME + "@" + host_ip + ":" + PATCHES_DIR)
    bld_server_conn.sendline('rsync -ave "ssh {} "'.format(RSYNC_SSH_OPTIONS) + dir_path + "/*" + " " + USERNAME + "@" + host_ip + ":" + PATCHES_DIR)

    #TEST
#    host_ip = controller_dict[CONTROLLER0].host_ip
#    cont_conn = Session(timeout=TIMEOUT)
#    cont_conn.connect(hostname=host_ip, username=USERNAME, password=PASSWORD)
#    cont_conn.setecho(ECHO)
#
#    deploy_key(cont_conn, host_ip)

    run_cmd(bld_server_conn, 'rsync -ave "ssh {}" '.format(RSYNC_SSH_OPTIONS) + LICENSE_FILE + " " + USERNAME + "@" + host_ip + ":" + HOME_DIR + "/license.lic")
    if custom_lab_setup is False:
        run_cmd(bld_server_conn, 'rsync -ave "ssh {}" '.format(RSYNC_SSH_OPTIONS) + lab_config_path + "/*" + " " + USERNAME + "@" + host_ip + ":" + HOME_DIR)
#        log.info("Executing: " + 'rsync -ave "ssh {}" '.format(RSYNC_SSH_OPTIONS) + lab_config_path + "/*" + " " + USERNAME + "@" + host_ip + ":" + HOME_DIR)
#        bld_server_conn.sendline('rsync -ave "ssh {}" '.format(RSYNC_SSH_OPTIONS) + lab_config_path + "/*" + " " + USERNAME + "@" + host_ip + ":" + HOME_DIR)
#        match_prompt(bld_server_conn)
#        print("\nafter =\n" + str(bld_server_conn.after)) #TODO: Can just print the commands before and then print the after
#        bld_server_conn.sendline("echo $?")
#        match_prompt(bld_server_conn)
#        print("\nafter =\n" + str(bld_server_conn.after)) #TODO: Can just print the commands before and then print the after

    run_cmd(cont_conn, 'grep -q "TMOUT=" ' + WRSROOT_ETC_PROFILE + ' && echo li69nux | sudo -S sed -i.bkp "/\(TMOUT=\|export TMOUT\)/d" ' + WRSROOT_ETC_PROFILE)
    run_cmd(cont_conn, 'echo li69nux | sudo -S sed -i.bkp "$ a\TMOUT=\\nexport TMOUT" ' + WRSROOT_ETC_PROFILE)

    run_cmd(cont_conn, 'export HISTTIMEFORMAT="%Y-%m-%d %T " >> ' + HOME_DIR + "/.bashrc")
    run_cmd(cont_conn, 'export PROMPT_COMMAND="date; $$PROMPT_COMMAND" >> ' + HOME_DIR + "/.bashrc")

    sys.exit(0)


# controller-0 must be rebooted before proceeding with config_controller

#TYPE export TMOUT=\n
#TYPE sed -i.bkp "s/TMOUT=900/TMOUT=/g" /etc/profile\n

# import and install the license file
#CALL  python3 ${WASSP_TESTCASE_BASE}/utils/sendFile.py -i $env.NODE.target.Boot.oamAddrA -u ${WRSUSER} -p ${WRSPASS} -s /folk/cgts/lab/TiS15-GA-demo.lic -d ${WRSDIR} -P 22
#TYPE mv -f ${WRSDIR}/TiS15-GA-demo.lic ${WRSDIR}/license.lic\n

#rough code: rsync -avz "$firstfile" "$secondfile"

# MOVE THIS TO BEFORE CONFIG_CONTROLLER GETS CALLED, AS BETTER TO COPY SYSTEM_CONFIG, BULK_ADD FILE, ETC. ALL AT ONCE
# Copy lab setup config for specific lab - as defined by labsetup variable contained in the target ini file
#TYPE rsync -av -e 'ssh -o ConnectTimeout=20 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ${EXECUTOR}@$BUILDSERVER:${JKPATH}${LOADPATH}/latest_build/layers/wr-cgcs/cgcs/extras.ND/lab/yow/$env.NODE.target.Boot.labsetup/* ${WRSDIR}/ \n
#WAIT 20 SEC {ignoreTimeout:True}

#FAILIF Configuration failed
#    TYPE sudo config_controller --config-file system_config\n
#    WAIT 30 MIN {ignoreTimeout:True} .*:~\$

#TYPE source /etc/nova/openrc \n
#WAIT 99 SEC

#TYPE system host-bulk-add hosts_bulk_add.xml\n
#WAIT 90 MIN Success

#TYPE nova service-list\n
#WAIT 30 SEC
#TYPE system alarm-list\n
#WAIT 30 SEC

#TYPE sudo sm-dump\n
#DELAY 3 SEC
#TYPE ${WRSPASS}\n
#WAIT 30 SEC

# CAN POSSIBLY COPY FILES OVER WHILE CONFIG_CONTROLLER IS RUNNING? WOULD NEED ANOTHER SSH CONNECTION OR USE TELNET
# include file to copy images, support scripts and whatever else we need
#INCLUDE ${WASSP_RUNTIMECONFIGS_BASE}/cp_support_files.frag

#TYPE nova keypair-add --pub_key ~/.ssh/id_rsa.pub controller-0\n
#WAIT 30 SEC
#DELAY 5 SEC

#TYPE chmod -R 777 ~/bin/ \n
#WAIT 3 SEC

sys.exit(0)