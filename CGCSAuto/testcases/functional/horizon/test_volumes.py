import time

from pytest import fixture, mark, raises

from consts import horizon
from consts.auth import Tenant
from consts.stx import GuestImages
from keywords import nova_helper
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.project.compute import imagespage, instancespage
from utils.horizon.pages.project.volumes import volumespage


@fixture(scope='function')
def volumes_pg(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Compute > Volumes page')
    volume_name = helper.gen_resource_name('volume')
    volumes_pg = volumespage.VolumesPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    volumes_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Volumes page')
        volumes_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return volumes_pg, volume_name


@fixture(scope='function')
def instances_pg(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Compute > Instances')
    volume_name = helper.gen_resource_name('volume')
    instances_pg = instancespage.InstancesPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    instances_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Instances page')
        instances_pg.go_to_target_page()

    request.addfinalizer(teardown)

    return instances_pg, volume_name


@mark.parametrize(('volume_source_type', 'source_name'), [
    (None, None),
    ('Image', 'tis-centos-guest')
])
def test_horizon_volume_create_delete(volumes_pg, volume_source_type, source_name):
    """
    Test the create, delete volume functionality:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Volumes page

    Teardown:
        - Back to Volumes page
        - Logout

    Test Steps:
        - Create new volume
        - Check that the volume is in the list and Available
        - Edit the volume
        - Check that the volum is edited successfully
        - Delete the volume
        - Check that the volume is absent in the list
    """
    volumes_pg, volume_name = volumes_pg
    LOG.tc_step('Create new volume {}, with source type {}'.format(volume_name, volume_source_type))
    volumes_pg.create_volume(
        volume_name=volume_name,
        volume_source_type=volume_source_type,
        source_name=source_name
    )

    LOG.tc_step('Check that the volume is in the list with Available')
    assert volumes_pg.is_volume_status(volume_name, 'Available')

    LOG.tc_step('Delete volume {}'.format(volume_name))
    volumes_pg.delete_volume(volume_name)

    LOG.tc_step('Check that the volume is absent in the list')
    assert volumes_pg.is_volume_deleted(volume_name)
    horizon.test_result = True


def test_horizon_manage_volume_attachments(instances_pg):
    """
    Test the attach/detach actions for volume:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Instances

    Teardown:
        - Back to Instances page
        - Logout

    Test Steps:
        - Create a new instance
        - Go to Project -> Compute -> Volumes, create volume
        - Attach the volume to the newly created instance
        - Check that volume is In-use and link to instance
        - Detach volume from instance
        - Check volume is Available
        - Delete the volume
        - Delete the instance
    """
    instances_pg, volume_name = instances_pg
    instance_name = helper.gen_resource_name('volume_attachment')

    LOG.tc_step('Create new instance {}'.format(instance_name))
    mgmt_net_name = '-'.join([Tenant.get_primary()['tenant'], 'mgmt', 'net'])
    flavor_name = nova_helper.get_basic_flavor(rtn_id=False)
    guest_img = GuestImages.DEFAULT['guest']
    instances_pg.create_instance(instance_name,
                                 boot_source_type='Image',
                                 create_new_volume=False,
                                 source_name=guest_img,
                                 flavor_name=flavor_name,
                                 network_names=[mgmt_net_name])
    assert not instances_pg.find_message_and_dismiss(messages.ERROR)
    assert instances_pg.is_instance_active(instance_name)

    LOG.tc_step('Go to Project -> Compute -> Volumes, create volume {}'.format(volume_name))
    volumes_pg = volumespage.VolumesPage(instances_pg.driver, instances_pg.port)
    volumes_pg.go_to_target_page()
    time.sleep(3)
    volumes_pg.create_volume(volume_name)
    assert (volumes_pg.is_volume_status(volume_name, 'Available'))

    LOG.tc_step('Attach the volume to the newly created instance')
    volumes_pg.attach_volume_to_instance(volume_name, instance_name)

    LOG.tc_step('Check that volume is In-use and link to instance')
    assert volumes_pg.is_volume_status(volume_name, 'In-use')
    assert instance_name in volumes_pg.get_volume_info(volume_name, 'Attached To')

    LOG.tc_step('Detach volume from instance')
    volumes_pg.detach_volume_from_instance(volume_name, instance_name)

    LOG.tc_step('Check volume is Available instead of In-use')
    assert volumes_pg.is_volume_status(volume_name, 'Available')

    LOG.tc_step('Delete the volume {}'.format(volume_name))
    volumes_pg.delete_volume(volume_name)
    assert volumes_pg.is_volume_deleted(volume_name)

    LOG.tc_step('Delete the instance {}'.format(instance_name))
    instances_pg.go_to_target_page()
    instances_pg.delete_instance(instance_name)
    instances_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not instances_pg.find_message_and_dismiss(messages.ERROR)
    assert instances_pg.is_instance_deleted(instance_name)
    horizon.test_result = True


@fixture(scope='function')
def volumes_pg_action(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Compute > Volumes page')
    volumes_pg = volumespage.VolumesPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    volumes_pg.go_to_target_page()
    volume_name = helper.gen_resource_name('volume')

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

    return volumes_pg, volume_name


def test_horizon_volume_edit(volumes_pg_action):
    """
    Test the edit volume functionality

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Volumes page
        - Create a new volume

    Teardown:
        - Back to Volumes page
        - Delete the newly created volume
        - Logout

    Test Steps:
        - Edit the volume Name, Description, Bootable
        - Check that the volume is edited successfully
    """
    LOG.tc_step('Edit the volume')
    volumes_pg, volume_name = volumes_pg_action
    new_name = "edited_" + volume_name
    volumes_pg.edit_volume(volume_name, new_name, "description", True)

    LOG.tc_step('Check that the volume is edited successfully')
    assert volumes_pg.is_volume_present(new_name)
    assert volumes_pg.is_volume_status(new_name, 'Available')
    assert volumes_pg.get_volume_info(new_name, 'Bootable') == 'Yes'

    volumes_pg.edit_volume(new_name, volume_name)
    horizon.test_result = True


def test_horizon_volume_extend(volumes_pg_action):
    """
    This test case checks extend volume functionality:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Instances
        - Create a new volume

    Teardown:
        - Back to Instances page
        - Delete the newly created volume
        - Logout

    Test Steps:
        - Extend volume
        - Check that the volume size is changed
    """
    volumes_pg, volume_name = volumes_pg_action
    LOG.tc_step('Extend volume')
    orig_size = int(volumes_pg.get_volume_info(volume_name, 'Size')[:-3])
    volumes_pg.extend_volume(volume_name, str(orig_size + 1))
    assert volumes_pg.is_volume_status(volume_name, 'Available')

    LOG.tc_step('Check that the volume size is changed')
    new_size = int(volumes_pg.get_volume_info(volume_name, 'Size')[:-3])
    assert orig_size < new_size
    horizon.test_result = True


def test_horizon_volume_upload_to_image(volumes_pg_action):
    """
    This test case checks upload volume to image functionality:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Instances
        - Create a new volume

    Teardown:
        - Back to Instances page
        - Delete the newly created volume
        - Logout

    Test Steps:
        - Upload volume to image with some disk format
        - Check that image is created with correct format
        - Delete the image
        - Repeat actions for all disk formats
    """
    volumes_pg_action, volume_name = volumes_pg_action
    all_formats = {"qcow2": u'QCOW2', "raw": u'RAW', "vdi": u'VDI',
                   "vhd": u'VHD', "vmdk": u'VMDK', "vhdx": u"VHDX"}
    for disk_format in all_formats:
        LOG.tc_step('Upload volume to image with disk format {}'.format(disk_format))
        image_name = helper.gen_resource_name('volume_image')
        volumes_pg_action.upload_to_image(volume_name, image_name, disk_format)
        assert not volumes_pg_action.find_message_and_dismiss(messages.ERROR)
        assert volumes_pg_action.is_volume_status(volume_name, 'Available')

        LOG.tc_step('Check that image is created with format {}'.format(disk_format))
        images_pg = imagespage.ImagesPage(volumes_pg_action.driver, volumes_pg_action.port)
        images_pg.go_to_target_page()
        assert images_pg.is_image_present(image_name)
        assert images_pg.is_image_active(image_name)
        assert images_pg.get_image_info(image_name, 'Disk Format') == all_formats[disk_format]

        LOG.tc_step('Delete image {}'.format(image_name))
        images_pg.delete_image(image_name)
        time.sleep(1)
        assert images_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not images_pg.find_message_and_dismiss(messages.ERROR)
        assert not images_pg.is_image_present(image_name)
        volumes_pg_action.go_to_target_page()
    horizon.test_result = True


def test_horizon_volume_launch_as_instance(volumes_pg_action):
    """
    This test case checks launch volume as instance functionality:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Instances
        - Create a new volume

    Teardown:
        - Back to Instances page
        - Delete the newly created volume
        - Logout

    Test Steps:
        - Edit new volume as bootable
        - Launch volume as instance
        - Check that instance is 'active' and attached by the volume
        - Check that volume status is 'in use'
        - Delete the instance
    """
    volumes_pg_action, volume_name = volumes_pg_action
    LOG.tc_step('Edit new volume as Bootable')
    volumes_pg_action.edit_volume(volume_name, volume_name, bootable=True)
    instance_name = helper.gen_resource_name('volume_instance')

    LOG.tc_step('Launch volume {} as instance'.format(volume_name))
    mgmt_net_name = '-'.join([Tenant.get_primary()['tenant'], 'mgmt', 'net'])
    flavor_name = nova_helper.get_basic_flavor(rtn_id=False)
    volumes_pg_action.launch_as_instance(volume_name,
                                         instance_name,
                                         delete_volume_on_instance_delete=False,
                                         flavor_name=flavor_name,
                                         network_names=[mgmt_net_name])
    LOG.tc_step('Check that instance is Active and attached by the volume')
    time.sleep(5)
    instances_pg = instancespage.InstancesPage(volumes_pg_action.driver, volumes_pg_action.port)
    instances_pg.go_to_target_page()
    assert instances_pg.is_instance_active(instance_name)
    volumes_pg_action.go_to_target_page()
    assert instance_name in volumes_pg_action.get_volume_info(volume_name, "Attached To")

    LOG.tc_step('Check that volume status is In-use')
    assert volumes_pg_action.is_volume_status(volume_name, 'In-use')

    LOG.tc_step('Delete the instance')
    instances_pg.go_to_target_page()
    instances_pg.delete_instance(instance_name)
    assert instances_pg.find_message_and_dismiss(messages.INFO)
    assert not instances_pg.find_message_and_dismiss(messages.ERROR)
    assert instances_pg.is_instance_deleted(instance_name)
    horizon.test_result = True


def test_horizon_non_bootable_volume_launch_as_instance_negative(volumes_pg_action):
    """
    This test case checks launch as instance option does not exist for non-bootable volume:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Instances
        - Create a non bootable volume

    Teardown:
        - Back to Instances page
        - Delete the newly created volume
        - Logout

    Test Steps:
        - Launch volume as instance
        - Check that ValueError exception is raised
    """
    volumes_pg_action, volume_name = volumes_pg_action
    instance_name = helper.gen_resource_name('volume_instance')
    LOG.tc_step('Meet Error when launching non-bootable volume {} as instance'.format(volume_name))
    mgmt_net_name = '-'.join([Tenant.get_primary()['tenant'], 'mgmt', 'net'])
    flavor_name = nova_helper.get_basic_flavor(rtn_id=False)

    with raises(ValueError):
        volumes_pg_action.launch_as_instance(volume_name, instance_name, delete_volume_on_instance_delete=True,
                                             flavor_name=flavor_name, network_names=[mgmt_net_name])
    horizon.test_result = True
