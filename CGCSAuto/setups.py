import configparser
import os
import re
import threading
import time

from consts.auth import Tenant, HostLinuxCreds, SvcCgcsAuto, CliAuth
from consts.cgcs import Prompt, MULTI_REGION_MAP, SUBCLOUD_PATTERN, SysType, DROPS
from consts.filepaths import WRSROOT_HOME, BuildServerPath
from consts.lab import Labs, add_lab_entry, NatBoxes, update_lab
from consts.proj_vars import ProjVar, InstallVars
from consts import build_server
from keywords import vm_helper, host_helper, nova_helper, system_helper, keystone_helper, common, network_helper, \
    install_helper, vlm_helper, dc_helper, container_helper
from utils import exceptions, lab_info
from utils import local_host
from utils.clients.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient, PASSWORD_PROMPT, SSHFromSSH
from utils.clients.local import RemoteCLIClient
from utils.clients.telnet import TELNET_LOGIN_PROMPT, TelnetClient
from utils.node import create_node_boot_dict, create_node_dict, VBOX_BOOT_INTERFACES
from utils.tis_log import LOG


def less_than_two_controllers(con_ssh=None, auth_info=Tenant.get('admin')):
    return len(system_helper.get_controllers(con_ssh=con_ssh, auth_info=auth_info)) < 2


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


def setup_primary_tenant(tenant):
    Tenant.set_primary(tenant)
    LOG.info("Primary Tenant for test session is set to {}".format(tenant['tenant']))


def setup_natbox_ssh(natbox):
    natbox_ip = natbox['ip']
    NATBoxClient.set_natbox_client(natbox_ip)
    nat_ssh = NATBoxClient.get_natbox_client()
    ProjVar.set_var(natbox_ssh=nat_ssh)

    return nat_ssh


def setup_keypair(con_ssh, nat_ssh=None):
    """
    copy private keyfile from controller-0:/opt/platform to natbox: priv_keys/
    Args:
        nat_ssh (SSHClient): NATBox client
        con_ssh (SSHClient)
    """
    if not container_helper.is_stx_openstack_deployed(con_ssh=con_ssh):
        LOG.info("stx-openstack is not applied. Skip nova keypair config.")
        return

    LOG.info("scp key file from controller to NATBox")
    # keyfile path that can be specified in testcase config
    keyfile_stx_origin = os.path.normpath(ProjVar.get_var('STX_KEYFILE_PATH'))

    # keyfile will always be copied to wrsroot home dir first and update file permission
    keyfile_stx_final = os.path.normpath(ProjVar.get_var('STX_KEYFILE_WRS_HOME'))
    public_key_stx = '{}.pub'.format(keyfile_stx_final)
    final_dir = os.path.dirname(keyfile_stx_final)

    # keyfile will also be saved to /opt/platform as well, so it won't be lost during system upgrade.
    keyfile_opt_pform = '/opt/platform/id_rsa'

    # copy keyfile to following NatBox location. This can be specified in testcase config
    keyfile_path_natbox = os.path.normpath(ProjVar.get_var('NATBOX_KEYFILE_PATH'))

    auth_info = Tenant.get_primary()
    keypair_name = auth_info.get('nova_keypair', 'keypair-{}'.format(auth_info['user']))
    nova_keypair = nova_helper.get_keypairs(name=keypair_name, auth_info=auth_info)

    if not con_ssh.file_exists(keyfile_stx_final):
        with host_helper.ssh_to_host('controller-0', con_ssh=con_ssh) as con_0_ssh:
            if not con_0_ssh.file_exists(keyfile_opt_pform):
                if con_0_ssh.file_exists(keyfile_stx_origin):
                    # Given private key file exists. Need to ensure public key exists in same dir.
                    if not con_0_ssh.file_exists('{}.pub'.format(keyfile_stx_origin)) and not nova_keypair:
                        raise FileNotFoundError('{}.pub is not found'.format(keyfile_stx_origin))
                else:
                    # Need to generate ssh key
                    if nova_keypair:
                        raise FileNotFoundError("Cannot find private key for existing nova keypair {}".
                                                format(nova_keypair))

                    con_0_ssh.exec_cmd("ssh-keygen -f '{}' -t rsa -N ''".format(keyfile_stx_origin), fail_ok=False)
                    if not con_0_ssh.file_exists(keyfile_stx_origin):
                        raise FileNotFoundError("{} not found after ssh-keygen".format(keyfile_stx_origin))

                # keyfile_stx_origin and matching public key should now exist on controller-0
                # copy keyfiles to home dir and opt platform dir
                con_0_ssh.exec_cmd('cp {} {}'.format(keyfile_stx_origin, keyfile_stx_final), fail_ok=False)
                con_0_ssh.exec_cmd('cp {}.pub {}'.format(keyfile_stx_origin, public_key_stx), fail_ok=False)
                con_0_ssh.exec_sudo_cmd('cp {} {}'.format(keyfile_stx_final, keyfile_opt_pform), fail_ok=False)

            # Make sure owner is wrsroot
            # If private key exists in opt platform, then it must also exist in home dir
            con_0_ssh.exec_sudo_cmd('chown wrsroot:wrs {}'.format(keyfile_stx_final), fail_ok=False)

        # ssh private key should now exists under home dir and opt platform on controller-0
        if con_ssh.get_hostname() != 'controller-0':
            # copy file from controller-0 home dir to controller-1
            con_ssh.scp_on_dest(source_user=HostLinuxCreds.get_user(),
                                source_ip='controller-0',
                                source_path='{}*'.format(keyfile_stx_final),
                                source_pswd=HostLinuxCreds.get_password(),
                                dest_path=final_dir, timeout=60)

    if not nova_keypair:
        LOG.info("Create nova keypair {} using public key {}".format(keypair_name, public_key_stx))
        if not con_ssh.file_exists(public_key_stx):
            con_ssh.scp_on_dest(source_user=HostLinuxCreds.get_user(), source_ip='controller-0',
                                source_path=public_key_stx,
                                source_pswd=HostLinuxCreds.get_password(),
                                dest_path=public_key_stx, timeout=60)
            con_ssh.exec_sudo_cmd('chown wrsroot:wrs {}'.format(public_key_stx), fail_ok=False)

        if ProjVar.get_var('REMOTE_CLI'):
            dest_path = os.path.join(ProjVar.get_var('TEMP_DIR'), os.path.basename(public_key_stx))
            common.scp_from_active_controller_to_localhost(source_path=public_key_stx, dest_path=dest_path, timeout=60)
            public_key_stx = dest_path
            LOG.info("Public key file copied to localhost: {}".format(public_key_stx))

        nova_helper.create_keypair(keypair_name, public_key=public_key_stx, auth_info=auth_info)

    # ssh private key should now exist under keyfile_path
    if not nat_ssh:
        nat_ssh = NATBoxClient.get_natbox_client()

    nat_ssh.exec_cmd('mkdir -p {}'.format(os.path.dirname(keyfile_path_natbox)))
    tis_ip = ProjVar.get_var('LAB').get('floating ip')
    for i in range(10):
        try:
            nat_ssh.scp_on_dest(source_ip=tis_ip,
                                source_user=HostLinuxCreds.get_user(),
                                source_pswd=HostLinuxCreds.get_password(),
                                source_path=keyfile_stx_final,
                                dest_path=keyfile_path_natbox, timeout=120)
            LOG.info("private key is copied to NatBox: {}".format(keyfile_path_natbox))
            break
        except exceptions.SSHException as e:
            if i == 9:
                raise

            LOG.info(e.__str__())
            time.sleep(10)


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
    labs = get_labs_list()

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


