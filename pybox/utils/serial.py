#!/usr/bin/python3


import socket
import streamexpect
import time


def connect(hostname):
    """
    Connect to local domain socket and return the socket object.

    Arguments:
    - Requires the hostname of target, e.g. controller-0
    """

    socketname = "/tmp/{}".format(hostname)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socketname)
    sock.setblocking(0)

    return sock

def expect_bytes(stream, text, timeout=120):
    """
    Wait for user specified text from stream.
    """

    print("Waiting for text: {}".format(text))
    stream.expect_bytes("{}".format(text).encode("utf-8"), timeout=timeout)
    print("Found text: {}".format(text))


def send_bytes(stream, text, timeout=120):
    """
    Send user specified text to stream.
    """
    
    print("Sending text: {}".format(text))
    stream.sendall("{}\n".format(text).encode('utf-8'))
    time.sleep(2)
    #stream.sendall("echo $?".encode('utf-8'))
    #rc = stream.expect_regex("(.*)".encode('utf-8'))
    rc = 0
    return rc
