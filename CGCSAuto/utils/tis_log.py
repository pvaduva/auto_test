import logging
import os

# from setup_consts import LOG_DIR
from utils import exceptions

FORMAT = "'%(asctime)s %(levelname)-5s %(filename)-10s %(funcName)-10s: %(message)s'"
# TEST_LOG_LEVEL = 21
# TODO: determine the name based on which lab to use
# FILE_NAME = LOG_DIR + '/TIS_AUTOMATION.log'

TC_STEP_SEP = '='*22
TC_START_SEP = '+'*65
TC_END_SEP = '='*60

TC_SETUP_STEP_SEP = TC_TEARDOWN_STEP_SEP = '='*22
TC_SETUP_START_SEP = TC_TEARDOWN_START_SEP = TC_RESULT_SEP = '-'*65


class TisLogger(logging.getLoggerClass()):
    def __init__(self, name='', level=logging.NOTSET):
        super().__init__(name, level)

        # os.makedirs(LOG_DIR, exist_ok=True)
        # logging.basicConfig(level=level, format=FORMAT, filename=FILE_NAME, filemode='w')
        # reset test_step number when creating a logger instance
        self.test_step = -1
        self.test_setup_step = -1
        self.test_teardown_step = -1
        self.show_log = self.isEnabledFor(logging.INFO)

    def tc_func_start(self, tc_name, *args):
        if self.show_log:
            separator = '{}\n'.format(TC_START_SEP)
            self._log(logging.DEBUG, '\n{}Test steps started for: {}'.format(separator, tc_name), args)
            self.test_step = 0
            # this is also the end of the test setup
            self.test_setup_step = -1

    def tc_func_end(self, msg, tc_name, *args, **kwargs):
        """

        Args:
            msg:
            *args:
            **kwargs:

        Returns:
        Examples: logger.test_end("Successfully created vm")
        """
        if self.show_log:
            msg = "\n{}\nTest Function Result for {}: {}\n\n".format(TC_END_SEP, tc_name, msg)
            self._log(logging.DEBUG, msg, args, **kwargs)
            self.test_step = -1

    def tc_step(self, msg, *args, **kwargs):
        if self.show_log:
            if self.test_step == -1:
                raise exceptions.ImproperUsage("Please call tc_start() first before calling tc_step()!")
            self.test_step += 1
            msg = "\n{} Test Step {}: {}".format(TC_STEP_SEP, self.test_step, msg)
            self._log(logging.INFO, msg, args, **kwargs)

    def tc_setup_start(self, tc_name, *args):
        if self.show_log:
            msg = ("\n{}\nSetup started for: {}".format(TC_SETUP_START_SEP, tc_name))
            self._log(logging.DEBUG, msg, args)
            self.test_setup_step = 0

    def tc_teardown_start(self, tc_name, *args):
        if self.show_log:
            msg = ("\n{}\nTeardown started for: {}".format(TC_TEARDOWN_START_SEP, tc_name))
            self._log(logging.DEBUG, msg, args)
            self.test_teardown_step = 0

    def tc_result(self, tc_name, result, *args):
        if self.show_log:
            msg = ("\n{}\nTest Result for: {} - {}".format(TC_RESULT_SEP, tc_name, result))
            self._log(logging.INFO, msg, args)
            self.test_teardown_step = -1

    def fixture_step(self, msg, *args, **kwargs):

        if self.show_log:

            if self.test_setup_step == -1 and self.test_teardown_step == -1:
                raise exceptions.ImproperUsage("Please call tc_setup/teardown_start() to initialize fixture step")

            elif self.test_setup_step != -1 and self.test_teardown_step != -1:
                raise exceptions.ImproperUsage("Please call tc_result() or tc_func_start() to reset fixture step")

            elif self.test_setup_step != -1:
                # in test setup
                self.test_setup_step += 1
                fixture_step = self.test_setup_step
                fixture_ = 'Setup'

            else:
                # in test teardown
                self.test_teardown_step += 1
                fixture_step = self.test_teardown_step
                fixture_ = 'Teardown'

            msg = "\n{} {} Step {}: {}".format(TC_SETUP_STEP_SEP, fixture_, fixture_step, msg)
            self._log(logging.INFO, msg, args, **kwargs)

# register our logger
logging.setLoggerClass(TisLogger)
LOG = logging.getLogger('testlog')

# # screen output handler
# handler = logging.StreamHandler()
# formatter = logging.Formatter('%(lineno)-4d%(levelname)-5s %(module)s.%(funcName)-8s: %(message)s')
# handler.setFormatter(formatter)
# handler.setLevel(logging.INFO)
# LOG.addHandler(handler)
