import logging
import os

# from setup_consts import LOG_DIR
from utils import exceptions

FORMAT = "'%(asctime)s %(levelname)-5s %(filename)-10s %(funcName)-10s: %(message)s'"
# TEST_LOG_LEVEL = 21
# TODO: determine the name based on which lab to use
# FILE_NAME = LOG_DIR + '/TIS_AUTOMATION.log'


class TisLogger(logging.getLoggerClass()):
    def __init__(self, name='', level=logging.NOTSET):
        super().__init__(name, level)

        # os.makedirs(LOG_DIR, exist_ok=True)
        # logging.basicConfig(level=level, format=FORMAT, filename=FILE_NAME, filemode='w')
        # reset test_step number when creating a logger instance
        self.test_step = -1
        self.show_log = self.isEnabledFor(logging.INFO)

    def tc_start(self, tc_name, *args):
        if self.show_log:
            separator = '++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++\n'
            self._log(logging.DEBUG, '\n{}Test steps started for: {}'.format(separator, tc_name), args)
            self.test_step = 0

    def tc_end(self, msg, tc_name, *args, **kwargs):
        """

        Args:
            msg:
            *args:
            **kwargs:

        Returns:
        Examples: logger.test_end("Successfully created vm")
        """
        if self.show_log:
            msg = "\n=================================================================\nTest Result for {}: {}\n\n".\
                format(tc_name, msg)
            self._log(logging.DEBUG, msg, args, **kwargs)
            self.test_step = -1

    def tc_step(self, msg, *args, **kwargs):
        if self.show_log:
            if self.test_step == -1:
                raise exceptions.ImproperUsage("Please call tc_start() first before calling tc_step()!")
            self.test_step += 1
            msg = "\n======================= Test Step {}: {}".format(self.test_step, msg)
            self._log(logging.INFO, msg, args, **kwargs)

    def tc_setup(self, tc_name, *args):
        if self.show_log:
            msg = ("\n------------------------------------------------------------------\nSetup started for: {}".
                   format(tc_name))
            self._log(logging.DEBUG, msg, args)

    def tc_teardown(self, tc_name, *args):
        if self.show_log:
            msg = ("\n----------------------------------------------------------------------\nTeardown started for: {}".
                   format(tc_name))
            self._log(logging.DEBUG, msg, args)

    def tc_result(self, tc_name, result, *args):
        if self.show_log:
            msg = ("\n----------------------------------------------------------------------\nTest Result for: {} - {}".
                   format(tc_name, result))
            self._log(logging.INFO, msg, args)

# register our logger
logging.setLoggerClass(TisLogger)
LOG = logging.getLogger('testlog')

# # screen output handler
# handler = logging.StreamHandler()
# formatter = logging.Formatter('%(lineno)-4d%(levelname)-5s %(module)s.%(funcName)-8s: %(message)s')
# handler.setFormatter(formatter)
# handler.setLevel(logging.INFO)
# LOG.addHandler(handler)

