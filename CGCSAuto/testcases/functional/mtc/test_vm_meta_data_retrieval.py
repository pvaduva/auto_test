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
from testfixtures.fixture_resources import ResourceCleanup


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
    LOG.tc_step("create VM make sure it's pingable")
    vm_id = vm_helper.boot_vm(source='image', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    LOG.tc_step('Query meta-data for vm instance id')
    # retrieve meta instance id by ssh to VM from natbox and wget to remote server
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        command = 'wget http://169.254.169.254/latest/meta-data/instance-id'
        vm_ssh.exec_cmd(command, fail_ok=False)
        command1 = 'more instance-id'
        instance_id_output = vm_ssh.exec_cmd(command1, fail_ok=False)[1]

    LOG.tc_step("Ensure instance id from metadata server is as expected")
    actual_inst_id = instance_id_output.split(sep='-')[1]
    inst_name = nova_helper.get_vm_instance_name(vm_id)
    expt_inst_id = inst_name.split(sep='-')[1]

    assert expt_inst_id == actual_inst_id, "Instance ID retrieved from metadata server is not as expected"
