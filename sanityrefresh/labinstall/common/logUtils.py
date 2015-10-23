import logging
import time

class CustomFormatter(logging.Formatter):

    level_format_dict = {
        logging.DEBUG: '[DEBUG] %(module)s: %(lineno)d: %(message)s',
        logging.INFO: '[INFO] %(message)s',
        logging.WARN: '[WARNING] (%(pathname)s, %(lineno)d) %(message)s',
        logging.ERROR: '[ERROR] (%(pathname)s, %(lineno)d) %(message)s',
        logging.CRITICAL: '[CRITICAL] (%(pathname)s, %(lineno)d) %(message)s'
        }

    def __init__(self, fmt='%(levelname)s: %(message)s',
                 datefmt='%Y-%m-%d %H:%M:%S'):
        logging.Formatter.__init__(self, fmt, datefmt)
        self.converter = time.gmtime

    def format(self, record):
        # Replace the original format with one customized by logging level
#        self._style._fmt = '[%(asctime)s.%(msecs)03d]'
        self._style._fmt = '(%(asctime)s) '
        self._style._fmt += CustomFormatter.level_format_dict[record.levelno]

        # Call the original formatter class to do the grunt work
        result = logging.Formatter.format(self, record)

        return result

#TODO: Possibly create separate handlers, outputting target logs to files: https://docs.python.org/3/howto/logging-cookbook.html, http://stackoverflow.com/questions/13733552/logger-configuration-to-log-to-file-and-print-to-stdout
# Also see Using LoggerAdapters to impart contextual information: https://docs.python.org/3/howto/logging-cookbook.html which is used in host/htee/utils/logUtils.py
#def getLogger(name, level):
def setLogger(log, level):
    print('level = ' + level)
    # create logger
#    log = logging.getLogger(name)

    log.setLevel(level)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # create formatter
    formatter = CustomFormatter()

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    log.addHandler(ch)

#    return log

def print_step(step):
    print('\n' + step)
    print('*' * len(step))
