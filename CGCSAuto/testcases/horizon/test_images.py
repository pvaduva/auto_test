from utils.horizon.regions import messages
from utils.horizon.pages.project.compute import imagespage
from utils.horizon.pages.admin.compute import imagespage as admin_imagespage
from utils.horizon.pages.project.compute import instancespage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG


class TestImagesBasic(helper.AdminTestCase):

    IMAGE_NAME = None

    @fixture(scope='function')
    def images_pg(self, home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Images')
        self.IMAGE_NAME = helper.gen_resource_name('image')
        images_pg = imagespage.ImagesPage(home_pg.driver)
        images_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Groups page')
            images_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return images_pg

    def test_image_create_delete(self, images_pg):
        """
        Test the image creation and deletion functionality:

        Setups:
            - Login as Admin
            - Go to Project > Compute > Images

        Teardown:
            - Back to Images page
            - Logout

        Test Steps:
            - Create a new image
            - Verify the image appears in the images table as active
            - Delete the newly created image
            - Verify the image does not appear in the table after deletion
        """

        with helper.gen_temporary_file() as file_name:
            LOG.tc_step('Create new image {}.'.format(self.IMAGE_NAME))
            images_pg.create_image(self.IMAGE_NAME, image_file=file_name)
            assert images_pg.find_message_and_dismiss(messages.INFO)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)

            LOG.tc_step('Verify the image appears in the images table as active')
            assert images_pg.is_image_active(self.IMAGE_NAME)

            LOG.tc_step('Delete image {}.'.format(self.IMAGE_NAME))
            images_pg.delete_image(self.IMAGE_NAME)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)

            LOG.tc_step('Verify the image does not appear in the table after deletion')
            assert not images_pg.is_image_present(self.IMAGE_NAME)

    def test_update_image_metadata(self, images_pg):
        """
        Test update image metadata

        Setups:
            - Login as Admin
            - Go to Project > Compute > Images

        Teardown:
            - Back to Images page
            - Logout

        Test Steps:
            - Create image from locally
            - Update image metadata
            - Verify metadata updated successfully
            - Delete the newly created image
        """

        with helper.gen_temporary_file() as file_name:
            LOG.tc_step('Create new image {}.'.format(self.IMAGE_NAME))
            images_pg.create_image(self.IMAGE_NAME, image_file=file_name,
                                   description='description')
            assert images_pg.find_message_and_dismiss(messages.INFO)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)
            assert images_pg.is_image_active(self.IMAGE_NAME)

            LOG.tc_step('Update image metadata and Verify metadata updated successfully')
            new_metadata = {'metadata1': "value1", 'metadata2': "value2"}
            images_pg.add_custom_metadata(self.IMAGE_NAME, new_metadata)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)
            assert images_pg.is_image_active(self.IMAGE_NAME)

            LOG.tc_step('Delete the image {}.'.format(self.IMAGE_NAME))
            images_pg.delete_image(self.IMAGE_NAME)

    def test_remove_protected_image(self, images_pg):
        """
        Test that protected image is not deletable:

        Setups:
            - Login as Admin
            - Go to Project > Compute > Image

        Teardown:
            - Back to Images page
            - Logout

        Test Steps:
            - Create a new image
            - Verify the image appears in the images table as active
            - Mark 'Protected' checkbox in edit action
            - Try to delete the image
            - Verify that exception is generated for the protected image
            - Un-mark 'Protected' checkbox in edit action
            - Delete the image
            - Verify the image does not appear in the table after deletion
        """

        with helper.gen_temporary_file() as file_name:
            LOG.tc_step('Create new image {}.'.format(self.IMAGE_NAME))
            images_pg.create_image(self.IMAGE_NAME, image_file=file_name,
                                   description='description')
            assert images_pg.find_message_and_dismiss(messages.INFO)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)

            LOG.tc_step('Verify the image appears in the images table as active')
            assert images_pg.is_image_active(self.IMAGE_NAME)

            LOG.tc_step('Mark "Protected" checkbox in edit action')
            images_pg.edit_image(self.IMAGE_NAME, protected=True)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)

            LOG.tc_step('Try to delete the image')
            images_pg.delete_image(self.IMAGE_NAME)
            assert not images_pg.find_message_and_dismiss(messages.SUCCESS)
            images_pg.find_message_and_dismiss(messages.ERROR)
            assert images_pg.is_image_present(self.IMAGE_NAME)

            LOG.tc_step('Un-mark "Protected" checkbox in edit action')
            images_pg.edit_image(self.IMAGE_NAME, protected=False)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)

            LOG.tc_step('Delete image {}.'.format(self.IMAGE_NAME))
            images_pg.delete_image(self.IMAGE_NAME)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)

            LOG.tc_step('Verify the image does not appear in the table after deletion')
            assert not images_pg.is_image_present(self.IMAGE_NAME)

    def test_edit_image_description_and_name(self, images_pg):
        """
        Test that image description is editable:

        Setups:
            - Login as Admin
            - Go to Project > Compute > Image

        Teardown:
            - Back to Images page
            - Logout

        Test Steps:
            - Create a new image
            - Toggle edit action and add some description and change name
            - Verify that new description and new name is seen on image details page
            - Delete the image
        """

        with helper.gen_temporary_file() as file_name:
            new_description_text = "new-description"
            new_image_name = 'edited_' + self.IMAGE_NAME

            LOG.tc_step('Create new image {}'.format(self.IMAGE_NAME))
            images_pg.create_image(self.IMAGE_NAME, image_file=file_name,
                                   description='description')
            assert images_pg.find_message_and_dismiss(messages.INFO)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)
            assert images_pg.is_image_active(self.IMAGE_NAME)

            LOG.tc_step('Toggle edit action and add some description and change name')
            images_pg.edit_image(self.IMAGE_NAME, description=new_description_text,
                                 new_name=new_image_name)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)

            LOG.tc_step('Verify that new description and new name is seen on image details page')
            assert images_pg.is_image_present(new_image_name)
            results = images_pg.check_image_details(new_image_name,
                                                    {'Description': new_description_text,
                                                     'Name': new_image_name})
            assert results

            LOG.tc_step('Delete image {}'.format(self.IMAGE_NAME))
            images_pg.go_to_target_page()
            images_pg.delete_image(new_image_name)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)

    def test_create_volume_from_image(self, images_pg):
        """
        Test create volume from image functionality:

        Setups:
            - Login as Admin
            - Go to Project > Compute > Image

        Teardown:
            - Back to Images page
            - Logout

        Test Steps:
            - Create a new image
            - Create new volume from image
            - Check that volume status is Available
            - Delete the volume
            - Delete the image
        """

        with helper.gen_temporary_file(suffix='.iso') as file_name:

            LOG.tc_step('Create new image {}.'.format(self.IMAGE_NAME))
            images_pg.create_image(self.IMAGE_NAME, image_file=file_name,
                                   description='description')
            assert images_pg.find_message_and_dismiss(messages.INFO)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)
            assert images_pg.is_image_active(self.IMAGE_NAME)

            volume_name = helper.gen_resource_name('volume_from_image')
            LOG.tc_step('Create new volume {} from image'.format(volume_name))
            volumes_pg = images_pg.create_volume_from_image(self.IMAGE_NAME,
                                                            volume_name=volume_name)
            assert volumes_pg.find_message_and_dismiss(messages.INFO)
            assert not volumes_pg.find_message_and_dismiss(messages.ERROR)

            LOG.tc_step('Check that volume status is Available')
            assert volumes_pg.is_volume_status(volume_name, 'Available')
            assert volumes_pg.is_volume_present(volume_name)

            LOG.tc_step('Delete volume {}.'.format(volume_name))
            volumes_pg.delete_volume(volume_name)
            assert volumes_pg.find_message_and_dismiss(messages.SUCCESS)
            assert not volumes_pg.find_message_and_dismiss(messages.ERROR)
            assert volumes_pg.is_volume_deleted(volume_name)

            LOG.tc_step('Delete image {}.'.format(self.IMAGE_NAME))
            images_pg.go_to_target_page()
            images_pg.delete_image(self.IMAGE_NAME)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)

    def test_filter_images(self, images_pg):
        """
        Test create filtering of images:

        Setups:
            - Login as Admin
            - Go to Project > Compute > Image

        Teardown:
            - Back to Images page
            - Logout

        Test Steps:
            - Create a new image
            - Go to Admin > Compute > Image
            - Use filter by image name
            - Check that filtered table has the wanted image
            - Clear filter and set nonexistent image name. Check that 0 rows are displayed
            - Delete the newly created image
        """

        with helper.gen_temporary_file(suffix='.iso') as file_name:
            LOG.tc_step('Create new image {}.'.format(self.IMAGE_NAME))
            images_pg.create_image(self.IMAGE_NAME, image_file=file_name,
                                   description='description')
            assert images_pg.find_message_and_dismiss(messages.INFO)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)
            assert images_pg.is_image_active(self.IMAGE_NAME)

            LOG.tc_step('Go to Admin > Compute > Image')
            admin_images_pg = admin_imagespage.ImagesPage(images_pg.driver)
            admin_images_pg.go_to_target_page()

            LOG.tc_step('Use filter by image name and Check that filtered table has the wanted image')
            admin_images_pg.images_table.filter(self.IMAGE_NAME)
            assert admin_images_pg.is_image_present(self.IMAGE_NAME)

            LOG.tc_step('Clear filter and set nonexistent image name and Check that 0 rows are displayed')
            nonexistent_image_name = "nonexistent_image_test"
            admin_images_pg.images_table.filter(nonexistent_image_name)
            assert admin_images_pg.images_table.rows == []

            admin_images_pg.images_table.filter('')
            LOG.tc_step('Delete image {}.'.format(self.IMAGE_NAME))
            admin_images_pg.delete_image(self.IMAGE_NAME)
            assert admin_images_pg.find_message_and_dismiss(messages.SUCCESS)


