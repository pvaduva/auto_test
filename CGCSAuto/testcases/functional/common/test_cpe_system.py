from pytest import mark

from utils import table_parser
from utils.tis_log import LOG
from keywords import system_helper, nova_helper


@mark.cpe_sanity
def test_cpe_services_and_functions():

    LOG.tc_step("Check controller+compute subfunction via system host-show")
    for controller in ['controller-0', 'controller-1']:
        assert system_helper.is_small_footprint(controller=controller), \
            "{} does not have controller+compute subfunction in system host-show".format(controller)

    LOG.tc_step("Check CPE system services via nova service-list")
    check_params = ["nova-scheduler",
                    "nova-cert",
                    "nova-conductor",
                    "nova-consoleauth",
                    "nova-scheduler",
                    "nova-compute"]

    services_tab = nova_helper.get_nova_services_table()
    binaries = table_parser.get_column(services_tab, 'Binary')
    assert set(check_params) <= set(binaries), "Not all binaries from {} exist in nova service-list".format(check_params)

