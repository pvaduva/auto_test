import configparser
import os
import re
import threading
import time

import pexpect

import setup_consts
from consts.auth import Tenant, HostLinuxCreds, SvcCgcsAuto, CliAuth
from consts.cgcs import Prompt, REGION_MAP, SysType
from consts.filepaths import PrivKeyPath, WRSROOT_HOME, BuildServerPath
from consts.lab import Labs, add_lab_entry, NatBoxes, edit_lab_entry
from consts.proj_vars import ProjVar, InstallVars
from consts import build_server
from keywords.common import scp_to_local, scp_from_active_controller_to_localhost
from keywords import vm_helper, host_helper, nova_helper, system_helper, keystone_helper, common, network_helper, \
    install_helper, vlm_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from utils import exceptions, lab_info
from utils import local_host
from utils.clients.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient, PASSWORD_PROMPT, SSHFromSSH
from utils.clients.local import RemoteCLIClient
from utils.clients.telnet import TELNET_LOGIN_PROMPT, TelnetClient
from utils.node import create_node_boot_dict, create_node_dict, VBOX_BOOT_INTERFACES
from utils.tis_log import LOG


def less_than_two_controllers():
    return len(system_helper.get_controllers()) < 2


def setup_tis_ssh(lab):
    con_ssh = ControllerClient.get_active_controller(fail_ok=True)

    if con_ssh is None:
        try:
            con_ssh = SSHClient(lab['floating ip'], HostLinuxCreds.get_user(), HostLinuxCreds.get_password(),
                                CONTROLLER_PROMPT)
            con_ssh.connect(retry=True, retry_timeout=30)
            ControllerClient.set_active_controller(con_ssh)
        except:
            if ProjVar.get_var('COLLECT_SYS_NET_INFO'):
                LOG.error("SSH to lab fip failed. Collecting lab network info.")
                collect_sys_net_info(lab=ProjVar.get_var('LAB'))
            raise
    # if 'auth_url' in lab:
    #     Tenant._set_url(lab['auth_url'])
    return con_ssh


def setup_vbox_tis_ssh(lab):
    if 'external_ip' in lab.keys():

        con_ssh = ControllerClient.get_active_controller(fail_ok=True)
        if con_ssh:
            con_ssh.disconnect()

        con_ssh = SSHClient(lab['external_ip'], HostLinuxCreds.get_user(), HostLinuxCreds.get_password(),
                            CONTROLLER_PROMPT, port=lab['external_port'])
        con_ssh.connect(retry=True, retry_timeout=30)
        ControllerClient.set_active_controller(con_ssh)

    else:
        con_ssh = setup_tis_ssh(lab)

    return con_ssh


def set_env_vars(con_ssh):
    # This is no longer needed
    return

    con_ssh.exec_cmd("bash")

    prompt_cmd = con_ssh.exec_cmd("echo $PROMPT_COMMAND")[1]
    tmout_val = con_ssh.exec_cmd("echo $TMOUT")[1]
    hist_time = con_ssh.exec_cmd("echo $HISTTIMEFORMAT")[1]
    source = False

    if prompt_cmd != 'date':
        if prompt_cmd:
            con_ssh.exec_cmd('''sed -i '/export PROMPT_COMMAND=.*/d' ~/.bashrc''')

        con_ssh.exec_cmd('''echo 'export PROMPT_COMMAND="date"' >> ~/.bashrc''')
        source = True

    if tmout_val != '0':
        con_ssh.exec_cmd("echo 'export TMOUT=0' >> ~/.bashrc")
        source = True

    if '%Y-%m-%d %T' not in hist_time:
        con_ssh.exec_cmd('''echo 'export HISTTIMEFORMAT="%Y-%m-%d %T "' >> ~/.bashrc''')
        source = True

    if source:
        con_ssh.exec_cmd("source ~/.bashrc")
        LOG.debug("Environment variable(s) updated.")


def setup_primary_tenant(tenant):
    Tenant.set_primary(tenant)
    LOG.info("Primary Tenant for test session is set to {}".format(tenant['tenant']))


def setup_natbox_ssh(keyfile_path, natbox, con_ssh):
    natbox_ip = natbox['ip']
    NATBoxClient.set_natbox_client(natbox_ip)
    nat_ssh = NATBoxClient.get_natbox_client()
    nat_ssh.exec_cmd('mkdir -p ~/priv_keys/')
    ProjVar.set_var(natbox_ssh=nat_ssh)

    _copy_keyfile_to_natbox(nat_ssh, keyfile_path, con_ssh=con_ssh)
    _copy_pubkey()
    return nat_ssh


def _copy_pubkey():
    with host_helper.ssh_to_host('controller-0') as con_0_ssh:
        pubkey_path = '{}/key.pub'.format(WRSROOT_HOME)
        if not con_0_ssh.file_exists(pubkey_path):
            try:
                LOG.info("Attempt to copy public key to both controllers and localhost if applicable")
                # copy public key to key.pub
                con_0_ssh.exec_cmd('cp {}/.ssh/*.pub {}'.format(WRSROOT_HOME, pubkey_path))

                if not system_helper.is_simplex():
                    # copy publickey to controller-1
                    con_0_ssh.scp_on_source(source_path=pubkey_path, dest_path=pubkey_path,
                                            dest_ip='controller-1',
                                            dest_user=HostLinuxCreds.get_user(),
                                            dest_password=HostLinuxCreds.get_password(), timeout=30)
            except:
                pass

        # copy public key to localhost
        if ProjVar.get_var('REMOTE_CLI') and con_0_ssh.file_exists(pubkey_path):
            dest_path = os.path.join(ProjVar.get_var('TEMP_DIR'), 'key.pub')
            scp_from_active_controller_to_localhost(source_path=pubkey_path, dest_path=dest_path, timeout=60)
            LOG.info("Public key file copied to localhost")


