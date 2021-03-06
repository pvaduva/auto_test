#!/usr/bin/env python3

'''
cgcsTestResultsParser.py - parse any given log file for test result

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
import urllib.parse as urllib
import xml.etree.cElementTree as ET
import testResultsParser
from optparse import OptionParser


def extract_result(line):
    detail_re = None
    match_result = re.match('.*tests="(\d+)" errors="(\d+)" failures="(\d+)" skip="(\d+)".*', line)
    if match_result:
        detail_re = {}
        detail_re['errors'] = 0
        detail_re['failed'] = 0
        detail_re['skip'] = 0
        detail_re['passed'] = 0
          
        detail_re['errors'] = int(match_result.group(2))
        detail_re['failed'] = int(match_result.group(3))
        detail_re['skip'] = int(match_result.group(4))

        if ((detail_re['failed'] == 1) or 
            (detail_re['errors'] == 1) or
            (detail_re['skip'] == 1)): 
            print ("Test case: FAILED")
        else:
            detail_re['passed'] = 1
            print ("Test case: PASS")
    return detail_re

#-----------------------------------------------------------------------------#   
class TestResultsParser():
    ''' Parse any user-specific test case results
    '''

    def __init__(self, testDataFile):
        ''' Obtain the test run results 
        '''

        self.testDataFile = testDataFile 

    def parse(self):
        ''' Parse any additional pieces of information and store the 
        amended results
        '''

        # set custom test results
        try:
            with open(self.testDataFile, 'r') as f:
                result_dict = self.extract_noseresult(f)
            f.close()
        except Exception as e:
            print ("Test case: FAILED. %s" % e)

    def extract_noseresult(self, lines):
    
        result = {}
        result['passed'] = 0
        result['failed'] = 0
        
        for l in lines:
            match_result = extract_result(l)
            if match_result != None:
                result['passed'] = result['passed'] + match_result['passed']
                result['failed'] = result['failed'] + match_result['failed']

        if (0 == result['passed'] + result['failed']):
            return None
        else:
            return result

#-----------------------------------------------------------------------------#
if __name__ == '__main__':

                        
    parser = OptionParser()

    parser.add_option('--file', '-f', dest='file',
                      help='Provide path to test results file')
    (options, args) = parser.parse_args()

    if not options.file:
        # print help and exit
        parser.parse_args(['-h'])
    
    TestResultsParser(options.file).parse()
