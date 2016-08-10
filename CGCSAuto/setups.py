import re
import time

from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient, PASSWORD_PROMPT

from consts.auth import Tenant
from consts.cgcs import Prompt
from consts.lab import Labs, add_lab_entry, NatBoxes
from consts.proj_vars import ProjVar

from keywords import vm_helper, host_helper
from keywords.common import scp_to_local


def setup_tis_ssh(lab):
    con_ssh = ControllerClient.get_active_controller(fail_ok=True)

    if con_ssh is None:
        con_ssh = SSHClient(lab['floating ip'], 'wrsroot', 'Li69nux*', CONTROLLER_PROMPT)
        con_ssh.connect()
        ControllerClient.set_active_controller(con_ssh)
    if 'auth_url' in lab:
        Tenant._set_url(lab['auth_url'])

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


def setup_natbox_ssh(keyfile_path, natbox):
    natbox_ip = natbox['ip']
    NATBoxClient.set_natbox_client(natbox_ip)
    __copy_keyfile_to_natbox(natbox, keyfile_path)
    return NATBoxClient.get_natbox_client()


def __copy_keyfile_to_natbox(natbox, keyfile_path):
    # con_ssh = ControllerClient.get_active_controller()
    with host_helper.ssh_to_host('controller-0') as con_0_ssh:
        # con_0_ssh = ssh_to_controller0(ssh_client=con_ssh)
        if not con_0_ssh.file_exists('/home/wrsroot/.ssh/id_rsa'):
            passphrase_prompt_1 = '.*Enter passphrase.*'
            passphrase_prompt_2 = '.*Enter same passphrase again.*'

            con_0_ssh.send('ssh-keygen')
            index = con_0_ssh.expect([passphrase_prompt_1, '.*Enter file in which to save the key.*'])
            if index == 1:
                con_0_ssh.send()
                con_0_ssh.expect(passphrase_prompt_1)
            con_0_ssh.send()    # Enter empty passphrase
            con_0_ssh.expect(passphrase_prompt_2)
            con_0_ssh.send()    # Repeat passphrase
            con_0_ssh.expect(Prompt.CONTROLLER_0)

        keyfile_name = keyfile_path.split(sep='/')[-1]
        cmd_1 = 'cp /home/wrsroot/.ssh/id_rsa ' + keyfile_name
        cmd_2 = 'chmod 600 ' + keyfile_name
        cmd_3 = 'scp {} {}@{}:{}'.format(keyfile_name, natbox['user'], natbox['ip'], keyfile_path)

        rtn_1 = con_0_ssh.exec_cmd(cmd_1)[0]
        if not rtn_1 == 0:
            raise exceptions.CommonError("Failed to create new keyfile on controller")
        rtn_2 = con_0_ssh.exec_cmd(cmd_2)[0]
        if not rtn_2 == 0:
            raise exceptions.CommonError("Failed to update permission for created keyfile")

        con_0_ssh.send(cmd_3)
        rtn_3_index = con_0_ssh.expect(['.*\(yes/no\)\?.*', Prompt.PASSWORD_PROMPT])
        if rtn_3_index == 0:
            con_0_ssh.send('yes')
            con_0_ssh.expect(Prompt.PASSWORD_PROMPT)
        con_0_ssh.send(natbox['password'])
        con_0_ssh.expect()
        if not con_0_ssh.get_exit_code() == 0:
            raise exceptions.CommonError("Failed to copy keyfile to NatBox")


def boot_vms(is_boot):
    # boot some vms for the whole test session if boot_vms flag is set to True
    if is_boot:
        con_ssh = ControllerClient.get_active_controller()
        if con_ssh.file_exists('~/instances_group0/launch_tenant1-avp1.sh'):
            vm_helper.launch_vms_via_script(vm_type='avp', num_vms=1, tenant_name='tenant1')
            vm_helper.launch_vms_via_script(vm_type='virtio', num_vms=1, tenant_name='tenant2')
        else:
            vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT_1)
            vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT_2)


def get_lab_dict(labname):
    labname = labname.strip().lower().replace('-', '_')
    labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]

    for lab in labs:
        if labname in lab['name'].replace('-', '_').lower().strip() \
                or labname == lab['short_name'].replace('-', '_').lower().strip() \
                or labname == lab['floating ip']:
            return lab
    else:
        if labname.startswith('128.224'):
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
        scp_to_local(source_path=logpath, source_ip=lab_ip, dest_path=dest_path)
        LOG.info("{} is successfully copied to local directory: {}".format(logpath, dest_path))
    except Exception as e:
        LOG.warning("Failed to copy log file to localhost.")
        LOG.error(e, exc_info=True)


def get_tis_timestamp(con_ssh):
    return con_ssh.exec_cmd('date +"%T"')[1]


def get_build_id(con_ssh):
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

    return build_id


def copy_files_to_con1():

    LOG.info("rsync test files from controller-0 to controller-1 if not already done")

    try:
        with host_helper.ssh_to_host("controller-1") as con_1_ssh:
            if con_1_ssh.file_exists('/home/wrsroot/heat'):
                LOG.info("Test files already exist on controller-1. Skip rsync.")
                return

    except Exception as e:
        LOG.error("Cannot ssh to controller-1. Skip rsync. \nException caught: {}".format(e.__str__()))
        return

    # cmd = 'scp -q -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null controller-0:/home/wrsroot/* ' \
    #       'controller-1:/home/wrsroot/'
    cmd = "rsync -avr -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' " \
          "/home/wrsroot/* controller-1:/home/wrsroot/"

    timeout = 120

    with host_helper.ssh_to_host("controller-0") as con_0_ssh:
        con_0_ssh.send(cmd)

        end_time = time.time() + timeout

        while time.time() < end_time:
            index = con_0_ssh.expect([con_0_ssh.prompt, PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=timeout)
            if index == 2:
                con_0_ssh.send('yes')

            if index == 1:
                con_0_ssh.send("Li69nux*")

            if index == 0:
                output = int(con_0_ssh.exec_cmd('echo $?')[1])
                if output in [0, 23]:
                    LOG.info("Test files are successfully copied to controller-1 from controller-0")
                    break
                else:
                    raise exceptions.SSHExecCommandFailed("Failed to rsync files from controller-0 to controller-1")

        else:
            raise exceptions.TimeoutException("Timed out rsync files to controller-1")