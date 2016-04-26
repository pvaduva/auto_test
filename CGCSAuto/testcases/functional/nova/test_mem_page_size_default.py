from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, ImageMetadata
from keywords import nova_helper, vm_helper, glance_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.sanity
@mark.parametrize('mem_page_size', [
    'small',
    'large',
    'any',
    '2048',
    '1048576',
])
def test_set_mem_page_size_extra_specs(flavor_id_module, mem_page_size):
    nova_helper.set_flavor_extra_specs(flavor_id_module, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})


#####################################################################################################################

@fixture(scope='module')
def flavor_2g(request):
    flavor = nova_helper.create_flavor(name='flavor-huge_page', ram=2048)[1]
    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor

testdata = [None, 'any', 'large', 'small', '2048']      # '1048576' will be tested in *huge_page.py
@fixture(params=testdata)
def flavor_mem_page_size(request, flavor_2g):
    mem_page_size = request.param
    
    if mem_page_size is None:
        nova_helper.unset_flavor_extra_specs(flavor_2g, FlavorSpec.MEM_PAGE_SIZE)
    else:
        nova_helper.set_flavor_extra_specs(flavor_2g, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

    return mem_page_size

@fixture(scope='module')
def image_cgcsguest(request):
    image_id = glance_helper.get_image_id_from_name(name='cgcs-guest')

    def delete_metadata():
        nova_helper.delete_image_metadata(image_id, ImageMetadata.MEM_PAGE_SIZE)
    request.addfinalizer(delete_metadata)

    return image_id

@mark.p1
@mark.parametrize('image_mem_page_size', testdata)
def test_boot_vm_mem_page_size(flavor_2g, flavor_mem_page_size, image_cgcsguest, image_mem_page_size):
    """
    Test boot vm with various memory page size setting in flavor and image.
    Notes: 1G huge page related tests are in test_mem_page_size_hugepage.py, as they require reconfigure the host.
    
    Args:
        flavor_2g (str): flavor id of a flavor with ram set to 2G
        flavor_mem_page_size (str): memory page size extra spec value to set in flavor
        image_cgcsguest (str): image id for cgcs-guest image
        image_mem_page_size (str): memory page metadata value to set in image

    Setup:
        - Create a flavor with 2G RAM (module)
        - Get image id of cgcs-guest image (module)

    Test Steps:
        - Set/Unset flavor memory page size extra spec with given value (unset if None is given)
        - Set/Unset memory page size metadata with given value (unset if None if given)
        - Attempt to boot a vm with above flavor and image
        - Verify boot result based on the mem page size values in the flavor and image

    Teardown:
        - Delete vm if booted
        - Delete created flavor (module)

    """

    if image_mem_page_size is None:
        nova_helper.delete_image_metadata(image_cgcsguest, ImageMetadata.MEM_PAGE_SIZE)
        expt_code = 0

    else:
        nova_helper.set_image_metadata(image_cgcsguest, **{ImageMetadata.MEM_PAGE_SIZE: image_mem_page_size})
        if flavor_mem_page_size is None:
            expt_code = 4

        elif flavor_mem_page_size.lower() in ['any', 'large']:
            expt_code = 0

        else:
            expt_code = 0 if flavor_mem_page_size.lower() == image_mem_page_size.lower() else 4

    LOG.tc_step("Attempt to boot a vm with flavor_mem_page_size: {}, and image_mem_page_size: {}. And check return "
                "code is {}.".format(flavor_mem_page_size, image_mem_page_size, expt_code))

    actual_code, vm_id, msg, vol_id = vm_helper.boot_vm(name='mem_page_size', flavor=flavor_2g, source='image',
                                                        source_id=image_cgcsguest, fail_ok=True)

    if vm_id:
        ResourceCleanup.add('vm', vm_id, scope='function', del_vm_vols=False)

    assert expt_code == actual_code, "Expect boot vm to return {}; Actual result: {} with msg: {}".format(
            expt_code, actual_code, msg)

    if expt_code != 0:
        assert "Page size" in msg


