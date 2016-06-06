###
# below testcases is part of us77170_StorageTestPlan.pdf specifically under
# https://jive.windriver.com/docs/DOC-45652
# It specifically test scenarios where an qos Specs created with read/write/total in bytes/iops
# and volumes type associated with those qos specs
# and when VMs are created using those volume types, they were checked that that those specs hold true on vms.
###



from pytest import fixture, mark, skip
from time import sleep
import ast

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper,cinder_helper,glance_helper
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

    # config lvg parameter for instance backing either image/lvm
    cli.system('host-lvg-modify', lvg_args, auth_info=Tenant.ADMIN, fail_ok=False)

    # unlock the node
    host_helper.unlock_host('compute-0')

    local_volume_group = {'instance_backing': request.param}

    return local_volume_group


qos_spec_params = [
        ('read_bytes_sec',  10485769),
        ('read_bytes_sec',  200000000),
        ('read_bytes_sec',  419430400),
        ('write_bytes_sec', 10485769),
        ('write_bytes_sec', 400000000),
        ('write_bytes_sec', 419430400),
        ('total_bytes_sec', 10485769),
        ('total_bytes_sec', 419430400),
        ('read_iops_sec',   200),
        ('read_iops_sec',   5000),
        ('write_iops_sec',  200),
        ('write_iops_sec',  5000),
        ('total_iops_sec',  200),
        ('total_iops_sec',  5000),

    ]

@fixture(scope='module', params=qos_spec_params)
def create_qos_specs(request, config_local_volume_group):

    # consumer must be set to both or xmldump will not display correct tag and data
    qos_dict = {'consumer':'both', request.param[0]: request.param[1]}
    qos_specs_id = cinder_helper.create_qos_specs("test_qos_specs", **qos_dict)[1]

    qos_specs = {'id': qos_specs_id,
                 'qos_spec': [request.param[0], request.param[1]]
                 }

    # associate qos specs to volume_type

    def delete_qos_specs():
        cinder_helper.delete_qos_specs(qos_specs_id)
    request.addfinalizer(delete_qos_specs)

    return qos_specs


@fixture(scope='module')
def create_volume_type(request):

    volume_type_id = cinder_helper.create_volume_type("test_volume_type")[1]

    volume_type = {'id': volume_type_id
                   }

    def delete_volume_type():
        cinder_helper.delete_volume_type(volume_type_id)
    request.addfinalizer(delete_volume_type)

    return volume_type


@fixture(scope='module')
def create_qos_association(request, create_volume_type, create_qos_specs):

    volume_type_id = create_volume_type['id']
    qos_specs_id = create_qos_specs['id']
    qos_spec = create_qos_specs['qos_spec']
    cinder_helper.associate_qos_to_volume_type(qos_specs_id, volume_type_id)

    qos_association = {'qos_id': qos_specs_id,
                       'volume_type_id': volume_type_id,
                       'qos_spec': qos_spec
                       }

    def delete_qos_association():
        cinder_helper.disassociate_qos_to_volume_type(qos_specs_id, volume_type_id)
    request.addfinalizer(delete_qos_association)

    return qos_association


@fixture(scope='module')
def create_volume_with_type(request, create_qos_association):

    volume_type_id = create_qos_association['volume_type_id']
    qos_spec = create_qos_association['qos_spec']

    img_id = glance_helper.get_image_id_from_name('cgcs-guest')

    volume_id = cinder_helper.create_volume("test_volume", vol_type=volume_type_id,image_id=img_id )[1]

    table_ = table_parser.table(cli.cinder('type-list', auth_info=Tenant.ADMIN))
    volume_type_name = table_parser.get_values(table_, 'Name', ID=volume_type_id)

    volume = {'id': volume_id,
              'volume_type_id': volume_type_id,
              'volume_type_name': volume_type_name,
              'qos_spec': qos_spec
              }

    def delete_volume():
        cinder_helper.delete_volumes(volume_id)
    request.addfinalizer(delete_volume)

    return volume


@fixture(scope='module')
def create_vm_with_volume(request, create_volume_with_type):

    volume_id = create_volume_with_type['id']
    volume_type_id = create_volume_with_type['volume_type_id']
    volume_type_name = create_volume_with_type['volume_type_name']
    qos_spec = create_volume_with_type['qos_spec']

    boot_source = 'volume'
    vm_id = vm_helper.boot_vm( source=boot_source, source_id=volume_id)[1]

    vm = {'id': vm_id,
          'volume_type_id': volume_type_id,
          'volume_type_name': volume_type_name,
          'qos_spec': qos_spec
          }

    def delete_vm():
        vm_helper.delete_vms(vm_id, delete_volumes=True)
    request.addfinalizer(delete_vm)

    return vm


