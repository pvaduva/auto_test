#!/usr/bin/env python3
#
# Copyright (c) 2016 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

"""
cgcs_mongo_reporter.py - parse any given log file for test result
                         and upload the results to the Mongo database

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

"""

import argparse
import configparser
import datetime
import os
import re

import pexpect

from consts.proj_vars import ProjVar
from utils.mongo_reporter.testResultsParser import TestResultsParser
from utils.tis_log import LOG

LOCAL_PATH = os.path.dirname(__file__)
WASSP_PATH = os.path.join(LOCAL_PATH, "..", "..", "..", "..", "..")


def collect_and_upload_results(test_name=None, result=None, log_dir=None,
                               build=None, build_server=None,
                               build_job=None):
    """
    collect the test environment variables
    """

    # get defaults from config file
    options = parse_config_file()

    # get the environment variables
    lab = options['lab'] if options.get('lab') else ProjVar.get_var('LAB')
    lab_name = lab['short_name'].upper().replace('-', '_')
    build = options['build'] if options.get('build') else build
    build_server = options.get('build_server') if \
        options.get('build_server') else build_server
    build_job = \
        options.get('build_job') if options.get('build_job') else build_job
    userstory = options.get('userstory') if options.get('userstory') else ''

    if ProjVar.get_var('REPORT_TAG'):
        tag = ProjVar.get_var('REPORT_TAG')
    else:
        tag = options['tag'] if options.get('tag') else \
            'regression_%s_%s' % (build, lab_name)

    system_type = ProjVar.get_var('SYS_TYPE')
    if system_type:
        if '+' in system_type:
            count = system_type.count('+')
            if count == 1:
                system_type = 'regular'
            elif count == 2:
                system_type = 'storage'
            else:
                system_type = 'unknown'
    else:
        if lab.get('storage_nodes'):
            system_type = 'storage'
        elif lab.get('compute_nodes'):
            system_type = 'regular'
        elif lab.get('controller_nodes'):
            if len(lab.get('controller_nodes')) == 1:
                system_type = 'aio-sx'
            else:
                system_type = 'aio-dx'
        else:
            system_type = 'unknown'
    system_type = system_type.upper()

    jira = options['jira'] if options.get('jira') else ''
    release_name = options['release_name']
    output = options['output']
    tester_name = options['tester_name'] if options.get('tester_name') \
        else os.environ['USER']

    logfile = 'none'   # Do not upload log file. Too time consuming.
    # determine domain. config.ini > test path
    if options['domain']:
        domain = options['domain']
    else:
        possible_domains = ['dc', 'horizon', 'common', 'heat', 'mtc',
                            'networking', 'security', 'patching',
                            'nova', 'storage', 'sysinv', 'containers']
        for possible_domain in possible_domains:
            if possible_domain.lower()+'/' in test_name:
                domain = possible_domain.upper()
                break
        else:
            domain = 'cgcsauto'

    if test_name is None:
        test_name = options['test_name']
    elif '::' in test_name:
        test_name = test_name.split('::')[-1]

    test_name = test_name.replace(" ", "_").replace('(', '_').\
        replace(')', '_').replace(';', '_')
    # get the results of the test execution
    if result is None:
        result = options['result']
        if options['result'] == '' or options['result'] is None:
            result_parser = TestResultsParser(logfile)
            result = result_parser.parse()

    # Prepare to upload
    # Covert result to uppercase, such as PASS, FAIL, SKIP
    result = re.findall('(skip|pass|fail)', result.lower())
    result = result[0].upper() if result else 'UNKNOWN'

    # create a data file containing test information
    os.system("rm -rf %s" % output)
    env_params = \
        "-o '%s' -x '%s'  -n '%s' -t '%s' -r '%s' -l '%s' -b '%s' -u '%s' -d " \
        "'%s' -j '%s' -a '%s' -R '%s' -s '%s' -L '%s' -J '%s'" % (
            output, tag, tester_name, test_name, result, lab_name, build,
            userstory, domain, jira, logfile, release_name, build_server,
            system_type, build_job)

    ini_writer = os.path.join(LOCAL_PATH, 'ini_writer.sh')
    cmd = "%s %s" % (ini_writer, env_params)
    os.system(cmd)

    # write to the mongo database
    test_reporter = os.path.join(WASSP_PATH,
                                 "wassp/host/tools/report/testReportManual.py")
    activate = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")

    report_file_name = log_dir + '/mongo_res.log'
    upload_cmd = "{} {} -f {} 2>&1 ".format(activate, test_reporter, output)

    with open(report_file_name, mode='a') as f:
        f.write("Mongo upload results for test case: %s\n" % test_name)
        local_child = pexpect.spawn(command=upload_cmd, encoding='utf-8',
                                    logfile=f, timeout=120)
        try:
            local_child.expect(pexpect.EOF, timeout=120)
        except Exception as e:
            # Don't throw exception otherwise whole test session will end
            err = "Test result failed to upload. \nException caught: " \
                  "{}\n".format(e.__str__())
            print(err)
            f.write('\n' + err + '\n')
            return None

        upload_output = local_child.before

        res = re.search("Finished saving test result .* to database",
                        upload_output)
        msg = "Test result successfully uploaded to MongoDB" if res else \
              "Test result failed to upload. Please check parameters stored " \
              "at {}\n{}".format(output, upload_output)

        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        extra_info = '\nDate: %s. Report tag: %s\n\n' % (today_date, tag)
        msg += extra_info

        f.write('\n' + msg + "\n")
        print(msg)

    return res


