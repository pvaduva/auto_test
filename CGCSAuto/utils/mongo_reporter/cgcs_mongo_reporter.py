#!/usr/bin/env python3

"""
cgcs_mongo_reporter.py - parse any given log file for test result
                         and upload the results to the Mongo database

Copyright (c) 2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

modification history:
---------------------
08jun16,amf  Add capability to get build info from lab
12mar16,amf  Creation

"""

import argparse
import configparser
import datetime
import os
import re

import pexpect

import setup_consts
from consts.proj_vars import ProjVar
from utils.mongo_reporter.testResultsParser import TestResultsParser
from utils.tis_log import LOG

LOCAL_PATH = os.path.dirname(__file__)
WASSP_PATH = os.path.join(LOCAL_PATH, "..", "..", "..", "..", "..")


def collect_and_upload_results(test_name=None, result=None, log_dir=None, build=None):
    """
    collect the test environment variables 
    """
    
    # get defaults from config file
    options = parse_config_file()
    
    # get the environment variables
    lab = options['lab'] if options['lab'] else ProjVar.get_var('LAB')
    lab_name = lab['short_name'].upper()
    build = options['build'] if options['build'] else build
    userstory = options['userstory'] if options['userstory'] else setup_consts.USERSTORY.upper()
    
    if ProjVar.get_var('REPORT_TAG'):
        tag = ProjVar.get_var('REPORT_TAG')
    else:
        tag = options['tag'] if options['tag'] else 'regression_%s_%s' % (build, lab_name)
    jira = options['jira'] if options['jira'] else 'Unknown'
    release_name = options['release_name']
    output = options['output']
    tester_name = options['tester_name'] if options['tester_name'] else os.environ['USER']
    
    if log_dir is None:
        logfile = options['logfile']
    else:
        everything_log = os.path.join(log_dir, 'TIS_AUTOMATION.log')
        testres_log = os.path.join(log_dir, 'test_results.log')
        # pytest_log = os.path.join(log_dir, 'pytestlog.log')
        logfile = ','.join([everything_log, testres_log])

    # determine domain. config.ini > test path > setup_consts(default)
    if options['domain']:
        domain = options['domain']
    else:
        possible_domains = ['Alarms', 'Common', 'Heat', 'MTC', 'Networking', 'Nova', 'Storage', 'Sysinv']
        for possible_domain in possible_domains:
            if possible_domain.lower()+'/' in test_name:
                domain = possible_domain.upper()
                break
        else:
            domain = setup_consts.DOMAIN.upper()

    if test_name is None:
        test_name = options['test_name']
    elif '::' in test_name:
        test_name = test_name.split('::')[-1]
    
    test_name = test_name.replace(" ", "_").replace('(', '_').replace(')', '_').replace(';', '_')
    # get the results of the test execution
    if result is None:
        result = options['result'] 
        if options['result'] == '' or options['result'] is None:
            result_parser = TestResultsParser(logfile)
            result = result_parser.parse()
    
    # convert to acceptable database format
    if result == 'Passed' or result == 'passed':
        result = 'PASS'
    elif result == 'Failed' or result == 'failed':
        result = 'FAIL'

    # create a data file containing test information
    os.system("rm -rf %s" % output)
    env_params = "-o %s -x %s  -n %s -t %s -r %s -l %s -b '%s' -u %s -d %s -j %s -a '%s' -R '%s'"\
                 % (output, tag, tester_name, test_name, result, 
                    lab_name, build, userstory, domain,
                    jira, logfile, release_name)

    ini_writer = os.path.join(LOCAL_PATH, 'ini_writer.sh')
    cmd = "%s %s" % (ini_writer, env_params)
    os.system(cmd)
    
    # write to the mongo database
    test_reporter = os.path.join(WASSP_PATH, "wassp/host/tools/report/testReportManual.py")
    activate = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")

    report_file_name = log_dir + '/mongo_res.log'
    upload_cmd = "{} {} -f {} 2>&1 ".format(activate, test_reporter, output)

    with open(report_file_name, mode='a') as f:
        f.write("Mongo upload results for test case: %s\n" % test_name)
        local_child = pexpect.spawn(command=upload_cmd, encoding='utf-8', logfile=f)
        local_child.expect(pexpect.EOF)
        upload_output = local_child.before

        res = re.search("Finished saving test result .* to database", upload_output)
        msg = "\nTest result successfully uploaded to MongoDB" if res else \
              "\nTest result failed to upload. Please check parameters stored at {}\n{}".format(output, upload_output)

        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        extra_info = '\nDate: %s. Report tag: %s\n\n' % (today_date, tag)
        msg += extra_info

        f.write(msg + "\n")
        print(msg)

    return res

    # upload_cmd = "{} {} -f {} >>{} 2>&1 ".format(activate, test_reporter, output, report_file_name)
    # log_msg += '\nReport upload command: {}'.format(upload_cmd)
    #
    # exit_code = os.system(upload_cmd)
    # LOG.info("mongo reporter exit code: {}".format(exit_code))
    # if not exit_code:
    #     msg = "Test result successfully uploaded to MongoDB."
    #     log_msg += msg
    #     rtn = True
    # else:
    #     log_msg += "\nTest result failed to upload. Please check parameters stored at %s" % output
    #     msg = log_msg
    #     rtn = False
    # today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    # extra_info = '\nDate: %s. Report tag: %s\n\n' % (today_date, tag)
    # msg += extra_info
    # log_msg += extra_info
    # print(msg)
    # with open(report_file_name, mode='a') as f:
    #     f.write(log_msg)
    #
    # return rtn


