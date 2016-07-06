###
# below testcases is part of us77170_StorageTestPlan.pdf specifically under
# https://jive.windriver.com/docs/DOC-45652
# It specifically test scenarios where an flavor created with image/lvm/remote specs
# and storage specs set specifically to disk read/write/total with different values
# and when VMs are created using those flavors, they were checked that that those specs hold true on vms.
###

from pytest import fixture, mark, skip
import ast
from time import sleep

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from consts.cgcs import BOOT_FROM_VOLUME, UUID, ServerGroupMetadata, NovaCLIOutput, FlavorSpec
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup
from setup_consts import P1, P2, P3


# instance_backing_params =['image','lvm']
instance_backing_params = [
        (FlavorSpec.DISK_READ_BYTES,   10485769,    'image'),
        (FlavorSpec.DISK_READ_BYTES,   419430400,   'image'),
        (FlavorSpec.DISK_READ_IOPS,    200,         'image'),
        (FlavorSpec.DISK_READ_IOPS,    5000,        'image'),
        (FlavorSpec.DISK_WRITE_BYTES,  10485769,    'image'),
        (FlavorSpec.DISK_WRITE_BYTES,  419430400,   'image'),
        (FlavorSpec.DISK_WRITE_IOPS,   200,         'image'),
        (FlavorSpec.DISK_WRITE_IOPS,   5000,        'image'),
        (FlavorSpec.DISK_TOTAL_BYTES,  10000000,    'image'),
        (FlavorSpec.DISK_TOTAL_BYTES,  419430400,   'image'),
        (FlavorSpec.DISK_TOTAL_IOPS,   500,         'image'),
        (FlavorSpec.DISK_TOTAL_IOPS,   5000,        'image'),
        (FlavorSpec.DISK_READ_BYTES,   10485769,    'lvm'),
        (FlavorSpec.DISK_READ_BYTES,   419430400,   'lvm'),
        (FlavorSpec.DISK_READ_IOPS,    200,         'lvm'),
        (FlavorSpec.DISK_READ_IOPS,    5000,        'lvm'),
        (FlavorSpec.DISK_WRITE_BYTES,  10485769,    'lvm'),
        (FlavorSpec.DISK_WRITE_BYTES,  419430400,   'lvm'),
        (FlavorSpec.DISK_WRITE_IOPS,   200,         'lvm'),
        (FlavorSpec.DISK_WRITE_IOPS,   5000,        'lvm'),
        (FlavorSpec.DISK_TOTAL_BYTES,  10000000,    'lvm'),
        (FlavorSpec.DISK_TOTAL_BYTES,  419430400,   'lvm'),
        (FlavorSpec.DISK_TOTAL_IOPS,   500,         'lvm'),
        (FlavorSpec.DISK_TOTAL_IOPS,   5000,        'lvm'),
    ]

@fixture(scope='session', params=instance_backing_params)
def config_local_volume_group(request):

    flavor_var= request.param[0]
    flavor_var_value = request.param[1]
    local_volume_type = request.param[2]
    local_volume_group = {
        'flavor_var': flavor_var,
        'flavor_var_value': flavor_var_value,
        'instance_backing': local_volume_type
    }

    # check the local volume group of compute-0
    inst_back = host_helper.get_local_storage_backing('compute-0', con_ssh=None)

    # if already same lvm skip
    if inst_back == local_volume_type:
        return local_volume_group

    # config lvg parameter for instance backing either image/lvm
    host_helper.set_host_local_backing_type('compute-0', inst_type=local_volume_type, vol_group='nova-local')

    print('local_vol {} and inst_back {}'.format(local_volume_type, inst_back))

    def reset_local_volume_group():
        # reset local volume group back to image
        print("teardown revert host")
        if local_volume_type != inst_back:
            host_helper.set_host_local_backing_type('compute-0', inst_type=inst_back, vol_group='nova-local')
    request.addfinalizer(reset_local_volume_group)

    return local_volume_group


@fixture(scope='module')
def flavor_with_disk_spec(request, config_local_volume_group):
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
    flavor_var = config_local_volume_group['flavor_var']
    flavor_var_value = config_local_volume_group['flavor_var_value']

    if config_local_volume_group['instance_backing'] == 'remote':
        storage = 'remote'
    else:
        storage = 'local_'+config_local_volume_group['instance_backing']

    flavor_id = nova_helper.create_flavor(vcpus=4, ram=1024, root_disk=2, check_storage_backing=False)[1]
    quota_disk_spec = {flavor_var: flavor_var_value,
                       'aggregate_instance_extra_specs:storage': storage,
                       'hw:cpu_policy': 'dedicated'
                       }

    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **quota_disk_spec)
    flavor = {'id': flavor_id,
              'disk_spec': [flavor_var, flavor_var_value],
              'storage_spec': storage
              }

    def delete_flavor():
        # must delete VM before flavors
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor)
    return flavor


@fixture(scope='module')
def vm_with_disk_spec(request, flavor_with_disk_spec):

    flavor_id = flavor_with_disk_spec['id']
    disk_extra_spec = flavor_with_disk_spec['disk_spec']
    storage_extra_spec = flavor_with_disk_spec['storage_spec']

    # must be from image
    sleep(20)
    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]

    vm = {'id': vm_id,
          'disk_spec': disk_extra_spec,
          'storage_spec': storage_extra_spec
          }

    def delete_vm():
        # must delete VM before flavors
        vm_helper.delete_vms(vm_id, delete_volumes=True)

    request.addfinalizer(delete_vm)

    return vm


def test_verify_disk_extra_on_virsh(vm_with_disk_spec):
    """
    from us77170_StorageTestPlan.pdf

    Verify the version number (or str) exist for the system when execute the "system show" cli

    Args:
        - Nothing

    Setup:
        - Setup flavor with specific bytes per second extra specs
        - create a vm using the created flavor

    Test Steps:
        -verify the extra spec used by vm is set and match to expected specs

    Teardown:
        -delete vm
        -delete specific bytes per second extra specs

    """
    vm_id = vm_with_disk_spec['id']
    disk_extra_spec = vm_with_disk_spec['disk_spec']
    virsh_tag = disk_extra_spec[0].split('quota:disk_')[1]
    expected_disk_spec_val = disk_extra_spec[1]

    vm_host_table = system_helper.get_vm_topology_tables('servers')[0]

    vm_host = table_parser.get_values(vm_host_table,'host', ID=vm_id)[0]

    instance_name = table_parser.get_values(vm_host_table, 'instance_name', ID=vm_id)[0]

    LOG.tc_step("SSH to the {} where VM is located".format(vm_host))

    with host_helper.ssh_to_host(vm_host) as comp_ssh:
        # code, virsh_list_output = comp_ssh.exec_sudo_cmd(cmd="sudo virsh list | grep --color='never' -o 'instance[^ ]*' ")

        LOG.tc_step("Extract the correct bytes value from virsh dumpxml")

        sed_cmd = "sed -n 's:.*<"+virsh_tag+">\(.*\)</"+virsh_tag+">.*:\\1:p' "

        dump_xml_cmd = "virsh dumpxml "+ instance_name + " | " + sed_cmd
        code, dump_xml_output = comp_ssh.exec_sudo_cmd(cmd=dump_xml_cmd)

    LOG.tc_step("Compare the expected bytes with the bytes from the xmldump")
    assert int(dump_xml_output) == expected_disk_spec_val






