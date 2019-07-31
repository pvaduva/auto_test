import time
from threading import Event
from pytest import fixture, mark, skip

from keywords import nova_helper, vm_helper, host_helper
from consts.stx import FlavorSpec
from utils.tis_log import LOG
from utils.multi_thread import MThread


@fixture(scope='module')
def check_hypervisors():
    hypervisors = host_helper.get_up_hypervisors()
    if len(hypervisors) < 2:
        skip("Less than two hypervisors for migration test")


@fixture(scope='module')
def flavors():
    flvs = {}
    for numa in ['0', '1']:
        numa_flv = nova_helper.create_flavor(name='numa{}'.format(numa), vcpus=2)[1]
        # ResourceCleanup.add('flavor', numa_flv, scope='module')
        flvs['numa{}'.format(numa)] = numa_flv
        extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: numa}
        nova_helper.set_flavor(numa_flv, **extra_specs)

    return flvs


def launch_delete_vms(flavors, end_time, end_event):
    iter_ = 0
    while time.time() < end_time:
        if end_event.is_set():
            assert 0, "Other thread failed. Terminate launch_del_vms thread"

        iter_ += 1
        LOG.info("Iter{} - Launch and delete vm0 on numa0 and vm1 on numa1".format(iter_))
        vms = []
        for name, flv_id in flavors.items():
            vm_id = vm_helper.boot_vm(name=name, flavor=flv_id)[1]
            vms.append(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

        time.sleep(15)
        vm_helper.delete_vms(vms=vms)


def live_migrate_vm(end_time, end_event):
    ded_flv = nova_helper.create_flavor(name='dedicated', vcpus=2)[1]
    nova_helper.set_flavor(ded_flv, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    vm_id = vm_helper.boot_vm(name='live-mig', flavor=ded_flv)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    while time.time() < end_time:
        if end_event.is_set():
            assert 0, "Other thread failed. Terminate live-mgiration thread."

        time.sleep(15)
        LOG.tc_step("Live migrate live-mig vm")
        vm_helper.live_migrate_vm(vm_id=vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


def test_live_migrate_while_launch_delete_vms(check_hypervisors, flavors):
    """
    Launch/delete vms while live migrating another vm
    Args:
        flavors:

    Test Steps:
        - Thread_1: Launch a 2vcpu vm with dedicated policy and keep live migrating it
        - Thread_2: Launch a 2vcpu-dedicated-vm on numa0, and another on numa1; stop and Delete them. Repeat.

    """
    end_event = Event()
    run_time = 10 * 3600
    # run_time = 300
    start_time = time.time()
    end_time = start_time + run_time
    thread_timeout = run_time + 300

    thread_1 = MThread(live_migrate_vm, end_time, end_event=end_event)
    thread_2 = MThread(launch_delete_vms, flavors, end_time, end_event=end_event)

    LOG.info("Starting threads")
    thread_1.start_thread(thread_timeout)
    thread_2.start_thread(thread_timeout)
    is_ended_1, error_1 = thread_1.wait_for_thread_end(fail_ok=True)
    is_ended_2, error_2 = thread_2.wait_for_thread_end(fail_ok=True)

    assert is_ended_1 and not error_1, "Threaded ended: {}. Error: {}".format(is_ended_1, error_1)
    assert is_ended_2 and not error_2, "Threaded ended: {}. Error: {}".format(is_ended_2, error_2)


def launch_delete_vm(flavor, end_time, end_event):
    iter_ = 0
    name, flv_id = flavor
    while time.time() < end_time:
        iter_ += 1
        if end_event.is_set():
            assert 0, "Another thread failed. Terminate rest."

        LOG.tc_step("Iter{} - Launch and delete vm on {}".format(iter_, name))
        vm_id = vm_helper.boot_vm(name=name, flavor=flv_id)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

        time.sleep(15)
        vm_helper.delete_vms(vms=vm_id)


def test_launch_delete_vms(flavors):
    """
    Launch two 2vcpu-vms on each numa node, wait for pingable, then stop and delete. Repeat this action.
    Args:
        flavors: flavors with numa0 and numa1 specified

    Test Steps:
        (Each vm launch/delete is using a separate thread)
        - Launch two 2vcpu-vms on each numa node
        - Wait for vms pingable
        - Stop and delete vms
        - Repeat above operations

    """
    end_event = Event()
    run_time = 10 * 3600
    # run_time = 300
    start_time = time.time()
    end_time = start_time + run_time
    thread_timeout = run_time + 300
    threads = []
    for name, flv_id in flavors.items():
        for i in range(2):
            thread = MThread(launch_delete_vm, [name, flv_id], end_time, end_event=end_event)
            thread.start_thread(thread_timeout)
            threads.append(thread)

    for thr in threads:
        thr.wait_for_thread_end()


@mark.parametrize(('boot_source', 'count'), [
    ('volume', 1000),
    ('image', 1000)
])
def test_migrate_stress(check_hypervisors, boot_source, count):

    LOG.tc_step("Launch a VM from {}".format(boot_source))
    vm = vm_helper.boot_vm(name='{}-stress'.format(boot_source), cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)

    block_mig = True if boot_source == 'image' else False
    if not block_mig:
        LOG.tc_step("Attempt to block migration on boot-from-volume VM and ensure if fails")
        code = vm_helper.live_migrate_vm(vm_id=vm, block_migrate=True)[0]
        assert 1 > code, "Block migration passed unexpectedly for boot-from-volume vm"
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)

    LOG.tc_step("Live migrate and ping vm 1000 times")
    for i in range(count):
        LOG.info('Live migration iter{}'.format(i+1))
        vm_helper.live_migrate_vm(vm)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)

    LOG.tc_step("Cold migrate vm followed by live migrate {} times".format(count))
    for i in range(count):
        LOG.info('Cold+live migration iter{}'.format(i + 1))
        vm_helper.cold_migrate_vm(vm_id=vm)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)

        vm_helper.live_migrate_vm(vm)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)
