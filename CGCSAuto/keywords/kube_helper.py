import time

import yaml

from utils import table_parser, exceptions
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from keywords import common, system_helper
from consts.cgcs import PodStatus


def exec_kube_cmd(sub_cmd, args=None, con_ssh=None, fail_ok=False, grep=None):
    """
    Execute an kubectl cmd on given ssh client. i.e., 'kubectl <sub_cmd> <args>'
    Args:
        sub_cmd (str):
        args (None|str):
        con_ssh:
        fail_ok:
        grep (None|str|tuple|list)

    Returns (tuple):
        (0, <std_out>)
        (1, <std_err>)

    """
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    cmd = 'kubectl {} {}'.format(sub_cmd.strip(), args.strip() if args else '').strip()

    get_exit_code = True
    if cmd.endswith(';echo'):
        get_exit_code = False
    if grep:
        if isinstance(grep, str):
            grep = (grep, )
        for grep_str in grep:
            if '-v ' not in grep_str and '-e ' in grep_str and 'NAMESPACE' not in grep_str:
                grep_str += ' -e NAMESPACE'
            cmd += ' | grep --color=never {}'.format(grep_str)

    code, out = con_ssh.exec_cmd(cmd, fail_ok=True, get_exit_code=get_exit_code)
    if code <= 0:
        return 0, out

    if fail_ok:
        return 1, out
    else:
        raise exceptions.KubeCmdError('CMD: {} Output: {}'.format(cmd, out))


def __get_kube_tables(namespace=None, types=None, con_ssh=None, fail_ok=False, grep=None):

    if isinstance(types, (list, tuple)):
        types = ','.join(types)

    args = types if types else ''
    if namespace == 'all':
        args += ' --all-namespaces'
    elif namespace:
        args += ' --namespace {}'.format(namespace)
    args += ' -o wide'

    code, out = exec_kube_cmd(sub_cmd='get', args=args, con_ssh=con_ssh, fail_ok=fail_ok, grep=grep)
    if code > 0:
        return code, out

    tables = table_parser.tables_kube(out)
    return code, tables


def get_pods(namespace='all', rtn_val='NAME', name=None, status=None, restarts=None, node=None,
             exclude=False, strict=True, con_ssh=None, grep=None):
    """
    Get pods
    Args:
        namespace (str|None): when None, --all-namespaces will be used.
        rtn_val (str|tuple|list): table header
        name (str|None|tuple|list): OR relation for items in tuple/list
        status (str|None|tuple|list):
        restarts (str|None|tuple|list):
        node (str|None|tuple|list):
        exclude (bool):
        strict (bool):
        con_ssh:
        grep (str|None)

    Returns (list):

    """
    code, out = __get_kube_tables(namespace=namespace, types='pod', con_ssh=con_ssh, fail_ok=True, grep=grep)
    if code > 0:
        return []

    table_ = out[0]
    multi_header = True
    if isinstance(rtn_val, str):
        rtn_val = (rtn_val, )
        multi_header = False

    values = []
    for header in rtn_val:
        values.append(table_parser.get_values(table_, header, exclude=exclude, strict=strict, name=name, node=node,
                                              status=status, restarts=restarts))
    if not multi_header:
        values = values[0]
    else:
        values = list(zip(*values))

    return values


def get_pods_info(namespace=None, type_names='pod', keep_type_prefix=False, con_ssh=None, fail_ok=False,
                  rtn_list=False, grep=None):
    """
    Get pods info via kubectl get
    Args:
        namespace (None|str): e.g., kube-system, openstack, default. If set to 'all', use --all-namespaces.
        type_names (None|list|tuple|str): e.g., ("deployments.apps", "services/calico-typha")
        keep_type_prefix (bool): e.g., whether to use 'service/cinder' or 'cinder' as value for 'NAME' key for each row
        con_ssh:
        fail_ok:
        rtn_list (bool)
        grep (str|list|tuple|None)

    Returns (dict|list of dict):
        key is the name prefix, e.g., service, default, deployment.apps, replicaset.apps
        value is a list. Each item is a dict rep for a row with lowercase keys.
            e.g., [{'name': 'cinder-api', 'age': '4d19h', ... },  ...]

    """
    code, out = __get_kube_tables(namespace=namespace, types=type_names, con_ssh=con_ssh, fail_ok=fail_ok, grep=grep)
    if code > 0:
        return [] if rtn_list else {}

    kube_info = {}
    for table_ in out:
        if table_['values']:
            name = table_parser.get_column(table_, 'name')[0]
            name_prefix = name.split('/', maxsplit=1)[0]
            dict_table = table_parser.row_dict_table(table_, key_header='name')
            rows = list(dict_table.values())
            if not keep_type_prefix and name_prefix != name:
                start_index = len(name_prefix) + 1
                for row_dict in rows:
                    row_dict['name'] = row_dict.pop('name')[start_index:]

            if name_prefix == name:
                # assume only one table returned with only 1 type_names specified
                name_prefix = type_names if isinstance(type_names, str) else type_names[0]
            kube_info[name_prefix] = rows

    LOG.debug('kubernetes info for namespace {}: {}'.format(namespace, kube_info))
    if rtn_list:
        kube_list = []
        for kube_rows in kube_info.values():
            kube_list += kube_rows
        return kube_list

    return kube_info