def get_labs_list():
    labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]
    labs = [lab_ for lab_ in labs if isinstance(lab_, dict)]
    return labs


def get_dc_labs_list(labs):
    if not labs:
        labs = get_labs_list()

    dc_labs = [lab for lab in labs if any([k for k, v in lab.items() if 'subcloud' in k and isinstance(v, dict)])]
    return dc_labs


def is_lab_subcloud(lab):
    dc_labs = get_dc_labs_list(get_labs_list())
    for dc_lab in dc_labs:
        subclouds = [k for k, v in dc_lab.items() if 'subcloud' in k]
        for subcloud in subclouds:
            if lab['short_name'] == dc_lab[subcloud]['short_name']:
                dc_float_ip = dc_lab['floating ip']
                return True, subcloud, dc_float_ip

    return False, None, None


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


def set_build_info(con_ssh):
    code, output = con_ssh.exec_cmd('cat /etc/build.info')
    build_path = sw_version = None
    if code != 0:
        build_id = build_host = job = build_by = ' '
    else:
        # get build_id
        build_id = re.findall('''BUILD_ID=\"(.*)\"''', output)
        build_id = build_id[0] if build_id else ''

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
            build_path = '/localdisk/loadbuild/{}/{}/{}'.format(build_by, job, build_id)

        # get sw_version
        sw_version = re.findall('''SW_VERSION=\"(.*)\"''', output)
        sw_version = sw_version[0] if sw_version else None

    ProjVar.set_var(BUILD_ID=build_id, BUILD_SERVER=build_host, JOB=job, BUILD_BY=build_by, BUILD_PATH=build_path,
                    BUILD_INFO=output)
    if sw_version:
        existing_versions = ProjVar.get_var('SW_VERSION')
        if not (existing_versions and sw_version == existing_versions[-1]):
            ProjVar.set_var(append=True, SW_VERSION=sw_version)

    return build_id, build_host, job, build_by


def _rsync_files_to_con1(con_ssh=None, central_region=False, file_to_check=None):
    region = 'RegionOne' if central_region else None
    auth_info = Tenant.get('admin', dc_region=region)
    if less_than_two_controllers(auth_info=auth_info, con_ssh=con_ssh):
        LOG.info("Less than two controllers on system. Skip copying file to controller-1.")
        return

    LOG.info("rsync test files from controller-0 to controller-1 if not already done")
    if not file_to_check:
        file_to_check = '/home/wrsroot/images/tis-centos-guest.img'
    try:
        with host_helper.ssh_to_host("controller-1", con_ssh=con_ssh) as con_1_ssh:
            if con_1_ssh.file_exists(file_to_check):
                LOG.info("Test files already exist on controller-1. Skip rsync.")
                return

    except Exception as e:
        LOG.error("Cannot ssh to controller-1. Skip rsync. \nException caught: {}".format(e.__str__()))
        return

    cmd = "rsync -avr -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' " \
          "/home/wrsroot/* controller-1:/home/wrsroot/"

    timeout = 1800
    with host_helper.ssh_to_host("controller-0", con_ssh=con_ssh) as con_0_ssh:
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
    con_ssh = None
    central_region = False
    if ProjVar.get_var('IS_DC'):
        _rsync_files_to_con1(con_ssh=ControllerClient.get_active_controller(name=ProjVar.get_var('PRIMARY_SUBCLOUD')),
                             file_to_check='{}/heat/README'.format(WRSROOT_HOME), central_region=central_region)
        con_ssh = ControllerClient.get_active_controller(name='RegionOne')
        central_region = True

    _rsync_files_to_con1(con_ssh=con_ssh, central_region=central_region)


