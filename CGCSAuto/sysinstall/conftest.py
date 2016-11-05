import logging
import os
from time import strftime, gmtime

import pytest

import setup_consts
import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars
from utils.mongo_reporter.cgcs_mongo_reporter import collect_and_upload_results
from utils.tis_log import LOG

con_ssh = None
has_fail = False


########################
# Command line options #
########################

def pytest_configure(config):

    # Lab install params
    lab_arg = config.getoption('lab')
    resume_install = config.getoption('resumeinstall')
    install_conf = config.getoption('installconf')
    skip_labsetup = config.getoption('skiplabsetup')

    setups.set_install_params(lab=lab_arg, skip_labsetup=skip_labsetup, resume=resume_install,
                              installconf_path=install_conf)


def pytest_unconfigure():

    tc_res_path = ProjVar.get_var('LOG_DIR') + '/test_results.log'

    with open(tc_res_path, mode='a') as f:
        f.write('\n\nLab: {}\n'
                'Build ID: {}\n'
                'Automation LOGs DIR: {}\n'.format(ProjVar.get_var('LAB_NAME'),
                                                   InstallVars.get_install_var('BUILD_ID'),
                                                   ProjVar.get_var('LOG_DIR')))

    LOG.info("Test Results saved to: {}".format(tc_res_path))
    with open(tc_res_path, 'r') as fin:
        print(fin.read())
