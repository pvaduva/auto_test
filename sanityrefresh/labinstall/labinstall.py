#!/usr/bin/env python3.4

'''
lab_install.py - Script to install Titanium Server software load onto lab

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

'''

'''
modification history:
---------------------
16oct15,kav  Creation
'''

import os
import sys
import textwrap
import argparse
import configparser
from pprint import pprint
from common.logUtils import *
from common.classes import Host

NODE_INFO_DIR='node_info'
LOGGER_NAME = os.path.splitext("path_to_file")[0]
log = logging.getLogger(LOGGER_NAME)

# Take parameter for list of controllers, list of computes, and list of storage nodes

def parse_args():
    parser = argparse.ArgumentParser(formatter_class=\
                                     argparse.RawTextHelpFormatter, add_help=False,
                                     description='Script to install Titanium'
                                     ' Server load on specified lab.')

    node_grp = parser.add_argument_group('Nodes')
    node_grp.add_argument('--controller', metavar='LIST', required=True,
                          help='Comma-separated list of VLM target barcodes'
                          ' for controllers')
    node_grp.add_argument('--compute', metavar='LIST', required=True,
                          help='Comma-separated list of VLM target barcodes'
                          ' for computes')
    node_grp.add_argument('--storage', metavar='LIST', required=True,
                          help='Comma-separated list of VLM target barcodes'
                          ' for storage nodes')

    parser.add_argument('LAB_CONFIG_LOCATION',
                        help=textwrap.dedent('''\
                        Specify either:\n\n
                        (a) Directory name for lab listed under:
                            -> cgcs/extras.ND/lab/yow/
                            e.g.: cgcs-ironpass-1_4\n
                        or\n
                        (b) Custom directory path for lab config files\n
                        Note:
                        '(a)' is used to install an existing lab, where the
                        directory contains the following config files:
                            -> system_config
                            -> hosts_bulk_add.xml
                            -> lab_setup.conf
                        '(b)' is intended for large office, where the directory
                        path would contain hosts_bulk_add.xml'''))

    bld_grp = parser.add_argument_group('Build server and paths')
    bld_grp.add_argument('--build-server', metavar='SERVER',
                         dest='build_server', default='yow-cgts3-lx',
                          help='Titanium Server build server'
                         ' host name\n(default: %(default)s)')
    bld_grp.add_argument('--build-server-dir-path', metavar='DIR_PATH',
                         dest='build_server_dir_path',
                         default='/localdisk/loadbuild/jenkins/',
                         help='Directory path accessible by build server'
                         '\n(default: %(default)s)')
    bld_grp.add_argument('--build-server-load-dir', metavar='LOAD_DIR',
                         dest='build_server_load_dir',
                         default='CGCS_2.0_Unified_Daily_Build',
                         help='Directory under DIR_PATH'
                         ' containing Titanium Server load'
                         '\n(default: %(default)s)')
    bld_grp.add_argument('--build-server-guest-dir', metavar='GUEST_DIR',
                         dest='build_server_guest_dir',
                         default='CGCS_2.0_Guest_Daily_Build',
                         help='Directory under DIR_PATH'
                         ' containing guest image\n(default: %(default)s)')
    bld_grp.add_argument('--build-server-patch_dir-paths', metavar='LIST',
                         dest='build_server_patch_dir_paths',
                         help=textwrap.dedent('''\
                         Comma-separated list of directory paths accessible by
                         build server containing patches\n
                         e.g.: for 15.05 patch testing, the following paths
                         would be specified:
                             -> /folk/cgts/patches-to-verify/ZTE/'
                             -> /folk/cgts/patches-to-verify/15.05'
                             -> /folk/cgts/rel-ops/Titanium-Server-15/15.05'''))

    other_grp = parser.add_argument_group('Other options:')
    other_grp.add_argument('--run-lab-setup', dest='run_lab_setup',
                           action='store_true', help='If specified,'
                           ' run lab_setup.sh')
    other_grp.add_argument('--log-level', dest='log_level',
                           choices=['DEBUG', 'INFO', 'WARNING', 'ERROR',
                                   'CRITICAL'],
                           default='DEBUG', help='Logging level')
    other_grp.add_argument('-h','--help', action='help',
                           help='Show this help message and exit')

    args = parser.parse_args()
    return args

def create_node_dict(nodes):
    node_dict = {}
    i = 0
    
    for node in nodes:
        print('going through ' + node)
        config = configparser.ConfigParser()        
        try:
            node_filename = NODE_INFO_DIR + '/{}.ini'.format(node)
            node_file = open(node_filename, 'r')
            config.readfp(node_file)
        except Exception as err:
            log.error('Failed to read {}:\n{}'.format(node_filename,err))
            sys.exit(1)

        node_info_dict = {}
        for section in config.sections():
#            print('section = ' + section)
#            print ('options =' + str(config.options(section)))
            for opt in config.items(section):
                key, value = opt
                node_info_dict[section + '_' + key] = value

#        print('node info dict = ' + str(node_info_dict))
        node_dict["controller-{}".format(i)]=Host(**node_info_dict)
        print('host =\n' + str(node_dict["controller-{}".format(i)]))
        i += 1

    return node_dict

if __name__ == '__main__':

    args = parse_args()

    setLogger(log, args.log_level)
    
    controller_nodes = tuple(args.controller.split(','))
    compute_nodes = tuple(args.compute.split(','))
    storage_nodes = tuple(args.storage.split(','))

    print('Controller: ' + str(controller_nodes))
    print('Compute: ' + str(compute_nodes))
    print('Storage: ' + str(storage_nodes))
    
    controller_dict = create_node_dict(controller_nodes)
    compute_dict = create_node_dict(compute_nodes)
    storage_dict = create_node_dict(storage_nodes)
