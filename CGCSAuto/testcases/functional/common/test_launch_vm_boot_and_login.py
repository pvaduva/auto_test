###
# test_584_lock_unlock_compute_node sanity_juno_unified_R3.xls
###

from pytest import fixture, mark, skip
from time import sleep

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import EventLogID, FlavorSpec, VMStatus
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, glance_helper,cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


def test_launch_vm_boot_and_login():
    """
    Verify the lab is able to boot up an VM from image and login through natbox

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        -boot up vm using default image
        - login into vm and excute 'whoami' expect user to be root

    Teardown:
        - Nothing

    """
    LOG.tc_step('Boot up a VM instance from image')
    boot_source = 'image'
    vm_id = vm_helper.boot_vm(source=boot_source)[1]
    ResourceCleanup.add('vm', vm_id, scope='module')
    vm_state = nova_helper.get_vm_status(vm_id)
    print(vm_state)
    assert vm_state == VMStatus.ACTIVE

    LOG.tc_step('Login into the VM and excute "whami" cli. Expect "root" to be returned ')
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        cmd = "whoami"
        cmd_output= vm_ssh.wait_for_cmd_output(cmd, 'root', timeout=10, strict=False, expt_timeout=3, check_interval=2)

    assert cmd_output, 'Expect "root" to be returned. However, this was not the case'
