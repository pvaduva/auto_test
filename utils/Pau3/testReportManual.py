#!/usr/bin/env python3

'''
testReportLinux.py - The Linux WASSP test case run results report script

Copyright (c) 2014-2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

This script is used to upload the result of manual test case into mongoDB.
'''

'''
modification history:
---------------------
12may15,srr  Storing user stories
11may15,srr  Filtering out empty tags and defects
08may15,srr  Handle defects and tags properly
12jan15,pya  Add gtsData and sutData for manual case
17sep14,tw   Allow upload 'tags', 'tcTotal', and 'tcPassed' data for manual case
07aug14,pya  Creation


'''
import os
import sys
import logging
import xml.etree.cElementTree as ET
import configparser
import time
import datetime
import uuid
from optparse import OptionParser

if __name__ == "__main__":
    # add to PYTHONPATH the parent of the current file folder
    sys.path.insert(0, os.path.dirname(
                                os.path.dirname(os.path.realpath(__file__))))

from testResultsParser import (TestRunResults, STEP_BUILD, STEP_BOOT,
                               STEP_RTC, STEP_EXEC, STATUS_PASS, STATUS_FAIL,
                               DB_PLATFORM_ATTRIBUTES, REPORT_SYSTEM_ATTRIBUTES)
from lib.idutils import SutData, GtsData
from lib.datetimeutils import getRunStartDate, RUN_START_DATE_FORMAT
from lib.validateutils import validateReleaseAndEnvName, getEnvironmentId

RESULT_STEPS = [STEP_BUILD, STEP_BOOT, STEP_RTC, STEP_EXEC]
DEFAULT_CHECK_LIST = ['testerName', 'testName', 'status', 'statusDetail']
STEP_CHECK_LIST = ['status', 'statusDetail' ]
ATTRS_CHECK_LIST = ['project']

log = logging.getLogger(__name__)

#------------------------------------------------------------------
class ResultsParser():
    ''' Parse a test case result
    '''

    def __init__(self, resultFile):
        self.config = self.getResultConfig(resultFile)
        self.testData = TestRunResults()

        # dictionary that holds all information about the System Under Test
        # (SUT)
        self.sutData = SutData()

        # dictionary that holds all information about the Generic Test Suite
        # (GTS)
        self.gtsData = GtsData()

        self.getDefaultData()

    def getResultConfig(self, resultFile):
        ''' Read and parse the data of result '''

        try:
            resultConfig = configparser.ConfigParser()
            resultConfig.optionxform = str
            resultConfig.read(resultFile)

            # Make sure the required fields are defined
            [ resultConfig.get('default', attr) for attr in DEFAULT_CHECK_LIST ]
            [ resultConfig.get('attributes', attr) for attr in ATTRS_CHECK_LIST ]
            [ resultConfig.get(step, attr) for step in RESULT_STEPS
                                          for attr in STEP_CHECK_LIST ]

            # When the overall status is PASS,
            # the status of each step should be PASS too.
            failInStepStatus = any(STATUS_FAIL in resultConfig.get(step, 'status').upper()
                                   for step in RESULT_STEPS)
            if resultConfig.get('default', 'status') == STATUS_PASS and failInStepStatus:
                raise Exception("Inconsistent status between "+
                                "overall status and step status.")

        except Exception as e:
            log.exception('File data is not valid.')
            sys.exit(1)

        return resultConfig

    def getDefaultData(self):
        ''' Get result information from results.ini '''

        for k, v in self.config.items('default'):
            if k == 'tags':
                for tag in filter(None, [val.strip() for val in v.split(',')]):
                    self.testData.tags.add(tag)
                continue
            if k == 'defects':
                for defect in filter(None, [val.strip()
                                                     for val in v.split(',')]):
                    self.testData.defects.add(defect)
                continue
            if k == 'userStories':
                self.testData.userStories = sorted(set(filter(None, [val.strip()
                                                     for val in v.split(',')])))
                continue
            if k == "uri":
                self.testData.testDir = v
                continue
            if k in ['tcTotal', 'tcPassed']:
                v = int(v)
            setattr(self.testData, k, v)

        for k, v in self.config.items('attributes'):
            #Ignore 'tags' and 'defects' in attributes items
            if k in ['tags', 'defects']:
                continue
            self.testData.addAttr(k, v)

        if not self.testData.testTimestamp:
            self.testData.testTimestamp = time.time()

        steps = set(RESULT_STEPS)
        sections = set(self.config.sections())

        for step in steps.intersection(sections):
            t_step = getattr(self.testData, step)

            for k, v in self.config.items(step):
                # handle multiple log files
                if k == 'logs':
                    for log in filter(None,
                                        [val.strip() for val in v.split(',')]):
                        t_step[k].add(log)
                    continue
                t_step[k] = v

        self.testData.testRun['localInfo'] = {}
        self.testData.testRun['path'] = ''
        self.testData.testRun['testPlan'] = ''
        self.testData.testRun['groupID'] = str(uuid.uuid4())

        for attrName, attrValue in self.testData.attributes:
            # process sutData
            if (attrValue and attrName in REPORT_SYSTEM_ATTRIBUTES.values()
                or attrName in DB_PLATFORM_ATTRIBUTES.values()):
                self.sutData.addAttr(attrName, attrValue)

        # Check if the platform is 64 bit
        boardName = self.testData.getAttr('board_name') or ''
        try:
            if boardName and next(boardName)[1].endswith('64'):
                self.testData.addAttr('bits', '64')
                self.sutData.addAttr('bits', '64')
        except StopIteration:
            pass

        # get the run start date
        self.testData.runStartDate = datetime.datetime.strptime(
            getRunStartDate(), RUN_START_DATE_FORMAT)

        # copy the test data attributes to the GTS
        self.gtsData.getTestDataAttrs(self.testData)

        # add the gts and sut objects to the testData as they
        # are needed for generating the TS ID when connected to
        # the database.
        self.testData.gtsData = self.gtsData
        self.testData.sutData = self.sutData

    def parse(self):
        ''' Return the data '''

        return self.testData

