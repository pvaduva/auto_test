from time import sleep, time

from testfixtures.fixture_resources import ResourceCleanup
from utils.multi_thread import MThread, Events, TiSBarrier, TiSLock
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper


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


def events_func(func_num, reps, event):
    for i in range(0, reps):
        if i > reps / 2:
            event.wait_for_event(30)
        LOG.info("Function #{}".format(func_num))
        sleep(1)


def test_events():
    e = Events("functions should wait here")
    LOG.tc_step("Create multiple threads")
    thread_1 = MThread(events_func, 1, 10, e)
    thread_2 = MThread(events_func, 2, 15, e)

    thread_1.start_thread(60)
    thread_2.start_thread(60)
    sleep(20)

    LOG.tc_step("Setting event")
    e.set()
    thread_1.wait_for_thread_end()
    thread_2.wait_for_thread_end()
    LOG.tc_step("Threads have finished")

    e.clear()
    e.wait_for_event(20, fail_ok=True)


def barr_func(func_num, rep, barrier):
    barrier.wait(10)
    for i in range(0, rep):
        LOG.info("function #{}".format(func_num))
        sleep(1)


def test_barriers():
    LOG.tc_step("Negative barrier example (not enough threads waiting)")
    barrier = TiSBarrier(2, timeout=20)
    thread_1 = MThread(barr_func, 1, 4, barrier)
    thread_1.start_thread(timeout=30)
    thread_1.wait_for_thread_end(fail_ok=True)

    LOG.tc_step("Positive barrier example")
    barrier = TiSBarrier(2, timeout=20)
    thread_1 = MThread(barr_func, 2, 4, barrier)
    thread_2 = MThread(barr_func, 3, 4, barrier)

    thread_1.start_thread(timeout=30)
    thread_2.start_thread(timeout=30)
    thread_1.wait_for_thread_end()
    thread_2.wait_for_thread_end()


def get_lock(lock, th_num):
    sleep(1)
    LOG.info("{} getting lock".format(th_num))
    if lock.acquire():
        LOG.info("{} got lock".format(th_num))
        sleep(5)
        LOG.info("{} release lock".format(th_num))
    else:
        LOG.info("Didn't get lock")
    lock.release()
    LOG.info("{} released lock".format(th_num))


def get_lock_with(lock, th_num):
    sleep(1)
    LOG.info("{} getting lock".format(th_num))
    with lock as got_lock:
        if got_lock:
            LOG.info("{} got lock".format(th_num))
            sleep(5)
            LOG.info("{} release lock".format(th_num))
        else:
            LOG.info("Didn't get lock")
    LOG.info("{} released lock".format(th_num))


def test_lock():
    LOG.tc_step("Positive lock example")
    lock = TiSLock(True)
    thread_1 = MThread(get_lock, lock, 1)
    thread_2 = MThread(get_lock, lock, 2)
    thread_1.start_thread(30)
    sleep(1)
    thread_2.start_thread(30)
    thread_1.wait_for_thread_end(0)
    thread_2.wait_for_thread_end(30)

    LOG.tc_step("Negative lock example")
    lock = TiSLock(True, 2)
    thread_1 = MThread(get_lock, lock, 1)
    thread_2 = MThread(get_lock, lock, 2)
    thread_1.start_thread(30)
    sleep(1)
    thread_2.start_thread(30)
    thread_1.wait_for_thread_end(0, fail_ok=True)
    thread_2.wait_for_thread_end(30, fail_ok=True)
