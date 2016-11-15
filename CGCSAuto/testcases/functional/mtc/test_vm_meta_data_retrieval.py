import time
import sys
from pytest import fixture, mark
import re
from utils import cli
from utils import table_parser
from utils.ssh import NATBoxClient
from utils.tis_log import LOG
from consts.timeout import VMTimeout, EventLogTimeout
from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus, EventLogID
from consts.auth import Tenant
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.sanity
def test_vm_meta_data_retrieval():
    """
    VM meta-data retrieval

    ssh ubuntu@<vm_private_ip>
    wget http://169.254.169.254/latest/meta-data/instance-id

    VM meta-data retrieval

    Test Steps:
        - create VM from image
        - retrieve meta data of instance id from  wget http://169.254.169.254/latest/meta-data/instance-id
        - compare instance id to the id from nova show vm_id
        - Pass if the result are the same

    Test Teardown:
        - Delete vms, volumes, flavor created


    """
    LOG.debug('Booting ubuntu VM')
    sourceid = glance_helper.get_image_id_from_name('cgcs-guest', strict=True)

    # create VM make sure it's pingable
    vm_id = vm_helper.boot_vm(source='image', source_id=sourceid)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    LOG.debug('Query meta-data')
    # retrieve meta instance id by ssh to VM from natbox and wget to remote server
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        command = 'wget http://169.254.169.254/latest/meta-data/instance-id'
        vm_ssh.exec_cmd(command)
        command1 = 'more instance-id'
        exitcode, instance_id_output = vm_ssh.exec_cmd(command1)

    instance_id_output = re.findall(r'\-\s*(\w+)', instance_id_output)
    LOG.info("Instance ID output from meta-data: {}".format(instance_id_output))

    # compare the retrieved meta data to nova show vm's OS-EXT-SRV-ATTR:instance_name variable
    instance_id = ['OS-EXT-SRV-ATTR:instance_name']
    table_instance_id = nova_helper.get_vm_nova_show_values(vm_id, instance_id)[0]
    LOG.info("Instance ID from table: {}".format(table_instance_id))
    table_instance_id = re.findall(r'\-\s*(\w+)', table_instance_id)
    LOG.info("Instance ID value from table: {}".format(table_instance_id))

    assert instance_id_output == table_instance_id, "Expected {} = to {}".format(instance_id_output,table_instance_id)
