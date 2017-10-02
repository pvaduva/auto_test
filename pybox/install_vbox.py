#!/usr/bin/python3

import argparse
import time
import re
import sys
import os.path
import pytest

try:
    import streamexpect
except ImportError:
    print("You do not have streamexpect installed.")
    exit(1)

from helper import vboxmanage
from consts.node import Nodes
from consts.networking import NICs, OAM, Serial
from consts.env import BuildServers, Licenses, Builds, ISOPATH
from utils.sftp import sftp_get
from utils import serial
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

def menu_selector(stream, controller_type, securityprofile, release, lowlatency):
    """
    Select the correct install option.

    Arguments:
    * stream(socket) - local domain socket to host
    * controller_type(str) - controller_aio, controller_lvm or controller_ceph
    * securityprofile(str) - standard or extended
    * release(str) - R2, R3, R4, etc.
    * lowlatency(bool) - True or False
    """

    #R5 only right now.
    # Wait for menu to load (add sleep so we can see what is picked)
    serial.expect_bytes(stream, "Press")
    # Pick install type
    if controller_type == "controller_aio":
        serial.send_bytes(stream, "\033[B")
    if lowlatency == True: 
        serial.send_bytes(stream, "\033[B")
    serial.send_bytes(stream, "\n")

    # Serial or Graphical menu (picking Serial by default)
    serial.expect_bytes(stream, "Press")
    #if install_mode = "graphical":
    #    serial.send_bytes(stream, "\033[B")
    serial.send_bytes(stream, "\n")

    # Security profile menu
    serial.expect_bytes(stream, "Press")
    if securityprofile == "extended": 
        serial.send_bytes(stream,"\033[B")
    serial.send_bytes(stream, "\n")


def setup_networking(stream, release):
    """
    Setup initial networking so we can transfer files.
    """

    ip = "10.10.10.1"
    host_ip = "10.10.10.254"
    password = "Li69nux*"
    if release == "R2":
        interface = "eth0"
    else:
        interface = "enp0s3"
    serial.send_bytes(stream, "sudo /sbin/ip addr add {}/24 dev {}".format(ip, interface))
    serial.expect_bytes(stream, "Password:")
    serial.send_bytes(stream, password)
    serial.send_bytes(stream, "sudo /sbin/ip link set {} up".format(interface))

    print("Wait a few seconds for networking to be established")
    time.sleep(10)
    #rc = serial.send_bytes(stream, "ping -c 3 {}".format(host_ip))
    #print(rc)


@pytest.mark.unit
def test_install_vbox(controller_type, securityprofile, release, lowlatency):
    """
    Installation of vbox.
    """
    # Power on controller-0
    # Install controller-0
    # Login
    # Change default password
    # Close stream
    vboxmanage.vboxmanage_startvm("controller-0")
    cont0_stream = streamexpect.wrap(serial.connect("controller-0"), echo=True)
    print("NOTE: Once we select menu options, you will not see much output on the console until the login prompt appears.")
    menu_selector(cont0_stream, controller_type, securityprofile, release, lowlatency)
    serial.expect_bytes(cont0_stream, "login", HostTimeout.INSTALL)

    # Change password on initial login
    serial.send_bytes(cont0_stream, "wrsroot")
    serial.expect_bytes(cont0_stream, "Password:")
    serial.send_bytes(cont0_stream, "wrsroot")
    serial.expect_bytes(cont0_stream, "assword:")
    serial.send_bytes(cont0_stream, "wrsroot")
    serial.expect_bytes(cont0_stream, "assword:")
    serial.send_bytes(cont0_stream, "Li69nux*")
    serial.expect_bytes(cont0_stream, "assword:")
    serial.send_bytes(cont0_stream, "Li69nux*")

    # Setup basic networking
    setup_networking(cont0_stream, release)
    
    cont0_stream.close()



if __name__ == "__main__":


    # START VBOX SETUP
    vboxoptions = handle_args().parse_args()
    print(vboxoptions)

    # Semantic checks
    assert not (vboxoptions.aio == True and vboxoptions.storage), "AIO cannot have storage nodes"
    assert not (vboxoptions.aio == True and vboxoptions.computes), "AIO cannot have compute nodes"
    assert not (vboxoptions.deletevms == True and vboxoptions.useexistingvms), "These options are incompatible with each other"
    if vboxoptions.release:
        assert vboxoptions.buildserver, "Must provide build server if release is specified" 
    if vboxoptions.buildserver:
        assert vboxoptions.release, "Must provide release if build server is specified" 

    #vboxmanage.vboxmanage_extpack()

    # List current VMs
    nodes_list = vboxmanage.vboxmanage_list("vms")
    print("The following VMs are present on the system: {}".format(nodes_list))

    # Delete VMs if the user requests it
    if vboxoptions.deletevms == True and len(nodes_list) != 0:
        print("Deleting existing VMs as requested by user: {}".format(nodes_list))
        vboxmanage.vboxmanage_controlvms(nodes_list, "poweroff")
        vboxmanage.vboxmanage_deletevms(nodes_list)

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
        vboxmanage.vboxmanage_hostonlyifcreate("vboxnet0", oam_config['ip'], oam_config['netmask'])

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
        print("We will create the following nodes: {}".format(nodes_list))
       
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

            vboxmanage.vboxmanage_modifyvm(node, uartbase=serial_config[0]['uartbase'], uartport=serial_config[0]['uartport'], uartmode=serial_config[0]['uartmode'], uartpath=serial_config[0]['uartpath'])
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
        print("Setup will proceed with existing VMs as requested by user")

    # Grab ISO
    for item in builds:
        if item['release'] == vboxoptions.release:
            remote_path = item['iso']

    for item in buildservers:
        if item['short_name'].upper() == vboxoptions.buildserver:
            remote_server = item['ip']


    if vboxoptions.useexistingiso == False:
        sftp_get(remote_path, remote_server, ISOPATH)
    else:
        print("Setup will proceed with existing ISO {} as requested by user".format(ISOPATH))
        assert os.path.isfile(ISOPATH), "ISO doesn't exist at: {}".format(ISOPATH)

    # Need a more programatic way to do this rather than hardcoding device - INVESTIGATE
    vboxmanage.vboxmanage_storageattach(storetype="dvddrive", disk=ISOPATH, device_num="1", port_num="1")

    # END VBOX SETUP

    # Start installing the system
    test_install_vbox(controller_type, vboxoptions.securityprofile, vboxoptions.release, vboxoptions.lowlatency)
