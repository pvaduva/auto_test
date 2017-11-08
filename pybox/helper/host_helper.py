import time
import streamexpect
import logging as LOG
from helper import vboxmanage
from consts.timeout import HostTimeout
from utils import serial


def unlock_host(stream, hostname):
    """
    Unlocks given host
    Args:
        stream(stream): Stream to active controller
        hostname(str): Name of host to unlock
    
    """
    LOG.info("Unlocking {}".format(hostname))    
    serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
    serial.expect_bytes(stream, "locked")
    if 'compute' in hostname:
        serial.send_bytes(stream, "system host-unlock {}".format(hostname))
        time.sleep(HostTimeout.COMPUTE_UNLOCK)
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "unlocked")
    elif 'controller' in hostname:
        serial.send_bytes(stream, "system host-unlock {}".format(hostname))
        time.sleep(HostTimeout.CONTROLLER_UNLOCK)
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "unlocked")
    elif 'storage' in hostname:
        serial.send_bytes(stream, "system host-unlock {}".format(hostname))
        time.sleep(HostTimeout.COMPUTE_UNLOCK)
        # storage unlock?
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "unlocked")
    LOG.info("{} is unlocked".format(hostname))
    
            
def lock_host(stream, hostname):
    """
    Locks the specified host.
    Args:
        stream(stream): Stream to controller-0
        hostname(str): Name of host to lock
    """
    LOG.info("Locking {}".format(hostname))    
    serial.send_bytes(stream, "system host-list |grep {}".format(hostname))
    serial.expect_bytes(stream, "unlocked")
    if 'compute' in hostname:
        serial.send_bytes(stream, "system host-lock {}".format(hostname))
        time.sleep(HostTimeout.LOCK)
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "locked")
    elif 'controller' in hostname:
        serial.send_bytes(stream, "system host-lock {}".format(hostname))
        time.sleep(HostTimeout.LOCK)
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "locked")
    elif 'storage' in hostname:
        serial.send_bytes(stream, "system host-lock {}".format(hostname))
        time.sleep(HostTimeout.LOCK)
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "locked")
    LOG.info("{} is locked".format(hostname))


def reboot_host(stream, hostname):
    """
    Reboots host specified
    Args:
        stream():
        hostname(str): Host to reboot
    """
    LOG.info("Rebooting {}".format(hostname))    
    serial.send_bytes(stream, "system host-reboot {}".format(hostname))
    serial.expect_bytes(stream, "rebooting", HostTimeout.REBOOT)
    
    
def install_host(stream, hostname, host_type, host_id):
    """
    Initiates install of specified host. Requires controller-0 to be installed.
    Args:
        stream(stream): Stream to cont0
        hostname(str): Name of host
        host_type(str): Type of host being installed e.g. 'storage' or 'compute'
        host_id(int): id to identify host
    """
        
    if hostname == 'controller-0':
        print("controller-0 is already installed")
        return
    serial.send_bytes(stream, "source /etc/nova/openrc")
    vboxmanage.vboxmanage_startvm(hostname)
    time.sleep(60)
    LOG.info("Installing {} with id {}".format(hostname, host_id))
    if host_type is 'controller':
        serial.send_bytes(stream, "system host-update {} personality=controller".format(host_id))
    elif host_type is 'storage':
        serial.send_bytes(stream, "system host-update {} personality=storage".format(host_id))
    else:
        serial.send_bytes(stream, "system host-update {} personality=compute hostname={}".format(host_id, hostname))
    time.sleep(120)


def change_password(stream):
    """
    changes the default password on initial login.
    Args:
        stream(stream): stream to cont0
    
    """
    LOG.info('Changing password to Li69nux*')    
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "Password:")
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "UNIX password:")
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "New password:")
    serial.send_bytes(stream, "Li69nux*")
    serial.expect_bytes(stream, "Retype new")
    serial.send_bytes(stream, "Li69nux*")
    serial.expect_bytes(stream, "~$")


def login(stream):
    """
    Logs into controller-0.
    Args:
        stream(stream): stream to cont0
    """    
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "assword:")
    serial.send_bytes(stream, "Li69nux*")
    time.sleep(2)
    serial.expect_bytes(stream, "~$")
    time.sleep(4)


def logout(stream):
    """
    Logs out of controller-0.
    Args:
        stream(stream): stream to cont0
    """    
    serial.send_bytes(stream, "logout")
    time.sleep(5)
    #serial.expect_bytes(stream, "W A R N I N G")
    #time.sleep(5)