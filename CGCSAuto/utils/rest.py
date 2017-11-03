import requests
import json
import re
from keywords import keystone_helper

from utils.tis_log import LOG
from utils.kpi import KPI


class Rest:
    """
        Base rest Class that uses requests and KPI class

        Supports;
            Basic REST invocations with requests
            generate_token_request   generates generic token request
            retrieve_token           actually receive token
            auth_header_select       utility function to switch auth.
            get                      perform HTTP GET
            delete                   perform HTTP DELETE
            patch                    perform HTTP PATCH
            put                      perform HTTP PUT
            post                     perform HTTP POST
    """
    def __init__(self, serviceName):
        """
        Initiate an object for handling REST calls.
        Args:
            serviceName - 

        """
        self.token = ""
        self.token_payload = ""

        self.baseURL = keystone_helper.get_endpoints(
            rtn_val='URL',
            service_name=serviceName,
            interface="public")[0]
        self.ksURL = keystone_helper.get_endpoints(
            rtn_val='URL',
            service_name='keystone',
            interface="public")[0]
        self.generate_token_request()
        self.retrieve_token('/auth/tokens')

    def generate_token_request(self, **kwargs):
        json_string = ('{"auth":'
                       '{"identity":{"methods": ["password"],'
                       '"password": {"user": {"domain":'
                       '{"name": "Default"},"name":'
                       '"admin","password":"Li69nux*"}}}}}')
        self.token_payload = json.loads(json_string)

    def retrieve_token(self, endpoint, token_request=None):
        if token_request is None:
            token_request = json.dumps(self.token_payload)
        headers = {'Content-type': 'application/json'}
        r = requests.post(self.ksURL+endpoint,
                          headers=headers,
                          data=token_request, verify=True)
        if r.status_code != 201:
            self.token = "THISTOKENDOESNOTEXIST"
        else:
            self.token = r.headers['X-Subject-Token']
        return(r.status_code, r.text)

    def auth_header_select(self, auth=True):
        if auth:
            headers = {'X-Auth-Token': self.token}
        else:
            headers = {'X-Auth-Token': "THISISNOTAVALIDTOKEN"}
        return(headers)

    def get(self, resource="", auth=True):
        headers = self.auth_header_select(auth)
        message = "baseURL: {} resource: {} headers: {}"
        LOG.info(message.format(self.baseURL, resource, headers))
        kpi = KPI()
        r = requests.get(self.baseURL + resource,
                         headers=headers, verify=True)
        delta = kpi.stop()
        return(r.status_code, r.json())

    def delete(self, resource="", auth=True):
        headers = self.auth_header_select(auth)
        message = "baseURL: {} resource: {} headers: {}"
        LOG.debug(message.format(self.baseURL, resource, headers))
        kpi = KPI()
        r = requests.delete(self.baseURL + resource,
                            headers=headers, verify=True)
        delta = kpi.stop()
        return(r.status_code, r.json())

    def patch(self, resource="", json_data={}, auth=True):
        headers = self.auth_header_select(auth)
        message = "baseURL: {} resource: {} headers: {} data: {}"
        LOG.debug(message.format(self.baseURL, resource,
                                headers, json_data))
        kpi = KPI()
        r = requests.patch(self.baseURL + resource,
                           headers=headers, data=json_data,
                           verify=True)
        delta = kpi.stop()
        return(r.status_code, r.json())

    def put(self, resource="", json_data={}, auth=True):
        headers = self.auth_header_select(auth)
        message = "baseURL: {} resource: {} headers: {} data: {}"
        LOG.debug(message.format(self.baseURL, resource,
                                headers, json_data))
        kpi = KPI()
        r = requests.put(self.baseURL + resource, 
                         headers=headers, data=json_data,
                         verify=True)
        kpi.stop()
        return(r.status_code, r.json())

    def post(self, resource="", json_data={}, auth=True):
        headers = self.auth_header_select(auth)
        message = "baseURL: {} resource: {} headers: {} data: {}"
        LOG.debug(message.format(self.baseURL, resource,
                                headers, json_data))
        kpi = KPI()
        r = requests.post(self.baseURL + resource,
                          headers=headers, data=json_data,
                          verify=True)
        kpi.stop()
        return(r.status_code, r.json())
