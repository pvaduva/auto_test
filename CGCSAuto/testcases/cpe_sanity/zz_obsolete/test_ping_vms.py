from pytest import mark, skip

import time
import keywords.cinder_helper
import keywords.glance_helper
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper

_skip = False

#@mark.cpe_sanity
def test_4700_ping_vm_from_external_network():
    vm_ids = vm_helper.get_any_vms(count=2)
    assert vm_ids != []
    time.sleep(10)
    vm_helper.ping_vms_from_natbox(vm_ids=vm_ids, fail_ok=False)


#@mark.cpe_sanity
def test_4701_ping_internal_between_vms():
    from_vm = vm_helper.get_any_vms(count=1)[0]
    vm_ids = vm_helper.get_any_vms(count=2)

    assert vm_ids != ()
    time.sleep(10)
    vm_helper.ping_vms_from_vm(to_vms=vm_ids, from_vm=from_vm, fail_ok=False)


@mark.parametrize('vm_image', [
    # 'cgcs-guest',
    # 'ubuntu',
    'wrl5',
    'centos',
])
def test_ping_vms_running_various_images(vm_image):
    image_id = keywords.glance_helper.get_image_id_from_name(name=vm_image, strict=False)
    if not image_id:
        skip("No image name has substring: {}.".format(vm_image))

    vol_size = 1
    if vm_image in ['ubuntu', 'centos']:
        vol_size = 8
    vol_id = keywords.cinder_helper.create_volume(name='vol_' + vm_image, image_id=image_id, size=vol_size)[1]
    vm_id = vm_helper.boot_vm(source='volume', source_id=vol_id)[1]

    vm_helper.ping_vms_from_vm(from_vm=vm_id)

