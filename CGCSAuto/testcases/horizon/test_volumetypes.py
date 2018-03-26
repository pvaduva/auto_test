from utils.horizon.regions import messages
from utils.horizon.pages.admin.volume import volumetypespage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG


class TestVolumeTypes(helper.AdminTestCase):
    VOLUME_TYPE_NAME = None
    QOS_SPEC_NAME = None

    @fixture(scope='function')
    def volume_types_pg(self, home_pg, request):
        LOG.fixture_step('Go to Admin > Volume > Volume Types page')
        self.VOLUME_TYPE_NAME = helper.gen_resource_name('volume_type')
        self.QOS_SPEC_NAME = helper.gen_resource_name('qos_spec')
        volume_types_pg = volumetypespage.VolumetypesPage(home_pg.driver)
        volume_types_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Volume Types page')
            volume_types_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return volume_types_pg

    @fixture(scope='function')
    def volume_qos_spec_action(self, volume_types_pg, request):
        LOG.fixture_step('Create new Qos Spec {}'.format(self.QOS_SPEC_NAME))
        self._create_qos_spec(volume_types_pg, self.QOS_SPEC_NAME)

        def teardown():
            LOG.fixture_step('Delete Qos Spec {}'.format(self.QOS_SPEC_NAME))
            self._delete_qos_spec(volume_types_pg, self.QOS_SPEC_NAME)

        request.addfinalizer(teardown)
        return volume_types_pg

    def _create_volume_type(self, volume_types_pg, volume_type_name):
        volume_types_pg.create_volume_type(volume_type_name)
        assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
        assert volume_types_pg.is_volume_type_present(volume_type_name)

    def _delete_volume_type(self, volume_types_pg, volume_type_name):
        volume_types_pg.delete_volume_type(volume_type_name)
        assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
        assert volume_types_pg.is_volume_type_deleted(volume_type_name)

    def test_volume_type_create_delete(self, volume_types_pg):
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
        LOG.tc_step('Create new volume type {} and Check that the volume type is in the list'
                    .format(self.VOLUME_TYPE_NAME))
        self._create_volume_type(volume_types_pg, self.VOLUME_TYPE_NAME)

        LOG.tc_step('Delete the volume type {} and Check that the volume type is absent in the list'
                    .format(self.VOLUME_TYPE_NAME))
        self._delete_volume_type(volume_types_pg, self.VOLUME_TYPE_NAME)

    def _create_qos_spec(self, volume_types_pg, qos_spec_name):
        volume_types_pg.create_qos_spec(qos_spec_name)
        assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
        assert volume_types_pg.is_qos_spec_present(qos_spec_name)

    def _delete_qos_spec(self, volume_types_pg, qos_spec_name):
        volume_types_pg.delete_qos_specs(qos_spec_name)
        assert volume_types_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not volume_types_pg.find_message_and_dismiss(messages.ERROR)
        assert not volume_types_pg.is_qos_spec_present(qos_spec_name)

    def test_qos_spec_create_delete(self, volume_types_pg):
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

        LOG.tc_step('Create new QoS Spec {} and Verify the QoS Spec appears in the QoS Specs table'
                    .format(self.QOS_SPEC_NAME))
        self._create_qos_spec(volume_types_pg, self.QOS_SPEC_NAME)

        LOG.tc_step('Delete QoS Spec {} and Verify the QoS Spec does not appear in the table after deletion'
                    .format(self.QOS_SPEC_NAME))
        self._delete_qos_spec(volume_types_pg, self.QOS_SPEC_NAME)

    def test_qos_spec_edit_consumer(self, volume_qos_spec_action):
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

        qos_spec_name = self.QOS_SPEC_NAME
        nova_compute_consumer = 'front-end'
        both_consumers = 'both'
        cinder_consumer = 'back-end'

        LOG.tc_step('Edit consumer of created QoS Spec to {}'.format(nova_compute_consumer))
        volume_qos_spec_action.edit_consumer(qos_spec_name, nova_compute_consumer)
        assert volume_qos_spec_action.find_message_and_dismiss(messages.SUCCESS)
        assert not volume_qos_spec_action.find_message_and_dismiss(messages.ERROR)
        LOG.tc_step('Verify current consumer of the QoS Spec in the QoS Specs table')
        assert volume_qos_spec_action.get_consumer(qos_spec_name) == nova_compute_consumer

        LOG.tc_step('Edit consumer of created QoS Spec to {}'.format(both_consumers))
        volume_qos_spec_action.edit_consumer(qos_spec_name, both_consumers)
        assert volume_qos_spec_action.find_message_and_dismiss(messages.SUCCESS)
        assert not volume_qos_spec_action.find_message_and_dismiss(messages.ERROR)
        LOG.tc_step('Verify current consumer of the QoS Spec in the QoS Specs table')
        assert volume_qos_spec_action.get_consumer(qos_spec_name) == both_consumers

        LOG.tc_step('Edit consumer of created QoS Spec to {}'.format(cinder_consumer))
        volume_qos_spec_action.edit_consumer(qos_spec_name, cinder_consumer)
        assert volume_qos_spec_action.find_message_and_dismiss(messages.SUCCESS)
        assert not volume_qos_spec_action.find_message_and_dismiss(messages.ERROR)
        LOG.tc_step('Verify current consumer of the QoS Spec in the QoS Specs table')
        assert volume_qos_spec_action.get_consumer(qos_spec_name) == cinder_consumer