def get_auth_via_openrc(con_ssh, use_telnet=False, con_telnet=None):
    valid_keys = ['OS_AUTH_URL',
                  'OS_ENDPOINT_TYPE',
                  'CINDER_ENDPOINT_TYPE',
                  'OS_USER_DOMAIN_NAME',
                  'OS_PROJECT_DOMAIN_NAME',
                  'OS_IDENTITY_API_VERSION',
                  'OS_REGION_NAME',
                  'OS_INTERFACE',
                  'OS_KEYSTONE_REGION_NAME']
    if use_telnet and con_telnet:
        code, output = con_telnet.exec_cmd('cat /etc/platform/openrc')
    else:
        code, output = con_ssh.exec_cmd('cat /etc/platform/openrc')

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
                         lab_files_dir=None, bs=None):
    lab_dict = None
    if not lab_arg and not installconf_path:
        raise ValueError("No lab is specified via cmdline or install_conf")

    if installconf_path:
        installconf = configparser.ConfigParser(allow_no_value=True)
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

    if controller_arg:
        lab_dict = get_lab_from_install_args(lab_arg, controller_arg, compute_arg, storage_arg, lab_files_dir,
                                             bs=bs)

    if lab_dict is None:
        if lab_arg:
            lab_dict = get_lab_dict(lab_arg)
    return lab_dict


def get_lab_from_install_args(lab_arg, controllers, computes, storages, lab_files_dir, bs):
    p = r'[,| ]+'
    controller_nodes = [int(node) for node in re.split(p, controllers.strip())] if controllers else []
    compute_nodes = [int(node) for node in re.split(p, computes.strip())] if computes else []
    storage_nodes = [int(node) for node in re.split(p, storages.strip())] if storages else []
    __build_server = bs if bs and bs != "" else BuildServerPath.DEFAULT_BUILD_SERVER
    files_server = __build_server
    if lab_files_dir:
        files_dir = lab_files_dir
        if files_dir.find(":/") != -1:
            files_server = files_dir[:files_dir.find(":/")]
            files_dir = files_dir[files_dir.find(":") + 1:]
    else:
        files_dir = None
    # Get lab info
    lab_info_ = None
    if lab_arg:
        lab_info_ = get_lab_dict(lab_arg)

    if controller_nodes and not lab_info_:
        labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]
        labs = [lab_ for lab_ in labs if isinstance(lab_, dict)]
        for lab in labs:
            if 'controller_nodes' in lab:
                if controller_nodes == lab['controller_nodes']:
                    lab_info_ = lab
                    break
        # Add new entry
        if not lab_info_:
            LOG.warning("no lab stored with the controller barcodes {}! Creating a new lab".format(controller_nodes))
            lab_info_ = {}
            controller_attributes = vlm_helper.get_attributes_dict(controller_nodes, val="barcodes")
            lab_info_["controller_nodes"] = controller_nodes
            for i in range(0, len(controller_attributes)):
                controller_name = "controller-{}".format(i)
                lab_info_["{} ip".format(controller_name)] = controller_attributes[i]["IP Address"]
            base_name = ''
            if files_dir and files_server:
                lab_info_.update(get_info_from_lab_files(files_server, files_dir))
                lab_info_["name"] = lab_info_.pop("system_name")    # rename system_name to name
            else:
                barcodes = controller_nodes + compute_nodes + storage_nodes
                aliases = vlm_helper.get_attributes_dict(barcodes, attr="alias", val="barcodes")
                print("list of aliases: {}".format(aliases))
                highest = "0"
                lowest = "inf"  # arbitrarily large number
                for alias_dict in aliases:
                    print("alias dictionary: {}".format(alias_dict))
                    alias = alias_dict["alias"]
                    print("alias: {}".format(alias))
                    node_num_pattern = r"-(\d+)"
                    node_num = re.search(node_num_pattern, alias).group(1)
                    if int(node_num) > int(highest):
                        highest = node_num
                    if float(node_num) < float(lowest):
                        lowest = node_num
                        base_name = alias
                lab_info_["name"] = base_name + "_{}".format(highest) if highest > lowest else base_name

            short_naming_dict = {"wildcat": "WCP", "ironpass": "IP", "wolfpass": "WP", "supermicro": "SM"}
            short_name_pattern = r".*-(\d+)(_\d+)?"
            match = re.search(short_name_pattern, lab_info_["name"])
            system_name = match.group(0)
            first_node_num = match.group(1)
            last_node_num = match.group(2) if match.group(2) else ""
            for server_type in short_naming_dict.keys():
                if server_type in system_name:
                    lab_info_["short_name"] = short_naming_dict[server_type] + "_{}{}".\
                        format(first_node_num, last_node_num)
            if not lab_info_.get("short_name"):
                lab_info_["short_name"] = lab_info_["name"].split("-")[2] + "_{}{}".\
                    format(first_node_num, last_node_num)

    if files_dir and files_server and not lab_info_:
        try:
            conf_file_info = get_info_from_lab_files(files_server, files_dir)
            lab_info_ = get_lab_dict(conf_file_info["system_name"])
        except ValueError:
            LOG.error("--file_dir path lead to a lab that is not supported. Please manually write install "
                      "configuration and try again. ")
            raise
        except AssertionError:
            LOG.error("Please ensure --file_dir was entered correctly and exists in {}. ".format(files_server))
            raise
    # Update lab info
    if compute_nodes:
        lab_info_["compute_nodes"] = compute_nodes
    if storage_nodes:
        lab_info_["storage_nodes"] = storage_nodes
    lab_dict = update_lab(lab_dict_name=lab_info_["short_name"].upper(), lab_name=lab_info_["short_name"],
                          floating_ip=None, **lab_info_)
    LOG.warning("Discovered the following lab info: {}".format(lab_dict))

    return lab_dict


