from pytest import mark

from utils import table_parser, cli
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import ImageMetadata
from keywords import vm_helper, glance_helper, cinder_helper, network_helper

from testfixtures.fixture_resources import ResourceCleanup


@mark.p3
@mark.parametrize(('vol_vif'), [
    ('e1000'),
    ('avp'),
    ('virtio'),
])
def test_attach_cinder_volume_to_instance(vol_vif):
    """
    Validate that cinder volume can be attached to VM created using wrl5_avp and wrl5_virtio image

    Args:
        vol_vif (str)

    Test Steps:
        - Create cinder volume
        - Boot VM use WRL image
        - Attach cinder volume to WRL virtuo/avp instance
        - Check VM nics vifs are not changed

    Teardown:
        - Delete VM
        - Delete cinder volume
    """
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id},
            {'net-id': internal_net_id, 'vif-model': 'avp'},
            ]

    LOG.tc_step("Boot up VM from default tis image")
    vm_id = vm_helper.boot_vm(name='vm_attach_vol_{}'.format(vol_vif), source='image', nics=nics, cleanup='function')[1]

    pre_nics = network_helper.get_vm_nics(vm_id)

    LOG.tc_step("Create an image with vif model metadata set to {}".format(vol_vif))
    img_id = glance_helper.create_image('vif_{}'.format(vol_vif), **{ImageMetadata.VIF_MODEL: vol_vif})[1]
    ResourceCleanup.add('image', img_id)

    LOG.tc_step("Boot a volume from above image")
    volume_id = cinder_helper.create_volume('vif_{}'.format(vol_vif), image_id=img_id)[1]
    ResourceCleanup.add('volume', volume_id)

    # boot a cinder volume and attached it to vm
    LOG.tc_step("Attach cinder Volume to VM")
    vm_helper.attach_vol_to_vm(vm_id, vol_id=volume_id)
    # teardown: delete vm and volume will happen automatically

    LOG.tc_step("Check vm nics vif models are not changed")
    post_nics = network_helper.get_vm_nics(vm_id)

    assert pre_nics == post_nics


@mark.parametrize('img_vif', [
    mark.sanity('avp'),
    mark.p2('virtio'),
    mark.p3('e1000')
])
def test_vif_model_from_image(img_vif):

    LOG.tc_step("Create an image with vif model metadata set to {}".format(img_vif))
    img_id = glance_helper.create_image('vif_{}'.format(img_vif), **{ImageMetadata.VIF_MODEL: img_vif})[1]
    ResourceCleanup.add('image', img_id)

    LOG.tc_step("Boot a volume from above image")
    volume_id = cinder_helper.create_volume('vif_{}'.format(img_vif), image_id=img_id)[1]
    ResourceCleanup.add('volume', volume_id)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id},
            {'net-id': internal_net_id, 'vif-model': 'avp'},
            ]

    LOG.tc_step("Boot a vm from above volume with following nics: {}".format(nics))
    vm_id = vm_helper.boot_vm(name='vif_img_{}'.format(img_vif), nics=nics, source='volume', source_id=volume_id,
                              cleanup='function')[1]

    LOG.tc_step("Verify nics info from nova show to ensure tenant net vif is as specified in image metadata")
    table_ = table_parser.table(cli.nova('show', vm_id, auth_info=Tenant.ADMIN))
    actual_nics = table_parser.get_value_two_col_table(table_, field='wrs-if:nics', merge_lines=False)
    actual_nics = [eval(nic_) for nic_ in actual_nics]

    assert 'virtio' == list(actual_nics[0].values())[0]['vif_model']
    assert 'avp' == list(actual_nics[2].values())[0]['vif_model']
    assert img_vif == list(actual_nics[1].values())[0]['vif_model']
