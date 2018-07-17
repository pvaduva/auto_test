from pytest import fixture, mark

from utils.tis_log import LOG
from keywords import vm_helper, network_helper, nova_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup

def test_service_function_chaining():
    """
        SFC flow classifier

        Test Steps:
            - Create two ports


        Test Teardown:
            - Delete vms, volumes created

    """

    providernets = network_helper.get_providernets(rtn_val='name', strict=True, type='vxlan')
    LOG.info("Providernets {}".format(providernets))
