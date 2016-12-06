import re
from time import strftime

from utils.ssh import SSHClient, CONTROLLER_PROMPT
from consts.lab import Labs
from consts.proj_vars import ProjVar


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
        if labname in lab['name'].replace('-', '_').lower().strip() \
                or labname == lab['short_name'].replace('-', '_').lower().strip() \
                or labname == lab['floating ip']:
            return lab
    else:
        lab_valid_short_names = [lab['short_name'] for lab in labs]
        # lab_valid_names = [lab['name'] for lab in labs]
        raise ValueError("{} is not found! Available labs: {}".format(labname, lab_valid_short_names))

