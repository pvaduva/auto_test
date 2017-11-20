#!/usr/bin/python3

import pdb
import subprocess
import argparse
import time
import re
import sys
import os.path
import pytest
import datetime
import logging
from utils.install_log import LOG

try:
    import streamexpect
except ImportError:
    LOG.info("You do not have streamexpect installed.")
    exit(1)
    
from helper import vboxmanage
from helper import install_lab
from helper import host_helper
from consts.node import Nodes
from consts.networking import NICs, OAM, Serial
from consts.env import BuildServers, Licenses, Builds, ISOPATH
from utils.sftp import sftp_get, sftp_send, send_dir
from utils import serial
from utils import threading
from consts.timeout import HostTimeout
from parser import handle_args




"""
Network Consolidation Abbreviations:
.
.       _ - Separate
.       M - Management Network
.       O - OAM Network
.       D - Data Network
.       I - Infrastructure Network
.       T - Tagged/VLAN
.       U - Untagged

Network Consolidation Options for controller (con):

.        M_O   - Separate Management & OAM Interface (Only supported for 2only)
.        M_O_I - Separate Management, OAM & Infrastructure network
.        M_O_TI- Seperate Management, OAM network & Tagged Infrastruture
.        MOI   - Combined Management, OAM, Infrastructure network
.        MO_I  - Combined Management, OAM network & separate Infrastruture Untagged
.        MO_TI  - Combined Management, OAM network & separate Infrastruture tagged
.        MI_O - Combined Management, Infrastructure & separate untagged OAM network (DEFAULT)
.        MI_TO - Combined Management, Infrastructure & separate Tagged OAM network
.        M_TOTI- Separate Management & combined Tagged OAM & tagged Infrastrucute network
.        M_UOTI- Separate Management & combined untagged OAM & tagged Infrastructure network
.        M_TOUI- Separate Management & combined tagged OAM & untagged Infrastructure network

Network Consolidation Options for Storage (str):
.        MI    - Combined Management, Infrastructure network (Default)
.        TMI   - Combined Tagged Management, Infrastructure network
.        M_I   - Separate Management & Infrastructure network
.        M_TI  - Separate Management & Tagged Infrastructure network

Network Consolidation Options for Compute (com):
.        MI_D   - Combined Management, Infrastructure & Separate Data network (Default)
.        TMI_D  - Combined Management, Tagged Infrastructure & Separate Data network
.        M_I_D  - Seperate Management, Infrastructure & Data network
.        M_TI_D - Seperate Management, Data & Tagged Infrastructure network


"""



