from time import sleep

from pytest import fixture
from pytest import mark, raises

from utils.horizon.regions import messages
from utils.horizon.pages.project.volumes import volumespage
from utils.horizon import helper
from utils.horizon.pages.project.compute import imagespage
from utils.horizon.pages.project.compute import instancespage
from utils.tis_log import LOG
from consts import horizon
from testfixtures.horizon import tenant_home_pg, driver


class TestVolumesBasic:

    VOLUME_NAME = None

    @fixture(scope='function')
    def volumes_pg(self, tenant_home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Volumes page')
        self.VOLUME_NAME = helper.gen_resource_name('volume')
        volumes_pg = volumespage.VolumesPage(tenant_home_pg.driver)
        volumes_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Volumes page')
            volumes_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return volumes_pg

    @fixture(scope='function')
    def instances_pg(self, tenant_home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Instances')
        self.VOLUME_NAME = helper.gen_resource_name('volume')
        instances_pg = instancespage.InstancesPage(tenant_home_pg.driver)
        instances_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Instances page')
            instances_pg.go_to_target_page()

        request.addfinalizer(teardown)

        return instances_pg

    @mark.parametrize(('volume_source_type', 'source_name'), [
        (None, None),
        ('Image', 'tis-centos-guest')
    ])
    def test_volume_create_delete(self, volumes_pg, volume_source_type, source_name):
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
        LOG.tc_step('Create new volume {}, with source type {}'.format(self.VOLUME_NAME, volume_source_type))
        volumes_pg.create_volume(
            volume_name=self.VOLUME_NAME,
            volume_source_type=volume_source_type,
            source_name=source_name
        )

        LOG.tc_step('Check that the volume is in the list with Available')
        assert volumes_pg.is_volume_status(self.VOLUME_NAME, 'Available')

        LOG.tc_step('Delete volume {}'.format(self.VOLUME_NAME))
        volumes_pg.delete_volume(self.VOLUME_NAME)

        LOG.tc_step('Check that the volume is absent in the list')
        assert volumes_pg.is_volume_deleted(self.VOLUME_NAME)
        horizon.test_result = True

    @mark.parametrize(('boot_source_type', 'source_name', 'flavor_name', 'network_names'), [
        ('Image', 'tis-centos-guest', 'small', ['tenant1-mgmt-net']),
    ])
    def test_manage_volume_attachments(self, instances_pg, boot_source_type, source_name, flavor_name, network_names):
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

        instance_name = helper.gen_resource_name('volume_attachment')
        LOG.tc_step('Create new instance {}'.format(instance_name))
        instances_pg.create_instance(instance_name,
                                     boot_source_type=boot_source_type,
                                     create_new_volume=False,
                                     source_name=source_name,
                                     flavor_name=flavor_name,
                                     network_names=network_names)
        assert not instances_pg.find_message_and_dismiss(messages.ERROR)
        assert instances_pg.is_instance_active(instance_name)

        LOG.tc_step('Go to Project -> Compute -> Volumes, create volume {}'.format(self.VOLUME_NAME))
        volumes_pg = volumespage.VolumesPage(instances_pg.driver)
        volumes_pg.go_to_target_page()
        sleep(3)
        volumes_pg.create_volume(self.VOLUME_NAME)
        assert (volumes_pg.is_volume_status(self.VOLUME_NAME, 'Available'))

        LOG.tc_step('Attach the volume to the newly created instance')
        volumes_pg.attach_volume_to_instance(self.VOLUME_NAME, instance_name)

        LOG.tc_step('Check that volume is In-use and link to instance')
        assert volumes_pg.is_volume_status(self.VOLUME_NAME, 'In-use')
        assert instance_name in volumes_pg.get_volume_info(self.VOLUME_NAME, 'Attached To')

        LOG.tc_step('Detach volume from instance')
        volumes_pg.detach_volume_from_instance(self.VOLUME_NAME, instance_name)

        LOG.tc_step('Check volume is Available instead of In-use')
        assert volumes_pg.is_volume_status(self.VOLUME_NAME, 'Available')

        LOG.tc_step('Delete the volume {}'.format(self.VOLUME_NAME))
        volumes_pg.delete_volume(self.VOLUME_NAME)
        assert volumes_pg.is_volume_deleted(self.VOLUME_NAME)

        LOG.tc_step('Delete the instance {}'.format(instance_name))
        instances_pg.go_to_target_page()
        instances_pg.delete_instance(instance_name)
        instances_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not instances_pg.find_message_and_dismiss(messages.ERROR)
        assert instances_pg.is_instance_deleted(instance_name)
        horizon.test_result = True

    @fixture(scope='function')
    def volumes_pg_action(self, tenant_home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Volumes page')
        volumes_pg = volumespage.VolumesPage(tenant_home_pg.driver)
        volumes_pg.go_to_target_page()
        self.VOLUME_NAME = helper.gen_resource_name('volume')
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
        assert volumespage.is_volume_status(self.VOLUME_NAME, 'Available')

    def _delete_volume(self, volumespage):
        volumespage.delete_volume(self.VOLUME_NAME)
        assert volumespage.is_volume_deleted(self.VOLUME_NAME)

    def test_volume_edit(self, volumes_pg_action):
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
        new_name = "edited_" + self.VOLUME_NAME
        volumes_pg_action.edit_volume(self.VOLUME_NAME, new_name, "description", True)

        LOG.tc_step('Check that the volume is edited successfully')
        assert volumes_pg_action.is_volume_present(new_name)
        assert volumes_pg_action.is_volume_status(new_name, 'Available')
        assert volumes_pg_action.get_volume_info(new_name, 'Bootable') == 'Yes'
        self.VOLUME_NAME = new_name
        horizon.test_result = True

    def test_volume_extend(self, volumes_pg_action):
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
        LOG.tc_step('Extend volume')
        orig_size = int(volumes_pg_action.get_volume_info(self.VOLUME_NAME, 'Size')[:-3])
        volumes_pg_action.extend_volume(self.VOLUME_NAME, str(orig_size + 1))
        assert volumes_pg_action.is_volume_status(self.VOLUME_NAME, 'Available')

        LOG.tc_step('Check that the volume size is changed')
        new_size = int(volumes_pg_action.get_volume_info(self.VOLUME_NAME, 'Size')[:-3])
        assert orig_size < new_size
        horizon.test_result = True

    def test_volume_upload_to_image(self, volumes_pg_action):
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

        all_formats = {"qcow2": u'QCOW2', "raw": u'Raw', "vdi": u'VDI',
                       "vmdk": u'VMDK'}
        for disk_format in all_formats:
            LOG.tc_step('Upload volume to image with disk format {}'.format(disk_format))
            image_name = helper.gen_resource_name('volume_image')
            volumes_pg_action.upload_to_image(self.VOLUME_NAME, image_name, disk_format)
            assert not volumes_pg_action.find_message_and_dismiss(messages.ERROR)
            assert volumes_pg_action.is_volume_status(self.VOLUME_NAME, 'Available')

            LOG.tc_step('Check that image is created with format {}'.format(disk_format))
            images_pg = imagespage.ImagesPage(volumes_pg_action.driver)
            images_pg.go_to_target_page()
            assert images_pg.is_image_present(image_name)
            assert images_pg.is_image_active(image_name)
            assert images_pg.get_image_info(image_name, 'Format') == all_formats[disk_format]

            LOG.tc_step('Delete image {}'.format(image_name))
            images_pg.delete_image(image_name)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)
            assert not (images_pg.is_image_present(image_name))
            volumes_pg_action.go_to_target_page()
        horizon.test_result = True

    @mark.parametrize(('flavor_name', 'network_names', 'boot_source_type'), [
        ('small', ['tenant1-mgmt-net'], 'Volume'),
    ])
    def test_volume_launch_as_instance(self, volumes_pg_action, boot_source_type, flavor_name, network_names):
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
        LOG.tc_step('Edit new volume as Bootable')
        volumes_pg_action.edit_volume(self.VOLUME_NAME, self.VOLUME_NAME, bootable=True)
        instance_name = helper.gen_resource_name('volume_instance')

        LOG.tc_step('Launch volume {} as instance'.format(self.VOLUME_NAME))
        volumes_pg_action.launch_as_instance(self.VOLUME_NAME,
                                             instance_name,
                                             boot_source_type=boot_source_type,
                                             delete_volume_on_instance_delete=False,
                                             flavor_name=flavor_name,
                                             network_names=network_names)
        LOG.tc_step('Check that instance is Active and attached by the volume')
        instances_pg = instancespage.InstancesPage(volumes_pg_action.driver)
        instances_pg.go_to_target_page()
        assert instances_pg.is_instance_active(instance_name)
        volumes_pg_action.go_to_target_page()
        assert instance_name in volumes_pg_action.get_volume_info(self.VOLUME_NAME, "Attached To")

        LOG.tc_step('Check that volume status is In-use')
        assert volumes_pg_action.is_volume_status(self.VOLUME_NAME, 'In-use')

        LOG.tc_step('Delete the instance')
        instances_pg.go_to_target_page()
        instances_pg.delete_instance(instance_name)
        assert instances_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not instances_pg.find_message_and_dismiss(messages.ERROR)
        assert instances_pg.is_instance_deleted(instance_name)
        horizon.test_result = True

    @mark.parametrize(('flavor_name', 'network_names'), [
        ('small', ['tenant1-mgmt-net']),
    ])
    def test_non_bootable_volume_launch_as_instance_negative(self, volumes_pg_action, flavor_name, network_names):
        """
        This test case checks launch non-bootable volume will raise valueError:

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

        instance_name = helper.gen_resource_name('volume_instance')
        LOG.tc_step('Meet Error when launching non-bootable volume {} as instance'.format(self.VOLUME_NAME))
        with raises(ValueError):
            volumes_pg_action.launch_as_instance(self.VOLUME_NAME, instance_name, delete_volume_on_instance_delete=True,
                                                 flavor_name=flavor_name, network_names=network_names)
        horizon.test_result = True
