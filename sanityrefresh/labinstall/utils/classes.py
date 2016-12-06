#!/usr/bin/env python3.4

"""
ssh.py - Class representation for hosts in Titanium Server system.

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
"""

from pprint import pprint
from .log import print_name_value
import copy

#TODO: Can rename this file to something more descriptive than classes.py

class Host(object):
    """Host representation.

    Host contains various attributes such as IP address, hostname, etc.,
    and methods to execute various functions on the host (e.g. ping, ps, etc.).

    """

    def __init__(self, **kwargs):
        """Returns custom logger for module with assigned level."""

        self.telnet_negotiate = False
        self.telnet_vt100query = False
        self.telnet_conn = None
        self.telnet_login_prompt = None
        self.ssh_conn = None
        self.administrative = None
        self.operational = None
        self.availability = None

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def print_attrs(self):
        # Attributes to list first
        first_attrs = ['name', 'personality', 'host_name', 'barcode', 'host_ip',
                       'telnet_ip', 'telnet_port']
        attrs = copy.deepcopy(vars(self))
        for key in first_attrs:
            value = attrs.pop(key, None)
            print_name_value(key, value)
        for item in sorted(attrs.items()):
            print_name_value(item[0], item[1])

    def __str__(self):
        return str(vars(self))

class Controller(Host):
    """Controller representation.

    """
    def  __init__(*initial_data, **kwargs):
        super().__init__(*initial_data, **kwargs)


class SystemLab(object):
    """System lab representation.

    SystemLab contains various attributes such as system floating ip address,
    controller, compute and storage node objects etc., and methods to execute
    various functions on the lab  (e.g. install, upgrade, etc.).

    """
    def __init__(self, **kwargs):


        self.name = None
        self.controller0 = None
        self.controller1 = None
        self.floating_ip = None
        self.software_version = ''
        self.computes = None
        self.storages = None
        self.ssh_conn = None

        for key in kwargs:
            setattr(self, key, kwargs[key])

