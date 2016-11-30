import re
from time import strftime

from utils.ssh import SSHClient, CONTROLLER_PROMPT
from consts.lab import Labs
from consts.proj_vars import ProjVar
import sys
sys.path.append('../sanityrefresh/labinstall')
from constants import *
import utils.local_host
import os
import os.path
import configparser
import copy

NODE_INFO_PATH = "sanityrefresh/labinstall/node_info"
LAB_SETTINGS_PATH= "sanityrefresh/labinstall/lab_settings"


def get_lab_floating_ip(labname=None):
    lab_dict = __get_lab_dict(labname)
    return lab_dict['floating ip']


def get_build_id(labname=None, log_dir=None):
    con_ssh = __get_lab_ssh(labname=labname, log_dir=log_dir)

    code, output = con_ssh.exec_cmd('cat /etc/build.info')
    if code != 0:
        build_id = ' '
    else:
        build_id = re.findall('''BUILD_ID=\"(.*)\"''', output)
        if build_id and build_id[0] != 'n/a':
            build_id = build_id[0]
        else:
            build_date = re.findall('''BUILD_DATE=\"(.*)\"''', output)
            if build_date and build_date[0]:
                build_id = build_date[0]
            else:
                build_id = ' '

    con_ssh.close()
    return build_id


def __get_lab_ssh(labname, log_dir=None):
    lab = __get_lab_dict(labname)
    if log_dir is None:
        log_dir = temp_dir = "/tmp/"
        ProjVar.set_var(log_dir=log_dir, temp_dir=temp_dir)
    con_ssh = SSHClient(lab['floating ip'], 'wrsroot', 'Li69nux*', CONTROLLER_PROMPT)
    con_ssh.connect()
    # if 'auth_url' in lab:
    #     Tenant._set_url(lab['auth_url'])
    return con_ssh


def get_all_targets(rtn_str=True, sep=' ', labname=None):
    """
    Return all the targets of given lab in string or list format

    Args:
        rtn_str (bool): True to return string else list
        sep (str):
        labname (str|None): e.g., yow-cgcs-wildcat-80_84 or wcp_80-84

    Returns (str|list): bar codes of all nodes for given lab

    """
    controllers, computes, storages = _get_all_targets_by_host_type(labname=labname)

    if rtn_str:
        return sep.join(controllers + computes + storages)
    else:
        return controllers + computes + storages


def _get_all_targets_by_host_type(labname=None):

    lab_dict = __get_lab_dict(labname)

    controllers = [str(bar_code) for bar_code in lab_dict['controller_nodes']]
    computes = [str(bar_code) for bar_code in lab_dict.get('compute_nodes', [])]
    storages = [str(bar_code) for bar_code in lab_dict.get('storage_nodes', [])]

    return controllers, computes, storages


def __get_lab_dict(labname):
    if labname is None:
        return ProjVar.get_var(var_name='LAB')

    labname = labname.strip().lower().replace('-', '_')
    labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]

    for lab in labs:
        if "name" in lab and labname in lab['name'].replace('-', '_').lower().strip() \
                or labname == lab['short_name'].replace('-', '_').lower().strip() \
                or labname == lab['floating ip']:
            return lab
    else:
        lab_valid_short_names = [lab['short_name'] for lab in labs]
        # lab_valid_names = [lab['name'] for lab in labs]
        raise ValueError("{} is not found! Available labs: {}".format(labname, lab_valid_short_names))


def create_node_boot_dict(labname):
    labname = labname.replace("yow-", '')
    local_path = os.path.dirname(__file__)
    lab_settings_filepath = os.path.join(local_path, '..', '..',
                                         LAB_SETTINGS_PATH, '%s.ini' % labname)

    if not os.path.isfile(lab_settings_filepath):
        msg = 'Lab settings file path was not found: {}'.format(lab_settings_filepath)
        raise ValueError(msg)
    else:
        config = configparser.ConfigParser()
        lab_setting_file = open(lab_settings_filepath, 'r')
        config.read_file(lab_setting_file)
        boot_device_dict = dict(config.items(CFG_BOOT_INTERFACES_NAME))
        return boot_device_dict

def create_node_dict(nodes, personality):
    """Read .ini file for each node and create Host object for the node.

    The data in the .ini file is read into a dictionary which is used to
    create a Host object for the node.

    Return dictionary of node names mapped to their respective Host objects.
    """
    node_dict = {}
    i = 0

    for node in nodes:

        config = configparser.ConfigParser()
        try:
            local_path = os.path.dirname(__file__)
            node_filepath = os.path.join(local_path, '..', '..',
                                         NODE_INFO_PATH, '%s.ini' % node)
            node_file = open(node_filepath, 'r')
            config.read_file(node_file)
        except Exception as e:
            raise ValueError('Failed to read \"{}\": '.format(node_filepath) + str(e))



        node_info_dict = {}
        for section in config.sections():
            for opt in config.items(section):
                key, value = opt
                node_info_dict[section + '_' + key] = value

        name = personality + "-{}".format(i)
        node_info_dict['name'] = name
        node_info_dict['personality'] = personality
        node_info_dict['barcode'] = node
        node_dict[name]=Host(**node_info_dict)
        i += 1

    return node_dict




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
        self.barcode = None

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def print_attrs(self):
        # Attributes to list first
        first_attrs = ['name', 'personality', 'host_name', 'barcode', 'host_ip',
                       'telnet_ip', 'telnet_port']
        attrs = copy.deepcopy(vars(self))
        for key in first_attrs:
            value = attrs.pop(key, None)
            print("{}: {}".format(key, value))
        for item in sorted(attrs.items()):
            print("{}: {}".format(item[0], item[1]))

    def __str__(self):
        return str(vars(self))

class Controller(Host):
    """Controller representation.

    """
    def  __init__(*initial_data, **kwargs):
        super().__init__(*initial_data, **kwargs)

