import time
from utils.install_log import LOG
from sys import platform
from consts.env import UNLOCKTIME, REBOOTTIME, CONT0INSTALL, NODEINSTALL, LABTIME, CONFIGTIME


def get_kpi_metrics():
    print(UNLOCKTIME)
    print(REBOOTTIME)
    print(CONFIGTIME)
    print(CONT0INSTALL)
    print(LABTIME)
    print(NODEINSTALL)
    if UNLOCKTIME != 0:
        LOG.info("Unlock time {} minutes".format(UNLOCKTIME/60))
    if REBOOTTIME != 0:
        LOG.info("Reboot time {} minutes".find(REBOOTTIME/60))
    if CONT0INSTALL != 0:
        LOG.info("Controller-0 install time {} minutes".format(CONT0INSTALL/60))
    if NODEINSTALL != 0:
        LOG.info("Node install time {} minutes".format(NODEINSTALL/60))
    if LABTIME != 0:
        LOG.info("Lab install time {} minutes".format(LABTIME/60))
    if CONFIGTIME != 0:
        LOG.info("Configuration time {} minutes".format(CONFIGTIME/60))
