from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3

#set flavor
#verfiy that flavour is created and the extra spec is set
#delete the specs and verfiy its deleted

disk_spec_params = [
        ('quota:disk_read_bytes_sec', 10485769),
        ('quota:disk_read_bytes_sec', 419430400),
        ('quota:disk_read_iops_sec', 200),
        ('quota:disk_read_iops_sec', 5000),
        ('quota:disk_write_bytes_sec', 10485769),
        ('quota:disk_write_bytes_sec', 419430400),
        ('quota:disk_write_iops_sec', 200),
        ('quota:disk_write_iops_sec', 5000),
        ('quota:disk_total_bytes_sec', 10485769),
        ('quota:disk_total_bytes_sec', 419430400),
        ('quota:disk_total_iops_sec', 200),
        ('quota:disk_total_iops_sec', 419430400)
    ]



@fixture(scope='module', params=disk_spec_params )
def volume_with_disk_spec(request):
    """
    Text fixture to create flavor with specific 'ephemeral', 'swap', and 'mem_page_size'
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'boot_source : image
         'pagesize': pagesize
        }
    """

    flavor_id = nova_helper.create_flavor()[1]
    quota_disk_spec = {request.param[0]: request.param[1]}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **quota_disk_spec)
    flavor = {'id': flavor_id,
              'extra_spec': [request.param[0], request.param[1]]
              }

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor)

    return flavor


def test_disk_extra_spec(flavor_with_disk_spec):

    flavor_id = flavor_with_disk_spec['id']
    extra_spec = flavor_with_disk_spec['extra_spec']

    flavor_extra_specs = nova_helper.get_flavor_extra_specs(flavor_id)

    assert flavor_extra_specs[extra_spec[0]] == str(extra_spec[1]), "Expected extra_spec {} to be {}. However, " \
                                                                    "it was {}".format(extra_spec, str(extra_spec[1]),
                                                                                       flavor_extra_specs[extra_spec])


def test_verify_disk_extra_on_vm(flavor_with_disk_spec):

    flavor_id = flavor_with_disk_spec['id']
    extra_spec = flavor_with_disk_spec['extra_spec']

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]

    # check vm using nova list then verfiy the flavour is added to vm
    vm_flavour_id = nova_helper.get_vm_flavor(vm_id)
    # retrieve flavor id
    print(vm_flavour_id)
    vm_flavor_extra_specs = nova_helper.get_flavor_extra_specs(vm_flavour_id)

    assert vm_flavor_extra_specs[extra_spec[0]] == str(extra_spec[1]), "Expected extra_spec {} to be {}. However, it " \
                                                                       "was {}".format(extra_spec, str(extra_spec[1]),
                                                                                       vm_flavor_extra_specs[extra_spec])
    vm_helper.delete_vms(vm_id, delete_volumes=True)

    # test it with virsh as well. add virsh parsing

