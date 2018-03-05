###
# below testcases is part of us77170_StorageTestPlan.pdf specifically under
# https://jive.windriver.com/docs/DOC-45652
# It specifically test scenarios where an qos Specs created with read/write/total in bytes/iops
# and volumes type associated with those qos specs
# and when VMs are created using those volume types, they were checked that that those specs hold true on vms.
###


from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.cgcs import QoSSpec, FlavorSpec
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def hosts_with_backing():
    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()

    LOG.fixture_step("Hosts with {} backing: {}".format(storage_backing, hosts))
    return storage_backing, hosts


class TestQoS:
    @fixture(scope='class')
    def flavor_for_qos_test(self, hosts_with_backing):
        storage_backing, hosts = hosts_with_backing

        LOG.fixture_step("Create a flavor with {} backing".format(storage_backing))
        flavor = nova_helper.create_flavor(storage_backing, check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor, scope='class')
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.STORAGE_BACKING: storage_backing})

        return flavor, hosts

    @mark.parametrize(('qos_spec', 'qos_spec_val'), [
        mark.p1((QoSSpec.READ_BYTES, 10485769)),
        mark.p1((QoSSpec.READ_BYTES, 200000000)),
        mark.p2((QoSSpec.READ_BYTES, 419430400)),
        mark.p2((QoSSpec.WRITE_BYTES, 10485769)),
        mark.p2((QoSSpec.WRITE_BYTES, 400000000)),
        mark.p2((QoSSpec.WRITE_BYTES, 419430400)),
        mark.p2((QoSSpec.TOTAL_BYTES, 10485769)),
        mark.p2((QoSSpec.TOTAL_BYTES, 419430400)),
        mark.p2((QoSSpec.READ_IOPS, 200)),
        mark.p2((QoSSpec.READ_IOPS, 5000)),
        mark.p2((QoSSpec.WRITE_IOPS, 200)),
        mark.p2((QoSSpec.WRITE_IOPS, 5000)),
        mark.p2((QoSSpec.TOTAL_IOPS, 200)),
        mark.p1((QoSSpec.TOTAL_IOPS, 5000)),
        ])
    def test_disk_read_write_qos_specs(self, qos_spec, qos_spec_val, flavor_for_qos_test):
        """
        from us77170_StorageTestPlan.pdf

        Verify disk speed qos specs via virsh cmd

        Setup:
            - Check storage backing and create flavor with storage backing under test   (module)

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

        flavor, expt_hosts = flavor_for_qos_test

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

        LOG.tc_step("Create volume with above volume type")
        volume_id = cinder_helper.create_volume(name_str, vol_type=volume_type_id)[1]
        ResourceCleanup.add('volume', volume_id)

        LOG.tc_step("Boot vm from above volume that has the disk QoS info")
        vm_id = vm_helper.boot_vm(name_str, flavor=flavor, source='volume', source_id=volume_id, cleanup='function')[1]

        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host in expt_hosts

        instance_name = nova_helper.get_vm_instance_name(vm_id)

        LOG.tc_step("Check VM disk {} is {} via 'virsh dumpxml' on {}".format(qos_spec, qos_spec_val, vm_host))

        with host_helper.ssh_to_host(vm_host) as host_ssh:

            sed_cmd = "sed -n 's:.*<" + qos_spec + ">\(.*\)</" + qos_spec + ">.*:\\1:p' "
            dump_xml_cmd = "virsh dumpxml " + instance_name + " | " + sed_cmd

            code, dump_xml_output = host_ssh.exec_sudo_cmd(cmd=dump_xml_cmd)
            LOG.info("Virsh output: {}".format(dump_xml_output))

        assert qos_spec_val == int(dump_xml_output), "Expected {} output bytes, but got {} bytes instead"\
            .format(qos_spec_val, int(dump_xml_output))


class TestFlavor:

    @mark.parametrize(('disk_spec_name', 'disk_spec_val'), [
        mark.p2((FlavorSpec.DISK_READ_BYTES,   10485769)),
        mark.p2((FlavorSpec.DISK_READ_BYTES,   419430400)),
        mark.p2((FlavorSpec.DISK_READ_IOPS,    200)),
        mark.p2((FlavorSpec.DISK_READ_IOPS,    5000)),
        mark.p2((FlavorSpec.DISK_WRITE_BYTES,  10485769)),
        mark.p2((FlavorSpec.DISK_WRITE_BYTES,  419430400)),
        mark.p2((FlavorSpec.DISK_WRITE_IOPS,   200)),
        mark.p2((FlavorSpec.DISK_WRITE_IOPS,   5000)),
        mark.p2((FlavorSpec.DISK_TOTAL_BYTES,  10000000)),
        mark.p2((FlavorSpec.DISK_TOTAL_BYTES,  419430400)),
        mark.p2((FlavorSpec.DISK_TOTAL_IOPS,   500)),
        mark.p2((FlavorSpec.DISK_TOTAL_IOPS,   5000)),
    ])
    def test_disk_read_write_flavor_specs(self, disk_spec_name, disk_spec_val, hosts_with_backing):
        """
        from us77170_StorageTestPlan.pdf

        Verify disk speed flavor extra specs via virsh cmd

        Setup:
            - Check storage backing for existing hosts

        Test Steps:
            - Create flavor with 4 vpus, 1G ram, 2G root disk
            - Add disk speed extra specs and storage backing under test
            - Boot a vm from image using above flavor
            - Check actual disk speed spec for vm via virsh command on vm host

        Teardown:
            - Delete created VM, flavor

        """
        storage_backing, expt_hosts = hosts_with_backing
        disk_spec_str = disk_spec_name.split('quota:disk_')[1]

        name_str = 'flv_{}_{}'.format(disk_spec_str, disk_spec_val)

        LOG.tc_step("Create flavor with 4 vpus, 1G ram, 2G root disk")
        flavor_id = nova_helper.create_flavor(name_str, vcpus=4, ram=1024, root_disk=2, check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor_id)

        extra_specs = {disk_spec_name: disk_spec_val,
                       FlavorSpec.STORAGE_BACKING: storage_backing,
                       FlavorSpec.CPU_POLICY: 'dedicated'
                       }

        LOG.tc_step("Set following extra specs: {}".format(extra_specs))
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

        LOG.tc_step("Boot vm from image with above flavor that has the disk speed info")
        # boot vm must be from image
        # TODO: why has to boot from image?
        boot_source = 'image'
        vm_id = vm_helper.boot_vm(name_str, flavor=flavor_id, source=boot_source, cleanup='function')[1]

        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host in expt_hosts, "VM host is not on {} host".format(storage_backing)

        instance_name = nova_helper.get_vm_instance_name(vm_id)

        LOG.tc_step("Check VM spec {} is {} via 'virsh dumpxml' on {}".format(disk_spec_str, disk_spec_val, vm_host))

        with host_helper.ssh_to_host(vm_host) as comp_ssh:

            # TODO: parse after virsh dump. Otherwise debugging is difficult upon test failure.

            sed_cmd = "sed -n 's:.*<"+disk_spec_str+">\(.*\)</"+disk_spec_str+">.*:\\1:p' "

            dump_xml_cmd = "virsh dumpxml " + instance_name + " | " + sed_cmd
            code, dump_xml_output = comp_ssh.exec_sudo_cmd(cmd=dump_xml_cmd)

        assert disk_spec_val == int(dump_xml_output), \
            "VM {} value is {} instead of {} in virsh".format(disk_spec_str, int(dump_xml_output), disk_spec_val)
