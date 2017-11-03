import time
import streamexpect
from helper import vboxmanage
from consts.timeout import HostTimeout
from utils import serial


def unlock_host(stream, hostname):
    serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
    serial.expect_bytes(stream, "locked")
    if 'compute' in hostname:
        serial.send_bytes(stream, "system host-unlock {}".format(hostname))
        time.sleep(HostTimeout.COMPUTE_UNLOCK)
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "online")
    elif 'controller' in hostname:
        serial.send_bytes(stream, "system host-unlock {}".format(hostname))
        time.sleep(HostTimeout.CONTROLLER_UNLOCK)
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "enabled")
    elif 'storage' in hostname:
        serial.send_bytes(stream, "system host-unlock {}".format(hostname))
        time.sleep(HostTimeout.COMPUTE_UNLOCK)
        # storage unlock?
        serial.send_bytes(stream, "system host-list | grep {}".format(hostname))
        serial.expect_bytes(stream, "enabled")


def install_host(stream, hostname, host_type, host_id):
    serial.send_bytes(stream, "source /etc/nova/openrc")
    vboxmanage.vboxmanage_startvm(hostname)
    time.sleep(45)
    if host_type is 'controller':
        serial.send_bytes(stream, "system host-update {} personality=controller".format(host_id))
    elif host_type is 'storage':
        serial.send_bytes(stream, "system host-update {} personality=storage".format(host_id))
    else:
        serial.send_bytes(stream, "system host-update {} personality=compute hostname={}".format(host_id, hostname))
    time.sleep(30)


def change_password(stream):
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "Password:")
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "assword:")
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "assword:")
    serial.send_bytes(stream, "Li69nux*")
    serial.expect_bytes(stream, "assword:")
    serial.send_bytes(stream, "Li69nux*")
    time.sleep(2)


def login(stream):
    serial.send_bytes(stream, "wrsroot")
    serial.expect_bytes(stream, "assword:")
    serial.send_bytes(stream, "Li69nux*")
    time.sleep(2)

def logout(stream):
    serial.send_bytes(stream, "logout")
    serial.expect_bytes(stream, "login:")
    time.sleep(2)