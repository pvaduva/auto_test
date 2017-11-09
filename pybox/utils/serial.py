#!/usr/bin/python3


import socket
import os
import streamexpect
import time
from helper import vboxmanage


def connect(hostname):
    """
    Connect to local domain socket and return the socket object.

    Arguments:
    - Requires the hostname of target, e.g. controller-0
    """

    # Need to power on host before we can connect
    vboxmanage.vboxmanage_startvm(hostname)

    socketname = "/tmp/{}".format(hostname)
    print("Connecting to socket named: {}".format(socketname))

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
    sock.shutdown()
    sock.close()


def expect_bytes(stream, text, fail_ok=False, timeout=120):
    """
    Wait for user specified text from stream.
    """
    time.sleep(2)
    print("Expecting text: {}".format(text))
    try:
        stream.expect_bytes("{}".format(text).encode('utf-8'), timeout=timeout)
    except:
        if fail_ok:
            return -1
        else:
            print("Did not find expected text")
            #disconnect(stream)
            raise

    print("Found expected text: {}".format(text))
    return 0


def send_bytes(stream, text, fail_ok=False, expect_prompt=True, timeout=120):
    """
    Send user specified text to stream.
    """

    print("Sending text: {}".format(text))
    try:
        stream.sendall("{}\n".format(text).encode('utf-8'))
        if expect_prompt:
            expect_bytes(stream, "~$", timeout=timeout)
    except:
        if fail_ok:
            return -1
        else:
            print("Failed to send text")
            #disconnect(stream)
            raise

    return 0 
