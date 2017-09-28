import re
import time
import os.path
import configparser

import setup_consts
from utils import exceptions, cli, lab_info
from utils.tis_log import LOG
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient, PASSWORD_PROMPT
from utils.node import create_node_boot_dict, create_node_dict
from consts.auth import Tenant, CliAuth, HostLinuxCreds
from consts.cgcs import Prompt
from consts.filepaths import PrivKeyPath, WRSROOT_HOME
from consts.lab import Labs, add_lab_entry, NatBoxes
from consts.proj_vars import ProjVar, InstallVars

from keywords import vm_helper, host_helper, nova_helper, system_helper, keystone_helper
from keywords.common import scp_to_local


def less_than_two_controllers():
    return len(system_helper.get_controllers()) < 2


def setup_tis_ssh(lab):
    con_ssh = ControllerClient.get_active_controller(fail_ok=True)

    if con_ssh is None:
        con_ssh = SSHClient(lab['floating ip'], HostLinuxCreds.get_user(), HostLinuxCreds.get_password(),
                            CONTROLLER_PROMPT)
        con_ssh.connect(retry=True, retry_timeout=30)
        ControllerClient.set_active_controller(con_ssh)
    # if 'auth_url' in lab:
    #     Tenant._set_url(lab['auth_url'])
    return con_ssh


def set_env_vars(con_ssh):
    # TODO: delete this after source to bash issue is fixed on centos
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
    __copy_keyfile_to_natbox(natbox, keyfile_path, con_ssh=con_ssh)
    return NATBoxClient.get_natbox_client()


