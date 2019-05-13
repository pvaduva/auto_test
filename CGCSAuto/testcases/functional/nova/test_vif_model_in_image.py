from pytest import mark

from utils.tis_log import LOG
from consts.cgcs import ImageMetadata
from keywords import vm_helper, glance_helper, cinder_helper, network_helper, system_helper


@mark.p3
@mark.parametrize('vol_vif', [
    'e1000',
    'avp',
    'virtio',
])
def test_attach_cinder_volume_to_instance(vol_vif, skip_for_ovs):
    """
    Validate that cinder volume can be attached to VM created using wrl5_avp and wrl5_virtio image

    Args:
        vol_vif (str)

    Test Steps:
        - Create cinder volume
        - Boot VM use WRL image
        - Attach cinder volume to WRL virtio/avp instance
        - Check VM nics vifs are not changed

    Teardown:
        - Delete VM
        - Delete cinder volume
    """
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    vif_model = 'avp' if system_helper.is_avs() else 'virtio'
    nics = [{'net-id': mgmt_net_id},
            {'net-id': tenant_net_id},
            {'net-id': internal_net_id, 'vif-model': vif_model},
            ]

    LOG.tc_step("Boot up VM from default tis image")
    vm_id = vm_helper.boot_vm(name='vm_attach_vol_{}'.format(vol_vif), source='image', nics=nics, cleanup='function')[1]

    prev_ports = network_helper.get_ports(server=vm_id)

    LOG.tc_step("Create an image with vif model metadata set to {}".format(vol_vif))
    img_id = glance_helper.create_image('vif_{}'.format(vol_vif), cleanup='function',
                                        **{ImageMetadata.VIF_MODEL: vol_vif})[1]

    LOG.tc_step("Boot a volume from above image")
    volume_id = cinder_helper.create_volume('vif_{}'.format(vol_vif), source_id=img_id, cleanup='function')[1]

    # boot a cinder volume and attached it to vm
    LOG.tc_step("Attach cinder Volume to VM")
    vm_helper.attach_vol_to_vm(vm_id, vol_id=volume_id)

    LOG.tc_step("Check vm nics vif models are not changed")
    post_ports = network_helper.get_ports(server=vm_id)

    assert prev_ports == post_ports


@mark.parametrize('img_vif', [
    mark.sanity('avp'),
    mark.p2('virtio'),
    mark.p3('e1000')
])
def test_vif_model_from_image(img_vif, skip_for_ovs):
    """
    Test vif model set in image metadata is reflected in vm nics when use normal vnic type.
    Args:
        img_vif (str):
        skip_for_ovs:

    Test Steps:
        - Create a glance image with given img_vif in metadata
        - Create a cinder volume from above image
        - Create a vm with 3 vnics from above cinder volume:
            - nic1 and nic2 with normal vnic type
            - nic3 with avp (if AVS, otherwise normal)
        - Verify nic1 and nic2 vif model is the same as img_vif
        - Verify nic3 vif model is avp (if AVS, otherwise normal)

    """

    LOG.tc_step("Create an image with vif model metadata set to {}".format(img_vif))
    img_id = glance_helper.create_image('vif_{}'.format(img_vif), cleanup='function',
                                        **{ImageMetadata.VIF_MODEL: img_vif})[1]

    LOG.tc_step("Boot a volume from above image")
    volume_id = cinder_helper.create_volume('vif_{}'.format(img_vif), source_id=img_id, cleanup='function')[1]

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    vif_model = 'avp' if system_helper.is_avs() else img_vif
    nics = [{'net-id': mgmt_net_id},
            {'net-id': tenant_net_id},
            {'net-id': internal_net_id, 'vif-model': vif_model}]

    LOG.tc_step("Boot a vm from above volume with following nics: {}".format(nics))
    vm_id = vm_helper.boot_vm(name='vif_img_{}'.format(img_vif), nics=nics, source='volume', source_id=volume_id,
                              cleanup='function')[1]

    LOG.tc_step("Verify vnics info from virsh to ensure tenant net vif is as specified in image metadata")
    internal_mac = network_helper.get_ports(server=vm_id, network=internal_net_id, rtn_val='MAC Address')[0]
    vm_interfaces = vm_helper.get_vm_interfaces_via_virsh(vm_id)
    for vm_if in vm_interfaces:
        if_mac, if_model = vm_if
        if if_mac == internal_mac:
            assert if_model == vif_model
        else:
            assert if_model == img_vif
