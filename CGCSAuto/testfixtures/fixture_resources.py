from copy import deepcopy


class ResourceCleanup:
    """
    Class to hold the cleanup list and related functions.
    """
    __resources_dict = {
        'vms_with_vols': [],
        'vms_no_vols': [],
        'volumes': [],
        'volume_types': [],
        'qos_ids': [],
        'flavors': [],
        'images': [],
        'server_groups': [],
        'routers': [],
        'router_interfaces': [],
        'subnets': [],
        'floating_ips': [],
        'heat_stacks': [],
        'ports': [],
    }
    __resources_to_cleanup = {
        'function': deepcopy(__resources_dict),
        'class': deepcopy(__resources_dict),
        'module': deepcopy(__resources_dict),
    }

    @classmethod
    def _get_resources(cls, scope):
        return cls.__resources_to_cleanup[scope]

    @classmethod
    def _reset(cls, scope):
        for key in cls.__resources_to_cleanup[scope]:
            cls.__resources_to_cleanup[scope][key] = []

    @classmethod
    def add(cls, resource_type, resource_id, scope='function', del_vm_vols=True):
        """
        Add resource to cleanup list.

        Args:
            resource_type (str): one of these: 'vm', 'volume', 'flavor
            resource_id (str|list): id(s) of the resource to add to cleanup list
            scope (str): when the cleanup should be done. Valid value is one of these: 'function', 'class', 'module'
            del_vm_vols (bool): whether to delete attached volume(s) if given resource is vm.

        """
        scope = scope.lower()
        resource_type = resource_type.lower()
        valid_scopes = ['function', 'class', 'module']
        valid_types = ['vm', 'volume', 'volume_type', 'qos', 'flavor', 'image', 'server_group', 'router',
                       'subnet', 'floating_ip', 'heat_stack', 'port']

        if scope not in valid_scopes:
            raise ValueError("'scope' param value has to be one of the: {}".format(valid_scopes))
        if resource_type not in valid_types:
            raise ValueError("'resource_type' param value has to be one of the: {}".format(valid_types))

        if resource_type == 'vm':
            if del_vm_vols:
                key = 'vms_with_vols'
            else:
                key = 'vms_no_vols'
        elif resource_type == 'qos':
            key = 'qos_ids'
        else:
            key = resource_type + 's'

        if not isinstance(resource_id, (list, tuple)):
            resource_id = [resource_id]

        for res_id in resource_id:
            cls.__resources_to_cleanup[scope][key].append(res_id)


class VlmHostsReserved:
    __hosts_reserved_dict = {
        'function': [],
        'class': [],
        'module': [],
        'session': [],
    }

    @classmethod
    def _reset(cls, scope):
        cls.__hosts_reserved_dict[scope] = []

    @classmethod
    def _get_hosts_reserved(cls, scope):
        return cls.__hosts_reserved_dict[scope]

    @classmethod
    def add(cls, hosts, scope='session'):
        """
        Add resource to cleanup list.

        Args:
            hosts (str|list): hostname(s)
            scope (str): one of these: 'function', 'class', 'module', 'session'

        """
        scope = scope.lower()
        valid_scopes = ['function', 'class', 'module', 'session']

        if scope not in valid_scopes:
            raise ValueError("'scope' param value has to be one of the: {}".format(valid_scopes))

        if not isinstance(hosts, (list, tuple)):
            hosts = [hosts]

        for host in hosts:
            cls.__hosts_reserved_dict[scope].append(host)