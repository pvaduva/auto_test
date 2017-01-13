#! /usr/bin/env python3

'''
Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.



DESCRIPTION:
This program queries the test case database for the results of a test run
and then sends an email report with the information.

usage is;
./cgcs_query_db.py -l Ottawa_ironpass_1-4 -m sanity 
                   -p IronPass -b 2016-02-26_22-04-23 -t "Test Report"
                   -s "first.last@windriver.com"

modification history:
---------------------
10jul16,amf  Add a backup report server
02mar16,amf  Add error handling for database query failures
13mar15,amf  initial creation
'''

import os
import sys
import shutil
import platform
import datetime
import argparse
from string import Template
from xlrd import open_workbook

LOCAL_DIR = os.path.abspath(os.path.dirname(__file__))

# Set constants
totalnum=1
passnum=0
passrate=0
execfail=0
RELEASE_NAME = "[MYSQL1:2226]"
PRIMARY_REPORT_SERVER="report.wrs.com"
BACKUP_REPORT_SERVER="yow-ssp3-lx.wrs.com:8000"

REPORT_SERVER=PRIMARY_REPORT_SERVER
CORP="corp.ad.wrs.com"

EMAILMESSAGE="/tmp/cgcs_emailmessage.html"
EMAIL_LIST="ENG-TiS@$CORP,Doina.Lepadatu@$CORP,Ed.Illidge@$CORP,Mark.Faig@$CORP"
PROJECT="CGCS+2.0"

def parse_args():
    ''' Get commandline options. 
    '''

    parser = argparse.ArgumentParser()

    # file name
    parser.add_argument('-b','--build', dest='build',
                        default='LATEST_BUILD')
    parser.add_argument('-c','--host', dest='hostIP')
    parser.add_argument('-d','--description', dest='description',
                        default='2 controllers + 2 computes')
    parser.add_argument('-l','--lab', dest='lab',
                        default='Ottawa_ironpass_1-4')
    parser.add_argument('-m','--mongotag', dest='mongo_tags',
                        default='sanity')
    parser.add_argument('-p','--platform', dest='platform',
                        default='IronPass')
    parser.add_argument('-t','--title', dest='reportTitle', 
                        default='TiS Daily Sanity Test Report')
    parser.add_argument('-s','--sendmail', dest='receiverlist',
                        default='nomail@corp.ad.wrs.com')
    parser.add_argument('-r', '--resdir', dest='resdir')

    # extract all args
    myArguments = parser.parse_args()

    # must have a filename and value
    #if not (myArguments.fileArg and myArguments.keyArg):
    #    print("errorMsg : need to supply a filename")
    #    sys.exit(1)

    return (myArguments)


#Get the total test runs from the MongoDB report database
def query_database(options, start_date, query_date, localfolder):
    ''' Create a database query and then parse the results to get the
        status of the test run.
    '''

    global querystring 
    query = True

    # create a temporary file for storing results of the database query
    tempFile = "/tmp/report_%s.html" % options.platform

    # create the database query
    querystring = \
'"http://%s/reportgenerator/rawresults/245faa5c-816d-11e4-a2ea-90b11c4fbb02/?main-TOTAL_FORMS=2\
&main-INITIAL_FORMS=2&main-MAX_NUM_FORMS=20\
&main-0-filter=project&main-0-options=CGCS+2.0\
&main-1-filter=tags&main-1-options=%s\
&mainform-submit=Search&lastRunFilter=on"' \
% (REPORT_SERVER, options.mongo_tags)

    query = querystring + ' -O %s' % tempFile
    os.system("wget %s" % query)

    # get the total number of tests
    totalnum = parseKey(tempFile, "Total:")
    print("Total: %s" % totalnum)

    if (totalnum == 0):
        print("Error. Database query timed out. Trying the query again.")
        os.system("wget %s" % query)
        # get the total number of tests
        totalnum = parseKey(tempFile, "Total:")
        print("Total: %s" % totalnum)

    if (totalnum == 0):
        # set everything to zero to indicate failure
        passnum = 0
        passrate = 0
        execfail = 0

        # use the alternative results file
        query = False
        localfile = os.path.join(localfolder, 'summary.json')
        passnum = parseKey(localfile, "passes", fileType='json')
        execfail = parseKey(localfile, "fails", fileType='json')
        totalnum = parseKey(localfile, "testRunCount", fileType='json')
        passrate = round((float(passnum)/float(totalnum))*100, 2)
    else:
        # get the results from the MongoDB report database
        PASS_STRING = parseKey(tempFile, "Passed:")
        print("PASS_STRING: %s" % PASS_STRING)
        try:
            passnum = PASS_STRING.split(' ')[0]
            passrate = PASS_STRING.split(' ')[-1]
            execfail = parseKey(tempFile, "Failed:")
        except:
            pass
    print("PASS: %s" % passnum)
    print("PASSRATE: %s" % passrate)
    print("Exec Fail: %s" % execfail)
   
    return (totalnum, passnum, passrate, execfail, query) 