def is_vbox(lab=None):
    if not lab:
        lab = ProjVar.get_var('LAB')
    lab_name = lab['name']
    nat_name = ProjVar.get_var('NATBOX').get('name')

    return 'vbox' in lab_name or nat_name == 'localhost' or nat_name.startswith('128.224.')


def get_nodes_info(lab=None):

    if not lab:
        lab = ProjVar.get_var('LAB')

    if is_vbox(lab=lab):
        return

    nodes_info = create_node_dict(lab['controller_nodes'], 'controller')
    nodes_info.update(create_node_dict(lab.get('compute_nodes', None), 'compute'))
    nodes_info.update(create_node_dict(lab.get('storage_nodes', None), 'storage'))

    LOG.debug("Nodes info: \n{}".format(nodes_info))
    return nodes_info


def collect_telnet_logs_for_nodes(end_event):
    nodes_info = get_nodes_info()
    node_threads = []
    kwargs = {'prompt': r'{}|:~\$'.format(TELNET_LOGIN_PROMPT), 'end_event': end_event}
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


def set_install_params(installconf_path, lab=None, skip=None, resume=False, controller0_ceph_mon_device=None, drop=None,
                       patch_dir=None, ovs=False, build_server=None, tis_build_dir="latest_build",
                       boot_server=None, controller1_ceph_mon_device=None, ceph_mon_gib=None, wipedisk=False,
                       boot="feed", iso_path=None, security="standard", low_latency=False, stop=None,
                       kubernetes=False, dc_float_ip=None, install_subcloud=None, no_openstack=False,
                       ipv6_config=False, helm_chart_path=None, no_manage=False,
                       deploy_openstack_from_controller_1=False, extract_deploy_config=False):

    if not lab and not installconf_path:
        raise ValueError("Either --lab=<lab_name> or --install-conf=<full path of install configuration file> "
                         "has to be provided")

    if not installconf_path:
        installconf_path = write_installconf(lab=lab, controller=None,
                                             tis_build_dir=tis_build_dir, lab_files_dir=None, build_server=build_server,
                                             files_server=None, compute=None, storage=None, license_path=None,
                                             guest_image=None, heat_templates=None, security=security,
                                             low_latency=low_latency, stop=stop, skip=skip, resume=resume,
                                             boot_server=boot_server, boot=boot, iso_path=iso_path, ovs=ovs,
                                             patch_dir=patch_dir, kubernetes=kubernetes, helm_chart_path=helm_chart_path)

    # print("Setting Install vars : {} ".format(locals()))

    # Initialize values
    errors = []
    lab_to_install = lab
    drop = int(drop) if drop else None
    bs = BuildServerPath.DEFAULT_BUILD_SERVER
    host_build_dir = BuildServerPath.LATEST_HOST_BUILD_PATHS.get(DROPS.get(drop, None),
                                                                 BuildServerPath.DEFAULT_HOST_BUILD_PATH)
    license_path = BuildServerPath.DEFAULT_LICENSE_PATH
    guest_image = files_server = hosts_bulk_add = boot_if_settings = tis_config = lab_setup = files_dir = \
        heat_templates = out_put_dir = multi_region_lab = dist_cloud_lab = None

    vbox = True if lab and 'vbox' in lab.lower() else False
    if vbox:
        LOG.info("The test lab is a VBOX TiS setup")

    # Parse install conf file
    installconf = configparser.ConfigParser()
    installconf.read(installconf_path)
    # Parse lab info
    lab_info_ = installconf['LAB']
    lab_name = lab_info_['LAB_NAME']
    dc_system = True if lab_info_.get('CENTRAL_REGION') else False
    vbox = True if 'vbox' in lab_name.lower() else False

    if lab_name:
        lab_to_install = get_lab_dict(lab_name)
    if not lab_to_install:
        raise ValueError("lab name has to be provided via cmdline option --lab=<lab_name> or inside install_conf")
    if dc_system and 'central_region' not in lab_to_install:
        raise ValueError("Distributed cloud system value mismatch")

    central_reg_info_ = eval(lab_info_.get('CENTRAL_REGION')) if dc_system else None
    con0_ip = lab_info_.get('CONTROLLER0_IP') if not dc_system else \
        (central_reg_info_['controller-0 ip'] if central_reg_info_ else None)
    if con0_ip:
        lab_to_install['controller-0 ip'] = con0_ip
    con1_ip = lab_info_.get('CONTROLLER1_IP') if not dc_system else \
        (central_reg_info_['controller-1 ip'] if central_reg_info_ else None)
    if con1_ip:
        lab_to_install['controller-1 ip'] = con1_ip
    float_ip = lab_info_['FLOATING_IP']
    if float_ip:
        lab_to_install['floating ip'] = float_ip

    # Parse nodes info
    nodes_info = installconf['NODES']
    naming_map = {'CONTROLLERS': 'controller_nodes',
                  'COMPUTES': 'compute_nodes',
                  'STORAGES': 'storage_nodes'}

    for confkey, constkey in naming_map.items():
        value_in_conf = nodes_info[confkey] if confkey in nodes_info.keys() else None
        if value_in_conf:
            barcodes = value_in_conf.split(sep=' ')
            lab_to_install[constkey] = barcodes

    if (not dc_system and not lab_to_install['controller_nodes']) or \
            (dc_system and not lab_to_install['central_region']['controller_nodes']):
        errors.append("Nodes barcodes have to be provided for custom lab")

    # Parse build info
    build_info = installconf['BUILD']
    conf_build_server = build_info['BUILD_SERVER']
    conf_host_build_dir = build_info['TIS_BUILD_PATH']
    conf_iso_path = build_info["BUILD_ISO_PATH"]
    conf_patch_dir = build_info["PATCHES"]
    if conf_build_server:
        bs = conf_build_server
    if conf_host_build_dir:
        host_build_dir = conf_host_build_dir
    if conf_iso_path:
        iso_path = conf_iso_path
    if conf_patch_dir:
        patch_dir = conf_patch_dir

    # Parse files info
    conf_files = installconf['CONF_FILES']
    conf_files_server = conf_files['FILES_SERVER']
    conf_license_path = conf_files['LICENSE_PATH']
    conf_tis_config = conf_files['FILES_DIR']
    conf_boot_if_settings = conf_files['BOOT_IF_SETTINGS_PATH']
    conf_hosts_bulk_add = conf_files['HOST_BULK_ADD_PATH']
    conf_labsetup = conf_files['LAB_SETUP_CONF_PATH']
    conf_guest_image = conf_files['GUEST_IMAGE_PATH']
    conf_heat_templates = conf_files['HEAT_TEMPLATES']
    conf_ovs = eval(conf_files['OVS_CONFIG'])
    conf_kuber = eval(conf_files['KUBERNETES_CONFIG'])
    conf_helm_chart = conf_files['HELM_CHART_PATH']
    if conf_files_server:
        files_server = conf_files_server
    if conf_license_path:
        license_path = conf_license_path
    if conf_tis_config:
        tis_config = conf_tis_config
    if conf_boot_if_settings:
        boot_if_settings = conf_boot_if_settings
    if conf_hosts_bulk_add:
        hosts_bulk_add = conf_hosts_bulk_add
    if conf_labsetup:
        lab_setup = conf_labsetup
    if conf_guest_image:
        guest_image = conf_guest_image
    if conf_heat_templates:
        heat_templates = conf_heat_templates
    ovs = conf_ovs
    kubernetes = conf_kuber

    helm_chart_path = conf_helm_chart

    boot_info = installconf["BOOT"]
    conf_boot_server = boot_info["BOOT_SERVER"]
    conf_low_latency = eval(boot_info["LOW_LATENCY_INSTALL"])
    conf_boot_type = boot_info["BOOT_TYPE"]
    if conf_boot_server:
        boot_server = conf_boot_server
    low_latency = conf_low_latency
    if conf_boot_type:
        boot = conf_boot_type

    installer_steps = installconf["CONTROL"]
    conf_resume_step = installer_steps["RESUME_POINT"]
    conf_final_step = installer_steps["STOP_POINT"]
    conf_skip_steps = installer_steps["STEPS_TO_SKIP"]
    if conf_resume_step:
        resume = conf_resume_step
    if conf_final_step:
        stop = conf_final_step
    if conf_skip_steps:
        skip = eval(conf_skip_steps)

    # install conf file parsing ended. Check for errors.
    if (not dc_system and not lab_to_install.get('controller-0 ip', None)) or \
            (dc_system and not lab_to_install['central_region'].get('controller-0 ip', None)):
        errors.append('Controller-0 ip has to be provided for custom lab')
    if errors:
        raise ValueError("Install param error(s): {}".format(errors))

    # Set default values if unset
    files_server = files_server if files_server else bs
    if files_dir:
        # add lab resource type and any other lab information in the lab files
        lab_info_dict = None
        if low_latency:
            lowlat_dir = files_dir + '-lowlatency'
            try:
                lab_info_dict = get_info_from_lab_files(files_server, lowlat_dir, lab_name=lab_to_install["name"],
                                                        host_build_dir=host_build_dir)
                files_dir = lowlat_dir if lab_info_dict else files_dir
            except (FileNotFoundError, ValueError):
                pass

        if not lab_info_dict:
            lab_info_dict = get_info_from_lab_files(files_server, files_dir, lab_name=lab_to_install["name"],
                                                    host_build_dir=host_build_dir)
        lab_to_install.update(dict((system_label, system_info) for (system_label, system_info) in lab_info_dict.items()
                                   if "system" in system_label))
        multi_region_lab = lab_info_dict["multi_region"]
        dist_cloud_lab = lab_info_dict["dist_cloud"]
        lab_to_install.update(lab_info_dict)

    else:
        dist_cloud_lab = dc_system
        lab_to_install['dist_cloud'] = dist_cloud_lab

    system_mode = get_system_mode_from_lab_info(lab_to_install, multi_region_lab=multi_region_lab,
                                                dist_cloud_lab=dist_cloud_lab)
    lab_to_install['system_mode'] = system_mode if system_mode else ''
    ProjVar.set_var(sys_type=system_mode)

    if system_mode and system_mode == SysType.DISTRIBUTED_CLOUD:
        # add nodes dictionary to centeral and subclouds
        if 'central_region' not in lab_to_install:
            raise ValueError("Distributed cloud system lab dictionary does not contain central region system info")

        central_reg_lab = lab_to_install['central_region']
        if central_reg_lab:
            central_reg_lab.update(get_nodes_info(lab=central_reg_lab))
            central_reg_lab['boot_device_dict'] = create_node_boot_dict(central_reg_lab['name'])
            central_reg_lab['system_mode'] = get_system_mode_from_lab_info(central_reg_lab)
        subclouds = [k for k in lab_to_install if 'subcloud' in k]
        for subcloud in subclouds:
            lab_to_install[subcloud].update(get_nodes_info(lab=lab_to_install[subcloud]))
            subcloud_lab = lab_to_install[subcloud]
            subcloud_lab['system_mode'] = get_system_mode_from_lab_info(subcloud_lab)

    else:
        # add nodes dictionary
        lab_to_install.update(create_node_dict(lab_to_install['controller_nodes'], 'controller', vbox=vbox))
        if 'compute_nodes' in lab_to_install:
            lab_to_install.update(create_node_dict(lab_to_install['compute_nodes'], 'compute', vbox=vbox))
        if 'storage_nodes' in lab_to_install:
            lab_to_install.update(create_node_dict(lab_to_install['storage_nodes'], 'storage', vbox=vbox))

        if vbox:
            lab_to_install['boot_device_dict'] = VBOX_BOOT_INTERFACES
            # get the ip address of the local linux vm
            cmd = r""""ip addr | grep "128.224" | grep "\<inet\>" | awk '{ print $2 }' | awk -F "/" '{ print $1 }'"""
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
                    raise ValueError("The external access port to connect to {} must be provided".format(external_ip))
            username = local_host.get_user()
            if "svc-cgcsauto" in username:
                password = SvcCgcsAuto.PASSWORD
            else:
                password = local_host.get_password()

            lab_to_install['local_user'] = username
            lab_to_install['local_password'] = password
        elif 'boot_device_dict' not in lab_to_install:
                lab_to_install['boot_device_dict'] = create_node_boot_dict(lab_to_install['name'])

    # Set undefined values
    boot_server = boot_server if boot_server else 'yow-tuxlab2'
    guest_server = bs
    if not guest_image:
        guest_image = BuildServerPath.GUEST_IMAGE_PATHS.get(DROPS.get(drop),
                                                            BuildServerPath.DEFAULT_GUEST_IMAGE_PATH)
    elif ':/' in guest_image:
        guest_server, guest_image = guest_image.split(':', 1)

    iso_server = patch_server = helm_chart_server = bs
    if not iso_path:
        iso_path_in_build_dir = BuildServerPath.ISO_PATH_CENGN if '/import/' in host_build_dir \
            else BuildServerPath.ISO_PATH
        iso_path = os.path.join(host_build_dir, iso_path_in_build_dir)
    if ':/' in iso_path:
        iso_server, iso_path = iso_path.split(':', 1)
    if patch_dir and ':/' in patch_dir:
        patch_server, patch_dir = patch_dir.split(':', 1)
    if helm_chart_path and ':/' in helm_chart_path:
        helm_chart_server, helm_chart_path = helm_chart_path.split(':', 1)

    InstallVars.set_install_vars(lab=lab_to_install,
                                 resume=resume,
                                 skips=skip,
                                 wipedisk=wipedisk,
                                 build_server=bs,
                                 boot_server=boot_server,
                                 host_build_dir=host_build_dir,
                                 guest_image=guest_image,
                                 guest_server=guest_server,
                                 files_server=files_server,
                                 hosts_bulk_add=hosts_bulk_add,
                                 boot_if_settings=boot_if_settings,
                                 tis_config=tis_config,
                                 lab_setup=lab_setup,
                                 heat_templates=heat_templates,
                                 license_path=license_path,
                                 controller0_ceph_mon_device=controller0_ceph_mon_device,
                                 controller1_ceph_mon_device=controller1_ceph_mon_device,
                                 ceph_mon_gib=ceph_mon_gib,
                                 security=security,
                                 boot_type=boot.strip().lower(),
                                 low_latency=low_latency,
                                 iso_path=iso_path,
                                 iso_server=iso_server,
                                 stop=stop,
                                 patch_dir=patch_dir,
                                 patch_server=patch_server,
                                 multi_region=multi_region_lab,
                                 dist_cloud=dist_cloud_lab,
                                 dc_float_ip=dc_float_ip,
                                 install_subcloud=install_subcloud,
                                 ovs=ovs,
                                 kubernetes=kubernetes,
                                 deploy_openstack=not no_openstack,
                                 deploy_openstack_from_controller_1=deploy_openstack_from_controller_1,
                                 ipv6_config=ipv6_config,
                                 helm_chart_path=helm_chart_path,
                                 helm_chart_server=helm_chart_server,
                                 no_manage=no_manage,
                                 extract_deploy_config=extract_deploy_config
                                 )