def _copy_keyfile_to_natbox(nat_ssh, keyfile_path, con_ssh):
    """
    copy private keyfile from controller-0:/opt/platform to natbox: priv_keys/
    Args:
        nat_ssh (SSHClient): NATBox client
        keyfile_path (str): Natbox path to scp keyfile to
        con_ssh (SSHClient)
    """

    # Assume the tenant key-pair was added by lab_setup from exiting keys from controller-0:/home/wrsroot/.ssh
    LOG.info("scp key file from controller to NATBox")
    keyfile_name = keyfile_path.split(sep='/')[-1]

    if not con_ssh.file_exists(keyfile_name):
        if not con_ssh.file_exists(PrivKeyPath.OPT_PLATFORM):

            gen_new_key = False
            with host_helper.ssh_to_host('controller-0') as con_0_ssh:
                if not con_0_ssh.file_exists(PrivKeyPath.WRS_HOME):
                    gen_new_key = True

            if gen_new_key:
                if nova_helper.get_key_pair():
                    raise exceptions.TiSError("Cannot find ssh keys for existing nova keypair.")

                passphrase_prompt_1 = '.*Enter passphrase.*'
                passphrase_prompt_2 = '.*Enter same passphrase again.*'

                con_ssh.send('ssh-keygen')
                index = con_ssh.expect([passphrase_prompt_1, '.*Enter file in which to save the key.*'])
                if index == 1:
                    con_ssh.send()
                    con_ssh.expect(passphrase_prompt_1)
                con_ssh.send()  # Enter empty passphrase
                con_ssh.expect(passphrase_prompt_2)
                con_ssh.send()  # Repeat passphrase
                con_ssh.expect(Prompt.CONTROLLER_0)

            # ssh keys should now exist under wrsroot home dir
            active_con = system_helper.get_active_controller_name()
            if active_con != 'controller-0':
                con_ssh.send(
                    'scp controller-0:{} {}'.format(PrivKeyPath.WRS_HOME, PrivKeyPath.WRS_HOME))

                index = con_ssh.expect([Prompt.PASSWORD_PROMPT, Prompt.CONTROLLER_1, Prompt.ADD_HOST])
                if index == 2:
                    con_ssh.send('yes')
                    index = con_ssh.expect([Prompt.PASSWORD_PROMPT, Prompt.CONTROLLER_1])
                if index == 0:
                    con_ssh.send(HostLinuxCreds.get_password())
                    con_ssh.expect()

                con_ssh.exec_sudo_cmd('cp {} {}'.format(PrivKeyPath.WRS_HOME, PrivKeyPath.OPT_PLATFORM), fail_ok=False)
                con_ssh.exec_cmd('rm {}'.format(PrivKeyPath.WRS_HOME))
            else:
                con_ssh.exec_sudo_cmd('cp {} {}'.format(PrivKeyPath.WRS_HOME, PrivKeyPath.OPT_PLATFORM), fail_ok=False)

        # ssh private key should now exist under /opt/platform dir
        cmd_1 = 'cp {} {}'.format(PrivKeyPath.OPT_PLATFORM, keyfile_name)
        con_ssh.exec_sudo_cmd(cmd_1, fail_ok=False)

        # change user from root to wrsroot
        cmd_2 = 'chown wrsroot:wrs {}'.format(keyfile_name)
        con_ssh.exec_sudo_cmd(cmd_2, fail_ok=False)

    # ssh private key should now exist under keyfile_path
    con_ssh.exec_cmd('stat {}'.format(keyfile_name), fail_ok=False)

    tis_ip = ProjVar.get_var('LAB').get('floating ip')
    for i in range(10):
        try:
            nat_ssh.flush()
            cmd_3 = 'scp -v -o ConnectTimeout=30 {}@{}:{} {}'.format(
                HostLinuxCreds.get_user(), tis_ip, keyfile_name, keyfile_path)
            nat_ssh.send(cmd_3)
            rtn_3_index = nat_ssh.expect([nat_ssh.get_prompt(), Prompt.PASSWORD_PROMPT, '.*\(yes/no\)\?.*'])
            if rtn_3_index == 2:
                nat_ssh.send('yes')
                nat_ssh.expect(Prompt.PASSWORD_PROMPT)
            elif rtn_3_index == 1:
                nat_ssh.send(HostLinuxCreds.get_password())
                nat_ssh.expect(timeout=30)
            if nat_ssh.get_exit_code() == 0:
                LOG.info("key file is successfully copied from controller to NATBox")
                return
        except pexpect.TIMEOUT as e:
            LOG.warning(e.__str__())
            nat_ssh.send_control()
            nat_ssh.expect()

        except Exception as e:
            LOG.warning(e.__str__())
            time.sleep(10)

    raise exceptions.CommonError("Failed to copy keyfile to NatBox")


def boot_vms(is_boot):
    # boot some vms for the whole test session if boot_vms flag is set to True
    if is_boot:
        con_ssh = ControllerClient.get_active_controller()
        if con_ssh.file_exists('~/instances_group0/launch_tenant1-avp1.sh'):
            vm_helper.launch_vms_via_script(vm_type='avp', num_vms=1, tenant_name='tenant1')
            vm_helper.launch_vms_via_script(vm_type='virtio', num_vms=1, tenant_name='tenant2')
        else:
            vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT1)
            vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT2)


def get_lab_dict(labname):
    labname = labname.strip().lower().replace('-', '_')
    labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]
    labs = [lab_ for lab_ in labs if isinstance(lab_, dict)]

    for lab in labs:
        if labname in lab.get('name').replace('-', '_').lower().strip() \
                or labname == lab.get('short_name').replace('-', '_').lower().strip() \
                or labname == lab.get('floating ip'):
            return lab
    else:
        if labname.startswith('128.224') or labname.startswith('10.'):
            return add_lab_entry(labname)

        lab_valid_short_names = [lab.get('short_name') for lab in labs]
        # lab_valid_names = [lab['name'] for lab in labs]
        raise ValueError("{} is not found! Available labs: {}".format(labname, lab_valid_short_names))


def get_natbox_dict(natboxname):
    natboxname = natboxname.lower().strip()
    natboxes = [getattr(NatBoxes, item) for item in dir(NatBoxes) if item.startswith('NAT_')]

    for natbox in natboxes:
        if natboxname.replace('-', '_') in natbox.get('name').replace('-', '_') or natboxname == natbox.get('ip'):
            return natbox
    else:
        if natboxname.startswith('128.224'):
            return NatBoxes.add_natbox(ip=natboxname)
        else:
            raise ValueError("{} is not a valid input.".format(natboxname))


def get_tenant_dict(tenantname):
    # tenantname = tenantname.lower().strip().replace('_', '').replace('-', '')
    tenants = [getattr(Tenant, item) for item in dir(Tenant) if not item.startswith('_') and item.isupper()]

    for tenant in tenants:
        if tenantname == tenant.get('tenant').replace('_', '').replace('-', ''):
            return tenant
    else:
        raise ValueError("{} is not a valid input".format(tenantname))


def collect_tis_logs(con_ssh):
    common.collect_software_logs(con_ssh=con_ssh)


def get_tis_timestamp(con_ssh):
    return con_ssh.exec_cmd('date +"%T"')[1]