def collect_user_input_and_upload_results(test_name=None, result=None, log_dir=None):
    """
    collect the test environment variables 
    """
    
    # check for any user input and defaults
    options = parse_user_args()
    
    # get the environment variables
    build = options.build
    lab = options.lab
    userstory = options.userstory
    domain = options.domain
    release_name = options.release_name
    output = options.output
    tester_name = options.tester_name
    tag = options.tag
    jira = 'Unknown'
    
    if log_dir is None:
        logfile = options.logfile
    else:
        logfile = os.path.join(log_dir, 'TIS_AUTOMATION.log')
    
    if test_name is None:
        test_name = options.test_name
    elif '::' in test_name:
        test_name = test_name.split('::')[-1]
    
    # get the results of the test execution
    if result is None:
        result = options.result
        if options.result == '' or options.result is None:
            result_parser = TestResultsParser(logfile)
            result = result_parser.parse()
    
    # convert to acceptable database format
    if result == 'Passed' or result == 'passed':
        result = 'PASS'
    elif result == 'Failed' or result == 'failed':
        result = 'FAIL'
    
    # create a data file containing test information
    os.system("rm -rf %s" % output)
    env_params = "-o %s -x %s  -n %s -t %s -r %s -l %s -b %s -u %s -d %s -j %s -a '%s' -R %s"\
                 % (output, tag, tester_name, test_name, result, 
                    lab, build, userstory, domain,
                    jira, logfile, release_name)
    
    LOG.info("Saving results for test case: %s" % test_name)
    LOG.info('Query parameters: %s' % env_params)
    ini_writer = os.path.join(LOCAL_PATH, 'ini_writer.sh')
    os.system("%s %s" % (ini_writer, env_params))
    
    # write to the mongo database
    test_reporter = os.path.join(WASSP_PATH, "wassp/host/tools/report/testReportManual.py")
    activate = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")
    if not os.system("%s %s -f %s 2>&1" % (activate, test_reporter, output)):
        msg = "Data upload successful."
    else:
        msg = "Data upload failed. Please check parameters stored at %s" % output
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    LOG.info('Date: %s. Report tag: %s' % (today_date, tag))
    LOG.info(msg)


def parse_user_args():
    """ Get commandline options.
    """

    # get the defauls from the config.ini file
    defaults = parse_config_file()

    # parse any command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--build', dest='build', default=defaults['build'])
    parser.add_argument('-l', '--lab', dest='lab', default=defaults['lab'])
    parser.add_argument('-u', '--userstory', dest='userstory', default=defaults['userstory'])
    parser.add_argument('-d', '--domain', dest='domain', default=defaults['domain'])
    parser.add_argument('-r', '--result', dest='result', default=defaults['result'])
    parser.add_argument('-R', '--release_name', dest='release_name', default=defaults['release_name'])
    parser.add_argument('-o', '--output', dest='output', default=defaults['output'])
    parser.add_argument('-n', '--tester_name', dest='tester_name', default=defaults['tester_name'])
    parser.add_argument('-t', '--test_name', dest='test_name', default=defaults['test_name'])
    parser.add_argument('-x', '--tag', dest='tag', default=defaults['tag'])
    parser.add_argument('-j', '--jira', dest='jira', default=defaults['jira'])
    parser.add_argument('-a', '--logfile', dest='logfile', default=defaults['logfile'])

    return parser.parse_args()


def parse_config_file():
    """ Get defaults from the ini file
    """

    # set the name of the config file
    config = configparser.ConfigParser()
    config_file = os.path.join(LOCAL_PATH, 'config.ini')
    try:
        config_file = open(config_file, 'r')
        config.read_file(config_file)
    except Exception:
        msg = "Failed to read file: " + config_file
        LOG.exception(msg)

    info_dict = {}
    for section in config.sections():
        for opt in config.options(section):
            info_dict[opt] = config.get(section, opt)

    return info_dict


# Used to invoke the query and report generation from the command line
if __name__ == "__main__":

    # collect entries and upload them
    collect_user_input_and_upload_results()