def write_installconf(lab, controller, lab_files_dir, build_server, files_server, tis_build_dir,
                      compute, storage, patch_dir, license_path, guest_image, heat_templates, boot, iso_path,
                      low_latency, security, stop, ovs,  boot_server, resume, skip, kubernetes, helm_chart_path):

    """
    Writes a file in ini format of the fresh_install variables
    Args:
        lab: Str name of the lab to fresh_install
        controller: Str comma separated list of controller node barcodes
        lab_files_dir: Str path to the directory containing the lab files
        build_server: Str name of a valid build server. Default is yow-cgts4-lx
        files_server
        tis_build_dir: Str path to the desired build directory. Default is the latest
        compute: Str comma separated list of compute node barcodes
        storage: Str comma separated list of storage node barcodes
        license_path: Str path to the license file
        guest_image: Str path to the guest image
        heat_templates: Str path to the python heat templates
        patch_dir
        boot
        iso_path
        low_latency
        security
        stop
        ovs
        boot_server
        resume
        skip

    Returns: the path of the written file

    """
    if lab:
        lab_dict = get_lab_dict(lab)
    else:
        lab_dict = ProjVar.get_var("LAB")
    if not lab_dict:
        lab_dict = get_lab_from_install_args(lab, controller, compute, storage, lab_files_dir, build_server)

    LOG.info("Lab info: {}\n\n".format(lab_dict))
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
        labconf_key = labconf_key.replace("-", "")
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
    if not ovs and 'starlingx' in tis_build_dir.lower():
        ovs = True

    build_dict = {"BUILD_SERVER": build_server,
                  "TIS_BUILD_PATH": tis_build_dir,
                  "BUILD_ISO_PATH": iso_path if iso_path else '',
                  "PATCHES": patch_dir if patch_dir else ''}

    files_dict = {"FILES_SERVER": files_server, "FILES_DIR": lab_files_dir if lab_files_dir else '',
                  "LICENSE_PATH": license_path if license_path else '',
                  "GUEST_IMAGE_PATH": guest_image if guest_image else '',
                  "HEAT_TEMPLATES": heat_templates if heat_templates else '',
                  "LAB_SETUP_CONF_PATH": lab_files_dir,
                  "BOOT_IF_SETTINGS_PATH": '',
                  "HOST_BULK_ADD_PATH": '',
                  "OVS_CONFIG": str(ovs),
                  "KUBERNETES_CONFIG": str(kubernetes),
                  "HELM_CHART_PATH": helm_chart_path if helm_chart_path else ''}

    boot_dict = {"BOOT_TYPE": boot, "BOOT_SERVER": boot_server if boot_server else '', "SECURITY_PROFILE": security,
                 "LOW_LATENCY_INSTALL": low_latency}
    control_dict = {"RESUME_POINT": resume if resume else '',
                    "STEPS_TO_SKIP": skip if skip else '', "STOP_POINT": stop if (stop or stop == 0) else ''}
    config["LAB"] = labconf_lab_dict
    config["NODES"] = node_dict
    config["BUILD"] = build_dict
    config["CONF_FILES"] = files_dict
    config["BOOT"] = boot_dict
    config["CONTROL"] = control_dict

    for k in config:
       config[k] = {kv: vv if vv else '' for kv, vv in config[k].items()}

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
    multi_region_identifer = r"\[REGION2_PXEBOOT_NETWORK\]"
    dist_cloud_identifer = r"DISTRIBUTED_CLOUD_ROLE"
    if conf_dir:
        lab_files_path = conf_dir
    elif lab_name is not None and host_build_dir is not None:
        version = install_helper.extract_software_version_from_string_path(host_build_dir)
        version = version if version in BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS else 'default'
        lab_files_path = "{}/{}/yow/{}".format(host_build_dir, BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS[version],
                                               install_helper.get_git_name(lab_name))
    else:
        raise ValueError("Could not access lab files")

    with host_helper.ssh_to_build_server(bld_srv=conf_server) as ssh_conn:
        if not ssh_conn.exec_cmd('test -d {}'.format(lab_files_path))[0] == 0:
            raise FileNotFoundError('{} does not exist on {}'.format(lab_files_path, conf_server))

        # check lab configuration for special cases (i.e. distributed cloud or multi region)
        multi_region = ssh_conn.exec_cmd("grep '{}' {}/TiS_config.ini_centos"
                                         .format(multi_region_identifer, lab_files_path))[0] == 0
        dist_cloud = ssh_conn.exec_cmd("grep '{}' {}/TiS_config.ini_centos*"
                                       .format(dist_cloud_identifer, lab_files_path))[0] == 0

    lab_info_dict["multi_region"] = multi_region
    lab_info_dict["dist_cloud"] = dist_cloud

    # get boot_device_dict
    configname = os.path.basename(os.path.normpath(conf_dir))
    settings_filepath = conf_dir + "/settings.ini"
    if ssh_conn.exec_cmd('test -f {}/settings.ini'.format(conf_dir))[0] == 0:
        lab_info_dict["boot_device_dict"] = create_node_boot_dict(
            configname=configname, settings_filepath=settings_filepath, settings_server_conn=ssh_conn)
    else:
        lab_info_dict["boot_device_dict"] = create_node_boot_dict(configname=configname)

    # collect SYSTEM info
    rc, output = ssh_conn.exec_cmd('grep -r --color=none {} {}'.format(info_prefix, lab_files_path), rm_date=False)
    assert rc == 0, 'Lab config path not found in {}:{}'.format(conf_server, lab_files_path)
    lab_info_ = output.replace(' ', '')
    lab_info_list = lab_info_.splitlines()
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

