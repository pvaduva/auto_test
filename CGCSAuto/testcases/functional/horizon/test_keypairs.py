from pytest import fixture

from consts import horizon
from keywords import nova_helper
from utils.tis_log import LOG
from utils.horizon.regions import messages
from utils.horizon.pages.project.compute import keypairspage


KEYPAIR_NAME = 'test keypair'


@fixture(scope='function')
def keypairs_pg(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Compute > Key Pairs')
    keypairs_pg = keypairspage.KeypairsPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    keypairs_pg.go_to_target_page()
    keypairs_list = nova_helper.get_keypairs()
    if KEYPAIR_NAME in keypairs_list:
        keypairs_pg.delete_keypair(KEYPAIR_NAME)

    def teardown():
        LOG.fixture_step('Back to Key Pairs Page')
        keypairs_pg.go_to_target_page()

    request.addfinalizer(teardown)

    return keypairs_pg


def test_horizon_keypair(keypairs_pg):
    """
    Test the keypair creation/deletion functionality:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Key Pairs

    Teardown:
        - Back to Key Pairs page
        - Logout

    Test Steps:
        - Create a new key pair
        - Verify that the key pair is in the list
        - Delete the newly created key pair
        - Verify that the key pair is not in the list
    """

    LOG.tc_step('Create new key pair {} and verify it appears in the list'.format(KEYPAIR_NAME))
    keypairs_pg.create_keypair(KEYPAIR_NAME)
    assert keypairs_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not keypairs_pg.find_message_and_dismiss(messages.ERROR)
    assert keypairs_pg.is_keypair_present(KEYPAIR_NAME)

    LOG.tc_step('Delete key pair {} and verify it does not appear in the list'.format(KEYPAIR_NAME))
    keypairs_pg.delete_keypair(KEYPAIR_NAME)
    assert keypairs_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not keypairs_pg.find_message_and_dismiss(messages.ERROR)
    assert not keypairs_pg.is_keypair_present(KEYPAIR_NAME)
    horizon.test_result = True
