
from pytest import fixture, mark, skip
from utils.tis_log import LOG
from consts.cgcs import VMStatus
from keywords import vm_helper, nova_helper, network_helper, host_helper, system_helper

from testfixtures.resource_mgmt import ResourceCleanup


# @fixture(scope='module', autouse=True)
# def check_launch_script_exists():
#     controller = system_helper.get_active_controller_name()
#     with host_helper.ssh_to_host(controller) as con_ssh:
#         cmd = "ls -A /home/sysadmin/instances_group0"
#         if con_ssh.exec_cmd(cmd)[1] == '':
#             skip("Lab setup using heat. No VM launch script.")
#
#
# # Remove since all vm types are already covered by other tests.
# @mark.parametrize('vm_type', [
#     'avp',
#     'vhost',
#     'vswitch',
#     'virtio',
#     # 'pcipt', CGTS-7376
#     'sriov'
# ])
# def _test_vif_models(vm_type):
#     """
#     boot avp,e100 and virtio instance
#     KNI is same as avp
#
#     Test Steps:
#         - boot up a vm with given vm type from script
#         - boot up a base vm with given vm type from script
#         - Ping VM from Natbox(external network)
#         - Live-migrate the VM and verify ping over management and data networks
#         - Cold-migrate the VM and verify ping over management and data networks
#         - Pause and un-pause the VM and verify ping over management and data networks
#         - Suspend and resume the VM and verify ping over management and data networks
#         - Stop and start the VM and verify ping over management and data networks
#         - Reboot the VM and verify ping over management and data networks
#
#     Test Teardown:
#         - Delete vm created
#
#     """
#     vms_launched = vm_helper.launch_vms_via_script(vm_type=vm_type, tenant_name='tenant2')
#     vshell = True if vm_type in ['vhost', 'vswitch'] else False
#
#     if not vms_launched:
#         skip("{} vms cannot be launched".format(vm_type))
#
#     LOG.tc_step("Boot vm to test with vm_type {} from script".format(vm_type))
#     vm_under_test = vms_launched[0]
#     ResourceCleanup.add('vm', vm_under_test)
#
#     LOG.tc_step("Boot a base vm to test with vm_type {} from script".format(vm_type))
#     vms_launched = vm_helper.launch_vms_via_script(vm_type=vm_type, tenant_name='tenant1')
#
#     if not vms_launched:
#         skip("{} vms cannot be launched".format(vm_type))
#
#     base_vm = vms_launched[0]
#     ResourceCleanup.add('vm', base_vm)
#
#     LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_under_test))
#     vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)
#
#     LOG.tc_step("Ping VM's data interface from another vm")
#     vm_helper.ping_vms_from_vm(base_vm, vm_under_test, net_types=['mgmt', 'data'], vshell=vshell)
#
#     for vm_action in [['cold_migrate'], ['live_migrate'], ['pause', 'unpause'], ['suspend', 'resume'],
#                       ['stop', 'start']]:
#         if vm_action[0] == 'auto_recover':
#             LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
#                         "base vm over management and data networks")
#             vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
#             vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
#         else:
#             LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_action))
#             for action in vm_action:
#                 if action is 'live_migrate' and vm_type in ['sriov', 'pcipt']:
#                     kwargs = {'fail_ok': True}
#                 else:
#                     kwargs = {}
#
#                 code = vm_helper.perform_action_on_vm(vm_under_test, action=action, **kwargs)[0]
#
#                 if kwargs != {}:
#                     assert 6 == code, 'Expected {} type vm to fail live-migration. VM migrated.'.format(vm_type)
#
#         vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)
#
#         LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works "
#                     "after {}".format(vm_action))
#         vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'], vshell=vshell)