#
# def list_migration_history(con_ssh):
#     nova_helper.get_migration_list_table(con_ssh=con_ssh)


def get_version_and_patch_info():
    version = ProjVar.get_var('SW_VERSION')[0]
    info = 'Software Version: {}\n'.format(version)

    patches = ProjVar.get_var('PATCH')
    if patches:
        info += 'Patches:\n{}\n'.format('\n'.join(patches))

    # LOG.info("SW Version and Patch info: {}".format(info))
    return info


def get_system_mode_from_lab_info(lab, multi_region_lab=False, dist_cloud_lab=False):
    """

    Args:
        lab:
        multi_region_lab:
        dist_cloud_lab:

    Returns:

    """

    if multi_region_lab:
        return SysType.MULTI_REGION
    elif dist_cloud_lab:
        return SysType.DISTRIBUTED_CLOUD

    elif 'system_mode' not in lab:
        if 'storage_nodes' in lab:
            return SysType.STORAGE
        elif 'compute_nodes' in lab:
            return SysType.REGULAR

        elif len(lab['controller_nodes']) > 1:
            return SysType.AIO_DX
        else:
            return SysType.AIO_SX

    elif 'system_mode' in lab:
        if "simplex" in lab['system_mode']:
            return SysType.AIO_SX
        else:
            return SysType.AIO_DX
    else:
        LOG.warning("Can not determine the lab to install system type based on provided information. Lab info: {}"
                    .format(lab))
        return None


