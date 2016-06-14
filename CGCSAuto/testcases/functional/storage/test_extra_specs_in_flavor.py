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
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3


instance_backing_params =['image', 'lvm']


@fixture(scope='module', params=instance_backing_params )
def config_local_volume_group(request):

    local_volume_group = {'instance_backing': request.param}
    #check the local volume group of compute-0
    table_ = table_parser.table(cli.system('host-lvg-show compute-0 nova-local', auth_info=Tenant.ADMIN, fail_ok=False))

    instance_backing = table_parser.get_value_two_col_table(table_,'parameters')
    inst_back = ast.literal_eval(instance_backing)['instance_backing']

    # if already same lvm skip
    if inst_back == request.param:
        return local_volume_group

    lvg_args = "-b "+request.param+" compute-0 nova-local"
    host_helper.lock_host('compute-0')
    #could be a bug seems to cause host-lvg-modify to fail add timer work around it
    #sleep(10)
    # config lvg parameter for instance backing either image/lvm
    cli.system('host-lvg-modify', lvg_args, auth_info=Tenant.ADMIN, fail_ok=False)

    # unlock the node
    host_helper.unlock_host('compute-0')

    local_volume_group = {'instance_backing': request.param}

    return local_volume_group


disk_spec_params = [
        ('quota:disk_read_bytes_sec',   10485769),
        ('quota:disk_read_bytes_sec',   419430400),
        ('quota:disk_read_iops_sec',    200),
        ('quota:disk_read_iops_sec',    5000),
        ('quota:disk_write_bytes_sec',  10485769),
        ('quota:disk_write_bytes_sec',  419430400),
        ('quota:disk_write_iops_sec',   200),
        ('quota:disk_write_iops_sec',   5000),
        ('quota:disk_total_bytes_sec',  10000000),
        ('quota:disk_total_bytes_sec',  419430400),
        ('quota:disk_total_iops_sec',   500),
        ('quota:disk_total_iops_sec',   5000),
    ]


@fixture(scope='module', params=disk_spec_params)
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
    if config_local_volume_group['instance_backing'] == 'remote':
        storage = 'remote'
    else:
        storage = 'local_'+config_local_volume_group['instance_backing']

    if len(host_helper.get_hosts_by_storage_aggregate(storage_backing=storage)) < 1:
        skip("No host support {} storage backing".format(storage))

    flavor_id = nova_helper.create_flavor(vcpus=4, ram=1024, root_disk=2)[1]
    quota_disk_spec = {request.param[0]: request.param[1],
                       'aggregate_instance_extra_specs:storage': storage,
                       'hw:cpu_policy': 'dedicated'
                       }

    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **quota_disk_spec)
    flavor = {'id': flavor_id,
              'disk_spec': [request.param[0], request.param[1]],
              'storage_spec': storage
              }

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor)

    return flavor


@fixture(scope='module')
def vm_with_disk_spec(request, flavor_with_disk_spec):

    flavor_id = flavor_with_disk_spec['id']
    disk_extra_spec = flavor_with_disk_spec['disk_spec']
    storage_extra_spec = flavor_with_disk_spec['storage_spec']

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]

    vm = {'id': vm_id,
          'disk_spec': disk_extra_spec,
          'storage_spec': storage_extra_spec
          }

    def delete_disk_spec_vm():
        vm_helper.delete_vms(vm_id, delete_volumes=True)
    request.addfinalizer(delete_disk_spec_vm)

    return vm


def test_disk_extra_spec(flavor_with_disk_spec):
    """
    from us77170_StorageTestPlan.pdf

    verify the extra specs are properly set and matching expecte specs

    Args:
        - Nothing

    Setup:
        - Setup flavor with specific bytes per second extra specs


    Test Steps:
        -verify the extra spec is set and match to expected specs

    Teardown:
        - delete specific bytes per second extra specs

    """
    flavor_id = flavor_with_disk_spec['id']
    extra_spec = flavor_with_disk_spec['disk_spec']

    flavor_extra_specs = nova_helper.get_flavor_extra_specs(flavor_id)
    LOG.tc_step("Verify the disk extra spec for specific flavor is setup correctly")

    assert flavor_extra_specs[extra_spec[0]] == str(extra_spec[1]), "Expected extra_spec {} to be {}. However, " \
                                                                    "it was {}".format(extra_spec, str(extra_spec[1]),
                                                                                       flavor_extra_specs[extra_spec])


def test_verify_disk_extra_on_vm( vm_with_disk_spec):
    """
    from us77170_StorageTestPlan.pdf
    verify the extra specs from flavor is created set on vm

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
    disk_spec = vm_with_disk_spec['disk_spec']
    vm_id = vm_with_disk_spec['id']
    LOG.tc_step("Check vm using nova list then verify the flavor is added to VM")
    # check vm using nova list then verfiy the flavour is added to vm
    vm_flavour_id = nova_helper.get_vm_flavor(vm_id)
    # retrieve flavor id
    LOG.tc_step("Compare the expected flavor ID with flavor ID attached to VM")
    vm_flavor_extra_specs = nova_helper.get_flavor_extra_specs(vm_flavour_id)

    assert vm_flavor_extra_specs[disk_spec[0]] == str(disk_spec[1]), "Expected extra_spec {} to be {}. However, it " \
                                                                     "was {}".format(disk_spec, str(disk_spec[1]),
                                                                                     vm_flavor_extra_specs[disk_spec])


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






