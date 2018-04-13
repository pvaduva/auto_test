#!/usr/bin/python3
import socket
import os
import streamexpect
from sys import platform, exit
import time
from helper import vboxmanage
from utils.install_log import LOG


def connect(hostname, port=10000):
    """
    Connect to local domain socket and return the socket object.

    Arguments:
    - Requires the hostname of target, e.g. controller-0
    - Requires TCP port if using Windows
    """

    # Need to power on host before we can connect
    vboxmanage.vboxmanage_startvm(hostname)
    if 'controller-0'in hostname:
        socketname = '/tmp/' + hostname + '_serial'
    else:
        socketname = "/tmp/{}".format(hostname)
    LOG.info("Connecting to {}".format(hostname))
    if platform == 'win32' or platform == 'win64':
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    else:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        if platform == 'win32' or platform == 'win64':
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.connect(('localhost', port))
        else:
            sock.connect(socketname)
    except:
        LOG.info("Connection failed")
        pass
        # disconnect(sock)
        sock = None
    # TODO (WEI): double check this 
    sock.setblocking(0)

    return sock


def disconnect(sock):
    """
    Disconnect a local doamin socket.

    Arguments:
    - Requires socket
    """

    # Shutdown connection and release resources
    LOG.info("Disconnecting from socket")
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()


def expect_bytes(stream, text, timeout=180, fail_ok=False):
    """
    Wait for user specified text from stream.
    """
    time.sleep(2)
    if timeout < 60:
        LOG.info("Expecting text within {} seconds: {}\n".format(timeout, text))
    else:
        LOG.info("Expecting text within {} minutes: {}\n".format((timeout/60), text))
    try:
        stream.expect_bytes("{}".format(text).encode('utf-8'), timeout=timeout)
    except streamexpect.ExpectTimeout:
        if fail_ok:
            return -1
        else:
            LOG.error("Did not find expected text")
            # disconnect(stream)
            raise
    except Exception as e:
            LOG.info("Connection failed with {}.".format(e))
            raise

    LOG.info("Found expected text: {}".format(text))
    return 0


def send_bytes(stream, text, fail_ok=False, expect_prompt=True, prompt=None, timeout=180, send=True):
    """
    Send user specified text to stream.
    """
    LOG.info("Sending text: {}".format(text))
    try:
        if send:
            stream.sendall("{}\n".format(text).encode('utf-8'))
        else:
            stream.sendall("{}".format(text).encode('utf-8'))
        if expect_prompt:
            time.sleep(4)
            if prompt:
                return expect_bytes(stream, prompt, timeout=timeout, fail_ok=fail_ok)
            else:
                rc = expect_bytes(stream, "~$", timeout=timeout, fail_ok=True)
                if rc != 0:
                    send_bytes(stream, '\n', expect_prompt=False)
                    expect_bytes(stream, 'keystone', timeout=timeout)
    except streamexpect.ExpectTimeout:
        if fail_ok:
            return -1
        else:
            LOG.error("Failed to send text, logging out.")
            stream.sendall("exit".encode('utf-8'))
            raise
    except Exception as e:
        LOG.info("Connection failed with {}.".format(e))
        raise

    return 0 