def test_verify_volume_type(create_volume_type):
    # use cinder type list find the newly create volume id exist

    LOG.tc_step("Compare the expected volume type with created volume type id")
    vol_type_id_list = cinder_helper.get_type_list()
    volume_type_id = create_volume_type['id']

    assert volume_type_id in vol_type_id_list, "expected volume type ID {} to be created. Actual ID is not in " \
                                               "cinder type-list: {}.".format(volume_type_id, vol_type_id_list)


def test_verify_qos_specs(create_qos_specs):

    LOG.tc_step("Compare the expected qos specs id with actually created qos specs id")
    qos_spec_id_list = cinder_helper.get_qos_list()
    qos_spec_id = create_qos_specs['id']

    assert qos_spec_id in qos_spec_id_list, "expected QOS specs ID to be {}. Actual ID is not in " \
                                            "cinder qos-list: {}.".format(qos_spec_id, qos_spec_id_list)


def test_associate_qos_spec_to_volume_type(create_qos_association):

    volume_type_id = create_qos_association['volume_type_id']
    qos_spec_id = create_qos_association['qos_id']

    LOG.tc_step("Compare the expected qos associated volume-id with actual volume-id")
    table_ = cinder_helper.get_qos_association(qos_spec_id)
    match_volume_type_id = table_parser.get_values(table_, 'ID', ID=volume_type_id)[0]

    assert volume_type_id == match_volume_type_id, "After QOS Association with volume type, expect associated volume " \
                                                   "ID to be {}. Actual volume ID is {} instead.".\
        format(volume_type_id, match_volume_type_id)


def test_create_volume_with_volume_type(create_volume_with_type):
    volume_id = create_volume_with_type['id']
    volume_type_id = create_volume_with_type['volume_type_id']
    volume_type_name = create_volume_with_type['volume_type_name']

    LOG.tc_step("Compare the expected volume type with actual volume type that was created using cinder list")
    table_ = table_parser.table(cli.cinder('list --all-tenant', auth_info=Tenant.ADMIN))
    match_vol_type_name = table_parser.get_values(table_, 'Volume Type', ID=volume_id)

    assert volume_type_name == match_vol_type_name, "After create a volume with ID {} use volume type name: {}. " \
                                                    "Actual create volume contain volume type name: {}" \
                                                    "".format(volume_id, volume_type_name, match_vol_type_name)


def test_verify_disk_extra_on_virsh(create_vm_with_volume):
    """
    from us77170_StorageTestPlan.pdf

    verify the qos extra specs are properly set and matching expecte specs

    Args:
        - Nothing

    Setup:
        - Setup flavor with specific bytes per second extra specs


    Test Steps:
        -verify the extra spec is set and match to expected specs

    Teardown:
        - delete specific bytes per second extra specs

    """
    vm_id = create_vm_with_volume['id']
    disk_extra_spec = create_vm_with_volume['qos_spec']
    virsh_tag = disk_extra_spec[0]
    expected_disk_spec_val = disk_extra_spec[1]

    LOG.tc_step("Look up vm-topology cli for which host vm is located")

    vm_host_table = system_helper.get_vm_topology_tables('servers')[0]

    vm_host = table_parser.get_values(vm_host_table,'host', ID=vm_id)[0]

    instance_name = table_parser.get_values(vm_host_table, 'instance_name', ID=vm_id)[0]

    LOG.tc_step("SSH to the {} where VM is located".format(vm_host))

    with host_helper.ssh_to_host(vm_host) as comp_ssh:

        LOG.tc_step("Extract the correct bytes value from virsh dumpxml")

        sed_cmd = "sed -n 's:.*<"+virsh_tag+">\(.*\)</"+virsh_tag+">.*:\\1:p' "

        dump_xml_cmd = "virsh dumpxml "+ instance_name + " | " + sed_cmd
        code, dump_xml_output = comp_ssh.exec_sudo_cmd(cmd=dump_xml_cmd)

    LOG.tc_step("Compare the expected bytes with the bytes from the xmldump")

    assert int(dump_xml_output) == expected_disk_spec_val, "Expected {} output bytes, But got {} instead"\
        .format(expected_disk_spec_val, int(dump_xml_output))
