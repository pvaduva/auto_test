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
    sys.exit(1)
    
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


def setup_networking(stream, release, ctrlr0_ip, password='Li69nux*'):
    """
    Setup initial networking so we can transfer files.
    """
    ip = ctrlr0_ip 
    host_ip = "10.10.10.254"
    if release == "R2":
        interface = "eth0"
    else:
        interface = "enp0s3"
    ret = serial.send_bytes(stream, "/sbin/ip address list", prompt=ctrlr0_ip, fail_ok=True, timeout=10)
    if ret != 0:
        LOG.info("Setting networking up.")
    else:
        LOG.info("Skipping networking setup")
        return
    LOG.info("{} being set up with ip {}".format(interface, ip))
    serial.send_bytes(stream, "sudo /sbin/ip addr add {}/24 dev {}".format(ip, interface), expect_prompt=False)
    host_helper.check_password(stream, password=password)
    time.sleep(2)
    serial.send_bytes(stream, "sudo /sbin/ip link set {} up".format(interface), expect_prompt=False)
    host_helper.check_password(stream, password=password)
    time.sleep(2)
    serial.send_bytes(stream, "sudo route add default gw {}".format(host_ip), expect_prompt=False)
    host_helper.check_password(stream, password=password)

    NETWORKING_TIME = 60
    LOG.info("Wait a minute for networking to be established")
    time.sleep(NETWORKING_TIME)

    # Ping from machine hosting virtual box to virtual machine
    # rc = subprocess.call(['ping', '-c', '3', ip])
    # assert rc == 0, "Network connectivity test failed"


@pytest.mark.unit
def install_controller_0(cont0_stream, controller_type, securityprofile, release, lowlatency,
                         install_mode, ctrlr0_ip, username='wrsroot', password='Li69nux*'):
    """
    Installation of controller-0.
    Takes about 30 mins
    """
    # Power on controller-0
    # Install controller-0
    # Login
    # Change default password
    # Setup basic networking
    # Return socket and stream

    LOG.info("Starting installation of controller-0")
    start_time=time.time()
    menu_selector(cont0_stream, controller_type, securityprofile, release, lowlatency, install_mode)
    serial.expect_bytes(cont0_stream, 'login:', timeout=HostTimeout.INSTALL)
    LOG.info("Completed installation of controller-0.")
    kpi.CONT0INSTALL = time.time() - start_time
    # Change password on initial login
    LOG.info("Controller-0 install duration: {} minutes".format(kpi.CONT0INSTALL/60))
    time.sleep(10)
    host_helper.change_password(cont0_stream, username=username, password=password)
    # Disable user logout
    host_helper.disable_logout(cont0_stream)

    # Setup basic networking
    time.sleep(10)
    setup_networking(cont0_stream, release, ctrlr0_ip, password=password)
    

def start_and_connect_nodes(host_list=None):
    """
    Start and connect to other nodes. 
    It requires controller-0 to be installed already 
    Args:
        host_list(list): list of host names to start and connect to.
    Steps:
        - Power on nodes and create stream to them.
        - Returns sockets and streams for future use
    """
    streams = {}
    socks = {}

    LOG.info(host_list)
    port = 10001
    for host in host_list:
        sock = serial.connect('{}'.format(host), port)
        stream = streamexpect.wrap(sock, echo=True, close_stream=False)
        time.sleep(10)
        socks[host] = sock
        streams[host] = stream
        port += 1

    return socks, streams

