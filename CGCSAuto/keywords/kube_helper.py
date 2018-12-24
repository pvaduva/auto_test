from utils import table_parser
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient


def __get_kube_tables(namespace=None, names=None, con_ssh=None, fail_ok=False):
    if not con_ssh:
         con_ssh = ControllerClient.get_active_controller()

    if isinstance(names, (list, tuple)):
        names = ','.join(names)

    args = names if names else ''
    args += ' --namespace {}'.format(namespace) if namespace else ' --all-namespaces'

    code, out = con_ssh.exec_cmd('kubectl get {}'.format(args.strip()), fail_ok=fail_ok)
    if code > 0:
        return code, out

    tables = table_parser.tables_kube(out)
    return code, tables


def get_namespace_info(namespace, names=None, keep_name_prefix=True, con_ssh=None, fail_ok=False):
    """

    Args:
        namespace (str): e.g., kube-system, openstack, default
        names (None|list|tuple|str): e.g., ("services", "deployments.apps")
        keep_name_prefix (bool): e.g., whether to use 'service/cinder' or 'cinder' as value for 'NAME' key for each row
        con_ssh:
        fail_ok:

    Returns (dict):
        key is the name prefix, e.g., service, default, deployment.apps, replicaset.apps
        value is a list. Each item is a dict rep for a row. e.g., [{'NAME': 'cinder-api', 'AGE': '4d19h', ... },  ...]

    """
    code, out = __get_kube_tables(namespace=namespace, names=names, con_ssh=con_ssh, fail_ok=fail_ok)
    if code > 0:
        return {}

    kube_info = {}
    for table_ in out:
        name_prefix = table_parser.get_column(table_, 'name')[0].split('/', maxsplit=1)[0]
        dict_table = table_parser.row_dict_table(table_, key_header='name')
        rows = list(dict_table.values())
        if not keep_name_prefix:
            start_index = len(name_prefix) + 1
            for row_dict in rows:
                row_dict['name'] = row_dict.pop('name')[start_index:]

        kube_info[name_prefix] = rows

    LOG.debug('kubernetes info for namespace {}: {}'.format(namespace, kube_info))
    return kube_info