def get_build_info(con_ssh):
    code, output = con_ssh.exec_cmd('cat /etc/build.info')
    build_path = None
    if code != 0:
        build_id = build_host = job = build_by = ' '
    else:
        # get build_id
        build_id = re.findall('''BUILD_ID=\"(.*)\"''', output)
        if build_id and build_id[0] != 'n/a':
            build_id = build_id[0]
        else:
            build_date = re.findall('''BUILD_DATE=\"(.*)\"''', output)
            if build_date and build_date[0] != 'n/a':
                build_id = build_date[0].rsplit(' ', 1)[0]
                build_id = str(build_id).replace(' ', '_').replace(':', '_')
            else:
                build_id = ' '

        # get build_host
        build_host = re.findall('''BUILD_HOST=\"(.*)\"''', output)
        build_host = build_host[0].split(sep='.')[0] if build_host else ' '

        # get jenkins job
        job = re.findall('''JOB=\"(.*)\"''', output)
        job = job[0] if job else ' '

        # get build_by
        build_by = re.findall('''BUILD_BY=\"(.*)\"''', output)
        build_by = build_by[0] if build_by else 'jenkins'   # Assume built by jenkins although this is likely wrong

        if build_id.strip():
            build_path = '/localhost/loadbuild/{}/{}/{}'.format(build_by, job, build_id)

    ProjVar.set_var(BUILD_ID=build_id, BUILD_SERVER=build_host, JOB=job, BUILD_BY=build_by, BUILD_PATH=build_path)

    return build_id, build_host, job, build_by


def _rsync_files_to_con1():
    if less_than_two_controllers():
        LOG.info("Less than two controllers on system. Skip copying file to controller-1.")
        return

    LOG.info("rsync test files from controller-0 to controller-1 if not already done")
    file_to_check = '/home/wrsroot/images/tis-centos-guest.img'
    try:
        with host_helper.ssh_to_host("controller-1") as con_1_ssh:
            if con_1_ssh.file_exists(file_to_check):
                LOG.info("Test files already exist on controller-1. Skip rsync.")
                return

    except Exception as e:
        LOG.error("Cannot ssh to controller-1. Skip rsync. \nException caught: {}".format(e.__str__()))
        return

    # cmd = 'scp -q -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null controller-0:/home/wrsroot/* ' \
    #       'controller-1:/home/wrsroot/'
    cmd = "rsync -avr -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' " \
          "/home/wrsroot/* controller-1:/home/wrsroot/"

    timeout = 1800
    with host_helper.ssh_to_host("controller-0") as con_0_ssh:
        LOG.info("rsync files from controller-0 to controller-1...")
        con_0_ssh.send(cmd)

        end_time = time.time() + timeout
        while time.time() < end_time:
            index = con_0_ssh.expect([con_0_ssh.prompt, PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=timeout,
                                     searchwindowsize=100)
            if index == 2:
                con_0_ssh.send('yes')

            if index == 1:
                con_0_ssh.send(HostLinuxCreds.get_password())

            if index == 0:
                output = int(con_0_ssh.exec_cmd('echo $?')[1])
                if output in [0, 23]:
                    LOG.info("Test files are successfully copied to controller-1 from controller-0")
                    break
                else:
                    raise exceptions.SSHExecCommandFailed("Failed to rsync files from controller-0 to controller-1")

        else:
            raise exceptions.TimeoutException("Timed out rsync files to controller-1")


def copy_test_files():
    _rsync_files_to_con1()


def get_auth_via_openrc(con_ssh):
    valid_keys = ['OS_AUTH_URL',
                  'OS_ENDPOINT_TYPE',
                  'CINDER_ENDPOINT_TYPE',
                  'OS_USER_DOMAIN_NAME',
                  'OS_PROJECT_DOMAIN_NAME',
                  'OS_IDENTITY_API_VERSION',
                  'OS_REGION_NAME',
                  'OS_INTERFACE']

    code, output = con_ssh.exec_cmd('cat /etc/nova/openrc')
    if code != 0:
        return None

    lines = output.splitlines()
    auth_dict = {}
    for line in lines:
        if 'export' in line:
            if line.split('export ')[1].split(sep='=')[0] in valid_keys:
                key, value = line.split(sep='export ')[1].split(sep='=')
                auth_dict[key.strip().upper()] = value.strip()

    return auth_dict


def get_lab_from_cmdline(lab_arg, installconf_path, controller_arg=None, compute_arg=None, storage_arg=None,
                         lab_files_dir=None, build_server=None):
    lab_dict = None
    if not lab_arg and not installconf_path:
        lab_dict = setup_consts.LAB
        # if lab_dict is None:
        #    raise ValueError("No lab is specified via cmdline or setup_consts.py")
        if lab_dict:
            LOG.warning("lab is not specified via cmdline! Using lab from setup_consts file: {}".format(
                lab_dict['short_name']))

    if installconf_path:
        installconf = configparser.ConfigParser()
        installconf.read(installconf_path)

        # Parse lab info
        lab_info_ = installconf['LAB']
        lab_name = lab_info_['LAB_NAME']
        if not lab_name:
            raise ValueError("Either --lab=<lab_name> or --install-conf=<full path of install configuration file> "
                             "has to be provided")
        if lab_arg and lab_arg.lower() != lab_name.lower():
            LOG.warning("Conflict in --lab={} and install conf file LAB_NAME={}. LAB_NAME in conf file will be used".
                        format(lab_arg, lab_name))
        lab_arg = lab_name

    if lab_dict is None:
        if lab_arg:
            lab_dict = get_lab_dict(lab_arg)
        else:
            LOG.warning("lab is not specified via cmdline! Using install args to find lab")
            lab_dict = get_lab_from_install_args(lab_arg, controller_arg, compute_arg, storage_arg, lab_files_dir,
                                                 build_server)

    return lab_dict


def get_lab_from_install_args(lab_arg, controllers, computes, storages, lab_files_dir, build_server):
    controller_nodes = [int(node) for node in controllers] if controllers else []
    compute_nodes = [int(node) for node in computes] if computes else []
    storage_nodes = [int(node) for node in storages] if storages else []
    __build_server = build_server if build_server and build_server != "" else BuildServerPath.DEFAULT_BUILD_SERVER
    files_server = __build_server
    if lab_files_dir:
        files_dir = lab_files_dir
        if files_dir.find(":/") != -1:
            files_server = files_dir[:files_dir.find(":/")]
            files_dir = files_dir[files_dir.find(":") + 1:]
    else:
        files_dir = None
    # Get lab info
    lab_info = None
    if lab_arg:
        lab_info = get_lab_dict(lab_arg)

    if controller_nodes and not lab_info:
        labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]
        labs = [lab_ for lab_ in labs if isinstance(lab_, dict)]
        for lab in labs:
            if 'controller_nodes' in lab:
                if controller_nodes == lab['controller_nodes']:
                    lab_info = lab
                    break
        # Add new entry
        if not lab_info:
            LOG.warning("no lab stored with the controller barcodes {}! Creating a new lab".format(controller_nodes))
            lab_info = {}
            controller_attributes = vlm_helper.get_attributes_dict(controller_nodes, val="barcodes")
            lab_info["controller_nodes"] = controller_nodes
            for i in range(0, len(controller_attributes)):
                controller_name = "controller-{}".format(i)
                lab_info["{} ip".format(controller_name)] = controller_attributes[i]["IP Address"]
            if files_dir and files_server:
                lab_info.update(get_info_from_lab_files(files_server, files_dir))
                lab_info["name"] = lab_info.pop("system_name") # rename system_name to name
            else:
                barcodes = controller_nodes + compute_nodes + storage_nodes
                aliases = vlm_helper.get_attributes_dict(barcodes, attr="alias", val="barcodes")
                print("list of aliases: {}".format(aliases))
                highest = "0"
                lowest = "inf" # arbitrarily large number
                for alias_dict in aliases:
                    print("alias dictionary: {}".format(alias_dict))
                    alias = alias_dict["alias"]
                    print("alias: {}".format(alias))
                    node_num_pattern = "-(\d+)"
                    node_num = re.search(node_num_pattern, alias).group(1)
                    if int(node_num) > int(highest):
                        highest = node_num
                    if float(node_num) < float(lowest):
                        lowest = node_num
                        base_name = alias
                lab_info["name"] = base_name + "_{}".format(highest) if highest > lowest else base_name
            short_naming_dict = {"wildcat": "WCP", "ironpass": "IP", "wolfpass": "WP", "supermicro": "SM"}
            short_name_pattern = ".*-(\d+)(_\d+)?"
            match = re.search(short_name_pattern, lab_info["name"])
            system_name = match.group(0)
            first_node_num = match.group(1)
            last_node_num = match.group(2) if match.group(2) else ""
            for server_type in short_naming_dict.keys():
                if server_type in system_name:
                    lab_info["short_name"] = short_naming_dict[server_type] + "_{}{}".format(first_node_num,
                                                                                             last_node_num)
            if not lab_info.get("short_name"):
                lab_info["short_name"] = lab_info["name"].split("-")[2] + "_{}{}".format(first_node_num,
                                                                                                 last_node_num)
            lab_info = add_lab_entry(floating_ip=None, dict_name=lab_info["short_name"].upper(), **lab_info)

    if files_dir and files_server and not lab_info:
        try:
            conf_file_info = get_info_from_lab_files(files_server, files_dir)
            lab_info = get_lab_dict(conf_file_info["system_name"])
        except ValueError:
            LOG.error("--file_dir path lead to a lab that is not supported. Please manually write install "
                      "configuration and try again. ")
            raise
        except AssertionError:
            LOG.error("Please ensure --file_dir was entered correctly and exists in {}. ".format(files_server))
            raise
    # Update lab info
    if compute_nodes:
        lab_info["compute_nodes"] = compute_nodes
    if storage_nodes:
        lab_info["storage_nodes"] = compute_nodes
    lab_dict = edit_lab_entry(lab_info["short_name"], **lab_info)
    LOG.warning("Discovered the following lab info: {}".format(lab_dict))

    return lab_dict