def apply_pod(file_path, pod_name, namespace=None, recursive=None, select_all=None, selectors=None, con_ssh=None,
              fail_ok=False, check_both_controllers=True):
    """
    Apply a pod from given file via kubectl apply
    Args:
        file_path (str):
        pod_name (str):
        namespace (None|str):
        recursive (None|bool):
        select_all (None|bool):
        selectors (dict): key value pairs
        con_ssh:
        fail_ok:
        check_both_controllers (bool):

    Returns (tuple):
        (0, <pod_info>(dict))
        (1, <std_err>)
        (2, <pod_info>)    # pod is not running after apply
        (3, <pod_info>)    # pod if not running on the other controller after apply

    """
    arg_dict = {
        '--all': select_all,
        '-l': selectors,
        '--recursive': recursive,
    }

    arg_str = common.parse_args(args_dict=arg_dict, vals_sep=',')
    arg_str += ' -f {}'.format(file_path)

    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    code, output = exec_kube_cmd(sub_cmd='apply', args=arg_str, con_ssh=con_ssh, fail_ok=fail_ok)
    if code > 0:
        return 1, output

    LOG.info("Check pod is running on current host")
    res, pods_info = wait_for_pods(pod_names=pod_name, namespace=namespace, con_ssh=con_ssh, fail_ok=fail_ok)
    if not res:
        return 2, pods_info[pod_name]

    if check_both_controllers and not system_helper.is_simplex(con_ssh=con_ssh):
        LOG.info("Check pod is running on the other controller as well")
        con_name = 'controller-1' if con_ssh.get_hostname() == 'controller-0' else 'controller-0'
        from keywords import host_helper
        with host_helper.ssh_to_host(hostname=con_name, con_ssh=con_ssh) as other_con:
            res, pods_info = wait_for_pods(pod_names=pod_name, namespace=namespace, con_ssh=other_con, fail_ok=fail_ok)
            if not res:
                return 3, pods_info[pod_name]

    LOG.info("{} pod is successfully applied and running".format(pod_name))
    return 0, pods_info[pod_name]


def wait_for_pods(pod_names, status=PodStatus.RUNNING, namespace=None, timeout=120, check_interval=3, con_ssh=None,
                  fail_ok=False, strict=False):
    """
    Wait for pod(s) to reach given status via kubectl get
    Args:
        pod_names (str|list|tuple):
        status (str):
        namespace (None|str):
        timeout:
        check_interval:
        con_ssh:
        fail_ok:
        strict (bool):

    Returns (tuple):
        (True, <actual_pods_info>)  # actual_pods_info is a dict with pod_name as key, and pod_info(dict) as value
        (False, <actual_pods_info>)

    """
    if isinstance(pod_names, str):
        pod_names = [pod_names]

    end_time = time.time() + timeout
    names_to_check = list(pod_names)
    actual_pods_info = {pod_name: None for pod_name in pod_names}
    while time.time() < end_time:
        pods_list = get_pods_info(namespace=namespace, type_names='pod', keep_type_prefix=False, con_ssh=con_ssh,
                                  fail_ok=True, rtn_list=True)

        for pod_dict in pods_list:
            pod_name = pod_dict.get('name')
            if (strict and pod_name in names_to_check) or \
                    (not strict and any([pod_name in name for name in names_to_check])):
                actual_pods_info[pod_name] = pod_dict
                if not status or status == pod_dict.get('status'):
                    names_to_check.remove(pod_name)
                    if not names_to_check:
                        return True, actual_pods_info

        time.sleep(check_interval)

    msg = 'Pods did not appear in {} seconds. pods: {}, namespace: {}, pods info: {}'.\
        format(timeout, pod_names, namespace, actual_pods_info)

    if fail_ok:
        LOG.info(msg)
        return False, actual_pods_info

    raise exceptions.KubeError(msg)


