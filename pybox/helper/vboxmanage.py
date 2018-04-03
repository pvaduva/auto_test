#!/usr/bin/python3

import subprocess
import re
import getpass
from utils.install_log import LOG
import time
from sys import platform
from consts import env


def vboxmanage_version():
    """ 
    Return version of vbox.
    """

    version = subprocess.check_output(['vboxmanage', '--version'], stderr = subprocess.STDOUT)

    return version


def vboxmanage_extpack(action="install"):
    """
    This allows you to install, uninstall the vbox extensions"
    """
    output = vboxmanage_version()
    version = re.match(b'(.*)r', output)
    version_path = version.group(1).decode('utf-8')

    LOG.info("Downloading extension pack")
    filename = 'Oracle_VM_VirtualBox_Extension_Pack-{}.vbox-extpack'.format(version_path)
    cmd = 'http://download.virtualbox.org/virtualbox/{}/{}'.format(version_path, filename)
    result = subprocess.check_output(['wget', cmd, '-P', '/tmp'], stderr=subprocess.STDOUT)
    LOG.info(result)

    LOG.info("Installing extension pack")
    result = subprocess.check_output(['vboxmanage', 'extpack', 'install', '/tmp/' + filename, '--replace'],
                                     stderr=subprocess.STDOUT)
    LOG.info(result)


def vboxmanage_list(option="vms"):
    """
    This returns a list of vm names. 
    """
    result = subprocess.check_output(['vboxmanage', 'list', option], stderr=subprocess.STDOUT)
    vms_list = []
    for item in result.splitlines():
        vm_name = re.match(b'"(.*?)"', item)
        vms_list.append(vm_name.group(1))

    return vms_list


def vboxmanage_showinfo(host):
    """
    This returns info about the host 
    """
    if not isinstance(host, str):
        host.decode('utf-8')
    result = subprocess.check_output(['vboxmanage', 'showvminfo', host, '--machinereadable'], stderr=subprocess.STDOUT)
    return result


def vboxmanage_createvm(hostname=None):
    """
    This creates a VM with the specified name.
    """

    assert hostname, "Hostname is required"
    LOG.info("Creating VM {}".format(hostname))
    result = subprocess.check_output(['vboxmanage', 'createvm', '--name', hostname, '--register', '--ostype',
                                      'Linux_64'], stderr=subprocess.STDOUT)


def vboxmanage_deletevms(hosts=None):
    """
    Deletes a list of VMs
    """

    assert hosts, "A list of hostname(s) is required"

    if len(hosts) != 0:
        for hostname in hosts:
            LOG.info("Deleting VM {}".format(hostname))
            result = subprocess.check_output(['vboxmanage', 'unregistervm', hostname, '--delete'],
                                             stderr=subprocess.STDOUT)

    vms_list = vboxmanage_list("vms")
    for items in hosts:
        assert items not in vms_list, "The following vms are unexpectedly present {}".format(vms_list)


def vboxmanage_hostonlyifcreate(name="vboxnet0", ip=None, netmask=None):
    """
    This creates a hostonly network for systems to communicate.
    """

    assert name, "Must provide network name"
    assert ip, "Must provide an OAM IP"
    assert netmask, "Must provide an OAM Netmask"

    LOG.info("Creating Host-only Network")

    result = subprocess.check_output(['vboxmanage', 'hostonlyif', 'create'], stderr=subprocess.STDOUT)

    LOG.info("Provisioning {} with IP {} and Netmask {}".format(name, ip, netmask))
    result = subprocess.check_output(['vboxmanage', 'hostonlyif', 'ipconfig', name, '--ip', ip, '--netmask',
                                      netmask], stderr=subprocess.STDOUT)


def vboxmanage_hostonlyifdelete(name="vboxnet0"):
    """
    Deletes hostonly network. This is used as a work around for creating too many hostonlyifs.

    """
    assert name, "Must provide network name"
    LOG.info("Removing Host-only Network")
    result = subprocess.check_output(['vboxmanage', 'hostonlyif', 'remove', name], stderr=subprocess.STDOUT)


def vboxmanage_modifyvm(hostname=None, cpus=None, memory=None, nic=None, nictype=None, nicpromisc=None, nicnum=None,
                        intnet=None, hostonlyadapter=None, uartbase=None, uartport=None,
                        uartmode=None, uartpath=None, nicbootprio2=1):
    """
    This modifies a VM with a specified name.
    """

    assert hostname, "Hostname is required"
    # Add more semantic checks
    cmd = ['vboxmanage', 'modifyvm', hostname]
    if cpus:
        cmd.extend(['--cpus', cpus])
    if memory:
        cmd.extend(['--memory', memory])
    if nic and nictype and nicpromisc and nicnum:
        cmd.extend(['--nic{}'.format(nicnum), nic])
        cmd.extend(['--nictype{}'.format(nicnum), nictype])
        cmd.extend(['--nicpromisc{}'.format(nicnum), nicpromisc])
        if intnet:
            cmd.extend(['--intnet{}'.format(nicnum), intnet])
        if hostonlyadapter:
            cmd.extend(['--hostonlyadapter{}'.format(nicnum), hostonlyadapter])
    if uartbase and uartport and uartmode and uartpath:
        cmd.extend(['--uart1'])
        cmd.extend(['{}'.format(uartbase)])
        cmd.extend(['{}'.format(uartport)])
        cmd.extend(['--uartmode1'])
        cmd.extend(['{}'.format(uartmode)])
        if platform == 'win32' or platform == 'win64':
            cmd.extend(['{}'.format(env.PORT)])
            env.PORT += 1
        else:
            if 'controller-0' in hostname:
                cmd.extend(['{}{}_serial'.format(uartpath, hostname)])
            else:
                cmd.extend(['{}{}'.format(uartpath, hostname)])
    if nicbootprio2:
        cmd.extend(['--nicbootprio2'])
        cmd.extend(['{}'.format(nicbootprio2)])
    cmd.extend(['--boot4']) 
    cmd.extend(['net'])
    LOG.info(cmd)

    LOG.info("Updating VM {} configuration".format(hostname))
    result = subprocess.check_output(cmd, stderr=subprocess.STDOUT)


