import pytest

from utils.tis_log import LOG
from utils.rest import Rest

from testfixtures.pre_checks_and_configs import stx_openstack_required
from testcases.rest import rest_test_helper


@pytest.fixture(scope='module')
def gnocchi_rest(stx_openstack_required):
    r = Rest('gnocchi', platform=False)
    return r


@pytest.mark.parametrize(('operation', 'resource'), [
    ('GET', '/v1/metric?limit=2'),
    ('GET', '/v1/resource'),
    ('GET', '/v1/resource_type'),
    ('GET', '/')
])
def test_rest_gnocchi(gnocchi_rest, operation, resource):
    if operation == "GET":
        LOG.info("getting... {}".format(resource))
        rest_test_helper.get(gnocchi_rest, resource=resource)
