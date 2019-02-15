import json
import urlparse

import requests

import ims.common.constants as constants
import ims.exception.hil_exceptions as hil_exceptions
from ims.common.log import create_logger, trace, log

logger = create_logger(__name__)


class HIL:
    class Request:
        def __init__(self, method, data, auth=None):
            self.method = method
            self.data = json.dumps(data)
            self.auth = None
            if auth:
                self.auth = auth

        def __str__(self):
            return str(
                {"method": str(self.method), "data": self.data,
                 "auth": self.auth})

    class Communicator:
        @trace
        def __init__(self, url, request):
            self.url = url
            self.request = request

        @trace
        def send_request(self):
            try:
                if self.request.method == "get":
                    return self.resp_parse(
                        requests.get(self.url, auth=self.request.auth))
                if self.request.method == "post":
                    return self.resp_parse(
                        requests.post(self.url, data=self.request.data,
                                      auth=self.request.auth))
            except requests.RequestException:
                raise hil_exceptions.ConnectionException()

        @trace
        def resp_parse(self, obj):
            if obj.status_code == 200:
                try:
                    return {constants.STATUS_CODE_KEY: obj.status_code,
                            constants.RETURN_VALUE_KEY: obj.json()}
                except ValueError:
                    return {constants.STATUS_CODE_KEY: obj.status_code}
            elif obj.status_code > 200 and obj.status_code < 400:
                return {constants.STATUS_CODE_KEY: obj.status_code}
            elif obj.status_code == 401:
                raise hil_exceptions.AuthenticationFailedException()
            elif obj.status_code == 403:
                raise hil_exceptions.AuthorizationFailedException()
            elif obj.status_code >= 400:
                # For PEP8
                error_msg = obj.json()[constants.MESSAGE_KEY]
                raise hil_exceptions.UnknownException(obj.status_code,
                                                      error_msg)

    @log
    def __init__(self, base_url, usr, passwd):
        self.base_url = base_url
        self.usr = usr
        self.passwd = passwd

    @trace
    def __call_rest_api(self, api):
        link = self.base_url + api
        request = HIL.Request('get', None, auth=(self.usr, self.passwd))
        return HIL.Communicator(link, request).send_request()

    @trace
    def __call_rest_api_with_body(self, api, body):
        link = self.base_url + api
        request = HIL.Request('post', body, auth=(self.usr, self.passwd))
        return HIL.Communicator(link, request).send_request()

    @log
    def list_free_nodes(self):
        api = 'free_nodes'
        return self.__call_rest_api(api=api)

    @log
    def query_project_nodes(self, project):
        api = '/project/' + project + '/nodes'
        return self.__call_rest_api(api=api)

    @log
    def detach_node_from_project(self, project, node):
        api = 'project/' + project + '/detach_node'
        body = {"node": node}
        return self.__call_rest_api_with_body(api=api, body=body)

    @log
    def attach_node_hil_project(self, project, node):
        api = 'project/' + project + '/connect_node'
        body = {"node": node}
        return self.__call_rest_api_with_body(api=api, body=body)

    @log
    def get_node_mac_addr(self, node, nic_to_boot_from):
        api = "node/" + node
        node_info = self.__call_rest_api(api)
        logger.debug("The Node Info = %s", node_info)
        for nic in node_info[constants.RETURN_VALUE_KEY]['nics']:
            if nic['label'] == nic_to_boot_from:
                return nic['macaddr']
        raise hil_exceptions.UnknownException(404, 'Nic does not exist')

    @log
    def validate_project(self, project):
        api = '/project/' + project + '/nodes'
        return self.__call_rest_api(api=api)