def wait_for_pods_gone(pod_names, types='pod', namespace=None, timeout=120, check_interval=3, con_ssh=None,
                       fail_ok=False, strict=True):
    """
        Wait for pod(s) to be gone from kubectl get
        Args:
            pod_names (str|list|tuple):
            types (str):
            namespace (None|str):
            timeout:
            check_interval:
            con_ssh:
            fail_ok:
            strict (bool): check no pods with given name exist if strict; else check no pods contains any given name

        Returns (tuple):
            (True, None)
            (False, <actual_pods_info>)   # actual_pods_info is a dict with pod_name as key, and pod_info(dict) as value

        """
    if isinstance(pod_names, str):
        pod_names = [pod_names]

    end_time = time.time() + timeout
    pods_info = remaining_pod = None
    while time.time() < end_time:
        pods_info = get_pods_info(namespace=namespace, type_names=types, keep_type_prefix=False, con_ssh=con_ssh,
                                  fail_ok=True)

        current_names = []
        for pods_type, pods_list in pods_info.items():
            current_names += [pod_dict['name'] for pod_dict in pods_list]

        current_names = list(set(current_names))
        for pod_name in pod_names:
            if (strict and pod_name in current_names) or \
                    (not strict and any([pod_name in name for name in current_names])):
                remaining_pod = pod_name
                break
        else:
            return True, None

        time.sleep(check_interval)

    msg = 'Pods did not appear in {} seconds. pod remains: {}, namespace: {}, pods info: {}'.\
        format(timeout, remaining_pod, namespace, pods_info)

    if fail_ok:
        LOG.info(msg)
        return False, remaining_pod

    raise exceptions.KubeError(msg)


def delete_pods(pod_names=None, select_all=None, pods_types='pod', namespace=None, recursive=None, selectors=None,
                con_ssh=None, fail_ok=False, check_both_controllers=True):
    """
    Delete pods via kubectl delete
    Args:
        pod_names (None|str|list|tuple):
        select_all (None|bool):
        pods_types (str|list|tuple):
        namespace (None|str):
        recursive (bool):
        selectors (None|dict):
        con_ssh:
        fail_ok:
        check_both_controllers (bool):

    Returns (tuple):
        (0, None)   # pods successfully deleted
        (1, <std_err>)
        (2, <undeleted_pods_info>(list of dict))    # pod(s) still exist in kubectl after deletion
        (3, <undeleted_pods_info_on_other_controller>(list of dict))    # pod(s) still exist on the other controller

    """
    arg_dict = {
        '--all': select_all,
        '-l': selectors,
        '--recursive': recursive,
    }

    arg_str = common.parse_args(args_dict=arg_dict, vals_sep=',')
    if pods_types:
        if isinstance(pods_types, str):
            pods_types = [pods_types]
        arg_str = '{} {}'.format(','.join(pods_types), arg_str).strip()

    if pod_names:
        if isinstance(pod_names, str):
            pod_names = [pod_names]
        arg_str = '{} {}'.format(arg_str, ' '.join(pod_names))

    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    code, output = exec_kube_cmd(sub_cmd='delete', args=arg_str, con_ssh=con_ssh, fail_ok=fail_ok)
    if code > 0:
        return 1, output

    LOG.info("Check pod is not running on current host")
    res, remaining = wait_for_pods_gone(pod_names=pod_names, types=pods_types, namespace=namespace, con_ssh=con_ssh,
                                        fail_ok=fail_ok)
    if not res:
        return 2, remaining

    if check_both_controllers and not system_helper.is_simplex(con_ssh=con_ssh):
        LOG.info("Check pod is running on the other controller as well")
        con_name = 'controller-1' if con_ssh.get_hostname() == 'controller-0' else 'controller-0'
        from keywords import host_helper
        with host_helper.ssh_to_host(hostname=con_name, con_ssh=con_ssh) as other_con:
            res, remaining = wait_for_pods_gone(pod_names=pod_names, namespace=namespace, types=pods_types,
                                                con_ssh=other_con, fail_ok=fail_ok)
            if not res:
                return 3, remaining

    LOG.info("{} are successfully removed.".format(pod_names))
    return 0, None


