import json
import requests
import copy

from pytest import fixture, mark, skip
from consts.auth import Tenant
from utils import table_parser, cli
from utils.tis_log import LOG
from consts.proj_vars import ProjVar


def get_ip_addr():
    return ProjVar.get_var('lab')['floating ip']


def create_url(ip, port, version, extension):
    url = 'http://'
    if ip:
        url += ip
    else:
        url += get_ip_addr()

    if port:
        url += ':{}'.format(port)

    if version:
        url += '/{}'.format(version)

    if extension:
        url += '/{}'.format(extension)

    return url


def get_user_token(con_ssh=None):
    """
    Return an authentication token for the admin.

    Args:
        con_ssh (SSHClient):

    Returns (list): a list containing at most one authentication token

    """
    table_ = table_parser.table(cli.openstack('token issue', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_values(table_, 'Value', Field='id')


def get_request(url, headers):
    resp = requests.get(url, headers=headers)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def post_request(url, data, headers):
    if not isinstance(data, str):
        data = json.dumps(data)
    resp = requests.post(url, headers=headers, data=data)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def put_request(url, data, headers):
    if not isinstance(data, str):
        data = json.dumps(data)
    resp = requests.put(url, headers=headers, data=data)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def delete_request(url, headers):
    resp = requests.delete(url, headers=headers)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def patch_request(url, data, headers):
    if not isinstance(data, str):
        data = json.dumps(data)
    resp = requests.patch(url, headers=headers, data=data)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None