def collect_user_input_and_upload_results(test_name=None, result=None,
                                          log_dir=None):
    """
    collect the test environment variables
    """

    # check for any user input and defaults
    options = parse_user_args()

    # get the environment variables
    build = options.build
    build_server = options.build_server
    build_job = options.build_job
    lab = options.lab.upper().replace('-', '_')
    userstory = options.userstory
    domain = options.domain
    release_name = options.release_name
    output = options.output
    tester_name = options.tester_name
    tag = options.tag
    system_type = options.system_label
    if isinstance(system_type, str):
        system_type = system_type.upper()

    jira = ''

    logfile = 'none'
    # if log_dir is None:
    #     logfile = options.logfile
    # else:
    #     logfile = os.path.join(log_dir, 'TIS_AUTOMATION.log')

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
    env_params = \
        "-o '%s' -x '%s'  -n '%s' -t '%s' -r '%s' -l '%s' -b '%s' -u '%s' " \
        "-d '%s' -j '%s' -a '%s' -R '%s' -s '%s' -L '%s' -J '%s'" % (
            output, tag, tester_name, test_name, result, lab, build,
            userstory, domain, jira, logfile, release_name, build_server,
            system_type, build_job)

    LOG.info("Saving results for test case: %s" % test_name)
    LOG.info('Query parameters: %s' % env_params)
    ini_writer = os.path.join(LOCAL_PATH, 'ini_writer.sh')
    os.system("%s %s" % (ini_writer, env_params))

    # write to the mongo database
    test_reporter = os.path.join(WASSP_PATH,
                                 "wassp/host/tools/report/testReportManual.py")
    activate = os.path.join(WASSP_PATH, ".venv_wassp/bin/python3")
    if not os.system("%s %s -f %s 2>&1" % (activate, test_reporter, output)):
        msg = "Data upload successful."
    else:
        msg = \
            "Data upload failed. Please check parameters stored at %s" % output
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
    parser.add_argument('-b', '--build', dest='build',
                        default=defaults['build'])
    parser.add_argument('-l', '--lab', dest='lab', default=defaults['lab'])
    parser.add_argument('-L', '--system_label', dest='system_label',
                        default=defaults['system_label'])
    parser.add_argument('-u', '--userstory', dest='userstory',
                        default=defaults['userstory'])
    parser.add_argument('-d', '--domain', dest='domain',
                        default=defaults['domain'])
    parser.add_argument('-r', '--result', dest='result',
                        default=defaults['result'])
    parser.add_argument('-R', '--release_name', dest='release_name',
                        default=defaults['release_name'])
    parser.add_argument('-o', '--output', dest='output',
                        default=defaults['output'])
    parser.add_argument('-n', '--tester_name', dest='tester_name',
                        default=defaults['tester_name'])
    parser.add_argument('-t', '--test_name', dest='test_name',
                        default=defaults['test_name'])
    parser.add_argument('-x', '--tag', dest='tag', default=defaults['tag'])
    parser.add_argument('-j', '--jira', dest='jira', default=defaults['jira'])
    parser.add_argument('-s', '--build_server', dest='build_server',
                        default=defaults['build_server'])
    parser.add_argument('-J', '--build_job', dest='build_job',
                        default=defaults['build_job'])
    parser.add_argument('-a', '--logfile', dest='logfile',
                        default=defaults['logfile'])

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