def get_pods_info_yaml(type_names='pods', namespace=None, con_ssh=None, fail_ok=False):
    """
    pods info parsed from yaml output of kubectl get cmd
    Args:
        namespace (None|str): e.g., kube-system, openstack, default. If set to 'all', use --all-namespaces.
        type_names (None|list|tuple|str): e.g., ("deployments.apps", "services/calico-typha")
        con_ssh:
        fail_ok:

    Returns (list): each item is a pod info dictionary

    """
    if isinstance(type_names, (list, tuple)):
        type_names = ','.join(type_names)
    args = type_names

    if namespace == 'all':
        args += ' --all-namespaces'
    elif namespace:
        args += ' --namespace={}'.format(namespace)

    args += ' -o yaml'

    code, out = exec_kube_cmd(sub_cmd='get', args=args, con_ssh=con_ssh, fail_ok=fail_ok)
    if code > 0:
        return []

    try:
        pods_info = yaml.load(out)
    except yaml.YAMLError:
        LOG.warning('Output is not yaml')
        return []

    pods_info = pods_info.get('items', [pods_info])

    return pods_info


def get_pod_value_jsonpath(type_name, jsonpath, namespace=None, con_ssh=None):
    """
    Get value for specified pod with jsonpath
    Args:
        type_name (str): e.g., 'service/kubernetes'
        jsonpath (str): e.g., '{.spec.ports[0].targetPort}'
        namespace (str|None): e.g.,  'kube-system'
        con_ssh:

    Returns (str):

    """
    args = '{} -o jsonpath="{}"'.format(type_name, jsonpath)
    if namespace:
        args += ' --namespace {}'.format(namespace)

    args += ';echo'
    value = exec_kube_cmd('get', args, con_ssh=con_ssh)[1]
    return value


def get_nodes_values(hosts=None, status=None, rtn_val='STATUS', exclude=False, con_ssh=None, fail_ok=False):
    """
    Get nodes values via 'kubectl get nodes'
    Args:
        hosts (None|str|list|tuple): table filter
        status (None|str|list|tuple): table filter
        rtn_val (str): any header of the nodes table
        exclude (bool): whether to exclude rows with given criteria
        con_ssh:
        fail_ok:

    Returns (None|list): None if cmd failed.

    """
    code, output = exec_kube_cmd('get', args='nodes', con_ssh=con_ssh, fail_ok=fail_ok)
    if code > 0:
        return None

    table_ = table_parser.table_kube(output)
    if hosts or status:
        table_ = table_parser.filter_table(table_, exclude=exclude, **{'NAME': hosts, 'STATUS': status})

    return table_parser.get_column(table_, rtn_val)


def get_nodes_in_status(hosts=None, status='Ready', exclude=False, con_ssh=None, fail_ok=False):
    """
    Get hosts in given status via kubectl get nodes
    Args:
        hosts (None|list|str|tuple): If specified, check given hosts only
        status:
        exclude:
        con_ssh:
        fail_ok:

    Returns (list):

    """
    return get_nodes_values(hosts=hosts, status=status, rtn_val='NAME', exclude=exclude, con_ssh=con_ssh,
                            fail_ok=fail_ok)


def wait_for_nodes_ready(hosts=None, timeout=120, check_interval=5, con_ssh=None, fail_ok=False):
    """
    Wait for hosts in ready state via kubectl get nodes
    Args:
        hosts (None|list|str|tuple): Wait for all hosts ready if None is specified
        timeout:
        check_interval:
        con_ssh:
        fail_ok:

    Returns (tuple):
        (True, None)
        (False, <nodes_not_ready>(list))

    """
    end_time = time.time() + timeout
    nodes_not_ready = None
    while time.time() < end_time:
        nodes_not_ready = get_nodes_in_status(hosts=hosts, status='Ready', exclude=True, con_ssh=con_ssh, fail_ok=True)
        if nodes_not_ready:
            LOG.info('{} not ready yet'.format(nodes_not_ready))
        elif nodes_not_ready is not None:
            LOG.info("All nodes are ready{}".format(': {}'.format(hosts) if hosts else ''))
            return True, None

        time.sleep(check_interval)

    msg = '{} are not ready within {}s'.format(nodes_not_ready, timeout)
    LOG.warning(msg)
    if fail_ok:
        return False, nodes_not_ready
    else:
        raise exceptions.KubeError(msg)


