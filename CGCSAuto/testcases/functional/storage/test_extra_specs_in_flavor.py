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
    mark.p2((FlavorSpec.DISK_READ_BYTES,   10485769,    'image')),
    mark.p2((FlavorSpec.DISK_READ_BYTES,   419430400,   'image')),
    mark.p2((FlavorSpec.DISK_READ_IOPS,    200,         'image')),
    mark.p2((FlavorSpec.DISK_READ_IOPS,    5000,        'image')),
    mark.p2((FlavorSpec.DISK_WRITE_BYTES,  10485769,    'image')),
    mark.p2((FlavorSpec.DISK_WRITE_BYTES,  419430400,   'image')),
    mark.p2((FlavorSpec.DISK_WRITE_IOPS,   200,         'image')),
    mark.p2((FlavorSpec.DISK_WRITE_IOPS,   5000,        'image')),
    mark.p2((FlavorSpec.DISK_TOTAL_BYTES,  10000000,    'image')),
    mark.p2((FlavorSpec.DISK_TOTAL_BYTES,  419430400,   'image')),
    mark.p2((FlavorSpec.DISK_TOTAL_IOPS,   500,         'image')),
    mark.p2((FlavorSpec.DISK_TOTAL_IOPS,   5000,        'image')),
    mark.p1((FlavorSpec.DISK_READ_BYTES,   10485769,    'lvm')),
    mark.p1((FlavorSpec.DISK_READ_IOPS,    5000,        'lvm')),
    mark.p1((FlavorSpec.DISK_WRITE_BYTES,  419430400,   'lvm')),
    mark.p1((FlavorSpec.DISK_WRITE_IOPS,   5000,        'lvm')),
    mark.p1((FlavorSpec.DISK_TOTAL_BYTES,  10000000,    'lvm')),
    mark.p1((FlavorSpec.DISK_TOTAL_IOPS,   5000,        'lvm')),
    ]


@fixture(scope='module', params=instance_backing_params)
def config_local_volume_group(request):

    flavor_var= request.param[0]
    flavor_var_value = request.param[1]
    local_volume_type = request.param[2]
    local_volume_group = {
        'flavor_var': flavor_var,
        'flavor_var_value': flavor_var_value,
        'instance_backing': request.param[2]
    }

    # check the local volume group of compute-0 before and changes
    pre_local_volume_type = host_helper.get_local_storage_backing('compute-0', con_ssh=None)

    # if already same local volume type as test skip
    if pre_local_volume_type == local_volume_type:
        return local_volume_group

    # config lvg parameter for instance backing either image/lvm
    host_helper.modify_host_lvg('compute-0', inst_backing=local_volume_type, lvm='nova-local')

    def reset_local_volume_group():
        # reset local volume group back to what it was before
        if local_volume_type != pre_local_volume_type:
            host_helper.modify_host_lvg('compute-0', inst_backing=pre_local_volume_type, lvm='nova-local')
    request.addfinalizer(reset_local_volume_group)

    return local_volume_group


def test_verify_disk_extra_on_virsh(config_local_volume_group):
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
    flavor_var = config_local_volume_group['flavor_var']
    flavor_var_value = config_local_volume_group['flavor_var_value']

    if config_local_volume_group['instance_backing'] == 'remote':
        storage = 'remote'
    else:
        storage = 'local_' + config_local_volume_group['instance_backing']

    # set flavour
    flavor_id = nova_helper.create_flavor(vcpus=4, ram=1024, root_disk=2, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_id)

    # set disk specs on flavour
    quota_disk_spec = {flavor_var: flavor_var_value,
                       'aggregate_instance_extra_specs:storage': storage,
                       'hw:cpu_policy': 'dedicated'
                       }
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **quota_disk_spec)

    # boot vm must be from image
    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]
    ResourceCleanup.add('vm', vm_id)

    virsh_tag = flavor_var.split('quota:disk_')[1]

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
    assert int(dump_xml_output) == flavor_var_value, "Expected disk spec value to be {}. See {} instead".format(flavor_var_value, int(dump_xml_output))