def is_vbox():
    lab_name = ProjVar.get_var('LAB_NAME')
    nat_name = ProjVar.get_var('NATBOX').get('name')

    return 'vbox' in lab_name or nat_name == 'localhost' or nat_name.startswith('128.224.')


def get_nodes_info():
    if is_vbox():
        return

    lab = ProjVar.get_var('LAB')
    nodes_info = create_node_dict(lab['controller_nodes'], 'controller')
    nodes_info.update(create_node_dict(lab.get('compute_nodes', None), 'compute'))
    nodes_info.update(create_node_dict(lab.get('storage_nodes', None), 'storage'))

    LOG.debug("Nodes info: \n{}".format(nodes_info))
    return nodes_info


def collect_telnet_logs_for_nodes(end_event):
    nodes_info = get_nodes_info()
    node_threads = []
    kwargs = {'prompt': '{}|:~\$'.format(TELNET_LOGIN_PROMPT), 'end_event': end_event}
    for node_name in nodes_info:
        kwargs['hostname'] = node_name
        kwargs['telnet_ip'] = nodes_info[node_name].telnet_ip
        kwargs['telnet_port'] = nodes_info[node_name].telnet_port
        node_thread = threading.Thread(name='Telnet-{}'.format(node_name), target=_collect_telnet_logs, kwargs=kwargs)
        node_thread.start()
        node_threads.append(node_thread)

    return node_threads


def _collect_telnet_logs(telnet_ip, telnet_port, end_event, prompt, hostname, timeout=None, collect_interval=60):
    node_telnet = TelnetClient(host=telnet_ip, prompt=prompt, port=telnet_port, hostname=hostname)
    if not timeout:
        timeout = 3600 * 48
    end_time = time.time() + timeout
    failure_count = 0
    while time.time() < end_time:
        if end_event.is_set():
            node_telnet.close()
            break
        try:
            # Read out everything in output buffer every minute
            node_telnet.connect(login=False)
            time.sleep(collect_interval)
            node_telnet.flush()
        except Exception as e:
            node_telnet.logger.error('Failed to collect telnet log. {}'.format(e))
            node_telnet.close()
            failure_count += 1
            if failure_count >= 5:
                node_telnet.logger.error("5 failures encountered to collect telnet logs. Abort.")
                raise
            time.sleep(60)      # cool down period if telnet connection fails
    else:
        node_telnet.logger.warning('Collect telnet log timed out')
        node_telnet.close()


