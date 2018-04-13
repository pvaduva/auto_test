from utils.horizon.regions import messages
from utils.horizon.pages.project.volumes import volumespage
from time import sleep
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG
from testfixtures.horizon import tenant_home_pg, driver


class TestVolumeSnapshots:

    VOLUME_NAME = None
    VOLUME_SNAPSHOT_NAME = None

    @fixture(scope='function')
    def volumes_pg(self, tenant_home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Volumes page')
        self.VOLUME_NAME = helper.gen_resource_name('volume')
        self.VOLUME_SNAPSHOT_NAME = helper.gen_resource_name('snapshot')
        volumes_pg = volumespage.VolumesPage(tenant_home_pg.driver)
        volumes_pg.go_to_target_page()
        LOG.fixture_step('Create new volume {}'.format(self.VOLUME_NAME))
        self._create_volume(volumes_pg)

        def teardown():
            LOG.fixture_step('Back to Volumes page')
            volumes_pg.go_to_target_page()
            LOG.fixture_step('Delete volume {}'.format(self.VOLUME_NAME))
            self._delete_volume(volumes_pg)

        request.addfinalizer(teardown)

        return volumes_pg

    def _create_volume(self, volumespage):
        volumespage.create_volume(self.VOLUME_NAME)
        assert volumespage.find_message_and_dismiss(messages.INFO)
        assert not volumespage.find_message_and_dismiss(messages.ERROR)
        assert volumespage.is_volume_status(self.VOLUME_NAME, 'Available')

    def _delete_volume(self, volumespage):
        volumespage.delete_volume(self.VOLUME_NAME)
        assert volumespage.find_message_and_dismiss(messages.SUCCESS)
        assert not volumespage.find_message_and_dismiss(messages.ERROR)
        assert volumespage.is_volume_deleted(self.VOLUME_NAME)

    def test_create_edit_delete_volume_snapshot(self, volumes_pg):
        """
        Test the create/delete volume snapshot action

        Setups:
            - Login as Tenant
            - Go to Project > Compute > Volumes page
            - Create a new volume

        Teardown:
            - Back to Volumes page
            - Delete the newly created volume
            - Logout

        Test Steps:
            - Create snapshot for existed volume
            - Check that snapshot is in the list and has reference to correct volume
            - Edit snapshot name and description
            - Delete the volume snapshot
            - Verify the snapshot does not appear in the list after deletion
        """
        LOG.tc_step('Create snapshot {}'.format(self.VOLUME_SNAPSHOT_NAME))
        volumes_snapshot_pg = volumes_pg.create_volume_snapshot(
            self.VOLUME_NAME, self.VOLUME_SNAPSHOT_NAME)
        assert volumes_pg.find_message_and_dismiss(messages.INFO)
        assert not volumes_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Check that snapshot is in the list and has reference to correct volume')
        assert volumes_snapshot_pg.is_volume_snapshot_available(self.VOLUME_SNAPSHOT_NAME)
        actual_volume_name = volumes_snapshot_pg.get_snapshot_info(
            self.VOLUME_SNAPSHOT_NAME, "Volume Name")
        assert self.VOLUME_NAME == actual_volume_name

        LOG.tc_step('Edit snapshot name and description')
        new_name = "new_" + self.VOLUME_SNAPSHOT_NAME
        volumes_snapshot_pg.edit_snapshot(self.VOLUME_SNAPSHOT_NAME, new_name, "description")
        assert volumes_snapshot_pg.find_message_and_dismiss(messages.INFO)
        assert not volumes_snapshot_pg.find_message_and_dismiss(messages.ERROR)
        assert volumes_snapshot_pg.is_volume_snapshot_available(new_name)

        LOG.tc_step('Delete snapshot {}'.format(self.VOLUME_SNAPSHOT_NAME))
        volumes_snapshot_pg.delete_volume_snapshot_by_row(new_name)
        assert volumes_snapshot_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not volumes_snapshot_pg.find_message_and_dismiss(messages.ERROR)
        assert volumes_snapshot_pg.is_volume_snapshot_deleted(
            new_name)

    def test_create_volume_from_snapshot(self, volumes_pg):
        """
        Test the create volume from snapshot action

        Setups:
            - Login as Tenant
            - Go to Project > Compute > Volumes page
            - Create a new volume

        Teardown:
            - Back to Volumes page
            - Delete the volume created at first
            - Logout

        Test Steps:
            - Create snapshot for existed volume
            - Create new volume from snapshot
            - Check the volume is created and has 'Available' status
            - Delete the volume snapshot
            - Delete the volume from snapshot
        """

        LOG.tc_step('Create new snapshot {}'.format(self.VOLUME_SNAPSHOT_NAME))
        volumes_snapshot_pg = volumes_pg.create_volume_snapshot(
            self.VOLUME_NAME, self.VOLUME_SNAPSHOT_NAME)
        assert volumes_pg.find_message_and_dismiss(messages.INFO)
        assert not volumes_pg.find_message_and_dismiss(messages.ERROR)
        assert volumes_snapshot_pg.is_volume_snapshot_available(self.VOLUME_SNAPSHOT_NAME)

        new_volume = 'new_' + self.VOLUME_NAME
        LOG.tc_step('Create new volume {} from snapshot'.format(new_volume))
        volumes_snapshot_pg.create_volume_from_snapshot(
            self.VOLUME_SNAPSHOT_NAME, volume_name=new_volume)

        LOG.tc_step('Check the volume is created and has Available status')
        assert volumes_pg.is_volume_status(new_volume, 'Available')

        volumes_snapshot_pg.go_to_target_page()
        sleep(1)

        LOG.tc_step('Delete the volume snapshot {}'.format(self.VOLUME_SNAPSHOT_NAME))
        volumes_snapshot_pg.delete_volume_snapshot_by_row(self.VOLUME_SNAPSHOT_NAME)
        assert volumes_snapshot_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not volumes_snapshot_pg.find_message_and_dismiss(messages.ERROR)
        assert volumes_snapshot_pg.is_volume_snapshot_deleted(
            self.VOLUME_SNAPSHOT_NAME)

        LOG.tc_step('Delete volume {}'.format(new_volume))
        volumes_pg.go_to_target_page()
        volumes_pg.delete_volume(new_volume)
        assert volumes_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not volumes_pg.find_message_and_dismiss(messages.ERROR)
        assert volumes_pg.is_volume_deleted(new_volume)






