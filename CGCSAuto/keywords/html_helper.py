import json
import requests

from consts.auth import Tenant
from utils import table_parser, cli
from utils.tis_log import LOG
from consts.proj_vars import ProjVar


def get_ip_addr():
    return ProjVar.get_var('lab')['floating ip']


def create_url(ip=None, port=None, version=None, extension=None):
    """
    Creates a url with the given parameters inn the form:
    http://<ip address>:<port>/<version>/<extension>
    Args:
        ip (str): the main ip address. If set to None will be set to the lab's ip address by default.
        port (int): the port number to connect to.
        version (str): for REST API. version number, e.g. "v1", "v2.0"
        extension (str): extensions to add to the url

    Returns (str): a url created with the given parameters

    """
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


def get_user_token(rtn_value='id', con_ssh=None):
    """
    Return an authentication token for the admin.

    Args:
        rtn_value (str):
        con_ssh (SSHClient):

    Returns (list): a list containing at most one authentication token

    """
    table_ = table_parser.table(cli.openstack('token issue', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    token = table_parser.get_value_two_col_table(table_, rtn_value)
    return token


def get_request(url, headers):
    """
    Sends a GET request to the url
    Args:
        url (str): url to send request to
        headers (dict): header to add to the request

    Returns (dict): The response for the request

    """
    LOG.info("Sending GET request to {}. Headers: {}".format(url, headers))
    resp = requests.get(url, headers=headers)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def post_request(url, data, headers):
    """
        Sends a POST request to the url
        Args:
            url (str): url to send request to
            data (dict): data to be sent in the request body
            headers (dict): header to add to the request

        Returns (dict): The response for the request

        """
    if not isinstance(data, str):
        data = json.dumps(data)
    LOG.info("Sending POST request to {}. Headers: {}. Data: {}".format(url, headers, data))
    resp = requests.post(url, headers=headers, data=data)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def put_request(url, data, headers):
    """
        Sends a GET request to the url
        Args:
            url (str): url to send request to
            data (dict): data to be sent in the request body
            headers (dict): header to add to the request

        Returns (dict): The response for the request

        """
    if not isinstance(data, str):
        data = json.dumps(data)
    LOG.info("Sending PUT request to {}. Headers: {}. Data: {}".format(url, headers, data))
    resp = requests.put(url, headers=headers, data=data)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def delete_request(url, headers):
    """
        Sends a GET request to the url
        Args:
            url (str): url to send request to
            headers (dict): header to add to the request

        Returns (dict): The response for the request

        """
    LOG.info("Sending DELETE request to {}. Headers: {}".format(url, headers))
    resp = requests.delete(url, headers=headers)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None


def patch_request(url, data, headers):
    """
        Sends a PATCH request to the url
        Args:
            url (str): url to send request to
            data (dict): data to be sent in the request body
            headers (dict): header to add to the request

        Returns (dict): The response for the request

        """
    if not isinstance(data, str):
        data = json.dumps(data)
    LOG.info("Sending PATCH request to {}. Headers: {}. Data: {}".format(url, headers, data))
    resp = requests.patch(url, headers=headers, data=data)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data

    LOG.info("Error {}".format(resp.status_code))
    return None