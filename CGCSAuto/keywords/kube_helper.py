import time

import yaml

from utils import table_parser, exceptions
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from keywords import common, system_helper, host_helper
from consts.cgcs import PodStatus


def exec_kube_cmd(sub_cmd, args=None, con_ssh=None, fail_ok=False):
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    cmd = 'kubectl {} {}'.format(sub_cmd.strip(), args.strip() if args else '').strip()

    get_exit_code = True
    if cmd.endswith(';echo'):
        get_exit_code = False
    code, out = con_ssh.exec_cmd(cmd, fail_ok=True, get_exit_code=get_exit_code)
    if code <= 0:
        return 0, out

    if fail_ok:
        return 1, out

    raise exceptions.KubeCmdError('CMD: {} Output: {}'.format(cmd, out))


def __get_kube_tables(namespace=None, types=None, con_ssh=None, fail_ok=False):

    if isinstance(types, (list, tuple)):
        types = ','.join(types)

    args = types if types else ''
    if namespace == 'all':
        args += ' --all-namespaces'
    elif namespace:
        args += ' --namespace {}'.format(namespace)

    code, out = exec_kube_cmd(sub_cmd='get', args=args, con_ssh=con_ssh, fail_ok=fail_ok)
    if code > 0:
        return code, out

    tables = table_parser.tables_kube(out)
    return code, tables


def get_pods_info(namespace=None, type_names='pods', keep_type_prefix=False, con_ssh=None, fail_ok=False,
                  rtn_list=False):
    """

    Args:
        namespace (None|str): e.g., kube-system, openstack, default. If set to 'all', use --all-namespaces.
        type_names (None|list|tuple|str): e.g., ("deployments.apps", "services/calico-typha")
        keep_type_prefix (bool): e.g., whether to use 'service/cinder' or 'cinder' as value for 'NAME' key for each row
        con_ssh:
        fail_ok:
        rtn_list (bool)

    Returns (dict):
        key is the name prefix, e.g., service, default, deployment.apps, replicaset.apps
        value is a list. Each item is a dict rep for a row with lowercase keys.
            e.g., [{'name': 'cinder-api', 'age': '4d19h', ... },  ...]

    """
    code, out = __get_kube_tables(namespace=namespace, types=type_names, con_ssh=con_ssh, fail_ok=fail_ok)
    if code > 0:
        return {}

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
        with host_helper.ssh_to_host(hostname=con_name, con_ssh=con_ssh) as other_con:
            res, pods_info = wait_for_pods(pod_names=pod_name, namespace=namespace, con_ssh=other_con, fail_ok=fail_ok)
            if not res:
                return 3, pods_info[pod_name]

    LOG.info("{} pod is successfully applied and running".format(pod_name))
    return 0, pods_info[pod_name]


def wait_for_pods(pod_names, status=PodStatus.RUNNING, namespace=None, timeout=120, check_interval=3, con_ssh=None,
                  fail_ok=False, strict=False):
    if isinstance(pod_names, str):
        pod_names = [pod_names]

    end_time = time.time() + timeout
    names_to_check = list(pod_names)
    actual_pods_info = {pod_name: None for pod_name in pod_names}
    while time.time() < end_time:
        pods_list = get_pods_info(namespace=namespace, type_names='pods', keep_type_prefix=False, con_ssh=con_ssh,
                                  fail_ok=True, rtn_list=True)

        for pod_dict in pods_list:
            pod_name = pod_dict['name']
            if (strict and pod_name in names_to_check) or \
                    (not strict and any([pod_name in name for name in names_to_check])):
                actual_pods_info[pod_name] = pod_dict
                if not status or status == pod_dict['status']:
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


def wait_for_pods_gone(pod_names, types='pods', namespace=None, timeout=120, check_interval=3,
                       con_ssh=None, fail_ok=False, strict=True):
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


def delete_pods(pod_names=None, select_all=None, pods_types='pods', namespace=None, recursive=None, selectors=None,
                con_ssh=None, fail_ok=False, check_both_controllers=True):
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

    LOG.info("Check pod is running on current host")
    res, remaining = wait_for_pods_gone(pod_names=pod_names, types=pods_types, namespace=namespace, con_ssh=con_ssh,
                                        fail_ok=fail_ok)
    if not res:
        return 2, remaining

    if check_both_controllers and not system_helper.is_simplex(con_ssh=con_ssh):
        LOG.info("Check pod is running on the other controller as well")
        con_name = 'controller-1' if con_ssh.get_hostname() == 'controller-0' else 'controller-0'
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
