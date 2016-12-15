from contextlib import contextmanager

from utils import exceptions
from utils.ssh import SSHClient

from consts.build_server import DEFAULT_BUILD_SERVER, BUILD_SERVERS
from consts.cgcs import Prompt
from consts.auth import SvcCgcsAuto


@contextmanager
def ssh_to_build_server(bld_srv=DEFAULT_BUILD_SERVER, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                        prompt=None):
    """
    ssh to given build server.
    Usage: Use with context_manager. i.e.,
        with ssh_to_build_server(bld_srv=cgts-yow3-lx) as bld_srv_ssh:
            # do something
        # ssh session will be closed automatically

    Args:
        bld_srv (str|dict): build server ip, name or dictionary (choose from consts.build_serve.BUILD_SERVERS)
        user (str): svc-cgcsauto if unspecified
        password (str): password for svc-cgcsauto user if unspecified
        prompt (str|None): expected prompt. such as: svc-cgcsauto@yow-cgts4-lx.wrs.com$

    Yields (SSHClient): ssh client for given build server and user

    """
    # Get build_server dict from bld_srv param.
    if isinstance(bld_srv, str):
        for bs in BUILD_SERVERS:
            if bs['name'] in bld_srv or bs['ip'] == bld_srv:
                bld_srv = bs
                break
        else:
            raise exceptions.BuildServerError("Requested build server - {} is not found. Choose server ip or "
                                              "server name from: {}".format(bld_srv, BUILD_SERVERS))
    elif bld_srv not in BUILD_SERVERS:
        raise exceptions.BuildServerError("Unknown build server: {}. Choose from: {}".format(bld_srv, BUILD_SERVERS))

    prompt = prompt if prompt else Prompt.BUILD_SERVER_PROMPT_BASE.format(user, bld_srv['name'])
    bld_server_conn = SSHClient(bld_srv['ip'], user=user, password=password, initial_prompt=prompt)
    bld_server_conn.connect()

    try:
        yield bld_server_conn
    finally:
        bld_server_conn.close()