def set_install_params(lab, skip, resume, installconf_path, controller0_ceph_mon_device, drop, patch_dir,
                       controller1_ceph_mon_device, ceph_mon_gib, wipedisk, boot, iso_path, security, low_latency, stop):
    if not lab and not installconf_path:
        raise ValueError("Either --lab=<lab_name> or --install-conf=<full path of install configuration file> "
                         "has to be provided")
    elif not installconf_path:
        installconf_path = write_installconf(lab=lab, controller=None, tis_build_dir=None, drop=drop,
                                             lab_files_dir=None, build_server=BuildServerPath.DEFAULT_BUILD_SERVER,
                                             compute=None, storage=None, license_path=None, guest_image=None,
                                             heat_templates=None, security=security, low_latency=low_latency, stop=stop)

    print("Setting Install vars : {} ".format(locals()))

    errors = []
    lab_to_install = lab
    drop = int(drop) if drop else None
    build_server = None
    host_build_dir = BuildServerPath.DEFAULT_HOST_BUILD_PATH
    guest_image = None
    files_server = None
    files_dir = None
    heat_templates = None
    license_path = None
    out_put_dir = None
    vbox = True if lab and 'vbox' in lab.lower() else False
    if vbox:
        LOG.info("The test lab is a VBOX TiS setup")

    if installconf_path:
        installconf = configparser.ConfigParser(allow_no_value=True)
        installconf.read(installconf_path)

        # Parse lab info
        lab_info_ = installconf['LAB']
        lab_name = lab_info_['LAB_NAME']
        vbox = True if 'vbox' in lab_name.lower() else False
        if vbox:
            LOG.info("The test lab is a VBOX TiS setup")
        if lab_name:
            lab_to_install = get_lab_dict(lab_name)

        if lab_to_install:
            con0_ip = lab_info_['CONTROLLER0_IP']
            if con0_ip:
                lab_to_install['controller-0 ip'] = con0_ip

            con1_ip = lab_info_['CONTROLLER1_IP']
            if con1_ip:
                lab_to_install['controller-1 ip'] = con1_ip

            float_ip = lab_info_['FLOATING_IP']
            if float_ip:
                lab_to_install['floating ip'] = float_ip

        else:
            raise ValueError("lab name has to be provided via cmdline option --lab=<lab_name> or inside install_conf "
                             "file")

        # Parse nodes info
        nodes_info = installconf['NODES']
        naming_map = {'CONTROLLERS': 'controller_nodes',
                      'COMPUTES': 'compute_nodes',
                      'STORAGES': 'storage_nodes'}

        for confkey, constkey in naming_map.items():
            if confkey in nodes_info:
                value_in_conf = nodes_info[confkey]
                if value_in_conf:
                    barcodes = value_in_conf.split(sep=' ')
                    lab_to_install[constkey] = barcodes
            else:
                continue

        if not lab_to_install['controller_nodes']:
            errors.append("Nodes barcodes have to be provided for custom lab")

        # Parse build info
        build_info = installconf['BUILD']
        conf_build_server = build_info['BUILD_SERVER']
        conf_host_build_dir = build_info['TIS_BUILD_PATH']
        if conf_build_server:
            build_server = conf_build_server
        if conf_host_build_dir:
            host_build_dir = conf_host_build_dir

        # Parse files info
        conf_files = installconf['CONF_FILES']
        conf_files_server = conf_files['FILES_SERVER']
        conf_files_dir = conf_files['FILES_DIR']
        conf_license_path = conf_files['LICENSE_PATH']
        conf_guest_image = conf_files['GUEST_IMAGE_PATH']
        conf_heat_templates = conf_files['HEAT_TEMPLATES']

        if conf_files_server:
            files_server = conf_files_server
        if conf_files_dir:
            files_dir = conf_files_dir
        else:
            files_dir = "{}/rt/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/{}".format(host_build_dir, lab_name)
        if conf_license_path:
            license_path = conf_license_path
        if conf_guest_image:
            guest_image = conf_guest_image
        if conf_heat_templates:
            heat_templates = conf_heat_templates

    else:
        lab_to_install = get_lab_dict(lab)

    if not lab_to_install.get('controller-0 ip', None):
        errors.append('Controller-0 ip has to be provided for custom lab')

    if errors:
        raise ValueError("Install param error(s): {}".format(errors))

    # compute directory for all logs based on lab, and timestamp on local machine
    out_put_dir = "/tmp/output_" + lab_to_install['name'] + '/' + time.strftime("%Y%m%d-%H%M%S")

    # add lab resource type and any other lab information in the lab files
    if low_latency:
        try:
            files_dir = files_dir + '-lowlatency'
            lab_info_dict = get_info_from_lab_files(files_server, files_dir, lab_name=lab_to_install["name"],
                           host_build_dir=host_build_dir)
        except:
            files_dir = files_dir[:files_dir.find('-lowlatency')]

    lab_info_dict = get_info_from_lab_files(files_server, files_dir, lab_name=lab_to_install["name"],
                                            host_build_dir=host_build_dir)
    lab_to_install.update(dict((system_label, system_info) for (system_label, system_info) in lab_info_dict.items() if "system" in system_label))
    multi_region_lab = lab_info_dict["multi_region"]
    dist_cloud_lab = lab_info_dict["dist_cloud"]

    if 'system_mode' not in lab_info_dict:
        if 'storage_nodes' in lab_to_install:
            system_mode = SysType.STORAGE
        else:
            system_mode = SysType.REGULAR
    else:
        if "simplex" in lab_info_dict['system_mode']:
            system_mode = SysType.AIO_SX
        else:
            system_mode = SysType.AIO_DX

    lab_to_install['system_mode'] = system_mode
    ProjVar.set_var(sys_type=system_mode)

    # add nodes dictionary
    lab_to_install.update(create_node_dict(lab_to_install['controller_nodes'], 'controller', vbox=vbox))
    if 'compute_nodes' in lab_to_install:
        lab_to_install.update(create_node_dict(lab_to_install['compute_nodes'], 'compute', vbox=vbox))
    if 'storage_nodes' in lab_to_install:
        lab_to_install.update(create_node_dict(lab_to_install['storage_nodes'], 'storage', vbox=vbox))

    if vbox:
        lab_to_install['boot_device_dict'] = VBOX_BOOT_INTERFACES
    else:
        lab_to_install['boot_device_dict'] = lab_info_dict['boot_device_dict']

    if vbox:
        # get the ip address of the local linux vm
        cmd = 'ip addr show | grep "128.224" | grep "\<inet\>" | awk \'{ print $2 }\' | awk -F "/" \'{ print $1 }\''
        local_external_ip = os.popen(cmd).read().strip()
        lab_to_install['local_ip'] = local_external_ip
        vbox_gw = installconf['VBOX_GATEWAY']
        external_ip = vbox_gw['EXTERNAL_IP']
        if external_ip and external_ip != local_external_ip:
            LOG.info("TiS VM external gwy IP is {}".format(external_ip))
            lab_to_install['external_ip'] = external_ip
            external_port = vbox_gw['EXTERNAL_PORT']
            if external_port:
                LOG.info("TiS VM external gwy port is {}".format(external_port))
                lab_to_install['external_port'] = external_port
            else:
                raise exceptions.UpgradeError("The  external access port along with external ip must be provided: {} "
                                              .format(external_ip))
        username = local_host.getpass.getuser()
        password = ''
        if "svc-cgcsauto" in username:
            password = SvcCgcsAuto.PASSWORD
        else:
            password = local_host.getpass.getpass()

        lab_to_install['local_user'] = username
        lab_to_install['local_password'] = password

    if resume:
        if isinstance(resume, str) and resume.isdigit():
            resume = int(resume)
        else:
            resume = fresh_install_helper.get_resume_step(lab_to_install)
    if stop is not None:
        stop = int(stop)

    InstallVars.set_install_vars(lab=lab_to_install, resume=resume,
                                 skips=skip,
                                 wipedisk=wipedisk,
                                 build_server=build_server,
                                 host_build_dir=host_build_dir,
                                 guest_image=guest_image,
                                 files_server=files_server,
                                 files_dir=files_dir,
                                 heat_templates=heat_templates,
                                 license_path=license_path,
                                 out_put_dir=out_put_dir,
                                 controller0_ceph_mon_device=controller0_ceph_mon_device,
                                 controller1_ceph_mon_device=controller1_ceph_mon_device,
                                 ceph_mon_gib=ceph_mon_gib,
                                 security=security,
                                 boot_type=boot,
                                 low_latency=low_latency,
                                 iso_path=iso_path,
                                 stop=stop,
                                 drop_num=drop,
                                 patch_dir=patch_dir,
                                 multi_region=multi_region_lab,
                                 dist_cloud=dist_cloud_lab
                                 )


