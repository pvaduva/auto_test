import re
import subprocess
import os
import sys

from utils.ssh import SSHClient, CONTROLLER_PROMPT
from consts.lab import Labs
from consts.proj_vars import ProjVar
from consts.auth import Tenant, HostLinuxCreds
from keywords import system_helper


def get_lab_floating_ip(labname=None):
    lab_dict = __get_lab_dict(labname)
    return lab_dict['floating ip']


def _get_patches(con_ssh, rtn_str=True):
    code, output = con_ssh.exec_sudo_cmd('sw-patch query', fail_ok=True)

    patches = []
    if code == 0:
        output_lines = output.splitlines()
        patches = list(output_lines)
        for line in output_lines:
            patches.remove(line)
            if line.startswith('========='):
                break
        patches = [patch.strip().split(sep=' ', maxsplit=1)[0] for patch in patches if patch.strip()]
    if rtn_str:
        patches = ' '.join(patches)

    return patches


def _get_build_info(con_ssh, *args):
    """

    Args:
        con_ssh (SSHClient):
        **args: 'SW_VERSION', 'BUILD_TARGET', 'BUILD_ID', 'BUILD_HOST', etc...

    Returns (list):

    """
    output = con_ssh.exec_cmd('cat /etc/build.info')[1]
    vals = []
    for arg in args:
        val = re.findall('''{}=\"(.*)\"'''.format(arg.upper()), output)
        val = val[0] if val else ''
        vals.append(val)

    return vals


def get_build_id(labname=None, log_dir=None, con_ssh=None):
    """

    Args:
        labname:
        log_dir:
        con_ssh (SSHClient):

    Returns:

    """
    close = False
    if con_ssh is None:
        close = True
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
                build_id = build_date[0].replace(' ', '_').replace(':', '-')
            else:
                build_id = '_'

    if close:
        con_ssh.close()

    return build_id


def __get_lab_ssh(labname, log_dir=None):
    """

    Args:
        labname:
        log_dir:

    Returns (SSHClient):

    """
    lab = __get_lab_dict(labname)

    # Doesn't have to save logs
    # if log_dir is None:
    #     log_dir = temp_dir = "/tmp/CGCSAUTO/"
    if log_dir is not None:
        ProjVar.set_var(log_dir=log_dir)

    ProjVar.set_var(lab=lab)
    ProjVar.set_var(source_admin=Tenant.ADMIN)
    con_ssh = SSHClient(lab['floating ip'], HostLinuxCreds.get_user(), HostLinuxCreds.get_password(), CONTROLLER_PROMPT)
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


def _get_sys_type(labname=None, log_dir=None, con_ssh=None):
    """

    Args:
        labname (str): such as wcp_76-77
        log_dir (str): where to save logs
        con_ssh (SSHClient):

    Returns (str): such as 2+2, 2+4+2, CPE, etc

    """

    close = False
    if con_ssh is None:
        close = True
        con_ssh = __get_lab_ssh(labname=labname, log_dir=log_dir)

    controllers, computes, storages = system_helper.get_hosts_by_personality(con_ssh=con_ssh, source_admin=True)

    sys_type = "{}+{}+{}".format(len(controllers), len(computes), len(storages)).replace('+0', '')

    if '+' not in sys_type:
        sys_type = 'AIO-DX' if sys_type == '2' else 'AIO-SX'

    if close:
        con_ssh.close()

    return sys_type


def __get_lab_dict(labname):
    """

    Args:
        labname (str):

    Returns (dict):

    """
    if labname is None:
        return ProjVar.get_var(var_name='LAB')

    labname = labname.strip().lower().replace('-', '_')
    labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]
    labs = [lab_ for lab_ in labs if isinstance(lab_, dict)]

    for lab in labs:
        if labname in lab['name'].replace('-', '_').lower().strip() \
                or labname == lab['short_name'].replace('-', '_').lower().strip() \
                or labname == lab['floating ip']:
            return lab
    else:
        lab_valid_short_names = [lab['short_name'] for lab in labs]
        # lab_valid_names = [lab['name'] for lab in labs]
        raise ValueError("{} is not found! Available labs: {}".format(labname, lab_valid_short_names))


def get_latest_logdir(labname, log_root_dir='~'):
    """
    Get the log dir
    Args:
        labname (str):
        log_root_dir (str):

    Returns:

    """
    log_root_dir = os.path.expanduser(log_root_dir)
    log_lab_dir = '{}/AUTOMATION_LOGS/{}/'.format(log_root_dir, labname.lower().replace('-', '_'))

    cmd = 'ls -t {} | head -n1'.format(log_lab_dir)

    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, close_fds=True)

    rtn_code = p.wait()
    (stderr, stdout) = (p.stderr, p.stdout)
    if not rtn_code == 0:
        print(str(stderr.read(), encoding='utf-8'))
        sys.exit(rtn_code)

    dir_timestamp = str(stdout.read(), encoding='utf-8')
    full_path = log_lab_dir + dir_timestamp

    return full_path


def get_lab_info(labname=None, log_dir=None):
    """
    Get build id (e.g., 2016-11-14_22-01-28), system type (e.g., 2+4+2)
    Args:
        labname (str): such as WCP_76-77, PV0, IP_1-4
        log_dir (str): log directory. logs will not be saved if unset

    Returns (tuple):

    """
    con_ssh = __get_lab_ssh(labname=labname, log_dir=log_dir)

    # get build id
    build_id = get_build_id(labname=labname, log_dir=log_dir, con_ssh=con_ssh)
    sys_type = _get_sys_type(labname=labname, log_dir=log_dir, con_ssh=con_ssh)

    con_ssh.close()
    return build_id, sys_type