#Get the total test runs from the MongoDB report database
def save_summary_report(plat, querydate):
    ''' Saves a copy of the latest results just in case the database query 
        fails.
    '''

    # create a temporary file for storing results of the database query
    summaryFolder = "/tmp/Logs/%s/Summary" % plat
    destFolder = os.path.join(summaryFolder, '..', plat, querydate)

    command = 'mkdir -p %s'

    try:
        os.makedirs(destFolder)
    except (OSError, FileExistsError):
        try:
            os.system(command % destFolder)
        except (OSError, FileExistsError):
            pass

    shutil.copy(os.path.join(summaryFolder,'summary.html'), destFolder)
    shutil.copy(os.path.join(summaryFolder,'summary.json'), destFolder)

    return destFolder

#Calculate passrate
def analyze_results(totalnum, passnum):
    ''' Analyze the results of the test results query to get the
        status of the test run.
    '''

    if ( totalnum == 0 ):
        print("Database query failed")
        status = 'Unknown'
        passrate = '<Unknown. Database query failed>'
    else:
        passrate = round(100*float(passnum)/float(totalnum), 2)

        print ("totalnum: %s" % totalnum)
        print ("passnum: %s" % passnum)
        print ("passrate: %s" % passrate)

        if (( passrate > 99 )) :
            status='GREEN'
        elif (( passrate > 74 )):
            status='YELLOW'
        else:
            status='RED'

    return (status, passrate)

def parseKey(fileName, key, fileType='html'):
    ''' Parse the lines from the data returned from the test results
        database to determine the total runs, number of pass, number of 
        failed, etc
    '''

    found = 0

    # Find the line with the key in it
    try:
        with open(fileName) as f:
            for line in f.readlines():
               if key in line:
                  break;

    except IOError as e:
        print ("Line not found")
        return(found)

    # Parse the line and obtain the key value
    try:
        if (fileType == 'json'):
            found = line.split(':')
            if len(found) > 1:
                found = found[1].split(',')
                found = found[0].strip()
            else:
                found = 0
        elif (fileType == 'html'):
            found = line.split('</li>')
            if len(found) > 1:
                found = found[0].split('<li><b>%s</b>' % key)
                found = found[1].strip()
            else:
                found = 0
    except Exception as e:
        # any other exceptions
        print ("Exception: %s" % e)
        return 0

    return(found)


def parseResFile(resfile):
    passnum = passrate = failnum = failrate = totalnum = skipnum = -1
    testcase_list = []
    with open(resfile, mode='r') as f:
        for line in f:
            if 'Passed ' in line or 'Failed	' in line or 'Skipped ' in line:
                testcase_list.append(line)

            elif 'Passed:' in line:
                passres = line.split(sep=' ')
                passnum = int(passres[1].strip())
                passrate = float(passres[2].replace('(', '').replace(')', '').strip())
            elif 'Failed:' in line:
                failres = line.split(sep=' ')
                failnum = int(failres[1].strip())
                failrate = float(failres[2].replace('(', '').replace(')', '').strip())
            elif 'Total:' in line:
                totalnum = int(line.split(' ')[1].strip())
            elif 'Skipped:' in line:
                skipnum = int(line.split(' ')[1].strip())

    testcase_list = '<br>'.join(testcase_list)
    return passnum, passrate, failnum, failrate, totalnum, skipnum, testcase_list


