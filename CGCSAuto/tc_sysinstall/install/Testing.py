#imports

import os
import re
import pytest
import pprint
import time
import configparser
import consts.proj_vars
from consts.lab import Labs
from consts.filepaths import BuildServerPath
from setups import set_install_params, write_installconf, setup_tis_ssh
from keywords.install_helper import get_git_name, ssh_to_build_server, download_image, download_heat_templates, \
    download_lab_config_files, get_ssh_public_key, download_license
from keywords.system_helper import get_active_controller_name
from utils.tis_log import LOG
from consts import bios


def eval_test(string):
    x = None
    if os.path.isdir(string):
        x = True
    if x:
        print('we could find x')
    else:
        print('out of scope')

def get_system_info(lab_cfg_path):
    sys_info_dict = {}
    cmd = "grep -r --color=none SYSTEM_ {}".format(lab_cfg_path)
    with ssh_to_build_server() as bld_server_conn:
        sys_info = bld_server_conn.exec_cmd(cmd)[1].replace(' ','')
        sys_info_list = sys_info.splitlines()
        print('turning this:')
        time.sleep(1)
        print(sys_info_list)
        for line in sys_info_list:
            key = line[line.find('SYSTEM_')+len('SYSTEM_'):line.find('=')].lower()
            val = line[line.find('=') + 1:]
            # Remove special characters
            sys_info_dict[key] = val
    print('---------------------------------------------------------------------------')
    time.sleep(1)
    print('into this:')
    return sys_info_dict

def print_install_params():
   setup = set_install_params(lab, installconf_path='/home/ebarrett/WindRiver/temp/SM_2.ini', skip=None,
                              resume=None, controller0_ceph_mon_device=None, controller1_ceph_mon_device=None,
                              ceph_mon_gib=None, wipedisk=None)
   pprint.pprint(consts.proj_vars.InstallVars.get_install_vars())

def create_node_dict(lab_dict):
    node_keys = [key for key in lab_dict.keys() if 'node' in key]
    # TODO: this line is way too disgusting
    node_values = [' '.join(list(map(str, lab_dict.pop(k)))) for k in node_keys]
    node_dict = dict(zip(node_keys, node_values))
    return node_dict

@pytest.mark.skip("called in main")
def test_setup(lab_name, controller, compute, storage, lab_files_server, lab_files_dir):
    install_path = write_installconf(lab=lab_name, controller=controller,
                                     lab_files_dir=lab_files_dir, build_server=None, tis_build_dir=None, compute=None,
                                     storage=None, license_path=None, guest_image=None, heat_templates=None, boot='pxe',
                                     iso_path=None)

    set_install_params(lab=None, skip="feed", resume=None, installconf_path=install_path, wipedisk=None,
                       controller0_ceph_mon_device=None, controller1_ceph_mon_device=None, ceph_mon_gib=None, boot='pxe',
                                     iso_path=None)
    params = consts.proj_vars.InstallVars.get_install_vars()
    consts.proj_vars.ProjVar.set_vars(lab=params["LAB"], natbox=None, logdir="/home/ebarrett/AUTOMATION_LOGS", tenant=None,
                                      is_boot=None, collect_all=None, report_all=None, report_tag=None,
                                      openstack_cli=None, always_collect=None)

    return params


def get_active_barcode(setup):
    lab_dict = setup["LAB"]
    con_ssh = setup_tis_ssh(lab_dict)
    active_con = get_active_controller_name(con_ssh)
    print("active controller is: {}".format(active_con))
    active_con_barcode = lab_dict[active_con].barcode
    print("{} barcode is {}".format(active_con, active_con_barcode))

    return active_con_barcode


def get_info_from_lab_files(conf_server, conf_dir, lab_name=None, host_build_dir=None):
    # Configuration server has to be a valid build server
    # If the configuration directory is given use that to get the system info
    # Otherwise the host_build_dir and lab_name is required for the default path to the configuration directory.
    # Both of which have defaults if not provided

    lab_info_dict = {}
    if conf_dir:
       lab_files_path = conf_dir
    elif lab_name is not None and host_build_dir is not None:
        lab_files_path = "{}/rt/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/{}".format(host_build_dir,
                                                                                             get_git_name
                                                                                             (lab_name))
    else:
        raise ValueError("Could not access lab files")

    with ssh_to_build_server(conf_server) as ssh_conn:
        info_prefix = "INTERFACE_PORT"

        cmd = 'test -d {}'.format(lab_files_path)
        assert ssh_conn.exec_cmd(cmd)[0] == 0, 'Lab config path not found in {}:{}'.format(conf_server, lab_files_path)

        cmd = 'grep -r --color=none {} {}'.format(info_prefix, lab_files_path)

        rc, output = ssh_conn.exec_cmd(cmd, rm_date=False)
        assert rc == 0, 'Lab config path not found in {}:{}'.format(conf_server, lab_files_path)

        lab_info = output.replace(' ', '')
        lab_info_list = lab_info.splitlines()
        for line in lab_info_list:
            key = line[line.find(info_prefix) + len(info_prefix):line.find('=')].lower()
            val = line[line.find('=') + 1:].lower()
            lab_info_dict[key] = val.replace('"', '')

        # Workaround for r430 labs
        lab_name = lab_info_dict["name"]
        last_num = -1
        if not lab_name[last_num].isdigit():
            while not lab_name[last_num].isdigit():
                last_num -= 1
            lab_info_dict["name"] = lab_name[:last_num+1]

        return lab_info_dict