def test_install_nodes(cont0_stream, socks, streams, labname, host_list=None):
    """
    Tests node install, requires controller-0 to be installed previously
    Args:
        cont0_stream:
        socks:
        streams:
        host_list(list): list of host names to install.
    Steps:
        - Create multiple threads
        - Set personalities for nodes
        - Wait for nodes to finish installing
    13-25 mins
    """

    host_id = 2

    LOG.info("test_install_nodes")
    LOG.info(host_list)
    threads = []
    new_thread = []
    serial.send_bytes(cont0_stream, "source /etc/nova/openrc", prompt='keystone')
    for host in host_list:
        ## Remove the lab name from the host
        tis_host = host[len(labname)+1:]
        time.sleep(10)
        if 'controller' in tis_host:
            new_thread.append(threading.InstallThread(cont0_stream, '{} thread'.format(tis_host), tis_host, 'controller',
                                                      host_id))
        elif 'compute' in tis_host:
            new_thread.append(threading.InstallThread(cont0_stream, '{} thread'.format(tis_host), tis_host, 'compute', host_id))
        else:
            new_thread.append(threading.InstallThread(cont0_stream, '{} thread'.format(tis_host), tis_host, 'storage', host_id))
        host_id += 1

    for host in new_thread:
        host.start()
        ## WZWZ double check this
        #time.sleep(2)
        time.sleep(10)
        threads.append(host)
    
    for items in threads:
        items.join(HostTimeout.HOST_INSTALL)

    """
    host_id = 2

    LOG.info(host_list)
    serial.send_bytes(cont0_stream, "source /etc/nova/openrc", prompt='keystone')
    for host in host_list:
        if 'controller' in host:
            host_helper.install_host(cont0_stream, host, 'controller', host_id)
        elif 'compute' in host:
            host_helper.install_host(cont0_stream, host, 'compute', host_id)
        else:
            host_helper.install_host(cont0_stream, host, 'storage', host_id)
        host_id += 1
    """

    # Now wait for nodes to come up. Look for login.
    # Close the socket if we are done  
    start_time = time.time()
    for host in host_list:
        try:
            serial.expect_bytes(streams[host], "login:", HostTimeout.HOST_INSTALL)
            LOG.info("{} installation complete".format(host))
            # serial.disconnect(socks[host])
        except Exception as e:
            LOG.info("Connection failed for host {} with {}.".format(host, e))
            ## Sometimes we get UnicodeDecodeError exception due to the output 
            ## of installation. So try one more time maybe
            LOG.info("WEI so try wait for {} login again?".format(host))
            if HostTimeout.HOST_INSTALL > (time.time()-start_time):
                serial.expect_bytes(streams[host], "login:", HostTimeout.HOST_INSTALL-(time.time()-start_time))
            #serial.disconnect(socks[host])
        #time.sleep(5)

    kpi.NODEINSTALL = time.time()-start_time
    LOG.info("Node install time: {} minutes".format(kpi.NODEINSTALL/60))

def get_all_vms(labname, option="vms"):
    node_list = []
    vm_list = vboxmanage.vboxmanage_list(option)
    LOG.info("The following VMs are present on the system: {}".format(vm_list))

    labname.encode('utf-8')
    for item in vm_list:
        if labname.encode('utf-8') in item and (b'controller-' in item or \
           b'compute-' in item or b'storage-' in item):
            node_list.append(item.decode('utf-8'))

    #print ("node list ", node_list)
    return node_list

def take_snapshot(labname, snapshot_name):
    node_list = get_all_vms(labname, option="runningvms")
    hosts = len(node_list)
    if hosts != 0:
        LOG.info("Taking snapshot of {}".format(snapshot_name))
        vboxmanage.vboxmanage_controlvms(node_list, "pause")
        time.sleep(5)
        vboxmanage.vboxmanage_takesnapshot(node_list, snapshot_name)
        time.sleep(5)
        vboxmanage.vboxmanage_controlvms(node_list, "resume")
        time.sleep(10)

    node_list = get_all_vms(labname, option="runningvms")
    retry = 0
    while retry < 20:
        LOG.info("Waiting for VMs to come up running after taking snapshot..."
                 "Up VMs are {} ".format(node_list))
        if len(node_list) < hosts:
            time.sleep(5)
            node_list = get_all_vms(labname, option="runningvms")
            retry += 1
        else:
            LOG.info("All VMs {} are up running after taking snapshot...".format(node_list))
            break
    ## TODO (WEI): add a return code to indicate if VMs are up running or not