def set_session(con_ssh):
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
            bs_ = ProjVar.get_var('BUILD_SERVER')
            session_id = upload_results.upload_test_session(lab_name=ProjVar.get_var('LAB')['name'],
                                                            build_id=build_id,
                                                            build_server=bs_,
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
    """
    set global variable region.
    This needs to be called after CliAuth.set_vars, since the custom region value needs to override what is
    specified in openrc file.

    local region and auth url is saved in CliAuth, while the remote region and auth url is saved in Tenant.

    Args:
        region: region to set

    """
    local_region = CliAuth.get_var('OS_REGION_NAME')
    if not region:
        if ProjVar.get_var('IS_DC'):
            region = 'SystemController'
        else:
            region = local_region
    Tenant.set_region(region=region)
    ProjVar.set_var(REGION=region)
    if region in MULTI_REGION_MAP:
        # Multi-region lab
        for tenant in ('tenant1', 'tenant2'):
            region_tenant = '{}{}'.format(tenant, MULTI_REGION_MAP[region])
            Tenant.update(tenant, username=region_tenant, tenant=region_tenant)
            if region != local_region:
                keystone_helper.add_or_remove_role(add_=True, role='admin', user=region_tenant, project=region_tenant)
    elif re.search(SUBCLOUD_PATTERN, region):
        # Distributed cloud, lab specified is a subcloud.
        urls = keystone_helper.get_endpoints(region=region, rtn_val='URL', interface='internal',
                                             service_name='keystone')
        if not urls:
            raise ValueError("No internal endpoint found for region {}. Invalid value for --region with specified lab."
                             "sub-cloud tests can be run on controller, but not the other way round".format(region))
        Tenant.set_url(urls[0])


def set_dc_vars():
    if not ProjVar.get_var('IS_DC') or ControllerClient.get_active_controller(name='RegionOne', fail_ok=True):
        return

    central_con_ssh = ControllerClient.get_active_controller()
    ControllerClient.set_active_controller(central_con_ssh, name='RegionOne')
    primary_subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
    sub_clouds = dc_helper.get_subclouds(avail='online', con_ssh=central_con_ssh)
    LOG.info("Online subclouds: {}".format(sub_clouds))

    lab = ProjVar.get_var('LAB')

    for subcloud in sub_clouds:
        subcloud_lab = lab.get(subcloud, None)
        if not subcloud_lab:
            raise ValueError('Please add {} to {} in consts/lab.py'.format(subcloud, lab['short_name']))

        LOG.info("Create ssh connection to {}, and add to ControllerClient".format(subcloud))
        subcloud_ssh = SSHClient(subcloud_lab['floating ip'],
                                 HostLinuxCreds.get_user(),
                                 HostLinuxCreds.get_password(),
                                 CONTROLLER_PROMPT)

        try:
            subcloud_ssh.connect(retry=True, retry_timeout=30)
            ControllerClient.set_active_controller(subcloud_ssh, name=subcloud)
        except exceptions.SSHRetryTimeout as e:
            if subcloud == primary_subcloud:
                raise
            LOG.warning('Cannot connect to {} via its floating ip. {}'.format(subcloud, e.__str__()))
            continue

        LOG.info("Add {} to DC_MAP".format(subcloud))
        subcloud_auth = get_auth_via_openrc(subcloud_ssh)
        auth_url = subcloud_auth['OS_AUTH_URL']
        region = subcloud_auth['OS_REGION_NAME']
        Tenant.add_dc_region(region_info={subcloud: {'auth_url': auth_url, 'region': region}})

        if subcloud == primary_subcloud:
            LOG.info("Set default cli auth to use {}".format(subcloud))
            Tenant.set_region(region=region)
            Tenant.set_url(url=auth_url)

    LOG.info("Set default controller ssh to {} in ControllerClient".format(primary_subcloud))
    ControllerClient.set_default_ssh(primary_subcloud)


def set_sys_type(con_ssh):
    set_dc_vars()

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


# TODO: handle ip's as hostnames
def initialize_server(server_hostname, prompt=None):
    if prompt is None:
        prompt = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', '.*')

    server_conn = SSHClient(server_hostname, user=SvcCgcsAuto.USER,
                            password=SvcCgcsAuto.PASSWORD, initial_prompt=prompt)
    server_conn.connect()
    server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    server_dict = {"name": server_hostname, "prompt": prompt, "ssh_conn": server_conn}

    return build_server.Server(**server_dict)