def exec_cmd_in_container(cmd, pod, namespace=None, container_name=None, stdin=None, tty=None, con_ssh=None,
                          fail_ok=False):
    """
    Execute given cmd in given pod via kubectl exec
    Args:
        cmd:
        pod:
        namespace:
        container_name:
        stdin:
        tty:
        con_ssh:
        fail_ok:

    Returns (tuple):
        (0, <std_out>)
        (1, <std_err>)

    """
    args = pod
    if namespace:
        args += ' -n {}'.format(namespace)
    if container_name:
        args += ' -c {}'.format(container_name)
    if stdin:
        args += ' -i'
    if tty:
        args += ' -t'
    args += ' -- {}'.format(cmd)

    code, output = exec_kube_cmd(sub_cmd='exec', args=args, con_ssh=con_ssh, fail_ok=fail_ok)
    return code, output


def get_openstack_pods_info(pod_names=None, strict=False, con_ssh=None, fail_ok=False):
    """
    Get openstack pods info for given pods.
    Args:
        pod_names (str|list|tuple): e.g, 'nova', ('nova-api', 'nova-compute', 'neutron')
        strict (bool): whether to do strict match for given name
        con_ssh:
        fail_ok

    Returns (list of list): each item in list is a list of pods info dict per pod_name. e.g.,
        if pod_names = ('nova-compute', 'glance-bootstrap'), returns will be:
        [[<nova-compute-compute-0 pod info>(dict), ...], [<glance-bootstrap pod info>(dict)]]

    """
    grep = None
    if pod_names:
        if isinstance(pod_names, str):
            pod_names = (pod_names,)
        grep_str = '|'.join(pod_names) + '|NAME'
        grep = '-E -i "{}"'.format(grep_str)

    openstack_pods = get_pods_info(namespace='openstack', type_names='pod', con_ssh=con_ssh, rtn_list=True, grep=grep,
                                   fail_ok=fail_ok)
    if not pod_names:
        return [openstack_pods]

    filtered_pods = []
    for pod_name in pod_names:
        pods_info_per_name = []
        for openstack_pod_info in openstack_pods:
            openstack_pod_name = openstack_pod_info.get('name')
            if strict and openstack_pod_name == pod_name or (not strict and pod_name in openstack_pod_name):
                pods_info_per_name.append(openstack_pod_info)
        filtered_pods.append(pods_info_per_name)

    return filtered_pods


def wait_for_pods_ready(pod_names=None, namespace='all', node=None, timeout=120, check_interval=5, con_ssh=None,
                        fail_ok=False, strict=False, pods_to_exclude=None):
    """
    Wait for pods ready
    Args:
        pod_names:
        namespace:
        node:
        timeout:
        check_interval:
        con_ssh:
        fail_ok:
        strict:
        pods_to_exclude (None|str|list|tuple)

    Returns:

    """
    LOG.info("Wait for pods ready..")
    bad_pods = None
    end_time = time.time() + timeout
    while time.time() < end_time:
        bad_pods = {}
        bad_pods_info = get_pods(rtn_val=('NAME', 'STATUS'), namespace=namespace, name=pod_names, node=node,
                                 grep='-v -e {} -e {}'.format(PodStatus.COMPLETED, PodStatus.RUNNING),
                                 con_ssh=con_ssh, strict=strict)

        for pod_info in bad_pods_info:
            if pods_to_exclude and pod_info[0] not in pods_to_exclude:
                bad_pods[pod_info[0]] = pod_info[1]

        if not bad_pods:
            LOG.info("All pods are healthy.")
            return True, bad_pods

        time.sleep(check_interval)

    msg = 'Some pods are not healthy: {}'.format(bad_pods)
    LOG.warning(msg)
    if fail_ok:
        return False, bad_pods
    else:
        raise exceptions.KubeError(msg)


