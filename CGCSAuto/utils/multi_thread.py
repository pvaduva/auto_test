import threading
import traceback
from utils.tis_log import LOG
from utils.exceptions import ThreadingError
from utils.ssh import SSHClient, ControllerClient, NATBoxClient
from consts.proj_vars import ProjVar

TIMEOUT_ERR = "Thread did not terminate within timeout. Thread details: {} {} {}"


class MThread(threading.Thread):
    """
    Multi threading class. Allows multiple threads to be run simultaneously.
    e.g. nova_helper.create_flavor('threading', 'auto', vcpus=2, ram=1024) is equivalent to...
        thread_1 = MThread(nova_helper.create_flavor, 'threading', 'auto', vcpus=2, ram=1024)
        thread_1.start_thread()
        thread_1.wait_for_thread_end()

    Other commands can be run between start_thread and wait_for_thread_end
    The function's output can be retrieved from thread_1.get_output()
    name should NOT be changed
    """
    total_threads = 0
    running_threads = []

    def __init__(self, func, *args, **kwargs):
        """

        Args:
            func (runnable): name of function to run. e.g. nova-helper.create_flavor. NOT nova_helper.create_flavor()
            *args:
            **kwargs:
        """
        threading.Thread.__init__(self)
        MThread.total_threads += 1
        self.thread_id = MThread.total_threads
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._output = None
        self.timeout = None

    def get_output(self):
        return self._output

    def start_thread(self, timeout=None):
        """
        Starts a thread.
        Test must wait for thread to terminate or it can continue running during other tests.

        Args:
            timeout (int): how long to wait for the thread to finish
            pass_ssh (bool): True - create a new ssh session and pass it as con_ssh to function
                             Use cli commands from multiple threads without conflicting with each other
        Returns:

        """
        self.timeout = timeout
        self.__start_thread_base()

    def __start_thread_base(self):
        self.start()

    def run(self):
        """
        Do not run this command. Start threads from start_thread functions
        Returns:

        """
        LOG.info("Starting thread {}".format(self.thread_id))
        # run the function
        try:
            MThread.running_threads.append(self)
            con_ssh = SSHClient(ProjVar.get_var('lab')['floating ip'])
            con_ssh.connect(use_current=False)
            ControllerClient.set_active_controller(con_ssh)
            NATBoxClient.set_natbox_client()
            LOG.info("Execute function {}({}, {})".format(self.func, self.args, self.kwargs))
            self._output = self.func(*self.args, **self.kwargs)
        except:
            LOG.error("Error found in thread call {}".format(traceback.format_exc()))
            raise
        finally:
            ControllerClient.get_active_controller().close()
            NATBoxClient.get_natbox_client().close()
            LOG.debug("Thread {} has finished".format(self.thread_id))
            MThread.running_threads.remove(self)

    def wait_for_thread_end(self, timeout=None, fail_ok=False):
        """
        Waits for thread (self) to finish executing.
        All tests should wait for threads to end before proceeding to teardown, unless it is expected to continue,
        e.g. LOG.tc_step will not work during setup or teardown
        Raise error if thread is still running after timeout
        Args:
            timeout (int): how long to wait for the thread to finish. self.timeout is preferred.

        Returns (bool): True if thread is not running, False/exception otherwise

        """
        if not self.is_alive():
            LOG.info("Thread was not running")
            return True

        if self.timeout:
            timeout = self.timeout
        else:
            if not timeout:
                LOG.warning("No timeout was specified. This can lead to waiting infinitely")

        LOG.info("Wait for {} to finish".format(self.thread_id))
        self.join(timeout)

        if not self.is_alive():
            LOG.info("Thread {} has finished".format(self.thread_id))
        else:
            # Thread didn't finish before timeout
            if fail_ok:
                return False
            raise ThreadingError(TIMEOUT_ERR.format(self.func, self.args, self.kwargs))
        return True


def get_multi_threads():
    return MThread.running_threads


def is_multi_thread_active():
    if len(get_multi_threads()) == 0:
        return False
    return True