# Create trend chart
def generate_trend_chart(cgcs_lab, mongo_tags, build):
    ''' Generate a trend report of the results for the previous test runs.
    '''

    trend_chart_file = "/tmp/Logs/cgcs/trend_chart.png"

    # Get the current date
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    N=6
    query_date = datetime.datetime.now() - datetime.timedelta(days=N)
    query_date = query_date.strftime("%Y-%m-%d")

    #/usr/bin/wget -4 "http://yow-ssp2-lx.wrs.com/smartTool/genTrendChart/genTrendChart.php?project=$PROJECT&tags=$MONGO_TAGS&startdate=$SIX_DAYS_AGO&enddate=$TODAY_DATE&lab=${CGCS_LAB}" -O $TREND_CHART_FILE

    #MONGODBLINK_TREND_CHART="<a href=http://$REPORT_SERVER/reportgenerator/trendData/aaaaaaaa-bbbb-cccc-eeee-ffffffffffff/?main-TOTAL_FORMS=3&main-INITIAL_FORMS=3&main-MAX_NUM_FORMS=20&main-0-filter=test+date&main-0-dateStart=$SIX_DAYS_AGO&main-0-dateEnd=$TODAY_DATE&main-1-filter=project&main-1-options=$PROJECT&main-2-filter=tags&main-2-options=$MONGO_TAGS&main-3-filter=lab&main-3-options=${CGCS_LAB}&mainform-submit=Search><img src=cid:trend_chart.png></a><br>"

    # create the database query
    querystring = \
'"http://yow-ssp2-lx.wrs.com/smartTool/genTrendChart/genTrendChart.php?project=CGCS+2.0\
&build=%s\
&startdate=%s\
&enddate=%s"' \
% (mongo_tags, query_date, today_date)

    query = querystring + ' -O %s' % trend_chart_file
    print(query)
    #os.system("wget %s" % query)

    # create the mongodb link
    mongolink = \
'"http://%s/reportgenerator/trendData/aaaaaaaa-bbbb-cccc-eeee-ffffffffffff/?main-TOTAL_FORMS=3\
&main-INITIAL_FORMS=3\
&main-MAX_NUM_FORMS=20\
&main-0-filter=test+date&main-0-dateStart=%s\
&main-0-dateEnd=%s\
&main-1-filter=project&main-1-options=CGCS+2.0\
&main-2-filter=tags&main-2-options=%s\
&mainform-submit=Search"'\
% (REPORT_SERVER, query_date, today_date, mongo_tags)

    return mongolink

# Create xls report
def generate_xls_report(mongo_tags, start_date, end_date):
    """
    Generate an XLS document containing the results for the previous test runs.

    Args:
        mongo_tags (list|str): tags to filter the result, such as [cgcsauto_cpesanity_WCP_76-77, 2017-01-05_22-02-35]
        start_date (str): e.g., 2017-01-05
        end_date (str): e.g.,  2017-01-06

    Returns:

    """

    if isinstance(mongo_tags, str):
        mongo_tags = [mongo_tags]

    mongo_tags = ','.join(mongo_tags)
    xls_report_file = "/tmp/Logs/cgcs/cgcs_report.xls"

    # Get the current date
    querystring = \
'"http://%s/reportgenerator/export/245faa5c-816d-11e4-a2ea-90b11c4fbb02/?main-TOTAL_FORMS=2\
&main-INITIAL_FORMS=2\
&main-MAX_NUM_FORMS=20\
&table-1--report-dynamictable=xls\
&mainform-submit=Search\
&lastRunFilter=on\
&main-1-filter=tags\
&main-1-options=%s\
&main-0-filter=project\
&main-0-options=CGCS+2.0"'\
% (REPORT_SERVER, mongo_tags)

    # querystring = "http://panorama.wrs.com:8181/#/testResults/?database=RNT&view=list" \
    #               "&dateField=[runStartDate]&programs=active&resultsMode=last" \
    #               "&startDate={}&endDate={}" \
    #               "&releaseName={}" \
    #               "&tags=[]".format(start_date, end_date, RELEASE_NAME, mongo_tags)
    query = querystring + ' -O %s' % xls_report_file
    os.system("wget %s" % query)

    return xls_report_file

# Get a summary of the test cases
def get_testcase_summary(xlsFile):

    FORMAT = ['Test Name', 'Test Result']
    values = ""

    # Call the XLS file parser and reporter
    wb = open_workbook(xlsFile)
    for s in wb.sheets():
        headerRow = s.row(0)
        columnIndex = [x for y in FORMAT for x in range(len(headerRow)) if y == headerRow[x].value]
        formatString = ("%s "*len(columnIndex))[0:-1] + "\n<br>"
        for row in range(1,s.nrows):
            currentRow = s.row(row)
            currentRowValues = ["{:<80}".format(currentRow[x].value) for x in columnIndex]
            values += formatString % tuple(currentRowValues)

    return values


