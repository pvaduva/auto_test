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
from utils import kpi
from sys import platform
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
from consts import env
from utils.sftp import sftp_get, sftp_send, send_dir
from utils import serial
from utils import threading
from consts.timeout import HostTimeout
from Parser import handle_args


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
        if controller_type == 'controller_aio':
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
            if lowlatency is True:
                LOG.info("Selecting low latency controller")
                serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
                serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        if install_mode == 'graphical':
            LOG.info("Selecting Graphical menu")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        serial.send_bytes(stream, "\n", expect_prompt=False, send=False)
        time.sleep(4)
    elif release == 'R3':
        if controller_type == "controller_aio":
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        if install_mode == 'graphical':
            LOG.info("Selecting Graphical menu")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        serial.send_bytes(stream, "\n", expect_prompt=False, send=False)
        time.sleep(4)
    elif release == 'R2':
        if controller_type == "controller_aio":
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        if install_mode == 'graphical':
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        time.sleep(4)
        serial.send_bytes(stream, "\n", expect_prompt=False, send=False)
    else:
        # Pick install type
        if controller_type == "controller_aio":
            LOG.info("Selecting AIO controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        if lowlatency is True:
            LOG.info("Selecting low latency controller")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        serial.send_bytes(stream, "\n", expect_prompt=False, send=False)
        time.sleep(4)
        # Serial or Graphical menu (picking Serial by default)
        if install_mode == "graphical":
            LOG.info("Selecting Graphical menu")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        else:
            LOG.info("Selecting Serial menu")
        serial.send_bytes(stream, "\n", expect_prompt=False, send=False)
        time.sleep(6)
        # Security profile menu
        if securityprofile == "extended":
            LOG.info("Selecting extended security profile")
            serial.send_bytes(stream, "\033[B", expect_prompt=False, send=False)
        time.sleep(2)
        serial.send_bytes(stream, "\n", expect_prompt=False, send=False)
        time.sleep(4)


def setup_networking(stream, release):
    """
    Setup initial networking so we can transfer files.
    """
    ip = "10.10.10.3"
    host_ip = "10.10.10.254"
    if release == "R2":
        interface = "eth0"
    else:
        interface = "enp0s3"
    ret = serial.send_bytes(stream, "/sbin/ip address list", prompt='10.10.10.3', fail_ok=True, timeout=10)
    if ret != 0:
        LOG.info("Setting networking up.")
    else:
        LOG.info("Skipping networking setup")
        return
    LOG.info("{} being set up with ip {}".format(interface, ip))
    serial.send_bytes(stream, "sudo /sbin/ip addr add {}/24 dev {}".format(ip, interface), expect_prompt=False)
    host_helper.check_password(stream)
    time.sleep(2)
    serial.send_bytes(stream, "sudo /sbin/ip link set {} up".format(interface), expect_prompt=False)
    host_helper.check_password(stream)
    time.sleep(2)
    serial.send_bytes(stream, "sudo route add default gw {}".format(host_ip), expect_prompt=False)
    host_helper.check_password(stream)

    NETWORKING_TIME = 60
    LOG.info("Wait a minute for networking to be established")
    time.sleep(NETWORKING_TIME)

    # Ping from machine hosting virtual box to virtual machine
    # rc = subprocess.call(['ping', '-c', '3', ip])
    # assert rc == 0, "Network connectivity test failed"


@pytest.mark.unit
def test_install_vbox(controller_type, securityprofile, release, lowlatency, install_mode):
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
    sock = serial.connect("controller-0", 10000)
    cont0_stream = streamexpect.wrap(sock, echo=True, close_stream=False)
    LOG.info("Starting installation of controller-0")
    start_time=time.time()
    menu_selector(cont0_stream, controller_type, securityprofile, release, lowlatency, install_mode)
    serial.expect_bytes(cont0_stream, 'login:', timeout=HostTimeout.INSTALL)
    LOG.info("Completed installation of controller-0.")
    kpi.CONT0INSTALL = time.time() - start_time
    # Change password on initial login
    LOG.info("Controller-0 install duration: {} minutes".format(kpi.CONT0INSTALL/60))
    time.sleep(10)
    host_helper.change_password(cont0_stream)
    # Disable user logout
    host_helper.disable_logout(cont0_stream)

    # Setup basic networking
    time.sleep(10)

    setup_networking(cont0_stream, release)
    return sock, cont0_stream
    

def test_install_nodes(cont0_stream, host_list=None):
    """
    Tests node install, requires controller-0 to be installed previously
    Args:
        host_list(list): list of host names to install.
    Steps:
        - Power on nodes and create stream to them.
        - Set personalities for nodes
        - Wait for nodes to finish installing
        - Returns streams for future use
    13-25 mins
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
    LOG.info(host_list)
    threads = []
    new_thread = []
    port = 10001
    serial.send_bytes(cont0_stream, "source /etc/nova/openrc", prompt='keystone')
    for host in host_list:
        stream = streamexpect.wrap(serial.connect('{}'.format(host), port), echo=True, close_stream=False)
        time.sleep(10)
        streams[host] = stream
        if 'controller' in host:
            new_thread.append(threading.InstallThread(cont0_stream, '{} thread'.format(host), host, 'controller',
                                                      host_id))
        elif 'compute' in host:
            new_thread.append(threading.InstallThread(cont0_stream, '{} thread'.format(host), host, 'compute', host_id))
        else:
            new_thread.append(threading.InstallThread(cont0_stream, '{} thread'.format(host), host, 'storage', host_id))
        host_id += 1
        port += 1

    for host in new_thread:
        host.start()
        time.sleep(2)
        threads.append(host)
    
    for items in threads:
        items.join(HostTimeout.HOST_INSTALL)

    # Look for login
    # Close the stream if we want
    start_time = time.time()
    for host in host_list:
        serial.expect_bytes(streams[host], "login:", HostTimeout.HOST_INSTALL)
        LOG.info("{} installation complete".format(host))
        # stream.close()

    kpi.NODEINSTALL = time.time()-start_time
    LOG.info("Node install time: {} minutes".format(kpi.NODEINSTALL/60))
    # Return streams dict in case we need to reference the streams later
    return streams


def create_vms(vboxoptions):
    """
    Creates vms using the arguments in vboxoptions.
    Takes about 4 mins
    """
    # Semantic checks
    assert not (vboxoptions.aio == True and vboxoptions.storage), "AIO cannot have storage nodes"
    assert not (vboxoptions.aio == True and vboxoptions.computes), "AIO cannot have compute nodes"
    assert not (
        vboxoptions.deletelab == True and vboxoptions.useexistinglab), "These options are incompatible with each other"
    if vboxoptions.release:
        assert vboxoptions.buildserver, "Must provide build server if release is specified"
    if vboxoptions.buildserver:
        assert vboxoptions.release, "Must provide release if build server is specified"
    # LOG.info("Retrieving vbox extention pack")
    # Doesn't work automatically because it requires admin privileges and asks for a prompt
    # vboxmanage.vboxmanage_extpack()
    node_list = []
    vm_list = vboxmanage.vboxmanage_list("vms")
    LOG.info("The following VMs are present on the system: {}".format(vm_list))
    for item in vm_list:
        if b'controller-' in item or b'compute-' in item or b'storage-' in item:
            node_list.append(item)
    # Delete VMs if the user requests it
    if vboxoptions.deletelab == True and len(node_list) != 0:
        LOG.info("Deleting existing VMs as requested by user: {}".format(node_list))
        vboxmanage.vboxmanage_controlvms(node_list, "poweroff")
        time.sleep(5)
        vboxmanage.vboxmanage_deletevms(node_list)

    # Pull in node configuration
    node_config = [getattr(Nodes, attr) for attr in dir(Nodes) if not attr.startswith('__')]
    nic_config = [getattr(NICs, attr) for attr in dir(NICs) if not attr.startswith('__')]
    oam_config = [getattr(OAM, attr) for attr in dir(OAM) if not attr.startswith('__')][0]
    buildservers = [getattr(env.BuildServers, attr) for attr in dir(env.BuildServers) if not attr.startswith('__')]
    licenses = [getattr(env.Licenses, attr) for attr in dir(env.Licenses) if not attr.startswith('__')]
    builds = [getattr(env.Builds, attr) for attr in dir(env.Builds) if not attr.startswith('__')]
    serial_config = [getattr(Serial, attr) for attr in dir(Serial) if not attr.startswith('__')]

    # Determine how to setup the controllers
    if vboxoptions.storage:
        controller_type = 'controller_ceph'
    elif vboxoptions.aio:
        controller_type = 'controller_aio'
    else:
        controller_type = 'controller_lvm'

    # Create and setup nodes
    if vboxoptions.useexistinglab == False:

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
        port = 10000
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
            if platform == 'win32' or platform == 'win64':
                vboxmanage.vboxmanage_modifyvm(node, uartbase=serial_config[0]['uartbase'],
                                               uartport=serial_config[0]['uartport'],
                                               uartmode=serial_config[0]['uartmode'],
                                               uartpath=port)
                port += 1
            else:
                vboxmanage.vboxmanage_modifyvm(node, uartbase=serial_config[0]['uartbase'],
                                               uartport=serial_config[0]['uartport'],
                                               uartmode=serial_config[0]['uartmode'],
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
    if vboxoptions.useexistingiso is False and vboxoptions.iso_location is None:
        for item in builds:
            if item['release'] == vboxoptions.release:
                remote_path = item['iso']
        for item in buildservers:
            if item['short_name'].upper() == vboxoptions.buildserver:
                remote_server = item['ip']
        sftp_get(remote_path, remote_server, env.ISOPATH.format(vboxoptions.release))
        PATH = env.ISOPATH.format(vboxoptions.release)
    elif vboxoptions.iso_location:
        PATH = vboxoptions.iso_location
        LOG.info("Setup will proceed with existing ISO {} as requested by user".format(PATH))
        assert os.path.isfile(PATH), "ISO doesn't exist at: {}".format(PATH)
    else:
        LOG.info("Setup will proceed with existing ISO {} as requested by user".format(
            env.ISOPATH.format(vboxoptions.release)))
        assert os.path.isfile(env.ISOPATH.format(vboxoptions.release)), \
            "ISO doesn't exist at: {}".format(env.ISOPATH.format(vboxoptions.release))
        PATH = env.ISOPATH.format(vboxoptions.release)
    # Need a more programatic way to do this rather than hardcoding device - INVESTIGATE
    vboxmanage.vboxmanage_storageattach(storetype="dvddrive", disk=PATH, device_num="1", port_num="1")

    # END VBOX SETUP

    # Start installing the system
    sock, cont0_stream = test_install_vbox(controller_type, vboxoptions.securityprofile, vboxoptions.release,
                                           vboxoptions.lowlatency,
                                           install_mode=vboxoptions.install_mode)
    return sock, cont0_stream

    
if __name__ == "__main__":
    """
    Main installation.
    Installation steps are dependant on arguments passed in.
    Full installation steps:
        - Install controller-0
        - Transfer files
        - Install Patches
        - Run config_controller
        - Install other nodes
        - Run lab_setup iterations
    """
    kpi.TOTALTIME = time.time()
    # pdb.set_trace()
    # START VBOX SETUP
    vboxoptions = handle_args().parse_args()
    if platform == 'win32' or platform == 'win64':
        if not os.path.exists(env.FILEPATH):
            os.mkdir(env.FILEPATH)
        if not os.path.exists(env.FILEPATH+vboxoptions.release):
            os.mkdir(env.FILEPATH+vboxoptions.release)
        if not os.path.exists(env.LOGPATH):
            os.mkdir(env.LOGPATH)
    else:
        if not os.path.exists(env.FILEPATH):
            os.mkdir(env.FILEPATH)
        if not os.path.exists(env.FILEPATH+vboxoptions.release):
            os.mkdir(env.FILEPATH+vboxoptions.release)
        if not os.path.exists(env.LOGPATH):
            os.mkdir(env.LOGPATH)
    if vboxoptions.nessus:
        vboxoptions.install_lab = True
        vboxoptions.run_scripts = True
        vboxoptions.iso_location = env.ISOPATH.format(vboxoptions.release)
        vboxoptions.patch_dir = env.FILEPATH + vboxoptions.release + "/patches/"
        vboxoptions.install_patches = True
        vboxoptions.deletelab = True
        vboxoptions.createlab = True
        vboxoptions.setup_files = env.FILEPATH + vboxoptions.release
        vboxoptions.buildserver = 'CGTS4'
    elif vboxoptions.complete:
        assert vboxoptions.buildserver, "Buildserver must be specified."
        vboxoptions.install_lab = True
        vboxoptions.run_scripts = True
        if vboxoptions.release != "R5":
            vboxoptions.get_patches = True
            vboxoptions.install_patches = True
        vboxoptions.deletelab = True
        vboxoptions.createlab = True
        vboxoptions.get_setup = True
        if (vboxoptions.release == 'R5' or vboxoptions.release == "R2") or vboxoptions.config_file:
            vboxoptions.configure = True
    if vboxoptions.controllers is None and vboxoptions.computes is None:
        if vboxoptions.aio:
            vboxoptions.controllers = 2
        else:
            vboxoptions.controllers = 2
            vboxoptions.computes = 2
    LOG.info(vboxoptions)
    if vboxoptions.createlab:
        sock, cont0_stream = create_vms(vboxoptions)
        node_list = []
        for item in vboxmanage.vboxmanage_list('vms'):
            if b'controller' in item or b'compute' in item or b'storage' in item:
                node_list.append(item.decode('utf-8'))
        LOG.info(node_list)
        assert 'controller-0' in node_list, "controller-0 not in vm list. Stopping installation."
    else:
        # if vms were created this should be done already
        node_list = []
        for item in vboxmanage.vboxmanage_list('vms'):
            if b'controller' in item or b'compute' in item or b'storage' in item:
                node_list.append(item.decode('utf-8'))
        LOG.info(node_list)
        assert 'controller-0' in node_list, "controller-0 not in vm list. Stopping installation."
        sock = serial.connect("controller-0", 10000)
        cont0_stream = streamexpect.wrap(sock, echo=True, close_stream=False)
        host_helper.login(cont0_stream, timeout=60)
        setup_networking(cont0_stream, vboxoptions.release)
    buildservers = [getattr(env.BuildServers, attr) for attr in dir(env.BuildServers) if not attr.startswith('__')]
    for item in buildservers:
        if item['short_name'].upper() == vboxoptions.buildserver:
            remote_server = item['ip']
    if vboxoptions.buildserver is None:
        remote_server = None
    if vboxoptions.setup_files:
        install_lab.get_lab_setup_files(cont0_stream, local_path=vboxoptions.setup_files)
    elif vboxoptions.get_setup:
        install_lab.get_lab_setup_files(cont0_stream, remote_host=remote_server, release=vboxoptions.release)
    if vboxoptions.patch_dir:
        install_lab.get_patches(cont0_stream, vboxoptions.patch_dir, release=vboxoptions.release)
    elif vboxoptions.get_patches:
        install_lab.get_patches(cont0_stream, remote_host=remote_server, release=vboxoptions.release)
    if vboxoptions.config_file:
        sftp_send(vboxoptions.config_file, destination="/home/wrsroot/TiS_config.ini_centos")
    elif vboxoptions.get_config:
        install_lab.get_config_file(remote_server, release=vboxoptions.release)
    # Configures controller-0
    if vboxoptions.install_patches:
        install_lab.install_patches_before_config(cont0_stream, vboxoptions.release)
    if not vboxoptions.configure and not vboxoptions.config_file:
        LOG.info("Pausing to allow for manual configuration. If any files are to be transferred manually please do so"
                 " now. Press enter to continue.")
        input()
    if vboxoptions.configure:
        remote_host = vboxoptions.buildserver
        ret = install_lab.config_controller(cont0_stream, config_file='/home/wrsroot/TiS_config.ini_centos',
                                            release=vboxoptions.release, remote_host=remote_server)
        if ret == 1:
            LOG.info("Pausing to allow for manual configuration. Press enter to continue.")
            input()
        if vboxoptions.release == 'R5':
            if vboxoptions.lvm:
                install_lab.enable_lvm(cont0_stream, vboxoptions.release)
            # wait for online status, run lab_setup, unlock cont0, provision hosts, continue from before.
            serial.send_bytes(cont0_stream, "source /etc/nova/openrc", prompt='keystone')
            install_lab.install_controller_0(cont0_stream)

    # installs nodes
    streams = {}
    if vboxoptions.install_lab and not vboxoptions.aio:
        LOG.info("Starting lab installation.")
        streams = test_install_nodes(cont0_stream, host_list=node_list)
    # runs lab_setup.sh
    if vboxoptions.run_scripts:

        install_lab.run_install_scripts(cont0_stream, host_list=node_list, aio=vboxoptions.aio,
                                        storage=vboxoptions.storage, release=vboxoptions.release, streams=streams)
    host_helper.logout(cont0_stream)
    serial.disconnect(sock)
    LOG.info("Installation complete.")
    kpi.get_kpi_metrics()
    LOG.info("Total time taken: {} minutes".format((time.time() - kpi.TOTALTIME) / 60))