def compare_interfaces(file_dir):
    host_build_dir = BuildServerPath.DEFAULT_HOST_BUILD_PATH
    config_file = None
    config_dict = {}

    local_path = os.path.dirname(__file__)
    node_dict = {}

    lab_dicts = []
    for attr in dir(Labs):
        lab_dict = getattr(Labs, attr)
        if isinstance(lab_dict, dict):
            if "controller_nodes" in lab_dict.keys():
                lab_dicts.append(lab_dict)
            else:
                continue

    installconf = configparser.ConfigParser(allow_no_value=True, strict=False)

    with ssh_to_build_server(files_server) as connection:
        print("\nTiS_config values:\n")
        for lab_info in lab_dicts:
            lab_name = get_git_name(lab_info["name"])
            print(lab_name)
            barcode = lab_info["controller_nodes"][0]
            conf_dir = "{}/rt/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/{}".format(host_build_dir, lab_name)
            system_files = connection.exec_cmd('ls {} | tr -d "[:blank:]"'.format(conf_dir))[1].splitlines()
            print("the files are:")
            print(system_files)
            interfaces = []
            for file in system_files:
                if "TiS_config.ini_centos" in file or "system_config" in file:
                    config_file = file
                    print("checking {}".format(config_file))
                    try:
                        installconf.read("{}/{}/{}".format(file_dir, lab_name, config_file))
                        network = installconf["OAM_NETWORK"]
                        interface = network["LOGICAL_INTERFACE"]
                        port = installconf[interface]["INTERFACE_PORTS"]
                        interfaces.append(port)
                    except KeyError:
                        print("key error")
                        continue
            config_dict[barcode] = interfaces

    print("\nnode_info values:\n")
    for lab_info in lab_dicts:
        lab_name = get_git_name(lab_info["name"])
        print(lab_name)
        barcode = lab_info["controller_nodes"][0]

        node_path = node_filepath = os.path.join(local_path, '..', '..', '..',
                                         NODE_INFO_PATH, '%s.ini' % barcode)
        try:
            installconf.read(node_filepath)
            node_info = installconf['host']
            node_interface = node_info["nic"]
            node_dict[barcode] = node_interface
        except KeyError:
            print("key error")
            continue

    print("\nconfig interfaces:")
    print(config_dict)
    print("\nnode interfaces")
    print(node_dict)

    found = True
    not_found = []
    for node_key, node_value in node_dict.items():
        if node_key in config_dict.keys():
            for item in config_dict[node_key]:
                found = node_value in item
                if found:
                    break
        else:
            not_found.append(node_key)
        if found is False:
            not_found.append({node_key: node_value})

    print("\nmismatches:")

    return not_found


def test_telnet(install_setup):
    from keywords.install_helper import open_telnet_session
    node_obj = install_setup["active_controller"]
    print("establishing connection to: ", node_obj.telnet_ip, " ", node_obj.telnet_port)
    connection = open_telnet_session(node_obj, None, None)
    connection.exec_cmd("ls")


NODE_INFO_PATH = "sanityrefresh/labinstall/node_info"
lab = 'yow-cgcs-supermicro-3'
controllers = None
computes = None
storages = None
files_server = 'yow-cgts4-lx'
lab_config_path = "{}/rt/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/{}".format(BuildServerPath.DEFAULT_HOST_BUILD_PATH, get_git_name(lab))
# print(compare_interfaces("/home/ebarrett/WindRiver/lab-files/yow"))
# setup = test_setup(lab_name=lab, controller=controllers, compute=computes, storage=storages,
#                   lab_files_server=files_server, lab_files_dir=lab_config_path)
from tc_sysinstall.install import conftest
# test_vars = conftest.install_setup()
# print("Install setup:")
# print(test_vars)
# active_controller = test_vars["active_controller"]
# test_telnet(active_controller)

string1 = str.encode("Use the ^ and v keys to change the selection.")
string2 = str.encode("^ and v to move selection")
regex = re.compile(b"\^ and v( keys)? to (move|change( the)?) selection")
match1 = regex.search(string1)
match2 = regex.search(string2)
if match1:
    print(match1.group(0))
if match2:
    print(match2.group(0))



