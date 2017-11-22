#!/usr/bin/python3


import socket
import os
import streamexpect
import time
import logging
from helper import vboxmanage
from utils.install_log import LOG


def connect(hostname):
    """
    Connect to local domain socket and return the socket object.

    Arguments:
    - Requires the hostname of target, e.g. controller-0
    """

    # Need to power on host before we can connect
    vboxmanage.vboxmanage_startvm(hostname)

    socketname = "/tmp/{}".format(hostname)
    LOG.info("Connecting to socket named: {}".format(socketname))

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socketname)
    except:
        pass
        disconnect(sock)

    sock.setblocking(0)

    return sock


def disconnect(sock):
    """
    Disconnect a local doamin socket.

    Arguemnts:
    - Requires socket
    """

    # Shutdown connection and release resources
    LOG.info("Disconnecting from socket")
    sock.shutdown()
    sock.close()


def expect_bytes(stream, text, timeout=120, fail_ok=False):
    """
    Wait for user specified text from stream.
    """
    time.sleep(2)
    LOG.info("Expecting text within {} minutes: {}".format((timeout/60), text))
    try:
        stream.expect_bytes("{}".format(text).encode('utf-8'), timeout=timeout)
    except:
        if fail_ok:
            return -1
        else:
            LOG.error("Did not find expected text")
            #disconnect(stream)
            raise

    LOG.info("Found expected text: {}".format(text))
    return 0


def send_bytes(stream, text, fail_ok=False, expect_prompt=True, prompt=None, timeout=120):
    """
    Send user specified text to stream.
    """

    LOG.info("Sending text: {}".format(text))
    try:
        stream.sendall("{}\n".format(text).encode('utf-8'))
        if expect_prompt:
        # ~$ causes issues when using keystone admin credentials since it uses '~(keystone_admin)]$' instead
        #TODO: find a better way to do this maybe controller-0?
            time.sleep(2)
            if prompt:
                expect_bytes(stream, prompt, timeout=timeout)
            else:
            
                expect_bytes(stream, "~$", timeout=timeout)
    except:
        if fail_ok:
            return -1
        else:
            LOG.error("Failed to send text")
            #disconnect(stream)
            raise

    return 0 