def vboxmanage_storagectl(hostname=None, storectl="sata", hostiocache="on"):
    """
    This creates a storage controller on the host.
    """

    assert hostname, "Hostname is required"
    assert storectl, "Type of storage controller is required"
    LOG.info("Creating {} storage controller on VM {}".format(storectl, hostname))
    result = subprocess.check_output(['vboxmanage', 'storagectl', hostname, '--name', storectl, '--add', storectl, '--hostiocache', hostiocache],
                                     stderr=subprocess.STDOUT)


def vboxmanage_storageattach(hostname=None, storectl="sata", storetype="hdd", disk=None, port_num="0",
                             device_num="0"):
    """
    This attaches a disk to a controller.
    """

    assert hostname, "Hostname is required"
    assert disk, "Disk name is required"
    assert storectl, "Name of storage controller is required"
    assert storetype, "Type of storage controller is required"
    LOG.info("Attaching {} storage to storage controller {} on VM {}".format(storetype, storectl, hostname))
    result = subprocess.check_output(['vboxmanage', 'storageattach', hostname, '--storagectl', storectl,
                                      '--medium', disk, '--type', storetype, '--port', port_num, '--device',
                                      device_num], stderr=subprocess.STDOUT)
    return result


def vboxmanage_createmedium(hostname=None, disk_list=None):
    """
    This creates the required disks.
    """

    assert hostname, "Hostname is required"
    assert disk_list, "A list of disk sizes is required"

    ## TODO (WEI): fix it
    disk_dir = "/folk/cgts/users/"

    username = getpass.getuser()
    device_num = 0
    port_num = 0
    disk_count = 1
    for disk in disk_list:
        if platform == 'win32' or platform == 'win64':
            file_name = "C:\\Users\\" + username + "\\vbox_disks\\" + hostname + "_disk_{}".format(disk_count)
        else:
            #file_name = "/home/" + username + "/vbox_disks/" + hostname + "_disk_{}".format(disk_count)
            ## TODO (WEI): This is for me only
            file_name = disk_dir + username + "/vbox_disks/" + hostname + "_disk_{}".format(disk_count)
        LOG.info("Creating disk {} with size {} on VM {} on device {} port {}".format(file_name, disk, hostname, device_num, port_num))

        result = subprocess.check_output(['vboxmanage', 'createmedium', 'disk', '--size', str(disk), '--filename',
                                          file_name, '--format', 'vdi', '--variant', 'standard'],
                                         stderr=subprocess.STDOUT)
        LOG.info(result)
        vboxmanage_storageattach(hostname, "sata", "hdd", file_name + ".vdi", str(port_num), str(device_num))
        disk_count += 1
        port_num += 1 


def vboxmanage_startvm(hostname=None):
    """
    This allows you to power on a VM.
    """

    assert hostname, "Hostname is required"

    LOG.info("Check if VM is running")
    running_vms = vboxmanage_list(option="runningvms")
    LOG.info(running_vms)

    if hostname.encode('utf-8') in running_vms:
        LOG.info("Host {} is already started".format(hostname))
    else:
        LOG.info("Powering on VM {}".format(hostname))
        # TODO (WEI) make it headless later
        result = subprocess.check_output(['vboxmanage', 'startvm', hostname, '--type', 'headless'], stderr=subprocess.STDOUT)
        #result = subprocess.check_output(['vboxmanage', 'startvm', hostname], stderr=subprocess.STDOUT)
        LOG.info(result)


def vboxmanage_controlvms(hosts=None, action=None):
    """
    This allows you to control a VM, e.g. pause, resume, etc.
    """

    assert hosts, "Hostname is required"
    assert action, "Need to provide an action to execute"
 
    for host in hosts:
        LOG.info("Executing {} action on VM {}".format(action, host))
        result = subprocess.call(["vboxmanage", "controlvm", host, action], stderr=subprocess.STDOUT)
    time.sleep(1)


## TODO (WEI): Add an "action" (take, restore, etc.) parameter to combine snapshot functions
def vboxmanage_takesnapshot(hosts=None, name=None):
    """
    This allows you to take snapshot of VMs.
    """

    assert hosts, "Hostname is required"
    assert name, "Need to provide a name for the snapshot"

    for host in hosts:
        LOG.info("Taking snapshot {} on VM {}".format(name, host))
        result = subprocess.call(["vboxmanage", "snapshot", host, "take", name], stderr=subprocess.STDOUT)
    time.sleep(10)


def vboxmanage_restoresnapshot(host=None, name=None):
    """
    This allows you to restore snapshot of a VM.
    """

    assert host, "Hostname is required"
    assert name, "Need to provide the snapshot to restore"

    LOG.info("Restoring snapshot {} on VM {}".format(name, host))
    result = subprocess.call(["vboxmanage", "snapshot", host, "restore", name], stderr=subprocess.STDOUT)
    time.sleep(10)

