from pytest import fixture

from consts import horizon
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.admin.volume import volumetypespage


@fixture(scope='function')
def volume_types_pg(admin_home_pg_container, request):
    LOG.fixture_step('Go to Admin > Volume > Volume Types page')
    volume_type_name = helper.gen_resource_name('volume_type')
    qos_spec_name = helper.gen_resource_name('qos_spec')
    volume_types_pg = volumetypespage.VolumetypesPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    volume_types_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Volume Types page')
        volume_types_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return volume_types_pg, volume_type_name, qos_spec_name


@fixture(scope='function')
def volume_qos_spec_action(volume_types_pg, request):
    volume_types_pg, volume_type_name, qos_spec_name = volume_types_pg
    
    LOG.fixture_step('Create new Qos Spec {}'.format(qos_spec_name))
    _create_qos_spec(volume_types_pg, qos_spec_name)

    def teardown():
        LOG.fixture_step('Delete Qos Spec {}'.format(qos_spec_name))
        _delete_qos_spec(volume_types_pg, qos_spec_name)

    request.addfinalizer(teardown)
    return volume_types_pg, volume_type_name, qos_spec_name


def _create_volume_type(volume_types_pg, volume_type_name):
    volume_types_pg.create_volume_type(volume_type_name)
    assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
    assert volume_types_pg.is_volume_type_present(volume_type_name)


def _delete_volume_type(volume_types_pg, volume_type_name):
    volume_types_pg.delete_volume_type(volume_type_name)
    assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
    assert not volume_types_pg.is_volume_type_present(volume_type_name)


def test_horizon_volume_type_create_delete(volume_types_pg):
    """
    Test the create, delete volume type:

    Setups:
        - Login as Tenant
        - Go to Admin > Volume > Volume Types page

    Teardown:
        - Back to Volume Types page
        - Logout

    Test Steps:
        - Create a new volume type
        - Check that the volume type is in the list
        - Delete the volume type
        - Check that the volume type is absent in the list
    """
    volume_types_pg, volume_type_name, qos_spec_name = volume_types_pg
    
    LOG.tc_step('Create new volume type {} and Check that the volume type is in the list'
                .format(volume_type_name))
    _create_volume_type(volume_types_pg, volume_type_name)

    LOG.tc_step('Delete the volume type {} and Check that the volume type is absent in the list'
                .format(volume_type_name))
    _delete_volume_type(volume_types_pg, volume_type_name)
    horizon.test_result = True


def _create_qos_spec(volume_types_pg, qos_spec_name):
    volume_types_pg.create_qos_spec(qos_spec_name)
    assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
    assert volume_types_pg.is_qos_spec_present(qos_spec_name)


def _delete_qos_spec(volume_types_pg, qos_spec_name):
    volume_types_pg.delete_qos_spec(qos_spec_name)
    assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
    assert not volume_types_pg.is_qos_spec_present(qos_spec_name)
    

def test_horizon_qos_spec_create_delete(volume_types_pg):
    """
    Test the QoS Spec creation and deletion functionality:

    Setups:
        - Login as Tenant
        - Go to Admin > Volume > Volume Types page

    Teardown:
        - Back to Volume Types page
        - Logout

    Test Steps:
        - Create a new QoS Spec
        - Verify the QoS Spec appears in the QoS Specs table
        - Delete the newly created QoS Spec
        - Verify the QoS Spec does not appear in the table after deletion
    """

    volume_types_pg, volume_type_name, qos_spec_name = volume_types_pg

    LOG.tc_step('Create new QoS Spec {} and Verify the QoS Spec appears in the QoS Specs table'
                .format(qos_spec_name))
    _create_qos_spec(volume_types_pg, qos_spec_name)

    LOG.tc_step('Delete QoS Spec {} and Verify the QoS Spec does not appear in the table after deletion'
                .format(qos_spec_name))
    _delete_qos_spec(volume_types_pg, qos_spec_name)
    horizon.test_result = True


def test_horizon_qos_spec_edit_consumer(volume_qos_spec_action):
    """
    Test the QoS Spec creation and deletion functionality:

    Setups:
        - Login as Tenant
        - Go to Admin > Volume > Volume Types page
        - Create a new Qos Spec

    Teardown:
        - Delete the newly created Qos Spec
        - Back to Volume Types page
        - Logout

    Test Steps:
        - Edit consumer of created QoS Spec (check all options - front-end, both, back-end)
        - Verify current consumer of the QoS Spec in the QoS Specs table
    """
    volume_types_pg, volume_type_name, qos_spec_name = volume_qos_spec_action
    nova_compute_consumer = 'front-end'
    both_consumers = 'both'
    cinder_consumer = 'back-end'

    LOG.tc_step('Edit consumer of created QoS Spec to {}'.format(nova_compute_consumer))
    volume_types_pg.edit_consumer(qos_spec_name, nova_compute_consumer)
    assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
    LOG.tc_step('Verify current consumer of the QoS Spec in the QoS Specs table')
    assert volume_types_pg.get_qos_spec_info(qos_spec_name, 'Consumer') == nova_compute_consumer

    LOG.tc_step('Edit consumer of created QoS Spec to {}'.format(both_consumers))
    volume_types_pg.edit_consumer(qos_spec_name, both_consumers)
    assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
    LOG.tc_step('Verify current consumer of the QoS Spec in the QoS Specs table')
    assert volume_types_pg.get_qos_spec_info(qos_spec_name, 'Consumer') == both_consumers

    LOG.tc_step('Edit consumer of created QoS Spec to {}'.format(cinder_consumer))
    volume_types_pg.edit_consumer(qos_spec_name, cinder_consumer)
    assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
    LOG.tc_step('Verify current consumer of the QoS Spec in the QoS Specs table')
    assert volume_types_pg.get_qos_spec_info(qos_spec_name, 'Consumer') == cinder_consumer
    horizon.test_result = True