def write_installconf(lab, controller, lab_files_dir, build_server, tis_build_dir, compute, storage, drop, patch_dir,
                      license_path, guest_image, heat_templates, boot, iso_path, low_latency, security, stop):
    """
    Writes a file in ini format of the fresh_install variables
    Args:
        lab: Str name of the lab to fresh_install
        controller: Str comma separated list of controller node barcodes
        lab_files_dir: Str path to the directory containing the lab files
        build_server: Str name of a valid build server. Default is yow-cgts4-lx
        tis_build_dir: Str path to the desired build directory. Default is the latest
        compute: Str comma separated list of compute node barcodes
        storage: Str comma separated list of storage node barcodes
        license_path: Str path to the license file
        guest_image: Str path to the guest image
        heat_templates: Str path to the python heat templates

    Returns: the path of the written file

    """
    __build_server = build_server if build_server and build_server != "" else BuildServerPath.DEFAULT_BUILD_SERVER
    host_build_dir = tis_build_dir if tis_build_dir and tis_build_dir != "" else BuildServerPath.DEFAULT_HOST_BUILD_PATH
    files_server = __build_server
    if lab_files_dir:
        files_dir = lab_files_dir
        if files_dir.find(":/") != -1:
            files_server = files_dir[:files_dir.find(":/")]
            files_dir = files_dir[files_dir.find(":") + 1:]
    else:
        files_dir = None
    if lab:
        lab_dict = get_lab_dict(lab)
    else:
        lab_dict = ProjVar.get_var("LAB")
    if not lab_dict:
        lab_dict = get_lab_from_install_args(lab, controller, compute, storage, lab_files_dir, build_server)
    files_dir = "{}/{}/yow/{}".format(host_build_dir, BuildServerPath.CONFIG_LAB_REL_PATH,
                                      install_helper.get_git_name(lab_dict['name'])) if not files_dir else files_dir
    # Write .ini file
    config = configparser.ConfigParser(allow_no_value=True)
    config.optionxform = str
    labconf_lab_dict = {}

    # [LAB] section
    for lab_key in lab_dict.keys():
        if lab_key == "name":
            labconf_key = "LAB_NAME"
            labconf_lab_dict[labconf_key] = lab_dict[lab_key]
            continue
        labconf_key = lab_key.replace(" ", "_")
        labconf_key = labconf_key.replace("-","")
        labconf_key = labconf_key.upper()
        labconf_lab_dict[labconf_key] = lab_dict[lab_key]
    # TODO: temp fix for simplex labs
    if "CONTROLLER1_IP" not in labconf_lab_dict.keys():
        labconf_lab_dict["CONTROLLER1_IP"] = ""

    # [NODES] section
    node_keys = [key for key in labconf_lab_dict if 'NODE' in key]
    node_values = [' '.join(list(map(str, labconf_lab_dict.pop(k)))) for k in node_keys]
    node_dict = dict(zip((k.replace("_NODES", "S") for k in node_keys), node_values))

    # [BUILD] and [CONF_FILES] section
    build_dict = {"BUILD_SERVER": build_server, "TIS_BUILD_PATH": tis_build_dir}
    files_dict = {"FILES_SERVER": files_server, "FILES_DIR": files_dir, "LICENSE_PATH": license_path,
                 "GUEST_IMAGE_PATH": guest_image, "HEAT_TEMPLATES": heat_templates}
    config["LAB"] = labconf_lab_dict
    config["NODES"] = node_dict
    config["BUILD"] = build_dict
    config["CONF_FILES"] = files_dict

    install_config_name = "{}_install.cfg.ini".format(lab_dict['short_name'])
    install_config_path = ProjVar.get_var('TEMP_DIR') + install_config_name
    try:
        with open(install_config_path, "w") as install_config_file:
            os.chmod(install_config_path, 0o777)
            config.write(install_config_file)
            install_config_file.close()
    except FileNotFoundError:
        os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
        with open(install_config_path, "w+") as install_config_file:
            os.chmod(install_config_path, 0o777)
            config.write(install_config_file)
            install_config_file.close()

    return install_config_path


def get_info_from_lab_files(conf_server, conf_dir, lab_name=None, host_build_dir=None):
    """
    retrieves information about the lab by parsing the lab files. If a specific server or directory isn't given
    will use the default build server and directory.
    Args:
        conf_server: str name of a valid build server (see: CGCSAuto/consts/build_server.py)
        conf_dir: str path to the directory containing the lab files
        lab_name: str name of the lab
        host_build_dir: str path to the desired build

    Returns: dict of key, value pairs of elements in the lab files that have "SYSTEM_" as a key.
    typically SYSTEM_NAME (from TiS_config.ini), and SYSTEM_MODE

    """
    lab_info_dict = {}
    info_prefix = "SYSTEM_"
    multi_region_identifer = "\[REGION2_PXEBOOT_NETWORK\]"
    dist_cloud_identifer = "DISTRIBUTED_CLOUD_ROLE"
    if conf_dir:
        lab_files_path = conf_dir
    elif lab_name is not None and host_build_dir is not None:
        lab_files_path = "{}/{}/yow/{}".format(host_build_dir, BuildServerPath.CONFIG_LAB_REL_PATH,
                                               install_helper.get_git_name(lab_name))
    else:
        raise ValueError("Could not access lab files")
    ssh_conn = install_helper.establish_ssh_connection(conf_server, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                                                       initial_prompt=Prompt.BUILD_SERVER_PROMPT_BASE.format(SvcCgcsAuto.USER, conf_server))
    assert ssh_conn.exec_cmd('test -d {}'.format(lab_files_path))[0] == 0, 'Lab config path not found in {}:{}'.format(conf_server, lab_files_path)

    # check lab configuration for special cases (i.e. distributed cloud or multi region)
    multi_region = ssh_conn.exec_cmd("grep '{}' {}/TiS_config.ini_centos".format(multi_region_identifer, lab_files_path))[0] == 0
    dist_cloud = ssh_conn.exec_cmd("grep '{}' {}/TiS_config.ini_centos".format(dist_cloud_identifer, lab_files_path))[0] == 0
    lab_info_dict["multi_region"] = multi_region
    lab_info_dict["dist_cloud"] = dist_cloud

    # get boot_device_dict
    configname = os.path.basename(os.path.normpath(conf_dir))
    settings_filepath = conf_dir + "/settings.ini"
    if ssh_conn.exec_cmd('test -f {}/settings.ini'.format(conf_dir))[0] == 0:
        lab_info_dict["boot_device_dict"] = create_node_boot_dict(configname=configname, settings_filepath=settings_filepath,
                                                             settings_server_conn=ssh_conn)
    else:
        lab_info_dict["boot_device_dict"] = create_node_boot_dict(configname=configname)

    # collect SYSTEM info
    rc, output = ssh_conn.exec_cmd('grep -r --color=none {} {}'.format(info_prefix, lab_files_path), rm_date=False)
    assert rc == 0, 'Lab config path not found in {}:{}'.format(conf_server, lab_files_path)
    lab_info = output.replace(' ', '')
    lab_info_list = lab_info.splitlines()
    for line in lab_info_list:
        key = line[line.find(info_prefix):line.find('=')].lower()
        val = line[line.find('=') + 1:].lower()
        lab_info_dict[key] = val.replace('"', '')
    # Workaround for r430 labs
    lab_name = lab_info_dict["system_name"]
    last_num = -1
    if not lab_name[last_num].isdigit():
        while not lab_name[last_num].isdigit():
            last_num -= 1
        lab_info_dict["name"] = lab_name[:last_num+1]

    return lab_info_dict


