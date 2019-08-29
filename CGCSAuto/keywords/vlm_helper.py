import re
import time
from multiprocessing import Process, Queue, Event

from consts.proj_vars import InstallVars, ProjVar
from consts.timeout import HostTimeout
from consts.vlm import VlmAction
from consts.auth import TestFileServer, Tenant
from keywords import host_helper, system_helper
from utils import exceptions, local_host
from utils.clients.ssh import ControllerClient
from utils.clients.local import LocalHostClient
from utils.tis_log import LOG

# VLM commands and options
VLM = "/folk/vlm/commandline/vlmTool"
VLM_CMDS = [VlmAction.VLM_RESERVE, VlmAction.VLM_UNRESERVE, VlmAction.VLM_FORCE_UNRESERVE, VlmAction.VLM_TURNON,
            VlmAction.VLM_TURNOFF, VlmAction.VLM_FINDMINE, VlmAction.VLM_REBOOT]


def local_client():
    client_ = LocalHostClient(connect=True)
    return client_


def _reserve_vlm_console(barcode, note=None):
    cmd = '{} {} -t {}'.format(VLM, VlmAction.VLM_RESERVE, barcode)
    if note:
        cmd += ' -n "{}"'.format(note)

    reserved_barcodes = local_client().exec_cmd(cmd)[1]
    if str(barcode) not in reserved_barcodes or "Error" in reserved_barcodes:
        # check if node is already reserved by user
        attr_dict = _get_attr_dict_for_vlm_console(barcode=barcode, attr='all')
        reserved_by = attr_dict['Reserved By']
        local_user = local_host.get_user()
        if reserved_by != local_user:
            msg = "Target {} is not reserved by {}".format(barcode, local_user)
            LOG.error(msg)
            return 1, msg
        else:
            msg = "Barcode {} already reserved".format(barcode)
            LOG.info(msg)
            return -1, msg
    else:
        msg = "Barcode {} reserved".format(barcode)
        LOG.info(msg)
        return 0, msg


def _force_unreserve_vlm_console(barcode):
    action = VlmAction.VLM_FORCE_UNRESERVE
    cmd = '{} {} -L {} -P {} -t {}'.format(VLM, action, TestFileServer.USER, TestFileServer.VLM_PASSWORD, barcode)
    attr_dict = _get_attr_dict_for_vlm_console(barcode=barcode, attr='all')
    LOG.info(attr_dict)
    reserved_by = attr_dict['Reserved By']
    reserve_note = attr_dict['Reserve Note']

    if not reserved_by:
        msg = "Target {} is not reserved. Do nothing".format(barcode)
        LOG.info(msg)
        return -1, msg
    elif reserved_by == local_host.get_user() or not reserve_note:
        print("Force unreserving target: {}".format(barcode))
        local_client().exec_cmd(cmd)
        reserved = _vlm_getattr(barcode, 'date')[1]
        if reserved:
            msg = "Failed to force unreserve target!"
            LOG.error(msg)
            return 1, msg
        else:
            msg = "Barcode {} was successfully unreserved".format(barcode)
            LOG.info(msg)
            return 0, msg
    else:
        msg = "Did not unreserve {} as it has a reservation note by {}: {}".format(barcode, reserved_by, reserve_note)
        LOG.error(msg)
        return 2, msg


def _vlm_findmine():
    output = local_client().exec_cmd('{} {}'.format(VLM, VlmAction.VLM_FINDMINE))[1]
    if re.search(r"\d+", output):
        reserved_targets = output.split(sep=' ')
        msg = "Target(s) reserved by user: {}".format(str(reserved_targets))
    else:
        msg = "User has no reserved target(s)"
        reserved_targets = []

    reserved_targets = [int(barcode) for barcode in reserved_targets]
    LOG.info(msg)

    return reserved_targets


def _vlm_getattr(barcode, attr='all'):
    cmd = '{} getAttr -t {} {}'.format(VLM, barcode, attr)
    return local_client().exec_cmd(cmd)


def _vlm_exec_cmd(action, barcode, reserve=True, fail_ok=False, client=None, count=1):
    if action not in VLM_CMDS:
        msg = '"{}" is an invalid action.'.format(action)
        msg += " Valid actions: {}".format(str(VLM_CMDS))
        raise ValueError(msg)

    if reserve:
        if int(barcode) not in _vlm_findmine():
            # reserve barcode
            if _reserve_vlm_console(barcode)[0] > 0:
                msg = "Failed to reserve target {}".format(barcode)
                if fail_ok:
                    LOG.info(msg)
                    return 1, msg
                else:
                    raise exceptions.VLMError(msg)

    if not client:
        client = local_client()

    output = None
    for i in range(count):
        output = client.exec_cmd('{} {} -t {}'.format(VLM, action, barcode))[1]
        if i < count:
            time.sleep(1)

    if output != "1":
        msg = 'Failed to execute "{}" on target {}. Output: {}'.format(action, barcode, output)
        LOG.error(msg)
        return 1, msg

    return 0, None


