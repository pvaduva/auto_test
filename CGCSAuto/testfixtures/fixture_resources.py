
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