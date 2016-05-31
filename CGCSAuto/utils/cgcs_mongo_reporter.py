#!/usr/bin/env python3

'''
cgcs_mongo_reporter.py - parse any given log file for test result
                         and upload the results to the Mongo database

Copyright (c) 2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

modification history:
---------------------
12mar16,amf  Creation

'''

import re
import os
import sys
import ast
import subprocess
import datetime
from utils.testResultsParser import TestResultsParser
import argparse
import configparser
import setups
import setup_consts
from consts.proj_vars import ProjVar

LOCAL_PATH = os.path.dirname(__file__)
WASSP_PATH = os.path.join(LOCAL_PATH,"..","..","..","..")

def collect_and_upload_results(test_name=None, result=None, log_dir=None):
   '''
    collect the test environment variables 
   '''

   # get defaults from config file
   options = parse_config_file()
   
   # get the environment variables
   build = options['build'] if options['build'] else get_build_info()
   lab = options['lab'] if options['lab'] else setup_consts.LAB['short_name'].upper()
   domain = options['domain'] if options['domain'] else setup_consts.DOMAIN.upper()
   userstory = options['userstory'] if options['userstory'] else setup_consts.USERSTORY.upper()
   tag = options['tag'] if options['tag'] else 'regression_%s_%s' % (build, lab)
   jira = options['jira'] if options['jira']  else 'Unknown'
   release_name = options['release_name']
   output = options['output']
   tester_name = options['tester_name']

   if log_dir is None:
       logfile = options['logfile']
   else:
       logfile = os.path.join(log_dir, 'TIS_AUTOMATION.log')

   if test_name is None:
       test_name = options['test_name']
   elif '::' in test_name:
       test_name = test_name.split('::')[-1]

   # get the results of the test execution
   if result is None:
       result = options['result'] 
       if options['result'] == '' or options['result'] is None:
           resultParser = TestResultsParser(logfile)
           result = resultParser.parse()

   # convert to acceptable database format
   if result == 'Passed' or result == 'passed':
       result = 'PASS'
   elif result == 'Failed' or result == 'failed':
       result = 'FAIL'

   # create a data file containing test information
   os.system("rm -rf %s" % output)
   env_params = "-o %s -x %s  -n %s -t %s -r %s -l %s -b '%s' -u %s -d %s -j %s -a '%s' -R '%s'"\
                  % (output, tag, tester_name, test_name, result, 
                     lab, build, userstory, domain,
                     jira, logfile, release_name)

   print("Saving results for test case: %s" % test_name)
   ini_writer = os.path.join(LOCAL_PATH, 'ini_writer.sh')
   cmd = "%s %s" % (ini_writer, env_params)
   os.system(cmd)

   # write to the mongo database
   test_reporter = os.path.join(WASSP_PATH, "wassp/host/tools/report/testReportManual.py")
   activate = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")
   os.system("%s %s -f %s 2>&1" % (activate, test_reporter, output))
   today_date = datetime.datetime.now().strftime("%Y-%m-%d")
   print('Date: %s. Report tag: %s' % (today_date, tag))
   print("Data upload successful.")

def collect_user_input_and_upload_results(test_name=None, result=None, log_dir=None):
   '''
    collect the test environment variables 
   '''

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
           resultParser = TestResultsParser(logfile)
           result = resultParser.parse()

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

   print("Saving results for test case: %s" % test_name)
   ini_writer = os.path.join(LOCAL_PATH, 'ini_writer.sh')
   os.system("%s %s" % (ini_writer, env_params))

   # write to the mongo database
   test_reporter = os.path.join(WASSP_PATH, "wassp/host/tools/report/testReportManual.py")
   activate = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")
   os.system("%s %s -f %s 2>&1" % (activate, test_reporter, output))
   today_date = datetime.datetime.now().strftime("%Y-%m-%d")
   print('Date: %s. Report tag: %s' % (today_date, tag))
   print("Data upload successful.")

def parse_user_args():
    ''' Get commandline options. 
    '''

    # get the defauls from the config.ini file
    defaults = parse_config_file()

    # parse any command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-b','--build', dest='build', default=defaults['build'])
    parser.add_argument('-l','--lab', dest='lab', default=defaults['lab'])
    parser.add_argument('-u','--userstory', dest='userstory', default=defaults['userstory'])
    parser.add_argument('-d','--domain', dest='domain', default=defaults['domain'])
    parser.add_argument('-r','--result', dest='result', default=defaults['result'])
    parser.add_argument('-R','--release_name', dest='release_name', default=defaults['release_name'])
    parser.add_argument('-o','--output', dest='output', default=defaults['output'])
    parser.add_argument('-n','--tester_name', dest='tester_name', default=defaults['tester_name'])
    parser.add_argument('-t','--test_name', dest='test_name', default=defaults['test_name'])
    parser.add_argument('-x','--tag', dest='tag', default=defaults['tag'])
    parser.add_argument('-j','--jira', dest='jira', default=defaults['jira'])
    parser.add_argument('-a','--logfile', dest='logfile', default=defaults['logfile'])

    return (parser.parse_args())

def parse_config_file():
    ''' Get defaults from the ini file
    '''

    # set the name of the config file
    config = configparser.ConfigParser()
    try:
        config_file = os.path.join(LOCAL_PATH, 'config.ini')
        config_file = open(config_file, 'r')
        config.read_file(config_file)
    except Exception:
        msg = "Failed to read file: " + config_file
        log.exception(msg)

    info_dict = {}
    for section in config.sections():
        for opt in config.options(section):
            info_dict[opt] =  config.get(section, opt)

    return info_dict

def get_build_info():
    ''' Get load build information. 
    '''

    # get the latest build available
    build_server = "128.224.145.134"
    build_location = "/localdisk/loadbuild/jenkins/CGCS_3.0_Unified_Daily_Build/"
    build_finder = os.path.join(LOCAL_PATH, '..', '..', 'utils', 'findLatestCgcsLoad2.sh')

    # parse any command line options
    command = "%s %s %s | awk -F / '{print $6}'" % (build_finder, build_server, build_location)
    build_info = os.popen(command).read()
    #os.environ['CGCS_BUILD']  = build_info
    return (build_info)

# Used to invoke the query and report generation from the command line
if __name__ == "__main__":

    # collect entries and upload them
    collect_user_input_and_upload_results()

