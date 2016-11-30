from time import sleep, time

from testfixtures.resource_mgmt import ResourceCleanup
from utils.multi_thread import MThread
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, cinder_helper
from utils.ssh import SSHClient, ControllerClient, NATBoxClient


def func(func_num, num, extra_arg=None):
    i = 0
    while i < num:
        LOG.info("func_num = {}\niteration = {}\nextra_arg = {}".format(func_num, i, extra_arg))
        sleep(1)
        i += 1

    LOG.info("{} done".format(func_num))


def test_multi_thread():
    LOG.tc_step("Create MThreads")
    thread_1 = MThread(func, 1, 10, extra_arg="Hello")
    thread_2 = MThread(func, 2, 6, extra_arg="Second")
    # runs after test steps complete
    thread_3 = MThread(func, 3, 20, extra_arg="run for a long time")
    thread_4 = MThread(nova_helper.create_flavor, 'threading', 'auto', vcpus=2, ram=1024)

    LOG.tc_step("Starting threads")
    thread_1.start_thread()
    thread_2.start_thread()
    thread_3.start_thread()
    thread_4.start_thread()
    LOG.tc_step("Finished starting threads")

    LOG.tc_step("Waiting for threads to finish")
    thread_1.wait_for_thread_end()
    thread_2.wait_for_thread_end()
    thread_4.wait_for_thread_end()
    LOG.tc_step("Threads have finished")

    id_ = thread_4.get_output()[1]
    LOG.info("flav_id = {}".format(id_))
    ResourceCleanup.add(resource_type='flavor', resource_id=id_)


def test_copies_of_threads():
    LOG.tc_step("Make multiple threads with same params")
    threads = []
    for i in range(1, 5):
        threads.append(MThread(func, i, 10, extra_arg="number: {}".format(i)))

    for thread in threads:
        thread.start_thread()

    for thread in threads:
        thread.wait_for_thread_end()


def test_timing():
    threads = []
    flav_id = nova_helper.create_flavor('thread_testing')[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flav_id)
    start_1 = time()
    for i in range(0, 6):
        thread = MThread(vm_helper.boot_vm, 'threading_vm', flavor=flav_id)
        thread.start_thread(240)
        threads.append(thread)

    for thread in threads:
        thread.wait_for_thread_end()
    for thread in threads:
        ResourceCleanup.add(resource_type='vm', resource_id=thread.get_output()[1])
    end_1 = time()

    start_2 = time()
    for i in range(0, 2):
        vm_id = vm_helper.boot_vm('loop_vm', flav_id)[1]
        ResourceCleanup.add(resource_type='vm', resource_id=vm_id)
    end_2 = time()

    LOG.info("Time results:\n"
             "Multithreading: {}\n"
             "Single loop: {}".format(end_1 - start_1, end_2 - start_2))