def restore_snapshot(node_list, name):
    LOG.info("Restore snapshot of {} for hosts {}".format(name, node_list))
    if len(node_list) != 0:
        vboxmanage.vboxmanage_controlvms(node_list, "poweroff")
        time.sleep(5)
    if len(node_list) != 0:
        for host in node_list:
            vboxmanage.vboxmanage_restoresnapshot(host, name)
            time.sleep(5)
        for host in node_list:
            if "controller-0" not in host:
                vboxmanage.vboxmanage_startvm(host)
                time.sleep(10)
        for host in node_list:
            if "controller-0" in host:
                vboxmanage.vboxmanage_startvm(host)
                time.sleep(10) 
    ## TODO (WEI) Before return make sure VM is up running again
    ## Not needed. vboxmanage.vboxmanage_startvm() returns when vm is running


def delete_lab(labname):
    node_list = get_all_vms(labname, option="vms")

    if vboxoptions.debug_rest:
        node_list.remove(labname + "-controller-0")

    if len(node_list) != 0:
        LOG.info("Deleting existing VMs: {}".format(node_list))
        vboxmanage.vboxmanage_controlvms(node_list, "poweroff")
        time.sleep(5)
        vboxmanage.vboxmanage_deletevms(node_list)

def create_lab(vboxoptions):
    """
    Creates vms using the arguments in vboxoptions.
    Takes about 4 mins
    """
    # Semantic checks
    assert not (vboxoptions.aio == True and vboxoptions.storage), "AIO cannot have storage nodes"
    assert not (vboxoptions.aio == True and vboxoptions.computes), "AIO cannot have compute nodes"
    assert not (
        vboxoptions.deletelab == True and vboxoptions.useexistinglab), "These options are incompatible with each other"
    ## WEI TODO: double check this
    #if vboxoptions.release:
    #    assert vboxoptions.buildserver, "Must provide build server if release is specified"
    if vboxoptions.buildserver:
        assert vboxoptions.release, "Must provide release if build server is specified"
    # LOG.info("Retrieving vbox extention pack")
    # Doesn't work automatically because it requires admin privileges and asks for a prompt
    # vboxmanage.vboxmanage_extpack()

    # Delete VMs if the user requests it
    if vboxoptions.deletelab == True:
        delete_lab(vboxoptions.labname)

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
                node_name = vboxoptions.labname + "-controller-{}".format(id)
                nodes_list.append(node_name)
        if vboxoptions.computes:
            for id in range(0, vboxoptions.computes):
                node_name = vboxoptions.labname + "-compute-{}".format(id)
                nodes_list.append(node_name)
        if vboxoptions.storage:
            for id in range(0, vboxoptions.storage):
                node_name = vboxoptions.labname + "-storage-{}".format(id)
                nodes_list.append(node_name)

        ### WZWZ to debug 
        if vboxoptions.debug_rest:
            nodes_list.remove(vboxoptions.labname + "-controller-0")

        LOG.info("We will create the following nodes: {}".format(nodes_list))
        port = 10000
        for node in nodes_list:
            vboxmanage.vboxmanage_createvm(node)
            vboxmanage.vboxmanage_storagectl(node, storectl="sata", hostiocache=vboxoptions.hostiocache)
            if "controller" in node:
                node_type = controller_type
            elif "compute" in node:
                node_type = "compute"
            elif "storage" in node:
                node_type = "storage"

            for item in node_config:
                if item['node_type'] == node_type:
                    vboxmanage.vboxmanage_modifyvm(node, cpus=str(item['cpus']), memory=str(item['memory']))
                    vboxmanage.vboxmanage_createmedium(node, item['disks'], vbox_home_dir=vboxoptions.vbox_home_dir)
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

            if "controller" in node:
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

    ## WZWZ to debug
    if vboxoptions.debug_rest:
        return controller_type

    # Determine ISO to use
    if vboxoptions.useexistingiso is False and vboxoptions.iso_location is None:
        for item in builds:
            if item['release'] == vboxoptions.release:
                remote_path = item['iso']
        for item in buildservers:
            if item['short_name'].upper() == vboxoptions.buildserver:
                remote_server = item['ip']
            else:
                print ("WEI temp fix. buildserver is not given. exit...")
                sys.exit(1)
        ##TODO (WEI): Fix it! Ensure that vboxoptions.buildserver is set in this scenario
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
    # TODO(WEI): Need a more programatic way to do this rather than hardcoding device and port - INVESTIGATE
    ctrlr0 = vboxoptions.labname + '-controller-0'
    vboxmanage.vboxmanage_storageattach(ctrlr0, storetype="dvddrive", disk=PATH, device_num="0", port_num="2")

    # END VBOX SETUP
    return controller_type


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

    # pdb.set_trace()
    # START VBOX SETUP
    vboxoptions = handle_args().parse_args()

    lab_config = [getattr(env.Lab, attr) for attr in dir(env.Lab) if not attr.startswith('__')]
    if vboxoptions.labname is None:
        vboxoptions.labname = lab_config[0]['name']

    if vboxoptions.controller0_ip is None:
        vboxoptions.controller0_ip = lab_config[0]['controller-0_ip']

    ## Just to delete the lab.
    ## Add this option for convenience 
    if vboxoptions.deletelab and not vboxoptions.createlab:
        delete_lab(vboxoptions.labname)
        LOG.info("lab {} is deleted.".format(vboxoptions.labname))
        sys.exit(0)

    ## WEI: Lab instal is quite stable up to the step when controller-0 is unlock.
    ##      So I do following to debug the rest.
    ## python3 install_vbox --createlab --debug-rest   (This will delete all the nodes except ctrlr-0, restore ctrlr-0, re-create rest of nodes.) 
    ## python3 install_vbox --install-lab
    if vboxoptions.createlab and vboxoptions.debug_rest:
        delete_lab(vboxoptions.labname)
        restore_snapshot([vboxoptions.labname + "-controller-0"], "snapshot-AFTER-unlock-controller-0")
 
    ## TODO (WEI): Sometimes compute nodes become locked/offline instead of locked/online
    if vboxoptions.run_scripts and vboxoptions.debug_rest and not vboxoptions.install_lab:
        vm_list = get_all_vms(vboxoptions.labname, option="vms")
        restore_snapshot(vm_list, "snapshot-AFTER-lab-install")
        time.sleep(120)

    kpi.TOTALTIME = time.time()

    ## First do semantic checks
    if not vboxoptions.release:
        vboxoptions.release = 'R5'

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
        #vboxoptions.patch_dir = env.FILEPATH + vboxoptions.release + "/patches/"
        vboxoptions.get_patches = False
        vboxoptions.install_patches = True
        vboxoptions.deletelab = True
        vboxoptions.createlab = True
        vboxoptions.setup_files = env.FILEPATH + vboxoptions.release
        vboxoptions.buildserver = 'CGTS4'
        vboxoptions.configure = True
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
    if vboxoptions.username is None:
        vboxoptions.username = lab_config[0]['username']
    if vboxoptions.password is None:
        vboxoptions.password = lab_config[0]['password'] 
    if vboxoptions.hostiocache:
        vboxoptions.hostiocache = 'on'
    else:
        vboxoptions.hostiocache = 'off'
    
    LOG.info(vboxoptions)

    ctrlr0 = vboxoptions.labname + "-controller-0" 

    if vboxoptions.createlab:
        controller_type = create_lab(vboxoptions)

        ## WZWZ to debug 
        if not vboxoptions.debug_rest:
            vboxmanage.vboxmanage_startvm(ctrlr0)
        else:
            time.sleep(30)

    node_list = get_all_vms(vboxoptions.labname, option="vms")
    LOG.info(node_list)
    assert ctrlr0 in node_list, "controller-0 not in vm list. Stopping installation."

    sock = serial.connect(ctrlr0, 10000)
    cont0_stream = streamexpect.wrap(sock, echo=True, close_stream=False)

    try:
        if not vboxoptions.debug_rest:
            if vboxoptions.createlab:
                install_controller_0(cont0_stream, controller_type, vboxoptions.securityprofile, 
                                     vboxoptions.release, vboxoptions.lowlatency, 
                                     install_mode=vboxoptions.install_mode, ctrlr0_ip=vboxoptions.controller0_ip,
                                     username=vboxoptions.username, password=vboxoptions.password)
            else:
                host_helper.login(cont0_stream, timeout=60, username=vboxoptions.username, password=vboxoptions.password)
                setup_networking(cont0_stream, vboxoptions.release, vboxoptions.controller0_ip, password=vboxoptions.password)

            ## WZWZ DEBUG
            ## Take snapshot
            #if vboxoptions.snapshot:
            #    take_snapshot(vboxoptions.labname, "snapshot-BEFORE-config-controller")

        buildservers = [getattr(env.BuildServers, attr) for attr in dir(env.BuildServers) if not attr.startswith('__')]
        for item in buildservers:
            if item['short_name'].upper() == vboxoptions.buildserver:
                remote_server = item['ip']
        if vboxoptions.buildserver is None:
            remote_server = None

        if vboxoptions.aio:
            host_type = "AIO-DX"
        else:
            host_type = "Standard"

        if vboxoptions.setup_files:
            install_lab.get_lab_setup_files(cont0_stream, local_path=vboxoptions.setup_files, 
                                            host_type=host_type, ctrlr0_ip=vboxoptions.controller0_ip, 
                                            username=vboxoptions.username, password=vboxoptions.password)
        elif vboxoptions.get_setup:
            install_lab.get_lab_setup_files(cont0_stream, remote_host=remote_server, release=vboxoptions.release, host_type=host_type)

        if vboxoptions.get_patches:
            install_lab.get_patches(cont0_stream, vboxoptions.controller0_ip, remote_host=remote_server, release=vboxoptions.release, 
                                    username=vboxoptions.username, password=vboxoptions.password)

        if vboxoptions.config_file:
            destination = "/home/" + vboxoptions.username + "/TiS_config.ini_centos"
            sftp_send(vboxoptions.config_file, remote_host=vboxoptions.controller0_ip, destination=destination,
                      username=vboxoptions.username, password=vboxoptions.password)
        elif vboxoptions.get_config:
            install_lab.get_config_file(vboxoptions.controller0_ip, remote_server, release=vboxoptions.release, 
                                        username=vboxoptions.username, password=vboxoptions.password)

        if vboxoptions.install_patches:
            install_lab.install_patches_before_config(cont0_stream, vboxoptions.release, username=vboxoptions.username, password=vboxoptions.password)

        if vboxoptions.configure and not vboxoptions.config_file and not vboxoptions.get_config:
            LOG.info("Pausing to allow for manual configuration. If any files are to be transferred "
                     "manually please do so now. Press enter to continue.")
            input()

        # Configures controller-0
        if vboxoptions.configure:
            ## WEI TODO: remove
            #if vboxoptions.enablehttps:
            #    config_file = '/home/wrsroot/system_config.centos_https'
            #else:
            #    config_file = '/home/wrsroot/system_config.centos_http'

            ## TODO (WEI): define a constant for config_file

            config_file = "/home/" + vboxoptions.username + "/TiS_config.ini_centos" 
            ret = install_lab.config_controller(cont0_stream, config_file=config_file,
                                                release=vboxoptions.release, remote_host=vboxoptions.buildserver,
                                                password=vboxoptions.password)
            if ret == 1:
                LOG.info("Pausing to allow for manual configuration. Press enter to continue.")
                input()

            ## WZWZ DEBUG
            #if vboxoptions.snapshot:
            #    take_snapshot(vboxoptions.labname, "snapshot-AFTER-config-controller")

            if vboxoptions.release == 'R5':
                # TODO (WEI): Remove it. cinder-volumes partition is created by lab_setup.sh
                # 
                #serial.send_bytes(cont0_stream, "source /etc/nova/openrc", prompt='keystone')
                #if vboxoptions.lvm:
                #    install_lab.enable_lvm(cont0_stream, vboxoptions.release)

                # wait for online status, run lab_setup, unlock cont0, provision hosts, continue from before.
                install_lab.lab_setup_controller_0_locked(cont0_stream,
                                                          username=vboxoptions.username, password=vboxoptions.password)

                if vboxoptions.snapshot:
                    take_snapshot(vboxoptions.labname, "snapshot-AFTER-unlock-controller-0")

        # Now install rest of the nodes
        LOG.info("Now installing rest of the nodes....")
        socks = {}
        streams = {}
        # Since we don't need to install controller-0, let's remove it
        node_list.remove(ctrlr0)

        # Don't want to mess with vms that aren't supposed to be.
        for item in node_list:
            if 'controller' not in item and 'compute' not in item and 'storage' not in item:
                node_list.remove(item)

        if vboxoptions.install_lab and not vboxoptions.aio:
            LOG.info("Starting lab installation after controller-0 is unlocked.")

            ## WZWZ to debug
            if vboxoptions.debug_rest:
                host_helper.login(cont0_stream, timeout=60, username=vboxoptions.username, password=vboxoptions.password)

            socks, streams = start_and_connect_nodes(host_list=node_list)
            try:
                test_install_nodes(cont0_stream, socks, streams, vboxoptions.labname, host_list=node_list)

                if vboxoptions.snapshot:
                    take_snapshot(vboxoptions.labname, "snapshot-AFTER-lab-install")

            except Exception as e:
                LOG.info("Install rest of nodes not successful. {}".format(e))
                for node in node_list:
                    serial.disconnect(socks[node])
                socks = {}
                streams = {}
                sys.exist(1)
            else: 
                for node in node_list:
                    serial.disconnect(socks[node])
                socks = {}
                streams = {}

        # runs lab_setup.sh
        if vboxoptions.run_scripts:
            ## WZWZ to debug
            if vboxoptions.debug_rest:
                host_helper.login(cont0_stream, timeout=60, username=vboxoptions.username, password=vboxoptions.password)
           
            if not streams:
                socks, streams = start_and_connect_nodes(host_list=node_list)

            try:
                install_lab.run_install_scripts(cont0_stream, host_list=node_list, aio=vboxoptions.aio,
                             storage=vboxoptions.storage, release=vboxoptions.release, 
                             socks=socks, streams=streams, labname=vboxoptions.labname, 
                             username=vboxoptions.username, password=vboxoptions.password)

                ## TODO: WEI uncomment it 
                #if vboxoptions.snapshot:
                #    take_snapshot(vboxoptions.labname, "snapshot-AFTER-lab-setup")
            except Exception as e:
                LOG.info("Run install script not successful. {}".format(e))
                for node in node_list:
                    serial.disconnect(socks[node])
            #else:
            #    for node in node_list:
            #        serial.disconnect(socks[node])

    except Exception as e:
        LOG.info("Oh no, something bad happened {}".format(e))
        host_helper.logout(cont0_stream)
        serial.disconnect(sock)
        raise
        
    host_helper.logout(cont0_stream)
    serial.disconnect(sock)
    LOG.info("Installation complete.")

    ## TODO (WEI): fix KPI and time numbers
    kpi.get_kpi_metrics()
    LOG.info("WEI These KPI numbers need to be fixed.")
    LOG.info("Total time taken: {} minutes".format((time.time() - kpi.TOTALTIME) / 60))
