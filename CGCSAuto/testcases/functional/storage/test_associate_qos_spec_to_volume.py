###
# below testcases is part of us77170_StorageTestPlan.pdf specifically under
# https://jive.windriver.com/docs/DOC-45652
# It specifically test scenarios where an qos Specs created with read/write/total in bytes/iops
# and volumes type associated with those qos specs
# and when VMs are created using those volume types, they were checked that that those specs hold true on vms.
###


from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.reasons import SkipReason
from consts.cgcs import QoSSpecs, FlavorSpec
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module', params=['local_image', 'local_lvm'])
def flavor_hosts_with_backing(request):
    storage_backing = request.param

    LOG.fixture_step("Get hosts with {} backing".format(storage_backing))
    hosts = host_helper.get_hosts_by_storage_aggregate(storage_backing=storage_backing)
    if not hosts:
        skip(SkipReason.NO_HOST_WITH_BACKING.format(storage_backing))

    LOG.fixture_step("Create a flavor with {} backing".format(storage_backing))
    flavor = nova_helper.create_flavor(storage_backing, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor, scope='module')
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.STORAGE_BACKING: storage_backing})

    return flavor, hosts


@mark.parametrize(('qos_spec', 'qos_spec_val'), [
    mark.p1((QoSSpecs.READ_BYTES,  10485769)),
    mark.p1((QoSSpecs.READ_BYTES,  200000000)),
    mark.p2((QoSSpecs.READ_BYTES,  419430400)),
    mark.p2((QoSSpecs.WRITE_BYTES, 10485769)),
    mark.p2((QoSSpecs.WRITE_BYTES, 400000000)),
    mark.p2((QoSSpecs.WRITE_BYTES, 419430400)),
    mark.p2((QoSSpecs.TOTAL_BYTES, 10485769)),
    mark.p2((QoSSpecs.TOTAL_BYTES, 419430400)),
    mark.p2((QoSSpecs.READ_IOPS,   200)),
    mark.p2((QoSSpecs.READ_IOPS,   5000)),
    mark.p2((QoSSpecs.WRITE_IOPS,  200)),
    mark.p2((QoSSpecs.WRITE_IOPS,  5000)),
    mark.p2((QoSSpecs.TOTAL_IOPS,  200)),
    mark.p1((QoSSpecs.TOTAL_IOPS,  5000)),
    ])
def test_verify_disk_extra_on_virsh(qos_spec, qos_spec_val, flavor_hosts_with_backing):
    """
    from us77170_StorageTestPlan.pdf

    Verify the qos extra specs via virsh cmd

    Setup:
        - Check storage backing and create flavor with storage backing under test

    Test Steps:
        - Create QoS with given QoS spec and value
        - Create a volume type
        - Associate QoS spec to the volume type
        - Create a volume from above volume type
        - Boot a vm using above flavor and volume
        - Check actual QoS spec for vm via virsh command on vm host

    Teardown:
        - Delete created VM, QoS, volume type
        - Delete created flavor         (module)

    """

    flavor, expt_hosts = flavor_hosts_with_backing

    qos_specs = {qos_spec: qos_spec_val}
    name_str = "qos_{}_{}".format(qos_spec, qos_spec_val)

    LOG.tc_step("Create QoS spec: {}".format(qos_specs))
    # consumer must be set to both or xmldump will not display correct tag and data
    qos_id = cinder_helper.create_qos_specs(consumer='both', qos_name=name_str, **qos_specs)[1]
    ResourceCleanup.add('qos', qos_id)

    LOG.tc_step("Create volume type and associate above QoS spec to it")
    volume_type_id = cinder_helper.create_volume_type("test_volume_type")[1]
    ResourceCleanup.add('volume_type', volume_type_id)

    cinder_helper.associate_qos_to_volume_type(qos_id, volume_type_id)

    img_id = glance_helper.get_image_id_from_name('cgcs-guest')

    LOG.tc_step("Create volume with above volume type")
    volume_id = cinder_helper.create_volume(name_str, vol_type=volume_type_id, image_id=img_id)[1]
    ResourceCleanup.add('volume', volume_id)

    # create vm from volume
    vm_id = vm_helper.boot_vm(name_str, flavor=flavor, source='volume', source_id=volume_id)[1]
    ResourceCleanup.add('vm', vm_id)

    vm_host = nova_helper.get_vm_host(vm_id)
    assert vm_host in expt_hosts

    instance_name = nova_helper.get_vm_instance_name(vm_id)

    LOG.tc_step("Check VM QoS spec {} is {} via 'virsh dumpxml' on {}".format(qos_spec, qos_spec_val, vm_host))

    with host_helper.ssh_to_host(vm_host) as host_ssh:

        sed_cmd = "sed -n 's:.*<" + qos_spec + ">\(.*\)</" + qos_spec + ">.*:\\1:p' "
        dump_xml_cmd = "virsh dumpxml " + instance_name + " | " + sed_cmd

        code, dump_xml_output = host_ssh.exec_sudo_cmd(cmd=dump_xml_cmd)
        LOG.info("Virsh output: {}".format(dump_xml_output))

    assert qos_spec_val == int(dump_xml_output), "Expected {} output bytes, but got {} bytes instead"\
        .format(qos_spec_val, int(dump_xml_output))