def get_lab_dict():
    return InstallVars.get_install_var('LAB')


def get_barcodes_dict(lab=None):
    if lab is None:
        lab = get_lab_dict()
        if ProjVar.get_var('IS_DC'):
            subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
            lab = lab[subcloud]

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


def get_barcodes_from_hostnames(hostnames,  lab=None):
    """
    Convert hostname(s) to barcodes
    Args:
        hostnames (str|list): hostname(s)
        lab (dict|None)

    Returns (list): list of barcodes
    """
    if isinstance(hostnames, str):
        hostnames = [hostnames]

    barcodes_dict = get_barcodes_dict(lab=lab)
    barcodes = []

    for host in hostnames:
        barcodes.append(barcodes_dict[host])

    return barcodes


def unreserve_hosts(hosts, lab=None):
    """
    Unreserve given hosts from vlm
    Args:
        lab (dict|None)
        hosts (str|list): hostname(s)

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_UNRESERVE, reserve=False, lab=lab)


def force_unreserve_hosts(hosts, val='hostname', lab=None):
    if isinstance(hosts, str):
        hosts = [hosts]

    barcodes = get_barcodes_from_hostnames(hosts, lab=lab) if val == 'hostname' else hosts

    LOG.info("forecefully unreserving hosts {}: {}".format(hosts, barcodes))
    for barcode in barcodes:
        rc, output = _force_unreserve_vlm_console(barcode)
        if rc > 0:
            err_msg = "Failed to unreserve barcode {} in vlm: {}".format(barcode, output)
            raise exceptions.VLMError(err_msg)


def get_hostnames_from_consts(lab=None):
    return list(get_barcodes_dict(lab=lab).keys())


def reserve_hosts(hosts, val='hostname', lab=None):
    """
    Reserve given host(s) or barcode(s) from vlm

    Args:
        hosts (str|list):
        val (str): 'hostname' or 'barcode'
        lab (str|None)

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    barcodes = get_barcodes_from_hostnames(hosts, lab=lab) if val == 'hostname' else hosts

    LOG.info("Reserving hosts {}: {}".format(hosts, barcodes))
    for barcode in barcodes:
        rc, output = _reserve_vlm_console(barcode)
        if rc > 0:
            err_msg = "Failed to reserve barcode {} in vlm: {}".format(barcode, output)
            raise exceptions.VLMError(err_msg)


def power_off_hosts(hosts, lab=None, reserve=True, count=1):
    """
    Power off given hosts
    Args:
        hosts (str|list): hostname(s)
        lab (str|None)
        reserve (bool): whether to reserve first
        count (int): how many times to perform the action

    Returns:

    """
    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_TURNOFF, reserve=reserve, lab=lab, count=count)


def power_on_hosts(hosts, reserve=True, post_check=True, reconnect=True, reconnect_timeout=HostTimeout.REBOOT,
                   hosts_to_check=None, con_ssh=None, region=None, count=1, check_interval=10):
    """

    Args:
        hosts (str|list): hostname(s)
        reserve (bool): whether to reserve first
        post_check (bool): whether to wait for hosts to be ready after power on
        reconnect (bool): whether or reconnect to lab via ssh after power on. Useful when power on controllers
        reconnect_timeout (int): max seconds to wait before reconnect succeeds
        hosts_to_check (list|str|None): host(s) to perform post check after power-on. when None, hosts_to_check=hosts
        check_interval (int)
        con_ssh (SSHClient):
        region:
        count (int): how many times to perform the action

    Returns:

    """

    if isinstance(hosts, str):
        hosts = [hosts]

    lab = None
    if region and ProjVar.get_var('IS_DC'):
        lab = ProjVar.get_var('LAB')[region]
    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_TURNON, lab=lab, reserve=reserve, count=count)

    if post_check:
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller(name=region)
        auth_info = Tenant.get('admin_platform',
                               dc_region='RegionOne' if region and region == 'central_region' else region)
        if reconnect:
            con_ssh.connect(retry=True, retry_timeout=reconnect_timeout)
            host_helper._wait_for_openstack_cli_enable(con_ssh=con_ssh, auth_info=auth_info, timeout=300,
                                                       reconnect=True, check_interval=check_interval)

        if not hosts_to_check:
            hosts_to_check = hosts
        elif isinstance(hosts_to_check, str):
            hosts_to_check = [hosts_to_check]

        host_helper.wait_for_hosts_ready(hosts_to_check, auth_info=auth_info, con_ssh=con_ssh,
                                         check_interval=check_interval)