def is_https(con_ssh):
    return keystone_helper.is_https_lab(con_ssh=con_ssh, source_openrc=True)


def scp_vswitch_log(con_ssh, hosts, log_path=None):
    source_file = '/scratch/var/extra/vswitch.info'
    for host in hosts:

        dest_file = "{}_vswitch.info".format(host)
        dest_file = '{}/{}'.format(WRSROOT_HOME, dest_file)

        if host == 'controller-0':
            LOG.info('cp vswitch log to {}'.format(dest_file))
            con_ssh.exec_cmd('cp {} {}'.format(source_file, dest_file))
        else:
            LOG.info("scp vswitch log from {} to controller-0".format(host))
            con_ssh.scp_files(source_file, dest_file, source_server=host, dest_server='controller-0',
                              source_user=HostLinuxCreds.get_user(), source_password=HostLinuxCreds.get_password(),
                              dest_password=HostLinuxCreds.get_password(), dest_user='', timeout=30, sudo=True,
                              sudo_password=None, fail_ok=True)

    LOG.info("SCP vswitch log from lab to automation log dir")
    if log_path is None:
        log_path = '{}/{}'.format(WRSROOT_HOME, '*_vswitch.info')
    source_ip = ProjVar.get_var('LAB')['controller-0 ip']
    dest_dir = ProjVar.get_var('PING_FAILURE_DIR')
    scp_to_local(dest_path=dest_dir,
                 source_user=HostLinuxCreds.get_user(), source_password=HostLinuxCreds.get_password(),
                 source_path=log_path, source_ip=source_ip, timeout=60)


def list_migration_history(con_ssh):
    nova_helper.get_migration_list_table(con_ssh=con_ssh)


def get_version_and_patch_info():
    version = ProjVar.get_var('SW_VERSION')[0]
    info = 'Software Version: {}\n'.format(version)

    patches = ProjVar.get_var('PATCH')
    if patches:
        info += 'Patches:\n{}\n'.format('\n'.join(patches))

    # LOG.info("SW Version and Patch info: {}".format(info))
    return info


def set_session(con_ssh):
    version = lab_info._get_build_info(con_ssh, 'SW_VERSION')[0]
    ProjVar.set_var(append=True, SW_VERSION=version)

    patches = lab_info._get_patches(con_ssh=con_ssh, rtn_str=False)
    if patches:
        ProjVar.set_var(PATCH=patches)

    patches = '\n'.join(patches)
    tag = ProjVar.get_var('REPORT_TAG')
    if tag and ProjVar.get_var('CGCS_DB'):
        try:
            from utils.cgcs_reporter import upload_results
            sw_version = '-'.join(ProjVar.get_var('SW_VERSION'))
            build_id = ProjVar.get_var('BUILD_ID')
            build_server = ProjVar.get_var('BUILD_SERVER')
            session_id = upload_results.upload_test_session(lab_name=ProjVar.get_var('LAB')['name'],
                                                            build_id=build_id,
                                                            build_server=build_server,
                                                            sw_version=sw_version,
                                                            patches=patches,
                                                            log_dir=ProjVar.get_var('LOG_DIR'),
                                                            tag=tag)
            ProjVar.set_var(SESSION_ID=session_id)
            LOG.info("Test session id: {}".format(session_id))
        except:
            LOG.exception("Unable to upload test session")


def enable_disable_keystone_debug(con_ssh, enable=True):
    """
    Enable or disable keystone debug from keystone.conf
    Args:
        con_ssh:
        enable:

    Returns:

    """
    restart = False
    file = '/etc/keystone/keystone.conf'
    LOG.info("Set keystone debug to {}".format(enable))
    if con_ssh.exec_sudo_cmd('cat {} | grep --color=never "insecure_debug = True"'.format(file))[0] == 0:
        if not enable:
            con_ssh.exec_sudo_cmd("sed -i '/^insecure_debug = /g' {}".format(file))
            restart = True
    else:
        if enable:
            find_cmd = "grep --color=never -E '^(debug|#debug) = ' {} | tail -1".format(file)
            pattern = con_ssh.exec_sudo_cmd(find_cmd, fail_ok=False)[1]
            con_ssh.exec_sudo_cmd("sed -i -E '/^{}/a insecure_debug = True' {}".format(pattern, file), fail_ok=False)
            restart = True

    if restart:
        is_enabled = con_ssh.exec_sudo_cmd('cat {} | grep --color=never insecure_debug'.format(file))[0] == 0
        if (enable and not is_enabled) or (is_enabled and not enable):
            LOG.warning("Keystone debug is not {} in keystone.conf!".format(enable))
            return

        LOG.info("Restart keystone service after toggling keystone debug")
        con_ssh.exec_sudo_cmd('sm-restart-safe service keystone', fail_ok=False)
        time.sleep(3)


def add_ping_failure(test_name):
    file_path = '{}{}'.format(ProjVar.get_var('PING_FAILURE_DIR'), 'ping_failures.txt')
    with open(file_path, mode='a') as f:
        f.write(test_name + '\n')


def set_region(region=None):
    local_region = CliAuth.get_var('OS_REGION_NAME')
    if not region:
        region = local_region
    Tenant.set_region(region=region)
    ProjVar.set_var(REGION=region)
    for tenant in ('tenant1', 'tenant2'):
        region_tenant = '{}{}'.format(tenant, REGION_MAP[region])
        Tenant.update_tenant_dict(tenant, username=region_tenant, tenant=region_tenant)
        if region != local_region:
            keystone_helper.add_or_remove_role(add_=True, role='admin', user=region_tenant, project=region_tenant)


def set_sys_type(con_ssh):
    sys_type = system_helper.get_sys_type(con_ssh=con_ssh)
    ProjVar.set_var(SYS_TYPE=sys_type)


def arp_for_fip(lab, con_ssh):
    fip = lab['floating ip']
    code, output = con_ssh.exec_cmd('ip addr | grep -B 4 {} | grep --color=never BROADCAST'.format(fip))
    if output:
        target_str = output.splitlines()[-1]
        dev = target_str.split(sep=': ')[1].split('@')[0]
        con_ssh.exec_cmd('arping -c 3 -A -q -I {} {}'.format(dev, fip))


