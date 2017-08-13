import time
from pytest import skip
from utils.tis_log import LOG

from keywords import system_helper, host_helper, vm_helper
from testfixtures.resource_mgmt import ResourceCleanup


def test_swact_20_times():
    """
    Skip Condition:
        - Less than two controllers on system

    Test Steps:
        - Boot a vm and ensure it's pingable
        - Start writing from pre-existed vm before swacting
        - Repeat following steps 20 times:
            - ensure system has standby controller
            - system host-swact
            - ensure all services are active in sudo sm-dump on new active controller
            - ensure pre-existed vm is still pingable from NatBox
            - ensure writing did not stop on pre-existed vm
            - ensure new vm can be launched in 2 minutes
            - ensure newly booted vm is pingable from NatBox
            - delete newly booted vm

    Teardown:
        - delete vms, volumes

    """
    if len(system_helper.get_controllers()) < 2:
        skip("Less than two controllers on system")

    if not system_helper.get_standby_controller_name():
        assert False, "No standby controller on system"

    LOG.tc_step("Boot a vm and ensure it's pingable")
    vm_base = vm_helper.boot_vm(name='pre_swact', cleanup='function')[1]

    LOG.tc_step("Start writing from pre-existed vm before swacting")
    vm_ssh, base_vm_thread = vm_helper.write_in_vm(vm_base, end_now_flag=True, expect_timeout=40, thread_timeout=60*100)
    base_vm_thread.end_now = False
    base_vm_thread.end_thread()
    # base_vm_thread.wait_for_thread_end(timeout=base_vm_thread.timeout)

    try:
        for i in range(20):
            iter_str = "Swact iter{}/20 - ".format(i+1)

            LOG.tc_step("{}Ensure system has standby controller".format(iter_str))
            standby = system_helper.get_standby_controller_name()
            assert standby

            LOG.tc_step("{}Swact active controller and ensure active controller is changed".format(iter_str))
            host_helper.swact_host()

            LOG.tc_step("{}Check all services are up on active controller via sudo sm-dump".format(iter_str))
            host_helper.wait_for_sm_dump_desired_states(controller=standby, fail_ok=False)

            LOG.tc_step("{}Ensure pre-exist vm still pingable post swact".format(iter_str))
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_base, timeout=30)

            time.sleep(5)
            LOG.tc_step("{}Ensure writing from pre-existed vm resumes after swact".format(iter_str))
            assert base_vm_thread.res is True, "Writing in pre-existed vm stopped after {}".format(iter_str.lower())

            LOG.tc_step("{}Attemp to boot new vm after 2 minutes of post swact and ensure it's pingable".
                        format(iter_str))
            time.sleep(60)
            for j in range(3):
                code, vm_new, msg, vol = vm_helper.boot_vm(name='post_swact', fail_ok=True, cleanup='function')

                if code == 0:
                    break

                LOG.warning("VM failed to boot - attempt{}".format(j+1))
                vm_helper.delete_vms(vms=vm_new)
                assert j < 2, "No vm can be booted 2+ minutes after swact"

                LOG.tc_step("{}VM{} failed to boot, wait for 30 seconds and retry".format(j+1, iter_str))
                time.sleep(30)

            vm_helper.wait_for_vm_pingable_from_natbox(vm_new)

            LOG.tc_step("{}Delete the vm created".format(iter_str))
            vm_helper.delete_vms(vms=vm_new)
    except:
        raise
    finally:
        LOG.tc_step("End the base_vm_thread")
        base_vm_thread.end_now = True
        base_vm_thread.wait_for_thread_end(timeout=10)

    post_standby = system_helper.get_standby_controller_name()
    assert post_standby, "System does not have standby controller after last swact"
