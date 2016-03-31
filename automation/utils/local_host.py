import socket
import getpass


def get_host_name():
    return socket.gethostname()


def get_host_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]


def get_user():
    return getpass.getuser()