def collect_sys_net_info(lab):
    """
    Collect networking related info on system if system cannot be reached.
    Only applicable to hardware systems.

    Args:
        lab (dict): lab to collect networking info for.

    Following info will be collected:
        - ping/ssh fip/uip from NatBox and Test server
        - if able to ssh to lab, collect ip neigh, ip route, ip addr.
            - ping/ssh NatBox from lab
            - ping lab default gateway from NatBox

    """
    LOG.warning("Collecting system network info upon session setup failure")
    res_ = {}
    source_user = SvcCgcsAuto.USER
    source_pwd = SvcCgcsAuto.PASSWORD
    source_prompt = SvcCgcsAuto.PROMPT

    dest_info_collected = False
    arp_sent = False
    for source_server in ('natbox', 'ts'):
        source_ip = NatBoxes.NAT_BOX_HW['ip'] if source_server == 'natbox' else SvcCgcsAuto.SERVER
        source_ssh = SSHClient(source_ip, source_user, source_pwd, initial_prompt=source_prompt)
        source_ssh.connect()
        for ip_type_ in ('fip', 'uip'):
            lab_ip_type = 'floating ip' if ip_type_ == 'fip' else 'controller-0 ip'
            dest_ip = lab[lab_ip_type]

            for action in ('ping', 'ssh'):
                res_key = '{}_{}_from_{}'.format(action, ip_type_, source_server)
                res_[res_key] = False
                LOG.info("\n=== {} to lab {} {} from {}".format(action, ip_type_, dest_ip, source_server))
                if action == 'ping':
                    # ping lab
                    pkt_loss_rate_ = network_helper.ping_server(server=dest_ip, ssh_client=source_ssh, fail_ok=True)[0]
                    if pkt_loss_rate_ == 100:
                        LOG.warning('Failed to ping lab {} from {}'.format(ip_type_, source_server))
                        break
                    res_[res_key] = True
                else:
                    # ssh to lab
                    dest_user = HostLinuxCreds.get_user()
                    dest_pwd = HostLinuxCreds.get_password()
                    prompt = CONTROLLER_PROMPT

                    try:
                        dest_ssh = SSHFromSSH(source_ssh, dest_ip, dest_user, dest_pwd, initial_prompt=prompt)
                        dest_ssh.connect()
                        res_[res_key] = True

                        # collect info on tis system if able to ssh to it
                        if not dest_info_collected:
                            LOG.info("\n=== ssh to lab {} from {} succeeded. Collect info from TiS system".format(
                                    ip_type_, source_server))
                            dest_info_collected = True
                            dest_ssh.exec_cmd('ip addr')
                            dest_ssh.exec_cmd('ip neigh')
                            dest_ssh.exec_cmd('ip route')
                            default_gateway = dest_ssh.exec_cmd(' ip route | grep --color=never default')[1]

                            # ping natbox from lab
                            nat_ip = NatBoxes.NAT_BOX_HW['ip']
                            pkt_loss_rate_to_nat = network_helper.ping_server(server=nat_ip,
                                                                              ssh_client=dest_ssh, fail_ok=True)[0]
                            res_['ping_natbox_from_lab'] = True if pkt_loss_rate_to_nat < 100 else False

                            # ssh to natbox from lab if ping succeeded
                            if pkt_loss_rate_to_nat < 100:
                                res_key_ssh_nat = 'ssh_natbox_from_lab'
                                res_[res_key_ssh_nat] = False
                                try:
                                    nat_ssh = SSHFromSSH(dest_ssh, nat_ip, source_user, source_pwd,
                                                         initial_prompt=source_prompt)
                                    nat_ssh.connect()
                                    res_[res_key_ssh_nat] = True
                                    nat_ssh.close()
                                except:
                                    LOG.warning('Failed to ssh to NatBox from lab')

                            # ping default gateway from natbox
                            if default_gateway:
                                default_gateway = re.findall('default via (.*) dev .*', default_gateway)[0]

                                nat_ssh_ = SSHClient(nat_ip, source_user, source_pwd, initial_prompt=source_prompt)
                                nat_ssh_.connect()
                                pkt_loss_rate_ = network_helper.ping_server(server=default_gateway,
                                                                            ssh_client=nat_ssh_, fail_ok=True)[0]
                                res_['ping_default_gateway_from_natbox'] = True if \
                                    pkt_loss_rate_ < 100 else False

                            # send arp if unable to ping fip from natbox
                            if res_.get('ping_fip_from_natbox') is False:
                                arp_for_fip(lab=lab, con_ssh=dest_ssh)
                                arp_sent = True
                        dest_ssh.close()
                    except:
                        LOG.warning('Failed to ssh to lab {} from {}'.format(ip_type_, source_server))

        source_ssh.close()

    if arp_sent:
        source_ip = NatBoxes.NAT_BOX_HW['ip']
        nat_ssh = SSHClient(source_ip, source_user, source_pwd, initial_prompt=source_prompt)
        nat_ssh.connect()
        pkt_loss_rate_ = network_helper.ping_server(server=lab['floating ip'], ssh_client=nat_ssh, fail_ok=True)[0]
        if pkt_loss_rate_ == 100:
            LOG.warning('Failed to ping lab fip from natbox after arp')
            res_['ping_fip_from_natbox_after_arp'] = False
        else:
            res_['ping_fip_from_natbox_after_arp'] = True

    LOG.info("Lab networking info collected: {}".format(res_))

    return res_


def setup_remote_cli_client():
    """
    Download openrc files from horizon andinstall remote cli clients to virtualenv
    Notes: This has to be called AFTER set_region, so that the tenant dict will be updated as per region.

    Returns (RemoteCliClient)

    """
    from keywords import horizon_helper
    # download openrc files
    horizon_helper.download_openrc_files()

    # install remote cli clients
    client = RemoteCLIClient.get_remote_cli_client()

    # copy test files
    LOG.info("Copy test files from controller to localhost for remote cli tests")
    for dir_name in ('images/', 'heat/', 'userdata/'):
        dest_path = '{}/{}'.format(ProjVar.get_var('TEMP_DIR'), dir_name)
        os.makedirs(dest_path, exist_ok=True)
        common.scp_from_active_controller_to_localhost(source_path='{}/{}/*'.format(WRSROOT_HOME, dir_name),
                                          dest_path=dest_path, is_dir=True)

    return client


def initialize_server(server_hostname, prompt=None):
    if prompt is None:
        prompt = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', server_hostname)

    server_conn = SSHClient(server_hostname, user=SvcCgcsAuto.USER,
                            password=SvcCgcsAuto.PASSWORD, initial_prompt=prompt)
    server_conn.connect()
    server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    server_dict = {"name": server_hostname, "prompt": prompt, "ssh_conn": server_conn}

    return build_server.Server(**server_dict)
