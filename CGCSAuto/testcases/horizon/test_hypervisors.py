from utils.horizon.regions import messages
from utils.horizon.pages.admin.compute import hypervisorspage
from pytest import fixture, mark
from utils.horizon import helper
from utils.tis_log import LOG


class TestHypervisors(helper.AdminTestCase):

    @fixture(scope='function')
    def hypervisors_pg(self, home_pg, request):
        LOG.fixture_step('Go to Admin > Compute > Hypervisors')
        hypervisors_pg = hypervisorspage.HypervisorsPage(home_pg.driver)
        hypervisors_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Hypervisors page')
            hypervisors_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return hypervisors_pg

    @mark.parametrize('host_name', [
        'controller-0'
    ])
    def test_compute_host_disable_service_negative(self, hypervisors_pg, host_name):

        hypervisors_pg.go_to_compute_host_tab()

        LOG.tc_step('Disable service of the host {}'.format(host_name))
        hypervisors_pg.disable_service(host_name)

        LOG.tc_step('Verify there is error message'.format(host_name))
        assert hypervisors_pg.find_message_and_dismiss(messages.ERROR)