def menu_selector(stream, controller_type, securityprofile, release, lowlatency, install_mode='serial'):
    """
    Select the correct install option.

    Arguments:
    * stream(socket) - local domain socket to host
    * controller_type(str) - controller_aio, controller_lvm or controller_ceph
    * securityprofile(str) - standard or extended
    * release(str) - R2, R3, R4, etc.
    * lowlatency(bool) - True or False
    """

    # R5 only right now.
    # Wait for menu to load (add sleep so we can see what is picked)
    serial.expect_bytes(stream, "Press")
    if release == 'R4':
        if controller_type =='controller_aio':
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
            if lowlatency == True:
                LOG.info("Selecting low latency controller")
                serial.send_bytes(stream, "\033[B", expect_prompt=False)
                serial.send_bytes(stream, "\033[B", expect_prompt=False)
        if install_mode == 'graphical':
            LOG.info("Selecting Graphical menu")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        serial.send_bytes(stream, "\n", expect_prompt=False)
    elif release == 'R3':
        if controller_type == "controller_aio":
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        if install_mode == 'graphical':
            LOG.info("Selecting Graphical menu")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        serial.send_bytes(stream, '\n', expect_prompt=False)
    elif release=='R2':
        if controller_type == "controller_aio":
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        if install_mode == 'graphical':
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
            # Selects graphics text install
            # serial.send_bytes(stream, "\033[B", expect_prompt=False)
        
        serial.send_bytes(stream, "\n", expect_prompt=False)
    else:
        # Pick install type
        if controller_type == "controller_aio":
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        if lowlatency == True:
            LOG.info("Selecting low latency controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        serial.send_bytes(stream, "\n", expect_prompt=False)
        
        # Serial or Graphical menu (picking Serial by default)
        # serial.expect_bytes(stream, "Press")
        if install_mode == "graphical":
            LOG.info("Selecting Graphical menu")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        LOG.info("Selecting Serial menu")
        serial.send_bytes(stream, "\n", expect_prompt=False)
        
        # Security profile menu
        # serial.expect_bytes(stream, "Press")
        if securityprofile == "extended":
            LOG.info("Selecting extended security profile")
            serial.send_bytes(stream, "\033[B", expect_prompt=False)
        serial.send_bytes(stream, "\n", expect_prompt=False)



def setup_networking(stream, release):
    """
    Setup initial networking so we can transfer files.
    """
    ip = "10.10.10.3"
    host_ip = "10.10.10.254"
    password = "Li69nux*"
    if release == "R2":
        interface = "eth0"
    else:
        interface = "enp0s3"
    LOG.info("{} being set up with ip {} ({}:{})".format(interface, ip, datetime.datetime.now().hour,datetime.datetime.now().minute))
    serial.send_bytes(stream, "sudo /sbin/ip addr add {}/24 dev {}".format(ip, interface), expect_prompt=False)
    ret = serial.expect_bytes(stream, "Password:", fail_ok=True, timeout=20)
    if ret == 0:
        serial.send_bytes(stream, password)
    time.sleep(2)
    serial.send_bytes(stream, "sudo /sbin/ip link set {} up".format(interface))
    serial.send_bytes(stream, "sudo route add default gw {}".format(host_ip))
    

    NETWORKING_TIME = 60
    LOG.info("Wait a minute for networking to be established")
    time.sleep(NETWORKING_TIME)

    # Ping from machine hosting virtual box to virtual machine
    #rc = subprocess.call(['ping', '-c', '3', ip])
    #assert rc == 0, "Network connectivity test failed"


@pytest.mark.unit
def test_install_vbox(controller_type, securityprofile, release, lowlatency, configure, install_mode):
    """
    Installation of vbox.
    Takes about 30 mins
    """
    # Power on controller-0
    # Install controller-0
    # Login
    # Change default password
    # Setup basic networking
    # Close stream
    vboxmanage.vboxmanage_startvm("controller-0")
    cont0_stream = streamexpect.wrap(serial.connect("controller-0"), echo=True, close_stream=False)
    LOG.info("Starting installation of controller-0")
    menu_selector(cont0_stream, controller_type, securityprofile, release, lowlatency, install_mode)
    serial.expect_bytes(cont0_stream, 'login:', timeout=HostTimeout.INSTALL)
    LOG.info("Completed installation of controller-0")
    # Change password on initial login
    time.sleep(10)
    host_helper.change_password(cont0_stream)

    # Disable user logout
    host_helper.disable_logout(cont0_stream)

    # Setup basic networking
    time.sleep(10)

    setup_networking(cont0_stream, release)
    return cont0_stream
    

def test_install_nodes(cont0_stream, host_list=None):
    """
    Tests node install, requires controller-0 to be installed previously
    Args:
        host_list(list): list of host names to install.
        
    45 mins cont-1
    Less for computes but they fail.
    """
    host_id = 2
    streams = {}

    # Since we don't need to install controller-0, let's remove it
    host_list.remove("controller-0")

    # Don't want to mess with vms that aren't supposed to be.
    for item in host_list:
        if 'controller' not in item and 'compute' not in item and 'storage' not in item:
            host_list.remove(item)
    # Create streams early so we can see what's happening
    # If we don't power on the host, socket connection will fail
    print(host_list)
    for host in host_list:
        stream = streamexpect.wrap(serial.connect('{}'.format(host)), echo=True, close_stream=False)
        streams[host] = stream
    serial.send_bytes(cont0_stream, "source /etc/nova/openrc", prompt='keystone')    
    threads = []
    cont1_thread = threading.InstallThread(cont0_stream, 'controller-1 thread', host, 'controller', host_id)
    host_id += 1
    comp0_thread = threading.InstallThread(cont0_stream, 'compute-0 thread', host, 'compute', host_id)
    host_id += 1
    comp1_thread = threading.InstallThread(cont0_stream, 'compute-1 thread', host, 'compute', host_id)
    host_id += 1
    
    cont1_thread.start()
    comp0_thread.start()
    comp1_thread.start()
    
    threads.append(cont1_thread)
    threads.append(comp0_thread)
    threads.append(comp1_thread)
    
    for items in threads:
        items.join(HostTimeout.HOST_INSTALL)
    
    """
    Old non-multithreaded implementation:
    for host in host_list:
        LOG.info("Installing host: {}".format(host)) 
        if host.startswith('controller'):
            host_helper.install_host(cont0_stream, host, 'controller', host_id)
            host_id += 1
        elif host.startswith('compute'):
            host_helper.install_host(cont0_stream, host, 'compute', host_id)
            host_id += 1
        else:
            host_helper.install_host(cont0_stream, host, 'storage', host_id)
            host_id += 1
    """
    
    # Look for login
    # Close the stream if we want
    for host in host_list:
        serial.expect_bytes(streams[host], "login:", HostTimeout.HOST_INSTALL)
        #stream.close()
    # Return streams dict in case we need to reference the streams later
    return streams


def test_get_install_files(cont0_stream, remote_host, setup_files):
    install_lab.get_lab_setup_scripts()
    install_lab.get_licence()
    install_lab.get_guest_img(cont0_stream)


@pytest.mark.unit
def test_lab_install(cont0_stream, host_list=None, aio=False, storage=False, setup_files=None):
    """
    Installs lab setup scripts
    Args:
        cont0_stream(stream):
        host_list(list): list of hosts
        aio(bool): if the lab is aio
        storage(bool): if the lab is a storage lab
        setup_files(str):Path to setup files. If none the files will be retrieved from CGTS4

    """
    serial.send_bytes(cont0_stream, "source /etc/nova/openrc")
    install_lab.run_install_scripts(cont0_stream, host_list, aio, storage)


def test_networking_setup(cont0_stream):
    """
    Sets up networking
    Args:
        cont0_stream(stream): stream to controller-0

    """
    setup_networking(cont0_stream, 'R5')
    time.sleep(10)
    

def create_vms(vboxoptions):
    """
    Creates vms using the arguments in vboxoptions.
    Takes about 4 mins
    """
    # Semantic checks
    assert not (vboxoptions.aio == True and vboxoptions.storage), "AIO cannot have storage nodes"
    assert not (vboxoptions.aio == True and vboxoptions.computes), "AIO cannot have compute nodes"
    assert not (
        vboxoptions.deletevms == True and vboxoptions.useexistingvms), "These options are incompatible with each other"
    if vboxoptions.release:
        assert vboxoptions.buildserver, "Must provide build server if release is specified"
    if vboxoptions.buildserver:
        assert vboxoptions.release, "Must provide release if build server is specified"
    # LOG.info("Retrieving vbox extention pack")
    # 
    # vboxmanage.vboxmanage_extpack()

    # List current VMs
    node_list = []
    vm_list = vboxmanage.vboxmanage_list("vms")
    LOG.info("The following VMs are present on the system: {}".format(vm_list))
    for item in vm_list:
        if b'controller' in item or b'compute' in item or b'storage' in item:
            node_list.append(item)
    # Delete VMs if the user requests it
    # Maybe only delete necessary vms? TODO
    if vboxoptions.deletevms == True and len(node_list) != 0:
        LOG.info("Deleting existing VMs as requested by user: {}".format(node_list))
        vboxmanage.vboxmanage_controlvms(node_list, "poweroff")
        vboxmanage.vboxmanage_deletevms(node_list)

    # Pull in node configuration
    node_config = [getattr(Nodes, attr) for attr in dir(Nodes) if not attr.startswith('__')]
    nic_config = [getattr(NICs, attr) for attr in dir(NICs) if not attr.startswith('__')]
    oam_config = [getattr(OAM, attr) for attr in dir(OAM) if not attr.startswith('__')][0]
    buildservers = [getattr(BuildServers, attr) for attr in dir(BuildServers) if not attr.startswith('__')]
    licenses = [getattr(Licenses, attr) for attr in dir(Licenses) if not attr.startswith('__')]
    builds = [getattr(Builds, attr) for attr in dir(Builds) if not attr.startswith('__')]
    serial_config = [getattr(Serial, attr) for attr in dir(Serial) if not attr.startswith('__')]

    # Determine how to setup the controllers
    if vboxoptions.storage:
        controller_type = 'controller_ceph'
    elif vboxoptions.aio:
        controller_type = 'controller_aio'
    else:
        controller_type = 'controller_lvm'

    # Create and setup nodes
    if vboxoptions.useexistingvms == False:
        # Delete exiting vboxnet0 to avoid creating unnecessary hostonlyifs
        # Using vboxnet40 to avoid deleting in use networks
        #vboxmanage.vboxmanage_hostonlyifdelete("vboxnet40")
        #vboxmanage.vboxmanage_hostonlyifcreate("vboxnet40", oam_config['ip'], oam_config['netmask'])

        # Create nodes list
        nodes_list = []
        if vboxoptions.controllers:
            for id in range(0, vboxoptions.controllers):
                node_name = "controller-{}".format(id)
                nodes_list.append(node_name)
        if vboxoptions.computes:
            for id in range(0, vboxoptions.computes):
                node_name = "compute-{}".format(id)
                nodes_list.append(node_name)
        if vboxoptions.storage:
            for id in range(0, vboxoptions.storage):
                node_name = "storage-{}".format(id)
                nodes_list.append(node_name)
        LOG.info("We will create the following nodes: {}".format(nodes_list))
        for node in nodes_list:
            vboxmanage.vboxmanage_createvm(node)
            vboxmanage.vboxmanage_storagectl(node)
            if node.startswith("controller"):
                node_type = controller_type
            elif node.startswith("compute"):
                node_type = "compute"
            else:
                node_type = "storage"

            for item in node_config:
                if item['node_type'] == node_type:
                    vboxmanage.vboxmanage_modifyvm(node, cpus=str(item['cpus']), memory=str(item['memory']))
                    vboxmanage.vboxmanage_createmedium(node, item['disks'])

            vboxmanage.vboxmanage_modifyvm(node, uartbase=serial_config[0]['uartbase'],
                                           uartport=serial_config[0]['uartport'], uartmode=serial_config[0]['uartmode'],
                                           uartpath=serial_config[0]['uartpath'])
            if node.startswith("controller"):
                node_type = "controller"

            for item in nic_config:
                if item['node_type'] == node_type:
                    for adapter in item.keys():
                        if adapter.isdigit():
                            data = item[adapter]
                            vboxmanage.vboxmanage_modifyvm(node,
                                                           nic=data['nic'], nictype=data['nictype'],
                                                           nicpromisc=data['nicpromisc'],
                                                           nicnum=int(adapter), intnet=data['intnet'],
                                                           hostonlyadapter=data['hostonlyadapter'])

    else:
        LOG.info("Setup will proceed with existing VMs as requested by user")

    # Determine ISO to use
    if vboxoptions.useexistingiso is False:
        for item in builds:
            if item['release'] == vboxoptions.release:
                remote_path = item['iso']
        for item in buildservers:
            if item['short_name'].upper() == vboxoptions.buildserver:
                remote_server = item['ip']
        sftp_get(remote_path, remote_server, '/folk/tmather/LabInstall/{}/bootimage.iso'.format(vboxoptions.release))
        # sftp_get(remote_path, remote_server, ISOPATH))
        PATH = '/folk/tmather/LabInstall/{}/bootimage.iso'.format(vboxoptions.release)
        # PATH=ISOPATH
    elif vboxoptions.iso_location:
        PATH = vboxoptions.iso_location
        LOG.info("Setup will proceed with existing ISO {} as requested by user".format(PATH))
        assert os.path.isfile(ISOPATH), "ISO doesn't exist at: {}".format(PATH)
    else:
        LOG.info("Setup will proceed with existing ISO {} as requested by user".format(ISOPATH))
        assert os.path.isfile(ISOPATH), "ISO doesn't exist at: {}".format(ISOPATH)
        PATH=ISOPATH
    # Need a more programatic way to do this rather than hardcoding device - INVESTIGATE
    vboxmanage.vboxmanage_storageattach(storetype="dvddrive", disk=PATH, device_num="1", port_num="1")

    # END VBOX SETUP

    # Start installing the system
    return test_install_vbox(controller_type, vboxoptions.securityprofile, vboxoptions.release, vboxoptions.lowlatency, vboxoptions.configure, install_mode=vboxoptions.install_mode)


def test_get_lab_files(cont0_stream, local_path=None, remote_host=None):
    install_lab.get_lab_setup_files(cont0_stream, remote_host, local_path=local_path)

    
if __name__ == "__main__":
   
    #pdb.set_trace()
    # START VBOX SETUP
    vboxoptions = handle_args().parse_args()
    LOG.info(vboxoptions)
    if vboxoptions.create_vms:
        cont0_stream = create_vms(vboxoptions)
    node_list = []
    for item in vboxmanage.vboxmanage_list('vms'):
        if b'controller' in item or b'compute' in item or b'storage' in item:  
            node_list.append(item.decode('utf-8'))
    LOG.info(node_list)
    assert 'controller-0' in node_list, "controller-0 not in vm list. Stopping installation."
    
    # if vms were created this should be done already
    if not vboxoptions.create_vms:
        cont0_stream = streamexpect.wrap(serial.connect("controller-0"), echo=True, close_stream=False)
        host_helper.login(cont0_stream, timeout=600)
        test_networking_setup(cont0_stream)    
    if vboxoptions.setup_files:
        test_get_lab_files(cont0_stream, vboxoptions.setup_files)
    elif vboxoptions.get_setup:
        test_get_lab_files(cont0_stream, remote_host=BuildServers.CGTS4['ip'])    
    # Configures controller-0 if requested
    if vboxoptions.configure:
        if vboxoptions.install_patches:
            install_lab.install_patches_before_config(cont0_stream, release=vboxoptions.release)
        install_lab.config_controller(cont0_stream, config_file=vboxoptions.config_file, release=vboxoptions.release)
        if vboxoptions.install_lab and vboxoptions.release == 'R5':
            # wait for online status, run lab_setup, unlock cont0, provision hosts, continue from before.
            install_lab.install_controller_0(cont0_stream) 
    #retrieves patches
    if vboxoptions.patch_dir:
        install_lab.get_patches(cont0_stream, vboxoptions.patch_dir, release=vboxoptions.release)
    elif vboxoptions.get_patches:
        install_lab.get_patches(cont0_stream, remote_host=BuildServers.CGTS4['ip'], release=vboxoptions.release)
    #installs patches    
    if vboxoptions.install_patches:
        install_lab.install_patches_before_config(cont0_stream)
    elif vboxoptions.make_patch_current:
        buildserver = vboxoptions.buildserver
        if not vboxoptions.get_patches:
            install_lab.get_patches(cont0_stream, vboxoptions.patch_dir, BuildServers.CGTS4['ip'], release=vboxoptions.release)
        install_lab.install_patches_before_config(cont0_stream)
    #installs nodes and runs lab_setup
    if vboxoptions.install_lab:
        LOG.info("Starting lab installation.")
        test_install_nodes(cont0_stream, host_list=node_list)
        test_lab_install(cont0_stream, aio=vboxoptions.aio, storage=vboxoptions.storage,
                         setup_files=vboxoptions.setup_files, release=vboxoptions.release)
    if vboxoptions.install_patches:
        # install_lab.install_patches_on_nodes()
        pass
    host_helper.logout(cont0_stream)
    cont0_stream.close()
