from consts.proj_vars import InstallVars
from consts.vlm import VlmAction
from consts.timeout import HostTimeout

from keywords import host_helper
from utils import exceptions, local_host
from utils.ssh import ControllerClient
from utils.tis_log import LOG


def get_lab_dict():
    return InstallVars.get_install_var('LAB')


def get_barcodes_dict(lab=None):
    if lab is None:
        lab = get_lab_dict()
    
    if not isinstance(lab, dict):
        raise ValueError("lab dict or None should be provided")
    
    node_types = ['controller', 'compute', 'storage']
    barcodes_dict = {}
    for node_type in node_types:
        nodes_ = "{}_nodes".format(node_type)
        if nodes_ in lab:
            i = 0
            for barcode in lab[nodes_]:
                hostname = "{}-{}".format(node_type, i)
                barcodes_dict[hostname] = barcode
                i += 1
    
    LOG.info("Barcodes dict for {}: {}".format(lab['short_name'], barcodes_dict))
    
    return barcodes_dict
        

def get_barcodes_from_hostnames(hostnames):
    """
    Convert hostname(s) to barcodes
    Args:
        hostnames (str|list): hostname(s) 

    Returns (list): list of barcodes
    """
    if isinstance(hostnames, str):
        hostnames = [hostnames]
        
    barcodes_dict = get_barcodes_dict()
    barcodes = []
    
    for host in hostnames:
        barcodes.append(barcodes_dict[host])
    
    return barcodes
    

def unreserve_hosts(hosts):
    """
    Unreserve given hosts from vlm
    Args:
        hosts (str|list): hostname(s)

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_UNRESERVE, reserve=False)


def reserve_hosts(hosts, val='hostname'):
    """
    Reserve given host(s) or barcode(s) from vlm

    Args:
        hosts (str|list):
        val (str): 'hostname' or 'barcode'

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    barcodes = get_barcodes_from_hostnames(hosts) if val == 'hostname' else hosts

    LOG.info("Reserving hosts {}: {}".format(hosts, barcodes))
    for barcode in barcodes:
        rc, output = local_host.reserve_vlm_console(barcode)
        if rc != 0:
            err_msg = "Failed to reserve barcode {} in vlm: {}".format(barcode, output)
            raise exceptions.VLMError(err_msg)


def power_off_hosts(hosts, reserve=True):
    """
    Power off given hosts
    Args:
        hosts (str|list): hostname(s)
        reserve (bool): whether to reserve first

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_TURNOFF, reserve=reserve)


def power_on_hosts(hosts, reserve=True, post_check=True, reconnect=True, reconnect_timeout=HostTimeout.REBOOT,
                   con_ssh=None):
    """

    Args:
        hosts (str|list): hostname(s)
        reserve (bool): whether to reserve first
        post_check (bool): whether to wait for hosts to be ready after power on
        reconnect (bool): whether or reconnect to lab via ssh after power on. Useful when power on controllers
        reconnect_timeout (int): max seconds to wait before reconnect succeeds
        con_ssh (SSHClient):

    Returns:

    """

    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_TURNON, reserve=reserve)

    if post_check:
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller()

        if reconnect:
            con_ssh.connect(retry=True, retry_timeout=reconnect_timeout)
            host_helper._wait_for_openstack_cli_enable(con_ssh=con_ssh)

        host_helper.wait_for_hosts_ready(hosts, con_ssh=con_ssh)


def reboot_hosts(hosts, reserve=True, post_check=True, reconnect=True, reconnect_timeout=HostTimeout.REBOOT,
                 con_ssh=None):
    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_REBOOT, reserve=reserve)

    if post_check:
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller()

        if reconnect:
            con_ssh.connect(retry=True, retry_timeout=reconnect_timeout)
            host_helper._wait_for_openstack_cli_enable(con_ssh=con_ssh)

        host_helper.wait_for_hosts_ready(hosts, con_ssh=con_ssh)


def _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_TURNON, reserve=True):
    if isinstance(hosts, str):
        hosts = [hosts]

    barcodes = get_barcodes_from_hostnames(hosts)
    for i in range(len(hosts)):
        host = hosts[i]
        barcode = barcodes[i]

        # if reserve:
        #     LOG.info("Reserving {}-{}".format(host, barcode))
        #     rc, output = local_host.reserve_vlm_console(barcode)
        #     if rc != 0:
        #         err_msg = "Failed to reserve vlm console for {}  barcode {}: {}".format(host, barcode, output)
        #         raise exceptions.VLMError(err_msg)

        LOG.info("{} {}-{}".format(action, host, barcode))
        rc, output = local_host.vlm_exec_cmd(action, barcode, reserve=reserve)
        if rc != 0:
            err_msg = "Failed to {} node {}-{}: {}".format(action, host, barcode, output)
            raise exceptions.VLMError(err_msg)

        LOG.info("{} succeeded on {}-{}".format(action, host, barcode))