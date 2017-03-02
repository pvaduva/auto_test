import multiprocessing as mp
from multiprocessing import Process, Queue

from consts.proj_vars import InstallVars
from consts.vlm import VlmAction
from consts.timeout import HostTimeout

from keywords import host_helper, system_helper
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


def get_hostnames_from_consts(lab=None):
    return list(get_barcodes_dict(lab=lab).keys())


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
                   hosts_to_check=None, con_ssh=None):
    """

    Args:
        hosts (str|list): hostname(s)
        reserve (bool): whether to reserve first
        post_check (bool): whether to wait for hosts to be ready after power on
        reconnect (bool): whether or reconnect to lab via ssh after power on. Useful when power on controllers
        reconnect_timeout (int): max seconds to wait before reconnect succeeds
        hosts_to_check (list|str|None): host(s) to perform post check after power-on. when None, hosts_to_check=hosts
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
            host_helper._wait_for_openstack_cli_enable(con_ssh=con_ssh, timeout=120, reconnect=True)

        if not hosts_to_check:
            hosts_to_check = hosts
        elif isinstance(hosts_to_check, str):
            hosts_to_check = [hosts_to_check]

        host_helper.wait_for_hosts_ready(hosts_to_check, con_ssh=con_ssh)


def reboot_hosts(hosts, reserve=True, post_check=True, reconnect=True, reconnect_timeout=HostTimeout.REBOOT,
                 hosts_to_check=None, con_ssh=None):
    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_REBOOT, reserve=reserve)

    if post_check:
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller()

        if reconnect:
            con_ssh.connect(retry=True, retry_timeout=reconnect_timeout)
            host_helper._wait_for_openstack_cli_enable(con_ssh=con_ssh)

        if not hosts_to_check:
            hosts_to_check = hosts
        elif isinstance(hosts_to_check, str):
            hosts_to_check = [hosts_to_check]

        host_helper.wait_for_hosts_ready(hosts_to_check, con_ssh=con_ssh)


def _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_TURNON, reserve=True):
    if isinstance(hosts, str):
        hosts = [hosts]

    barcodes = get_barcodes_from_hostnames(hosts)
    for i in range(len(hosts)):
        host = hosts[i]
        barcode = barcodes[i]

        LOG.info("{} {} {}".format(action, host, barcode))
        rc, output = local_host.vlm_exec_cmd(action, barcode, reserve=reserve)
        if rc != 0:
            err_msg = "Failed to {} node {} {}: {}".format(action, host, barcode, output)
            raise exceptions.VLMError(err_msg)

        LOG.info("{} succeeded on {} {}".format(action, host, barcode))


def power_off_hosts_simultaneously(hosts=None):
    """
    Power off hosts in multi-processes to simulate power outage. This can be used for DOR.
    Args:
        hosts (list|None): when None, all hosts on system will be powered off

    Returns:

    """
    def _power_off(barcode_, power_off_event_, timeout_, output_queue):

        if power_off_event_.wait(timeout=timeout_):
            rc, output = local_host.vlm_exec_cmd(VlmAction.VLM_TURNOFF, barcode_, reserve=False)
            rtn = rc, output

        else:
            err_msg = "Timed out waiting for power_off_event to be set"
            LOG.error(err_msg)
            rtn = 2, err_msg

        if 0 == rtn[0]:
            LOG.info("{} powered off successfully".format(barcode_))
        else:
            LOG.error("Failed to power off {}.".format(barcode_))
        output_queue.put({barcode_: rtn})

    if not hosts:
        hosts = system_helper.get_hostnames()

    barcodes = get_barcodes_from_hostnames(hosts)
    # Use event to send power off signal to all processes
    power_off_event = mp.Event()
    new_ps = []
    # save results for each process
    out_q = Queue()
    for barcode in barcodes:
        new_p = Process(target=_power_off, args=(barcode, power_off_event, 180, out_q))
        new_ps.append(new_p)
        new_p.start()

    LOG.info("Powering off hosts in multi-processes to simulate power outage: {}".format(hosts))
    # send power-off signal
    power_off_event.set()

    for p in new_ps:
        p.join(timeout=300)

    # Process results
    results = out_q.get(timeout=10)
    for node, res in results:
        if res[0] != 0:
            raise exceptions.VLMError(res[1])