def __copy_keyfile_to_natbox(natbox, keyfile_path, con_ssh):
    """
    copy private keyfile from controller-0:/opt/platform to natbox: priv_keys/
    Args:
        natbox (dict): NATBox info such as ip
        keyfile_path (str): Natbox path to scp keyfile to
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
                con_ssh.send()    # Enter empty passphrase
                con_ssh.expect(passphrase_prompt_2)
                con_ssh.send()    # Repeat passphrase
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

    cmd_3 = 'scp {} {}@{}:{}'.format(keyfile_name, natbox['user'], natbox['ip'], keyfile_path)
    con_ssh.send(cmd_3)
    rtn_3_index = con_ssh.expect(['.*\(yes/no\)\?.*', Prompt.PASSWORD_PROMPT])
    if rtn_3_index == 0:
        con_ssh.send('yes')
        con_ssh.expect(Prompt.PASSWORD_PROMPT)
    con_ssh.send(natbox['password'])
    con_ssh.expect(timeout=30)
    if not con_ssh.get_exit_code() == 0:
        raise exceptions.CommonError("Failed to copy keyfile to NatBox")

    LOG.info("key file is successfully copied from controller to NATBox")


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
        if labname in lab['name'].replace('-', '_').lower().strip() \
                or labname == lab['short_name'].replace('-', '_').lower().strip() \
                or labname == lab['floating ip']:
            return lab
    else:
        if labname.startswith('128.224') or labname.startswith('10.'):
            return add_lab_entry(labname)

        lab_valid_short_names = [lab['short_name'] for lab in labs]
        # lab_valid_names = [lab['name'] for lab in labs]
        raise ValueError("{} is not found! Available labs: {}".format(labname, lab_valid_short_names))


def get_natbox_dict(natboxname):
    natboxname = natboxname.lower().strip()
    natboxes = [getattr(NatBoxes, item) for item in dir(NatBoxes) if not item.startswith('_')]

    for natbox in natboxes:
        if natboxname.replace('-', '_') in natbox['name'].replace('-', '_') or natboxname == natbox['ip']:
            return natbox
    else:
        raise ValueError("{} is not a valid input.".format(natboxname))


def get_tenant_dict(tenantname):
    tenantname = tenantname.lower().strip().replace('_', '').replace('-', '')
    tenants = [getattr(Tenant, item) for item in dir(Tenant) if not item.startswith('_') and item.isupper()]

    for tenant in tenants:
        if tenantname == tenant['tenant'].replace('_', '').replace('-', ''):
            return tenant
    else:
        raise ValueError("{} is not a valid input".format(tenantname))


def collect_tis_logs(con_ssh):
    LOG.info("Collecting all hosts logs...")
    con_ssh.send('collect all')

    expect_list = ['.*password for wrsroot:', 'collecting data.', con_ssh.prompt]
    index_1 = con_ssh.expect(expect_list, timeout=10)
    if index_1 == 2:
        LOG.error("Something is wrong with collect all. Check ssh console log for detail.")
        return
    elif index_1 == 0:
        con_ssh.send(con_ssh.password)
        con_ssh.expect('collecting data')

    index_2 = con_ssh.expect(['/scratch/ALL_NODES.*', con_ssh.prompt], timeout=900)
    if index_2 == 0:
        output = con_ssh.cmd_output
        con_ssh.expect()
        logpath = re.findall('.*(/scratch/ALL_NODES_.*.tar).*', output)[0]
        LOG.info("\n################### TiS server log path: {}".format(logpath))
    else:
        LOG.error("Collecting logs failed. No ALL_NODES logs found.")
        return

    lab_ip = ProjVar.get_var('LAB')['floating ip']
    dest_path = ProjVar.get_var('LOG_DIR')
    try:
        LOG.info("Copying log file from lab {} to local {}".format(lab_ip, dest_path))
        scp_to_local(source_path=logpath, source_ip=lab_ip, dest_path=dest_path, timeout=300)
        LOG.info("{} is successfully copied to local directory: {}".format(logpath, dest_path))
    except Exception as e:
        LOG.warning("Failed to copy log file to localhost.")
        LOG.error(e, exc_info=True)


def get_tis_timestamp(con_ssh):
    return con_ssh.exec_cmd('date +"%T"')[1]


def get_build_info(con_ssh):
    code, output = con_ssh.exec_cmd('cat /etc/build.info')
    if code != 0:
        build_id = ' '
        build_host = ' '
    else:
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

        build_host = re.findall('''BUILD_HOST=\"(.*)\"''', output)
        build_host = build_host[0].split(sep='.')[0] if build_host else ' '

    return build_id, build_host


def copy_files_to_con1():
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


def get_lab_from_cmdline(lab_arg, installconf_path):
    lab_dict = None
    if not lab_arg and not installconf_path:
        lab_dict = setup_consts.LAB
        if lab_dict is None:
            raise ValueError("No lab is specified via cmdline or setup_consts.py")
        LOG.warning("lab is not specified via cmdline! Using lab from setup_consts file: {}".format(
                lab_dict['short_name']))

    if installconf_path:
        installconf = configparser.ConfigParser()
        installconf.read(installconf_path)

        # Parse lab info
        lab_info = installconf['LAB']
        lab_name = lab_info['LAB_NAME']
        if not lab_name:
            raise ValueError("Either --lab=<lab_name> or --install-conf=<full path of install configuration file> "
                             "has to be provided")
        if lab_arg and lab_arg.lower() != lab_name.lower():
            LOG.warning("Conflict in --lab={} and install conf file LAB_NAME={}. LAB_NAME in conf file will be used".
                        format(lab_arg, lab_name))
        lab_arg = lab_name

    if lab_dict is None:
        lab_dict = get_lab_dict(lab_arg)
    return lab_dict


def set_install_params(lab, skip_labsetup, resume, installconf_path, controller0_ceph_mon_device,
                       controller1_ceph_mon_device, ceph_mon_gib):

    if not lab and not installconf_path:
        raise ValueError("Either --lab=<lab_name> or --install-conf=<full path of install configuration file> "
                         "has to be provided")

    errors = []
    lab_to_install = lab
    build_server = None
    host_build_dir = None
    guest_image = None
    files_server = None
    hosts_bulk_add = None
    boot_if_settings = None
    tis_config = None
    lab_setup = None
    heat_templates = None
    license_path = None
    out_put_dir = None

    if installconf_path:
        installconf = configparser.ConfigParser()
        installconf.read(installconf_path)

        # Parse lab info
        lab_info = installconf['LAB']
        lab_name = lab_info['LAB_NAME']
        if lab_name:
            lab_to_install = get_lab_dict(lab_name)

        if lab_to_install:
            con0_ip = lab_info['CONTROLLER0_IP']
            if con0_ip:
                lab_to_install['controller-0 ip'] = con0_ip

            con1_ip = lab_info['CONTROLLER0_IP']
            if con1_ip:
                lab_to_install['controller-1 ip'] = con1_ip
        else:
            raise ValueError("lab name has to be provided via cmdline option --lab=<lab_name> or inside install_conf "
                             "file")

        # Parse nodes info
        nodes_info = installconf['NODES']
        naming_map = {'CONTROLLERS': 'controller_nodes',
                      'COMPUTES': 'compute_nodes',
                      'STORAGES': 'storage_nodes'}

        for confkey, constkey in naming_map.items():
            value_in_conf = nodes_info[confkey]
            if value_in_conf:
                barcodes = value_in_conf.split(sep=' ')
                lab_to_install[constkey] = barcodes

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
        conf_license_path = conf_files['LICENSE_PATH']
        conf_tis_config = conf_files['TIS_CONFIG_PATH']
        conf_boot_if_settings = conf_files['BOOT_IF_SETTINGS_PATH']
        conf_hosts_bulk_add = conf_files['HOST_BULK_ADD_PATH']
        conf_labsetup = conf_files['LAB_SETUP_CONF_PATH']
        conf_guest_image = conf_files['GUEST_IMAGE_PATH']
        conf_heat_templates = conf_files['HEAT_TEMPLATES']

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

    else:
        lab_to_install = get_lab_dict(lab)

    if not lab_to_install.get('controller-0 ip', None):
        errors.append('Controller-0 ip has to be provided for custom lab')

    if errors:
        raise ValueError("Install param error(s): {}".format(errors))

    # compute directory for all logs based on lab, and timestamp on local machine
    out_put_dir = "/tmp/output_" + lab_to_install['name'] + '/' + time.strftime("%Y%m%d-%H%M%S")

    # add nodes dictionary
    lab_to_install.update(create_node_dict(lab_to_install['controller_nodes'], 'controller'))
    if 'compute_nodes' in lab_to_install:
        lab_to_install.update( create_node_dict(lab_to_install['compute_nodes'], 'compute'))
    if 'storage_nodes' in lab_to_install:
        lab_to_install.update(create_node_dict(lab_to_install['storage_nodes'], 'storage'))

    lab_to_install['boot_device_dict'] = create_node_boot_dict(lab_to_install['name'])

    InstallVars.set_install_vars(lab=lab_to_install, resume=resume, skip_labsetup=skip_labsetup,
                                 build_server=build_server,
                                 host_build_dir=host_build_dir,
                                 guest_image=guest_image,
                                 files_server=files_server,
                                 hosts_bulk_add=hosts_bulk_add,
                                 boot_if_settings=boot_if_settings,
                                 tis_config=tis_config,
                                 lab_setup=lab_setup,
                                 heat_templates=heat_templates,
                                 license_path=license_path,
                                 out_put_dir=out_put_dir,
                                 controller0_ceph_mon_device=controller0_ceph_mon_device,
                                 controller1_ceph_mon_device=controller1_ceph_mon_device,
                                 ceph_mon_gib=ceph_mon_gib
                                 )


def is_https(con_ssh):
    return keystone_helper.is_https_lab(con_ssh=con_ssh, source_admin=True)


def scp_vswitch_log(con_ssh, hosts, log_path=None):
    source_file = '/scratch/var/extra/vswitch.info'
    for host in hosts:
        LOG.info("scp vswitch log from {} to controller-0".format(host))
        dest_file = "{}_vswitch.info".format(host)
        dest_file = os.path.join(WRSROOT_HOME, dest_file)
        con_ssh.scp_files(source_file, dest_file, source_server=host, dest_server='controller-0',
                          source_user=HostLinuxCreds.get_user(), source_password=HostLinuxCreds.get_password(), dest_password=HostLinuxCreds.get_password(),
                          dest_user='', timeout=30, sudo=True, sudo_password=None, fail_ok=True)

    LOG.info("SCP vswitch log from lab to automation log dir")
    if log_path is None:
        log_path = os.path.join(WRSROOT_HOME, '*_vswitch.info')
    source_ip = ProjVar.get_var('LAB')['controller-0 ip']
    dest_dir = ProjVar.get_var('TEMP_DIR')
    scp_to_local(dest_path=dest_dir, source_user=HostLinuxCreds.get_user(), source_password=HostLinuxCreds.get_password(), source_path=log_path,
                 source_ip=source_ip, timeout=60)


def list_migration_history(con_ssh):
    nova_helper.run_migration_list(con_ssh=con_ssh)


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
    if tag:
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
