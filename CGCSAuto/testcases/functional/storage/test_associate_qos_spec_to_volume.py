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
from testfixtures.resource_mgmt import ResourceCleanup
from setup_consts import P1, P2, P3

instance_backing_params = [
    mark.p1(('read_bytes_sec',  10485769,   'image')),
    mark.p1(('read_bytes_sec',  200000000,  'image')),
    mark.p2(('read_bytes_sec',  419430400,  'image')),
    mark.p2(('write_bytes_sec', 10485769,   'image')),
    mark.p2(('write_bytes_sec', 400000000,  'image')),
    mark.p2(('write_bytes_sec', 419430400,  'image')),
    mark.p2(('total_bytes_sec', 10485769,   'image')),
    mark.p2(('total_bytes_sec', 419430400,  'image')),
    mark.p2(('read_iops_sec',   200,        'image')),
    mark.p2(('read_iops_sec',   5000,       'image')),
    mark.p2(('write_iops_sec',  200,        'image')),
    mark.p2(('write_iops_sec',  5000,       'image')),
    mark.p2(('total_iops_sec',  200,        'image')),
    mark.p1(('total_iops_sec',  5000,       'image')),
    mark.p2(('read_bytes_sec',  10485769,   'lvm')),
    mark.p2(('read_bytes_sec',  200000000,  'lvm')),
    mark.p2(('read_bytes_sec',  419430400,  'lvm')),
    mark.p2(('write_bytes_sec', 10485769,   'lvm')),
    mark.p2(('write_bytes_sec', 400000000,  'lvm')),
    mark.p2(('write_bytes_sec', 419430400,  'lvm')),
    mark.p2(('total_bytes_sec', 10485769,   'lvm')),
    mark.p2(('total_bytes_sec', 419430400,  'lvm')),
    mark.p2(('read_iops_sec',   200,        'lvm')),
    mark.p2(('read_iops_sec',   5000,       'lvm')),
    mark.p2(('write_iops_sec',  200,        'lvm')),
    mark.p2(('write_iops_sec',  5000,       'lvm')),
    mark.p2(('total_iops_sec',  200,        'lvm')),
    mark.p2(('total_iops_sec',  5000,       'lvm')),

    ]


@fixture(scope='module', params=instance_backing_params )
def config_local_volume_group(request):

    qos_var = request.param[0]
    qos_var_value = request.param[1]
    local_volume_type = request.param[2]
    local_volume_group = {
        'qos_var': qos_var,
        'qos_var_value': qos_var_value,
        'instance_backing': request.param[2]
    }

    # check the local volume group of compute-0 before and changes
    pre_local_volume_type = host_helper.get_local_storage_backing('compute-0', con_ssh=None)

    # if already same local_volume_type on compute-0 skip config local_volume_type
    if pre_local_volume_type == local_volume_type:
        return local_volume_group

    # config lvg parameter for instance backing either image/lvm
    host_helper.set_host_local_backing_type('compute-0', inst_type=local_volume_type, vol_group='nova-local')

    def reset_local_volume_group():
        # reset local volume group back to what it was before
        if local_volume_type != pre_local_volume_type:
            host_helper.set_host_local_backing_type('compute-0', inst_type=pre_local_volume_type, vol_group='nova-local')
    request.addfinalizer(reset_local_volume_group)

    return local_volume_group


@fixture(scope='module')
def create_qos_specs(request, config_local_volume_group):

    qos_var = config_local_volume_group['qos_var']
    qos_var_value = config_local_volume_group['qos_var_value']

    # consumer must be set to both or xmldump will not display correct tag and data
    qos_dict = {'consumer':'both', qos_var: qos_var_value}
    qos_specs_id = cinder_helper.create_qos_specs("test_qos_specs", **qos_dict)[1]

    qos_specs = {'id': qos_specs_id,
                 'qos_spec': [qos_var, qos_var_value]
                 }

    # associate qos specs to volume_type
    ResourceCleanup.add('qos_spec', qos_specs_id, scope='module')

    return qos_specs


@fixture(scope='module')
def create_volume_type(request):

    volume_type_id = cinder_helper.create_volume_type("test_volume_type")[1]
    volume_type = {'id': volume_type_id
                   }
    ResourceCleanup.add('volume_type', volume_type_id, scope='module')

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


def test_verify_qos_specs(create_qos_specs):

    qos_spec_id_list = cinder_helper.get_qos_list()
    qos_spec_id = create_qos_specs['id']
    LOG.tc_step("Compare the expected qos specs id with actually created qos specs id {}".format(qos_spec_id))
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


def test_verify_disk_extra_on_virsh(create_qos_association):
    """
    from us77170_StorageTestPlan.pdf

    verify the qos extra specs are properly set and matching expecte specs

    Args:
        - Nothing

    Setup:
        - Setup qos specswith specific bytes per second extra specs on specifc volume type


    Test Steps:
        -verify the extra spec is set and match to expected specs on vm through varish cli

    Teardown:
        - delete specific bytes per second extra specs vm/volume-type/qos-specs

    """

    volume_type_id = create_qos_association['volume_type_id']
    qos_spec = create_qos_association['qos_spec']
    img_id = glance_helper.get_image_id_from_name('cgcs-guest')

    # create volume with defined volume type
    volume_id = cinder_helper.create_volume("test_volume", vol_type=volume_type_id, image_id=img_id)[1]
    ResourceCleanup.add('volume', volume_id)

    # create vm from volume
    boot_source = 'volume'
    vm_id = vm_helper.boot_vm(source=boot_source, source_id=volume_id)[1]
    ResourceCleanup.add('vm', vm_id)

    virsh_tag = qos_spec[0]
    expected_disk_spec_val = qos_spec[1]

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

    LOG.tc_step("Compare the expected {} bytes with the bytes from the xmldump".format(expected_disk_spec_val))

    assert int(dump_xml_output) == expected_disk_spec_val, "Expected {} output bytes, But got {} instead"\
        .format(expected_disk_spec_val, int(dump_xml_output))
