YOW_CGTS4_LX = {
    'name': 'yow-cgts4-lx',
    'ip': '128.224.145.137',
}

YOW_CGTS3_LX = {
    'name': 'yow-cgts3-lx',
    'ip': '128.224.145.134',
}

DEFAULT_BUILD_SERVER = YOW_CGTS4_LX

BUILD_SERVERS = [YOW_CGTS3_LX, YOW_CGTS4_LX]


def get_build_server_info(hostname):
    if hostname:
        for bs in BUILD_SERVERS:
            if bs['name'] == hostname:
                return bs
    return None


class Server(object):
    """Server representation.

    Server contains various attributes such as IP address, hostname, etc.,
    and methods to execute various functions on the Server.

    """

    def __init__(self, **kwargs):
        """Returns custom logger for module with assigned level."""

        self.ssh_conn = None
        self.server_ip = None
        self.prompt = None
        self.name = None

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def __str__(self):
        return str(vars(self))