class TestImagesAdvanced(helper.TenantTestCase):

    IMAGE_NAME = None

    @fixture(scope='function')
    def images_pg(self, home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Images')
        self.IMAGE_NAME = helper.gen_resource_name('image')
        images_pg = imagespage.ImagesPage(home_pg.driver)
        images_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Groups page')
            images_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return images_pg

    def test_launch_instance_from_image(self, images_pg):
        """
        Test launch instance from image functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Compute > Image

        Teardown:
            - Back to Images page
            - Logout

        Test Steps:
            - Create a new image
            - Launch new instance from image
            - Check that status of newly created instance is Active
            - Delete the newly lunched instance
            - Delete the newly created image
        """

        with helper.gen_temporary_file(suffix='.iso') as file_name:
            LOG.tc_step('Create new image {}.'.format(self.IMAGE_NAME))
            images_pg.create_image(self.IMAGE_NAME, image_file=file_name,
                                   description='description')
            assert images_pg.find_message_and_dismiss(messages.INFO)
            assert not images_pg.find_message_and_dismiss(messages.ERROR)
            assert images_pg.is_image_active(self.IMAGE_NAME)

            instance_name = helper.gen_resource_name('image_instance')
            LOG.tc_step('Launch new instance {} from image.'.format(instance_name))
            images_pg.launch_instance_from_image(self.IMAGE_NAME, instance_name)
            instance_pg = instancespage.InstancesPage(images_pg.driver)
            instance_pg.go_to_target_page()
            assert not instance_pg.find_message_and_dismiss(messages.ERROR)

            LOG.tc_step('Check that status of newly created instance is Active.')
            assert instance_pg.is_instance_active(instance_name)

            LOG.tc_step('Delete instance {}.'.format(instance_name))
            instance_pg.delete_instance(instance_name)
            assert not instance_pg.find_message_and_dismiss(messages.ERROR)
            assert instance_pg.is_instance_deleted(instance_name)

            LOG.tc_step('Delete image {}.'.format(self.IMAGE_NAME))
            images_pg.go_to_target_page()
            images_pg.delete_image(self.IMAGE_NAME)
            assert images_pg.find_message_and_dismiss(messages.SUCCESS)






