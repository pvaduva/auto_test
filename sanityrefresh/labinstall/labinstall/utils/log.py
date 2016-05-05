#!/usr/bin/env python3.4

"""
log.py - Custom logger

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
"""

import logging
import sys
import time
import threading

LOG_LEVELS = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR,
              logging.CRITICAL]
LOG_LEVEL_NAMES = [logging.getLevelName(level) for level in LOG_LEVELS]
GLOBAL_LOG_LEVEL = logging.DEBUG

#class CustomAdapter(logging.LoggerAdapter):
#    """
#    This example adapter expects the passed in dict-like object to have a
#    'connid' key, whose value in brackets is prepended to the log message.
#    """
#    def process(self, msg, kwargs):
#        return '[%s] %s' % (self.extra['connid'], msg), kwargs

class CustomFormatter(logging.Formatter):
    """Define customized format based on log level."""

    # For filename and line number, add: (%(pathname)s, %(lineno)d)
    # For module: %(module)s
    level_format_dict = {
        logging.DEBUG: '{:11}'.format('[DEBUG]') +'[%(threadName)s] %(message)s',
        logging.INFO: '{:11}'.format('[INFO]') +'[%(threadName)s] %(message)s',
        logging.WARN: '{:11}'.format('[WARN]') +'[%(threadName)s] %(message)s',
        logging.ERROR: '{:11}'.format('[ERROR]') +'[%(threadName)s] %(message)s',
        logging.CRITICAL: '{:11}'.format('[CRITICAL]') +'[%(threadName)s] %(message)s',
#        logging.INFO: '[INFO] [%(threadName)s] %(message)s',
#        logging.WARN: '[WARNING] [%(threadName)s] %(message)s',
#        logging.ERROR: '[ERROR] [%(threadName)s] %(message)s',
#        logging.CRITICAL: '[CRITICAL] [%(threadName)s] %(message)s'
        }

    def __init__(self, fmt='%(levelname)s: %(message)s',
                 datefmt='%Y-%m-%d %H:%M:%S'):
        logging.Formatter.__init__(self, fmt, datefmt)
        self.converter = time.gmtime

    def format(self, record):
        """Replace the original format with one customized by log level."""
        # For milliseconds, use this instead: '[%(asctime)s.%(msecs)03d]'
        self._style._fmt = '(%(asctime)s) '
        self._style._fmt += CustomFormatter.level_format_dict[record.levelno]

        # Call the original formatter class to do the grunt work
        result = logging.Formatter.format(self, record)

        return result

class LogLevelFilter(logging.Filter):
    """Filter messages with log level less than the specified level."""
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno < self.level # "<" instead of "<=": since logger.setLevel is inclusive, this should be exclusive

def getLogger(name):
    """Return custom logger for module with assigned level."""
    log = logging.getLogger(name)

    # Required to prevent output via root logger,
    # which is set to WARNING by default
    #TODO: See how to fix this as if you add another handler, the event might
    #      not get passed as it would require the flag to be True
    log.propagate = False
    log.setLevel(GLOBAL_LOG_LEVEL)

    # Define stdout handler
    ch_stdout = logging.StreamHandler(sys.stdout)
    ch_stdout.addFilter(LogLevelFilter(logging.WARNING))
    ch_stdout.setLevel(GLOBAL_LOG_LEVEL)

    ch_stderr = logging.StreamHandler(sys.stderr)
    ch_stderr.setLevel(max(GLOBAL_LOG_LEVEL, logging.WARNING))

    formatter = CustomFormatter()

    # Add formatter to console handlers
    ch_stdout.setFormatter(formatter)
    ch_stderr.setFormatter(formatter)

    # Add console handlers to logger
    log.addHandler(ch_stdout)
    log.addHandler(ch_stderr)

#    log = CustomAdapter(log, {'connid': threading.current_thread().name})

    return log

def print_name_value(name, value):
    """Print name and value for argument in separate columns."""
    template = "{:30} \t{}"
    print(template.format(name + ":", str(value)))

def print_step(step):
    """Print string describing step with a border around it."""
    char = '*'
    length = len(step)
    print()
    print(char * length)
    print(step)
    print(char * length)
    print()