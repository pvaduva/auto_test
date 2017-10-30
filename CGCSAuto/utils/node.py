
import os
import os.path
import configparser
import copy

NODE_INFO_PATH = "sanityrefresh/labinstall/node_info"
LAB_SETTINGS_PATH= "sanityrefresh/labinstall/lab_settings"
CFG_BOOT_INTERFACES_NAME = "boot_interfaces"

VBOX_BOOT_INTERFACES = {
    'controller-0': '0300',
    'controller-1': '0800',
    'compute-0': '0800',
    'compute-1': '0800'
}

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


def create_node_dict(nodes, personality, vbox=False):
    """Read .ini file for each node and create Host object for the node.

    The data in the .ini file is read into a dictionary which is used to
    create a Host object for the node.

    Return dictionary of node names mapped to their respective Host objects.
    """
    node_dict = {}
    i = 0

    for node in nodes:
        node_info_dict = {}
        if not vbox:
            config = configparser.ConfigParser()
            try:
                local_path = os.path.dirname(__file__)
                node_filepath = os.path.join(local_path, '..', '..',
                                             NODE_INFO_PATH, '%s.ini' % node)
                node_file = open(node_filepath, 'r')
                config.read_file(node_file)
            except Exception as e:
                raise ValueError('Failed to read \"{}\": '.format(node_filepath) + str(e))

            #node_info_dict = {}
            for section in config.sections():
                for opt in config.items(section):
                    key, value = opt
                    node_info_dict[section + '_' + key] = value

        name = personality + "-{}".format(i)
        node_info_dict['name'] = name
        node_info_dict['personality'] = personality
        node_info_dict['barcode'] = node
        node_dict[name]=Node(**node_info_dict)
        i += 1

    return node_dict


class Node(object):
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

class Controller(Node):
    """Controller representation.

    """
    def  __init__(*initial_data, **kwargs):
        super().__init__(*initial_data, **kwargs)

