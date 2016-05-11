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
from testResultsParser import TestResultsParser
import argparse
import configparser

LOCAL_PATH = os.path.dirname(__file__)
WASSP_PATH = os.path.join(LOCAL_PATH,"..","..","..")

def collect_and_upload_results(test_name=None, log_dir=None):
   '''
    collect the test environment variables 
   '''

   # check for any user input and defaults
   options = parse_args()
   
   # get the environment variables
   build = options.build
   lab = options.lab
   userstory = options.userstory
   domain = options.domain
   release_name = options.release_name
   output = options.output
   tester_name = options.tester_name
   tag = options.tag
   jira = options.jira

   if log_dir is None:
       logfile = options.logfile
   else:
       logfile = os.path.join(log_dir, 'TIS_AUTOMATION.log')
       print('logfile: %s' % logfile)

   if test_name is None:
       test_name = options.test_name

   # get the results of the test execution
   if options.result == '' or options.result is None:
       print('Using parser file')
       resultParser = TestResultsParser(logfile)
       result = resultParser.parse()
   else:
       print('Using options')
       result = options.result

   # create a data file containing test information
   os.system("rm %s" % output)
   env_params = "-o %s -x %s  -n %s -t %s -r %s -l %s -b %s -u %s -d %s -j %s -a %s -R %s"\
                  % (output, tag, tester_name, test_name, result, 
                     lab, build, userstory, domain,
                     jira, logfile, release_name)
   os.system("./ini_writer.sh %s" % env_params)

   # write to the mongo database
   test_reporter = os.path.join(WASSP_PATH, "wassp/host/tools/report/testReportManual.py")
   activate = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")
   #os.system("%s %s -f %s 2>&1" % (activate, test_reporter, output))

def parse_args():
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
        for opt in config.items(section):
            key, value = opt
            info_dict[key] = value

    return info_dict


# Used to invoke the query and report generation from the command line
if __name__ == "__main__":

    # collect entries and upload them
    collect_and_upload_results()

