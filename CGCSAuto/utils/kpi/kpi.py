import inspect
import time
import re

from utils.tis_log import LOG


class KPI:
    """
    Normally would use functions but using data members to retain
    t0 time.
    .stop makes use of the stack inspection to retrieve the method
    or function name that the KPI object is being run in with the
    parameters.

    delta value is adjusted by 1000 to get milliseconds
    """
    def __init__(self):
        self.timer0 = time.time()

    def stop(self):
        delta = time.time() - self.timer0
        call = inspect.stack()[1][3]
        check = re.search('(\(.+\))', str(inspect.stack()[2][4]))
        if check is None:
            check = str(inspect.stack()[2][4])
        else:
            check = re.search('(\(.+\))', 
                              str(inspect.stack()[2][4])).group()
        LOG.info("KPI: {} {} {}".format(call, check, delta * 1000))
        return delta
