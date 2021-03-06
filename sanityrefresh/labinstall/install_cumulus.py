
#!/usr/bin/env python3.4

'''
install_cumulus.py - Installs Titanium Server load on TiS configuration.

Copyright (c) 2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
'''


import os
import time
from constants import *
from utils.ssh import SSHClient
from utils.common import create_node_dict, wr_exit, exec_cmd
from utils.classes import Host
import pexpect


def create_cumulus_node_dict(nodes, personality):

    node_dict = {}

    for node in nodes:
        node_info_dict = {}
        name = personality + "-{}".format(node)
        node_info_dict['name'] = name
        node_info_dict['personality'] = personality
        node_info_dict['barcode'] = "tis_on_tis"
        node_dict[name]=Host(**node_info_dict)
    return node_dict



class Cumulus_TiS(object):
    """Cumulus TIS Tenanat representation.

    Cumulus_TiS contains various attributes such as IP address, hostname, etc.,
    and methods to execute various functions on the host (e.g. ping, ps, etc.).

    """

    def __init__(self, **kwargs):
        """Returns custom logger for module with assigned level."""


        self.userid = None
        self.password = None
        self.server = None
        self.ssh_conn = None
        self.floating_ips = []
        self.log = None
        self.bld_server_conn = None
        self.load_path = None
        self.guest_load_path = None
        self.output_dir = None
        self.lab_cfg_path = None
        self.cumulus_options = None
        self.storage = False
        self.cumulus_userid = None
        self.cumulus_password = None

        for key in kwargs:
            setattr(self, key, kwargs[key])

        self.setSSHConnection()
        self.validate()


    def __str__(self):
        return str(vars(self))


    def validate(self):

        file_script = "/folk/{}/{}".format(self.userid, CUMULUS_SETUP_SCRIPT )
        file_config = "/folk/{}/{}".format(self.userid, CUMULUS_SETUP_CFG_FILENAME )
        file_cleanup = "/folk/{}/{}".format(self.userid, CUMULUS_CLEANUP_SCRIPT )
        cmd = "test -f {}; test -f {}; test -f {}".format(file_script, file_config, file_cleanup)
        if self.ssh_conn.exec_cmd(cmd)[0] != 0:
            msg = "cumulus script files missing; Ensure the following files " \
                  " exist in /folk/{}: {} {} {}".\
                format(file_script, file_config, file_cleanup, self.userid)

            self.log.info(msg)
            wr_exit()._exit(1, msg)


        user_openrc = "/folk/{}/openrc.{}".format(self.userid, self.userid)
        if self.ssh_conn.exec_cmd("test -f " + user_openrc)[0] != 0:
            msg = "user openrc file missing."

            self.log.info(msg)
            wr_exit()._exit(1, msg)

        # check if floating ips are allocated:
        cmd = "source " + user_openrc
        cmd += " ; neutron floatingip-list |  awk \'/128.224/ { print $5 }\'"
        rc, floating_ips = self.ssh_conn.exec_cmd(cmd)
        if rc is not 0 or floating_ips is None or \
                        len(floating_ips.split('\n')) < 3:
            msg = "Floating IPs are not allocated to your tenant project:\n " \
                  " Log into horizon with your keystone user and select your" \
                  " project. Go to the Project -> Compute -> Access & Security" \
                  " page. Select the Floating IPs tab. If there aren't three IPs" \
                  " allocated, use the Allocate IP To Project button to allocate more"

            self.log.info(msg)
            wr_exit()._exit(1, msg)

        self.log.info(floating_ips)
        self.floating_ips = floating_ips.split('\n')
        self.log.info(floating_ips)

        self.cumulus_options = self.parse_cumulus_conf(file_config)
        # check if floating ips are specified. in cumulus_setup.conf file

        if {"EXTERNALOAMFLOAT", "EXTERNALOAMC0", "EXTERNALOAMC1" }  \
                not in set(self.cumulus_options) and set(self.floating_ips) \
                <= set([self.cumulus_options["EXTERNALOAMFLOAT"], self.cumulus_options["EXTERNALOAMC0"], self.cumulus_options["EXTERNALOAMC1"]]):
            msg = "The {} conf file must be updated with allocated floating " \
                  "ips".format(CUMULUS_SETUP_CFG_FILENAME)
            self.log.error(msg)
            wr_exit()._exit(1, msg)

        for k, v in self.cumulus_options.items():
            self.log.info(k +" = " + v +"\n")


    def setSSHConnection(self):

        self.ssh_conn = SSHClient(log_path=self.output_dir + "/cumulus_" + self.userid + ".ssh.log")
        self.ssh_conn.connect(hostname=self.server, username=self.userid,
                            password=self.password)


    def tis_install(self):

        CUMULUS_HOME_DIR = "/folk/" + str(self.userid)
        CUMULUS_USERID = self.userid
        CUMULUS_SERVER = self.server
        CUMULUS_PASSWORD = self.password
        self.setSSHConnection()
        cumulus_tis_conn =  self.ssh_conn
        log = self.log

        # get tis image
        if cumulus_tis_conn.exec_cmd("test -d " + CUMULUS_TMP_TIS_IMAGE_PATH)[0] == 0:
            tis_image_path = CUMULUS_TMP_TIS_IMAGE_PATH + \
                             "/{}".format(CUMULUS_USERID)

            if cumulus_tis_conn.exec_cmd("test -d " + tis_image_path)[0] != 0:
                cumulus_tis_conn.sendline("mkdir -p " + tis_image_path)
                cumulus_tis_conn.find_prompt()
                cumulus_tis_conn.sendline("chmod 755 " + tis_image_path)
                cumulus_tis_conn.find_prompt()
        else:
            tis_image_path = "/folk/{}".format(CUMULUS_USERID)
            cmd = "df --output=avail -h {} | sed '1d;s/[^0-9]//g'".format(tis_image_path)
            rc, avail = cumulus_tis_conn.exec_cmd(cmd)
            if rc != 0 and avail < BOOT_IMAGE_ISO_SIZE:
                msg = "Unable to check available disk space or not sufficient" \
                      " space in {} for tis image. Currently availabe space is" \
                      " {}.".format(tis_image_path, avail)
                log.exception(msg)
                wr_exit()._exit(1,msg)

        bld_server_image_path = os.path.join(self.load_path, BLD_TIS_IMAGE_PATH)
        pre_opts = 'sshpass -p "{0}"'.format(CUMULUS_PASSWORD)
        self.bld_server_conn.rsync(bld_server_image_path,
                                  CUMULUS_USERID, CUMULUS_SERVER,
                                  tis_image_path, pre_opts=pre_opts)

        # test if image is downloaded from load server
        user_openrc = "/folk/{}/openrc.{}".format(self.userid, self.userid)
        cmd = "source {}; test -s {}/{}".format(user_openrc, tis_image_path, TIS_IMAGE)
        if cumulus_tis_conn.exec_cmd(cmd)[0] != 0:
                msg = "Failed to download tis image file from load server: {}".\
                    format(bld_server_image_path)
                log.exception(msg)
                wr_exit()._exit(1,msg)

        # clean up any prior cumumls install
        cmd = CUMULUS_HOME_DIR + "/" + CUMULUS_CLEANUP_SCRIPT
        if cumulus_tis_conn.exec_cmd(cmd)[0] != 0:
                msg = "WARNING: Fail to clean-up previous installation"
                log.warning(msg)

        # delete if previous tis image if exist in cumulu
        cmd = "source {};".format(user_openrc)
        cmd += " nova image-list  | grep " + CUMULUS_USERID +"-tis | awk \'{print $4}\'"
        if cumulus_tis_conn.exec_cmd(cmd)[0] is 0:
            # delete image first
            cmd = "source {}; nova image-delete {}-tis".format(user_openrc, CUMULUS_USERID)
            if cumulus_tis_conn.exec_cmd(cmd)[0] != 0:
                msg = "Failed to delete previous tis image: {}-tis from cumulus".\
                    format(CUMULUS_USERID)
                log.exception(msg)
                wr_exit()._exit(1,msg)

        # create glance image
        log.info("Creating glance image using name {}-tis".format(CUMULUS_USERID))
        cmd = "source {}; glance image-create --name $USER-tis --container-format bare " \
              "--disk-format qcow2 --file {}/{}".format(user_openrc, tis_image_path, TIS_IMAGE)

        if cumulus_tis_conn.exec_cmd(cmd, 600)[0] != 0:
            msg = "Failed to create tis image from image file: {}".\
                    format(bld_server_image_path)
            log.exception(msg)
            wr_exit()._exit(1,msg)

        # cumulus_setup: network configuration and create launch scripts for
        # virtual controller and compute nodes
        cmd = "./" + CUMULUS_SETUP_SCRIPT
        rc, output = cumulus_tis_conn.exec_cmd(cmd, 120)
        if rc is not 0:
            msg = " Fail in {}".format(CUMULUS_SETUP_SCRIPT)
            msg += " : " + str(output)
            log.error(msg)
            wr_exit()._exit(1,msg)

    def get_floating_ip(self, name):
        if name in ["EXTERNALOAMFLOAT", "EXTERNALOAMC0", "EXTERNALOAMC1"]:
            return self.cumulus_options[name]
        else:
            return None

    def launch_controller0(self):
        # Launch first virtual controller
        cumulus_tis_conn = self.ssh_conn
        rc, output = cumulus_tis_conn.exec_cmd("./instances/launch_virtual-controller-0.sh")
        if rc is not 0:
            msg = " Fail to launch a virtual controller-0."
            self.log.error(msg)
            wr_exit()._exit(1,msg)

        # wait 5 minutes until the controller-0 boot up and then attempt to set up ssh connection
        # using the default 10.10.10.3 oam ip. If success, reset password

        floatingip = self.floating_ips[0]

        time.sleep(180)

        controller0_ssh_conn = SSHClient(log_path=self.output_dir + "/controller-0.ssh.log")
        controller0_ip = self.get_floating_ip("EXTERNALOAMC0")


        cmd = "ping -w {} -c 4 {}".format(PING_TIMEOUT, controller0_ip)
        ping = 0

        while ping < MAX_LOGIN_ATTEMPTS:

            self.log.info('Pinging controller-0 with ip address {}'.format(controller0_ip))
            rc, output = cumulus_tis_conn.exec_cmd(cmd)
            if rc:
                self.log.info("Sleeping for 180 seconds...")
                time.sleep(180)
                ping += 1
            else:
                break

        if ping == MAX_LOGIN_ATTEMPTS:
            msg = 'Waited 1200 seconds and the controller did not respond'
            self.log.error(msg)
            wr_exit()._exit(1, msg)


        ssh_key_fpath = os.path.expanduser(KNOWN_HOSTS_PATH)
        if os.path.isfile(ssh_key_fpath):
            exec_cmd(REMOVE_HOSTS_SSH_KEY_CMD.format(ssh_key_fpath, controller0_ip).split())


        cmd = 'ssh wrsroot@' + controller0_ip
        controller0_ssh_conn._spawn(cmd)
        #controller0_ssh_conn.expect("(yes/no)?")
        controller0_ssh_conn.expect(".*\(yes/no\)\? ?$")
        controller0_ssh_conn.sendline("yes")
        controller0_ssh_conn.expect(PASSWORD_PROMPT)
        controller0_ssh_conn.sendline(WRSROOT_DEFAULT_PASSWORD)
        controller0_ssh_conn.expect(PASSWORD_PROMPT)
        controller0_ssh_conn.sendline(WRSROOT_DEFAULT_PASSWORD)
        controller0_ssh_conn.expect(PASSWORD_PROMPT)
        controller0_ssh_conn.sendline(WRSROOT_PASSWORD)
        controller0_ssh_conn.expect(PASSWORD_PROMPT)
        controller0_ssh_conn.sendline(WRSROOT_PASSWORD)
        time.sleep(5)

    def launch_controller1(self):

        rc, output = self.ssh_conn.exec_cmd("./instances/launch_virtual-controller-1.sh")
        if rc is not 0:
            msg = " Fail to launch a virtual controller-1."
            self.log.error(msg)
            wr_exit()._exit(1,msg)



    def launch_computes(self):

        compute_count = self.get_number_of_computes()
        
        for i in range(0, compute_count):
            rc, output = self.ssh_conn.exec_cmd("./instances/launch_virtual-compute-" + str(i) + ".sh")
            if rc is not 0:
                msg = " Fail to launch a virtual compute-" + str(i) + "."
                self.log.error(msg)
                wr_exit()._exit(1,msg)

    def launch_storages(self):

        storage_count = self.get_number_of_storages()
        
        for i in range(0, storage_count):
            rc, output = self.ssh_conn.exec_cmd("./instances/launch_virtual-storage-" + str(i) + ".sh")
            if rc is not 0:
                msg = " Fail to launch a virtual storage-" + str(i) + "."
                self.log.error(msg)
                wr_exit()._exit(1,msg)

            self.storage = True

    def parse_cumulus_conf(self, filename):

        comment_chars = '#'
        option_char = '='
        options = {}
        cmd = "cat " + filename

        rc, output = self.ssh_conn.exec_cmd(cmd, show_output=False)
        if rc is 0 and output is not None:
            lines = output.split('\n')
            for line in lines:
                # First, remove comments:
                if comment_chars in line:
                    # split on comment char, keep only the part before
                    line, comment = line.split(comment_chars, 1)
                # Second, find lines with an option=value:
                if option_char in line:
                    # split on option char:
                    option, value = line.split(option_char, 1)
                    # strip spaces:
                    option = option.strip()
                    value = value.strip()
                    # store in dictionary:
                    options[option] = value
        else:
            options = None
        return options
    
    def get_number_of_computes(self):
        if not 'COMPUTES' in self.cumulus_options.keys():
            return 0
        return int(self.cumulus_options['COMPUTES'])

    def get_number_of_storages(self):
        if not 'STORAGES' in self.cumulus_options.keys():
            return 0
        return int(self.cumulus_options['STORAGES'])

