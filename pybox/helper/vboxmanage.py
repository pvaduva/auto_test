#!/usr/bin/python3

import subprocess
import re
import getpass

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

    print("Downloading extension pack")
    filename = 'Oracle_VM_VirtualBox_Extension_Pack-{}.vbox-extpack'.format(version_path)
    cmd = 'http://download.virtualbox.org/virtualbox/{}/{}'.format(version_path, filename)
    result = subprocess.check_output(['wget', cmd, '-P', '/tmp'], stderr = subprocess.STDOUT)
    print(result)

    print("Installing extension pack")
    result = subprocess.check_output(['vboxmanage', 'extpack', 'install', '/tmp/' + filename, '--replace'], stderr = subprocess.STDOUT)
    print(result)

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


def vboxmanage_showinfo(host="controller-0"):
    """
    This returns info about the host 
    """

    result = subprocess.check_output(['vboxmanage', 'showvminfo', host, '--machinereadable'], stderr=subprocess.STDOUT)
    return result


def vboxmanage_createvm(hostname=None):
    """
    This creates a VM with the specified name.
    """

    assert hostname, "Hostname is required"
    print("Creating VM {}".format(hostname))
    result = subprocess.check_output(['vboxmanage', 'createvm', '--name', hostname, '--register', '--ostype', 'Linux_64'], stderr=subprocess.STDOUT)


def vboxmanage_deletevms(hosts=None):
    """
    Deletes a list of VMs
    """

    assert hosts, "A list of hostname(s) is required"

    if len(hosts) != 0:
        for hostname in hosts:
            print("Deleting VM {}".format(hostname))
            result = subprocess.check_output(['vboxmanage', 'unregistervm', hostname, '--delete'], stderr=subprocess.STDOUT)

    vms_list = vboxmanage_list("vms")
    assert not vms_list, "The following VMs are unexpectedly present: {}".format(vms_list)


def vboxmanage_hostonlyifcreate(name="vboxnet0", ip=None, netmask=None):
    """
    This creates a hostonly network for systems to communicate.
    """

    assert name, "Must provide network name"
    assert ip, "Must provide an OAM IP"
    assert netmask, "Must provide an OAM Netmask"

    print("Creating Host-only Network")
    result = subprocess.check_output(['vboxmanage', 'hostonlyif', 'create'], stderr=subprocess.STDOUT)

    print("Provisioning {} with IP {} and Netmask {}".format(name, ip, netmask))
    result = subprocess.check_output(['vboxmanage', 'hostonlyif', 'ipconfig', name, '--ip', ip, '--netmask', netmask], stderr=subprocess.STDOUT)


def vboxmanage_hostonlyifdelete(name="vboxnet0"):
    """
    Deletes hostonly network. This is used as a work around for creating too many hostonlyifs.

    """
    assert name, "Must provide network name"
    print("Removing Host-only Network")
    result = subprocess.check_output(['vboxmanage', 'hostonlyif', 'remove', name], stderr=subprocess.STDOUT)


def vboxmanage_modifyvm(hostname=None, cpus=None, memory=None, nic=None, nictype=None, nicpromisc=None, nicnum=None, intnet=None, hostonlyadapter=None, uartbase=None, uartport=None, uartmode=None, uartpath=None, nicbootprio2=1):
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
        cmd.extend(['{}/{}'.format(uartpath, hostname)])
    if nicbootprio2:
        cmd.extend(['--nicbootprio2'])
        cmd.extend(['{}'.format(nicbootprio2)])
    cmd.extend(['--boot4']) 
    cmd.extend(['net'])
    print(cmd)

    print("Updating VM {} configuration".format(hostname))
    result = subprocess.check_output(cmd, stderr=subprocess.STDOUT)


def vboxmanage_storagectl(hostname=None, storectl="ide"):
    """
    This creates a storage controller on the host.
    """

    assert hostname, "Hostname is required"
    assert storectl, "Type of storage controller is required"
    print("Creating {} storage controller on VM {}".format(storectl, hostname))
    result = subprocess.check_output(['vboxmanage', 'storagectl', hostname, '--name', storectl, '--add', storectl], stderr=subprocess.STDOUT)


def vboxmanage_storageattach(hostname="controller-0", storectl="ide", storetype="hdd", disk=None, port_num="0", device_num="0"):
    """
    This attaches a disk to a controller.
    """

    assert hostname, "Hostname is required"
    assert disk, "Disk name is required"
    assert storectl, "Name of storage controller is required"
    assert storetype, "Type of storage controller is required"
    print("Attaching {} storage to storage controller {} on VM {}".format(storetype, storectl, hostname))
    result = subprocess.check_output(['vboxmanage', 'storageattach', hostname, '--storagectl', storectl, '--medium', disk, '--type', storetype, '--port', port_num, '--device', device_num], stderr=subprocess.STDOUT)
    return result


def vboxmanage_createmedium(hostname=None, disk_list=None):
    """
    This creates the required disks.
    """

    assert hostname, "Hostname is required"
    assert disk_list, "A list of disk sizes is required"

    username = getpass.getuser()
    device_num = 0
    port_num = 0
    disk_count = 1
    for disk in disk_list:
        # Need a better way to do this
        if disk_count == 2:
            device_num = 1
        elif disk_count == 3:
            port_num = 1
            device_num = 0
        elif disk_count == 4:
            device_num = 1
       # file_name = "/home/" + username + "/vbox_disks/" + hostname + "_disk_{}".format(disk_count)      #required when using own machine  
        file_name = "/folk/" + username + "/vbox_disks/" + hostname + "_disk_{}".format(disk_count)
        print("Creating disk {} on VM {} on device {} port {}".format(file_name, hostname, device_num, port_num))
        result = subprocess.check_output(['vboxmanage', 'createmedium', 'disk', '--size', str(disk), '--filename', file_name, '--format', 'vdi', '--variant', 'standard'], stderr=subprocess.STDOUT)
        vboxmanage_storageattach(hostname, "ide", "hdd", file_name + ".vdi", str(port_num), str(device_num))
        disk_count = disk_count + 1


def vboxmanage_startvm(hostname=None):
    """
    This allows you to power on a VM.
    """

    assert hostname, "Hostname is required"

    print("Powering on VM {}".format(hostname))
    result = subprocess.check_output(['vboxmanage', 'startvm', hostname], stderr=subprocess.STDOUT)
    print(result)


def vboxmanage_controlvms(hosts=None, action=None):
    """
    This allows you to control a VM, e.g. pause, resume, etc.
    """

    assert hosts, "Hostname is required"
    assert action, "Need to provide an action to execute"
 
    for host in hosts:
        print("Executing {} action on VM {}".format(action, host))
        result = subprocess.call(['vboxmanage', 'controlvm', host, action], stderr=subprocess.STDOUT)

