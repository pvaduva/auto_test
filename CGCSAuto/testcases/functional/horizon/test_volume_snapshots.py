import time

from pytest import fixture

from consts import horizon
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.project.volumes import volumespage


@fixture(scope='function')
def volumes_pg(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Compute > Volumes page')
    volume_name = helper.gen_resource_name('volume')
    volume_snapshot_name = helper.gen_resource_name('snapshot')
    volumes_pg = volumespage.VolumesPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    volumes_pg.go_to_target_page()

    LOG.fixture_step('Create new volume {}'.format(volume_name))
    volumes_pg.create_volume(volume_name)
    assert volumes_pg.is_volume_status(volume_name, 'Available')

    def teardown():
        LOG.fixture_step('Back to Volumes page')
        volumes_pg.go_to_target_page()

        LOG.fixture_step('Delete volume {}'.format(volume_name))
        volumes_pg.delete_volume(volume_name)
        assert volumes_pg.is_volume_deleted(volume_name)

    request.addfinalizer(teardown)

    return volumes_pg, volume_name, volume_snapshot_name


def test_horizon_create_edit_delete_volume_snapshot(volumes_pg):
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
    volumes_pg, volume_name, volume_snapshot_name = volumes_pg

    LOG.tc_step('Create snapshot {}'.format(volume_snapshot_name))
    volumes_snapshot_pg = volumes_pg.create_volume_snapshot(
        volume_name, volume_snapshot_name)
    assert volumes_pg.find_message_and_dismiss(messages.INFO)
    assert not volumes_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Check that snapshot is in the list and has reference to correct volume')
    assert volumes_snapshot_pg.is_volume_snapshot_available(volume_snapshot_name)
    actual_volume_name = volumes_snapshot_pg.get_snapshot_info(
        volume_snapshot_name, "Volume Name")
    assert volume_name == actual_volume_name

    LOG.tc_step('Edit snapshot name and description')
    new_name = "new_" + volume_snapshot_name
    volumes_snapshot_pg.edit_snapshot(volume_snapshot_name, new_name, "description")
    assert volumes_snapshot_pg.find_message_and_dismiss(messages.INFO)
    assert not volumes_snapshot_pg.find_message_and_dismiss(messages.ERROR)
    assert volumes_snapshot_pg.is_volume_snapshot_available(new_name)

    LOG.tc_step('Delete snapshot {}'.format(volume_snapshot_name))
    volumes_snapshot_pg.delete_volume_snapshot_by_row(new_name)
    assert volumes_snapshot_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volumes_snapshot_pg.find_message_and_dismiss(messages.ERROR)
    assert volumes_snapshot_pg.is_volume_snapshot_deleted(
        new_name)
    horizon.test_result = True


def test_horizon_create_volume_from_snapshot(volumes_pg):
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
    volumes_pg, volume_name, volume_snapshot_name = volumes_pg

    LOG.tc_step('Create new snapshot {}'.format(volume_snapshot_name))
    volumes_snapshot_pg = volumes_pg.create_volume_snapshot(
        volume_name, volume_snapshot_name)
    assert volumes_pg.find_message_and_dismiss(messages.INFO)
    assert not volumes_pg.find_message_and_dismiss(messages.ERROR)
    assert volumes_snapshot_pg.is_volume_snapshot_available(volume_snapshot_name)

    new_volume = 'new_' + volume_name
    LOG.tc_step('Create new volume {} from snapshot'.format(new_volume))
    volumes_snapshot_pg.create_volume_from_snapshot(
        volume_snapshot_name, volume_name=new_volume)

    LOG.tc_step('Check the volume is created and has Available status')
    assert volumes_pg.is_volume_status(new_volume, 'Available')

    volumes_snapshot_pg.go_to_target_page()
    time.sleep(1)

    LOG.tc_step('Delete the volume snapshot {}'.format(volume_snapshot_name))
    volumes_snapshot_pg.delete_volume_snapshot_by_row(volume_snapshot_name)
    assert volumes_snapshot_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not volumes_snapshot_pg.find_message_and_dismiss(messages.ERROR)
    assert volumes_snapshot_pg.is_volume_snapshot_deleted(
        volume_snapshot_name)

    LOG.tc_step('Delete volume {}'.format(new_volume))
    volumes_pg.go_to_target_page()
    volumes_pg.delete_volume(new_volume)
    assert volumes_pg.is_volume_deleted(new_volume)
    horizon.test_result = True