def reboot_hosts(hosts, lab=None, reserve=True, post_check=True, reconnect=True, reconnect_timeout=HostTimeout.REBOOT,
                 hosts_to_check=None, con_ssh=None):
    if isinstance(hosts, str):
        hosts = [hosts]

    _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_REBOOT, lab=lab, reserve=reserve)

    if post_check:
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller(name=lab['short_name'] if lab else None)

        if reconnect:
            con_ssh.connect(retry=True, retry_timeout=reconnect_timeout)
            host_helper._wait_for_openstack_cli_enable(con_ssh=con_ssh)

        if not hosts_to_check:
            hosts_to_check = hosts
        elif isinstance(hosts_to_check, str):
            hosts_to_check = [hosts_to_check]

        host_helper.wait_for_hosts_ready(hosts_to_check, con_ssh=con_ssh)


def _perform_vlm_action_on_hosts(hosts, action=VlmAction.VLM_TURNON, lab=None, reserve=True, fail_ok=False, count=1):
    if isinstance(hosts, str):
        hosts = [hosts]

    barcodes = get_barcodes_from_hostnames(hosts, lab=lab)
    for i in range(len(hosts)):
        host = hosts[i]
        barcode = barcodes[i]

        LOG.info("{} {} {}".format(action, host, barcode))
        _vlm_exec_cmd(action, barcode, reserve=reserve, fail_ok=fail_ok, count=count)


def power_off_hosts_simultaneously(hosts=None, region=None):
    """
    Power off hosts in multi-processes to simulate power outage. This can be used for DOR.
    Args:
        hosts (list|None): when None, all hosts on system will be powered off
        region:

    Returns:

    """
    def _power_off(barcode_, power_off_event_, timeout_, output_queue):

        client = local_client()
        if power_off_event_.wait(timeout=timeout_):
            rc, output = _vlm_exec_cmd(VlmAction.VLM_TURNOFF, barcode_, reserve=False, client=client, count=2)
            rtn = (rc, output)

        else:
            err_msg = "Timed out waiting for power_off_event to be set"
            LOG.error(err_msg)
            rtn = (2, err_msg)

        if 0 == rtn[0]:
            LOG.info("{} powered off successfully".format(barcode_))
        else:
            LOG.error("Failed to power off {}.".format(barcode_))
        output_queue.put({barcode_: rtn})

    auth_info = Tenant.get('admin_platform', dc_region='RegionOne' if region and region == 'central_region' else region)
    if not hosts:
        hosts = system_helper.get_hosts(auth_info=auth_info)

    lab = None
    if region and ProjVar.get_var('IS_DC'):
        lab = ProjVar.get_var('LAB')[region]

    barcodes = get_barcodes_from_hostnames(hostnames=hosts, lab=lab)
    # Use event to send power off signal to all processes
    power_off_event = Event()
    new_ps = []
    # save results for each process
    out_q = Queue()
    for barcode in barcodes:
        new_p = Process(target=_power_off, args=(barcode, power_off_event, 180, out_q))
        new_ps.append(new_p)
        new_p.start()

    LOG.info("Powering off hosts in multi-processes to simulate power outage: {}".format(hosts))
    # send power-off signal
    time.sleep(3)
    power_off_event.set()

    for p in new_ps:
        p.join(timeout=300)

    # Process results
    results = out_q.get(timeout=10)
    LOG.info("Overall results: {}".format(results))
    for node, res in results.items():
        if res[0] != 0:
            raise exceptions.VLMError(res[1])


def _get_attr_dict_for_vlm_console(barcode, attr='all'):
    attribute_dict = {}
    output = _vlm_getattr(barcode, attr)[1]
    for line in output.splitlines():
        if line:
            if attr == "all":
                key = line[:line.find(":")].strip()
            else:
                key = attr
            val = line[line.find(":") + 1:].strip()
            attribute_dict[key] = val
    return attribute_dict


def get_attributes_dict(hosts, attr="all", val='hostname'):
    if isinstance(hosts, str):
        hosts = [hosts]

    attributes = []
    barcodes = get_barcodes_from_hostnames(hosts) if val == 'hostname' else hosts
    for barcode in barcodes:
        attribute_dict = _get_attr_dict_for_vlm_console(barcode=barcode, attr=attr)
        attributes.append(attribute_dict)
    return attributes