# Fill in the e-mail body
def generate_email_body(status, totalnum, passnum, failnum, 
                        passrate, options, query_date,
                        link, description, query, testcase_list=None):
    ''' Create a test report containing the information of the test runs.
    '''

    consolelogs_link = 'http://yow-cgcs-test.wrs.com/Logs/consolelogs/'
    hteelogs_link = 'http://yow-cgcs-test.wrs.com/Logs/%s/' % options.platform
    mongolink = generate_trend_chart(options.lab, 
                                     options.mongo_tags,
                                     options.build)

    xlsFile = generate_xls_report(options.mongo_tags)
    if testcase_list is None:
        testcase_list = get_testcase_summary(xlsFile)

    if (query):
        emailmessage = open(os.path.join(LOCAL_DIR, 'cgcs_mail_template.txt'))
    else:
        emailmessage = open(os.path.join(LOCAL_DIR, 'cgcs_error_template.txt'))

    doc = Template(emailmessage.read()) 

    params = { 'status':status, 
               'passnum':passnum, 'totalnum':totalnum,
               'failnum':failnum, 'passrate':passrate,
               'load':options.build, 'lab':options.lab, 'description':description,
               'query_date':query_date, 'link':link,
               'consolelogs_link':consolelogs_link, 'hteelogs_link':hteelogs_link, 
               'trend_link':mongolink, 'testcase_list': testcase_list
              }

    result = doc.substitute(params)
    with open('/tmp/email.out', 'w') as f:
        f.write(result)
    print(result)


def send_email(title, mailing_list, report_file, trend_file):
    ''' Send an email containing the test report.
    '''

    #msg = '/usr/bin/mutt -e "set from="svc-cgcsauto@windriver.com"" -e "set realname="svc-cgcsauto"" -e "set content_type=text/html" -a "%s" -s "%s" -- "%s" < "%s"'\
 #% (trend_file, title, mailing_list, report_file)
    msg = '/usr/bin/mutt -e "set from="svc-cgcsauto@windriver.com"" -e "set realname="svc-cgcsauto"" -e "set content_type=text/html"  -s "%s" -- "%s" < "%s"'\
 % (title, mailing_list, report_file)
    os.system(msg)


# Used to invoke the query and report generation from the command line
if __name__ == "__main__":

    global querystring
    # Get the command line options
    options = parse_args()

    # Get the current date
    N=0
    start_date = datetime.datetime.now() - datetime.timedelta(days=1)
    now = datetime.datetime.now() - datetime.timedelta(days=N)
    start_date = start_date.strftime("%Y-%m-%d")
    query_date = now.strftime("%Y-%m-%d")
    print("Query date:", query_date)

    # Save a copy of the local results
    localfolder = save_summary_report(options.platform, query_date)

    skipnum = -1

    # Query the database
    (total, passnum, passrate, execfail, query) = query_database(options,
                                                                 start_date,
                                                                 query_date,
                                                                 localfolder)
    link = querystring

    # Override a number of parameters if local file path is given
    testcase_list = None
    if options.resdir:
        resdir_ = options.resdir
        respath_ = os.path.join(options.resdir, 'test_result.log')
        passnum, passrate, failnum, failrate, total, skipnum, testcase_list = parseResFile(respath_)
        if '/tmp/Logs/' in resdir_:
            link = resdir_.replace('/tmp/', 'http://yow-cgcs-test.wrs.com/')
        query = True

    # Analyse the results
    status, passrate = analyze_results(total, passnum)
    if status == 'GREEN':
        cmd = 'echo GREEN > "/tmp/status.log"'
        os.system(cmd)

    # Generate the email
    load = options.build
    description = options.description
    generate_email_body(status, total, passnum, execfail, passrate, 
                        options, query_date, link, 
                        description, query, testcase_list=testcase_list)

    # Send the email
    title = '%s [%s] - %s' % (options.reportTitle, load, status)
    emailaddress = options.receiverlist
    trend_chart_file = "/tmp/Logs/cgcs/trend_chart.png"
    report_file = "/tmp/email.out"
    send_email(title, emailaddress, report_file, trend_chart_file)