#----------------------------------------------------------------------
class WASSPReport():
    ''' Process the test case run results and report them
    '''

    def __init__(self, resultFile):
        ''' Parse the test run results based on the result file
        '''

        # parse the test run
        self.resultsParser = ResultsParser(resultFile)
        self.testData = self.resultsParser.parse()

    #-------------------------------------------------------------------------#
    def processReport(self):
        ''' Send the report to logs and database
        '''

        #_____________________________________________________________________#
        # report the step results to the default logger
        for step in RESULT_STEPS:
            self.reportResultsToLog(step=step)

        #_____________________________________________________________________#
        # report the overall results to the default logger
        self.reportResultsToLog()

        #_____________________________________________________________________#
        # send the results to a database
        self.reportResultsToMongo()

    #-------------------------------------------------------------------------#
    def reportResultsToLog(self, step=None):
        ''' Report the test run results to the default logger
        '''

        if step:
            stepInfo = getattr(self.testData, step)

            logSep()
            # report the step status
            log.info('%s status: %s', step.capitalize(),
                     stepInfo['status'])

            logSep()
            # report the step logs
            for file in stepInfo['logs']:
                log.info('%s log file: %s', step.capitalize(), file)
        else:
            logSep()
            log.info('Test status: %s', self.testData.status)
            log.info('Details: %s', self.testData.statusDetail)
            logSep()

    #-------------------------------------------------------------------------#
    def reportResultsToMongo(self):
        ''' Report the test run results to a user specified database
        '''

        try:
            from testResultsMongo import reportTestResults

            # store results in the database
            reportTestResults(self.testData,
                              configData=self.testData.testRun['localInfo'])

        except Exception:
            log.exception('Reporting test results to database failed')

#-----------------------------------------------------------------------------#
def logSep(sep='=', count=60):
    ''' Log a separator line
    '''
    log.info(sep*count)

#-----------------------------------------------------------------------------#

if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s',
                        level=logging.INFO)

    parser = OptionParser(usage="Usage: %prog [OPTION] [FILE]")

    parser.add_option('--file', '-f', dest='file',
                      help='[REQUIRED] Provide path to results.ini')
    parser.add_option('--verbose', '-v', dest='verbose',
                      action='store_true', default=False, help='Verbose')
    (options, args) = parser.parse_args()

    if not options.file:
        # print help and exit
        parser.parse_args(['-h'])

    if options.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    report = WASSPReport(options.file)

    # save the supplied release and environment names for validation
    relname = os.environ.get('RELEASE_NAME', report.testData.releaseName)
    if relname:
        os.environ['RELEASE_NAME'] = relname
    envname = os.environ.get('ENVIRONMENT_NAME',
                                        report.testData.environmentName)
    if envname:
        os.environ['ENVIRONMENT_NAME'] = envname

    # validate Release key and Environment name
    # Note: None is returned for invalid values.
    #(releaseKey,
    # envNameKey,
    # origRelease,
    # origEnvName) = validateReleaseAndEnvName()

    (releaseKey,
     envNameKey) = validateReleaseAndEnvName()

    #if (releaseKey is None) or (envNameKey is None):
    #    logging.error('Invalid release or environment name supplied'
    #              'Release:"%s", environment name:"%s"',
    #              releaseKey or origRelease,
    #              envNameKey or origEnvName)
    #    sys.exit(1)

    if (releaseKey is None) or (envNameKey is None):
        logging.error('Invalid release or environment name supplied'
                  'Release:"%s", environment name:"%s"',
                  releaseKey,
                  envNameKey)
        sys.exit(1)

    envId = getEnvironmentId()

    if envId:
        report.testData.environmentId = envId
        report.testData.environmentName = envNameKey
        report.testData.releaseName = releaseKey

    report.processReport()

    # exit with an error code on failure
    if report.testData.status != STATUS_PASS:
        sys.exit(1)