def wait_for_openstack_pods_in_status(pod_names=None, status=None, con_ssh=None, timeout=60, check_interval=5,
                                      fail_ok=False):
    """
    Wait for openstack pods to be in Completed or Running state
    Args:
        pod_names (str|tuple|list|None):
        status (str|tuple|list|None):
        con_ssh:
        timeout:
        check_interval:
        fail_ok:

    Returns:

    """
    end_time = time.time() + timeout

    bad_pods = None
    while time.time() < end_time:
        res, bad_pods = is_openstack_pods_in_status(pod_names=pod_names, con_ssh=con_ssh, status=status)
        if res:
            LOG.info("Openstack pods{} are in expected status{}".format(' {}'.format(pod_names) if pod_names else '',
                                                                        ': {}'.format(status) if status else '.'))
            return True, []

        time.sleep(check_interval)

    msg = "Some openstack pod(s) not in expected status: {}".format(bad_pods)
    LOG.info(msg)
    if fail_ok:
        return False, bad_pods
    else:
        raise exceptions.KubeError(msg)


def is_openstack_pods_in_status(pod_names=None, status=None, con_ssh=None):
    if isinstance(pod_names, str):
        pod_names = (pod_names,)

    pods_info_set = get_openstack_pods_info(pod_names=pod_names, con_ssh=con_ssh, fail_ok=True)
    bad_pods = {}
    for i in range(len(pods_info_set)):
        pods_info = pods_info_set[i]
        if not pods_info:
            k = pod_names[i] if pod_names else 'all'
            bad_pods[k] = None

        for pod_info in pods_info:
            pod_name = pod_info.get('name')
            pod_status = pod_info.get('status')
            expt_status = status
            if not status:
                expt_status = [PodStatus.RUNNING] if 'api' in pod_name else \
                    [PodStatus.RUNNING, PodStatus.COMPLETED]
            elif isinstance(status, str):
                expt_status = [status]

            if pod_status not in expt_status:
                bad_pods[pod_name] = pod_status
                msg = "Pod {} status is {}. Expect: {}".format(pod_name, pod_status, status)
                LOG.info(msg)

    res = False if bad_pods else True
    return res, bad_pods


def get_pod_logs(pod_name, namespace='openstack', grep_pattern=None, tail_count=10, strict=False,
                 fail_ok=False, con_ssh=None):
    """
    Get logs for given pod via kubectl logs cmd
    Args:
        pod_name (str): partial or full pod_name. If full name, set strict to True.
        namespace (str|None):
        grep_pattern (str|None):
        tail_count (int|None):
        strict (bool):
        fail_ok:
        con_ssh:

    Returns (str):

    """
    if pod_name and not strict:
        grep = '-E -i "{}|NAME"'.format(pod_name)
        pod_name = get_pods_info(namespace='openstack', type_names='pod', con_ssh=con_ssh, rtn_list=True,
                                  grep=grep, fail_ok=fail_ok)[0].get('name')
    namespace = '-n {} '.format(namespace) if namespace else ''

    grep = ''
    if grep_pattern:
        if isinstance(grep_pattern, str):
            grep_pattern = (grep_pattern, )
        grep = ''.join([' | grep --color=never {}'.format(grep_str) for grep_str in grep_pattern])
    tail = ' | tail -n {}'.format(tail_count) if tail_count else ''
    args = '{}{}{}{}'.format(namespace, pod_name, grep, tail)
    code, output = exec_kube_cmd(sub_cmd='logs', args=args, con_ssh=con_ssh)
    if not output and not fail_ok:
        raise exceptions.KubeError("No kubectl logs found with args: {}".format(args))
    return output


def dump_pods_info(con_ssh=None):
    """
    Dump pods info for debugging purpose.
    Args:
        con_ssh:

    Returns:

    """
    # exec_kube_cmd('get pods', '--all-namespaces -o wide', con_ssh=con_ssh, fail_ok=True)
    exec_kube_cmd('get pods', '--all-namespaces -o wide | grep -v -e Running -e Completed', con_ssh=con_ssh,
                  fail_ok=True)
    exec_kube_cmd('get pods',
                  """--all-namespaces -o wide | grep -v -e Running -e Completed -e NAMESPACE | awk '{system("kubectl describe pods -n "$1" "$2)}'""",
                  con_ssh=con_ssh, fail_ok=True)

    # exec_kube_cmd('get pods', """--all-namespaces -o wide |
    # grep -v -e Running -e Completed -e NAMESPACE | awk '{system("kubectl logs -n "$1" "$2)}'""")
