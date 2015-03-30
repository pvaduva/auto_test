#!/usr/bin/env python3
"""
This script performs 3 SNMP operations: get, get next and get bulk.  The goal is to test the newly introduced
historical alarms table.  In order to function, the test requires access to two MIB files: the WRS alarm MIB
and the WRS Enterprise MIB.  It uses pysnmp to execute the SNMP commands.  pysnmp requires conversion of the
MIBs from a text file to a py file.  This is done using smidump.  In order to run this test, the user will
need to install the following packages on their test server, i.e. the system that invokes the test:

  * smitools (this can be installed via the packaging manager, i.e. apt)
  * pysnmp (this can be installed via easy install)
  * pyasn1 (this is required by pysnmp and it should be pulled in automatically)

The DUT (device under test) has the requirement that the SNMP community string has been created.  If you are
running the test manually, you can do this via the following steps:

  * ssh to the DUT
  * type "source /etc/nova/openrc"
  * type "system snmp-comm-add -c test_community" 

After that, you can run the script on the command line by typing:

  ./test_snmp_historical_alarms.py <floatingIPAddr>
"""
# imports
from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.smi import builder
from pysnmp import debug
import os
import itertools
import time
import sys
import logging
from random import randint

# constants
COMMUNITY_STRING = "test_community"
SNMP_PORT = 161

MAX_ALRM_TBL_SIZE = 2000
MAX_REP = 3 
NON_REP = 1

OID = {"wrsAlarmHistoryIndex": "1.3.6.1.4.1.731.1.1.1.1.2.1.1",
       "wrsAlarmHistoryUuid": "1.3.6.1.4.1.731.1.1.1.1.2.1.2",
       "wrsAlarmHistoryAlarmId": "1.3.6.1.4.1.731.1.1.1.1.2.1.3",
       "wrsAlarmHistoryAlarmState": "1.3.6.1.4.1.731.1.1.1.1.2.1.4",
       "wrsAlarmHistoryEntityInstanceId": "1.3.6.1.4.1.731.1.1.1.1.2.1.5",
       "wrsAlarmHistoryDateAndTime": "1.3.6.1.4.1.731.1.1.1.1.2.1.6",
       "wrsAlarmHistoryAlarmSeverity": "1.3.6.1.4.1.731.1.1.1.1.2.1.7",
       "wrsAlarmHistoryReasonText": "1.3.6.1.4.1.731.1.1.1.1.2.1.8",
       "wrsAlarmHistoryEventType": "1.3.6.1.4.1.731.1.1.1.1.2.1.9",
       "wrsAlarmHistoryProbableCause": "1.3.6.1.4.1.731.1.1.1.1.2.1.10",
       "wrsAlarmHistoryProbableRepairAction": "1.3.6.1.4.1.731.1.1.1.1.2.1.11",
       "wrsAlarmHistoryServiceAffecting": "1.3.6.1.4.1.731.1.1.1.1.2.1.12",
       "wrsAlarmHistorySuppressionAllowed": "1.3.6.1.4.1.731.1.1.1.1.2.1.13",
       "wrsAlarmHistoryEntry": "1.3.6.1.4.1.731.1.1.1.1.2.1",
       "wrsAlarmHistoryTable": "1.3.6.1.4.1.731.1.1.1.1.2"}

MIB_PATH = "/tmp/mibs"
MIB_SRC = ["wrsEnterpriseReg.mib.txt", "wrsAlarmMib.mib.txt"]

# MIB to preload, MIB source file, MIB output file
MIB_SRCLIST = [["", "wrsEnterpriseReg.mib.txt", "WRS-ENTERPRISE-REG-MIB"],
               ["wrsEnterpriseReg.mib.txt", "wrsAlarmMib.mib.txt", "WRS-ALARM-MIB"]]

def mibTextToPy(mib_path):
    """ Convert mibs to a format that pysnmp can actually use. 
    """

    logging.info("Setting MIB Path")
    cmdGen = cmdgen.CommandGenerator() 

    mibBuilder = builder.MibBuilder()
    mibBuilder = cmdGen.snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder 
    mibSources = mibBuilder.getMibSources() + (builder.DirMibSource(mib_path), )
    mibBuilder.setMibSources(*mibSources)
    logging.info(mibBuilder.getMibSources())

    if os.path.isdir(mib_path):
        for mib in MIB_SRCLIST:
            mib_preload = mib[0]
            mib_srcname = mib[1]
            mib_destname = mib[2]
            if not os.path.isfile(os.path.join(mib_path, mib_srcname)):
                logging.critical("FAILED: Required MIB %s is missing from \
                                  path %s") % (mib_srcname, mib_path)
                return 1
            logging.info("Converting MIB to py")
            if mib_preload: 
                cmd = "smidump -k -p %s -f python %s | libsmi2pysnmp > %s" % \
                      (os.path.join(mib_path, mib_preload),
                       os.path.join(mib_path, mib_srcname),
                       os.path.join(mib_path, mib_destname) + ".py")
            else:
                cmd = "smidump -k -f python %s | libsmi2pysnmp > %s" % \
                      (os.path.join(mib_path, mib_srcname),
                       os.path.join(mib_path, mib_destname) + ".py")
            logging.info(cmd)
            os.system(cmd)
            logging.info("Loading MIB")
            mibBuilder.loadModules(mib_destname)
            logging.info(mib_destname)
    else:
        logging.critical("FAILED: MIB directory %s is not present") % mib_path
        return 1

    return cmdGen 

def snmpGet(community_string, snmp_ip, snmp_port, cmdGen, oid):
    """ This function takes the community string, the snmp IP, the snmp
        port, the MIB name and the MIB object name, and returns the OID.
    """

    errorIndication, errorStatus, errorIndex, varBinds = cmdGen.getCmd(
        cmdgen.CommunityData(community_string),
        cmdgen.UdpTransportTarget((snmp_ip, snmp_port)),
        oid, lookupNames=True, lookupValues=True)

    if errorIndication:
        logging.error(errorIndication)
    else:
        if errorStatus:
            logging.error("%s at %s" % (errorStatus.prettyPrint(),
                           errorIndex and varBinds[int(errorIndex)-1] 
                           or '?'))
        else:
            for name, val in varBinds:
                logging.info("%s = %s" % (name.prettyPrint(), val.prettyPrint()))
            return 0

    return 1

def snmpGetNext(community_string, snmp_ip, snmp_port, cmdGen, oid):
    """ This function performs an snmp walk using the obtained OID.
    """
            
    errorIndication, errorStatus, errorIndex, varBindTable = cmdGen.nextCmd(
        cmdgen.CommunityData(community_string),
        cmdgen.UdpTransportTarget((snmp_ip, snmp_port)),
        oid, lookupNames=True, lookupValues=True)

    if errorIndication:
        logging.error(errorIndication)
    else:
        if errorStatus:
            logging.error("%s at %s" % (errorStatus.prettyPrint(),
                          errorIndex and varBinds[int(errorIndex)-1] 
                          or '?'))
        else:
            for varBindTableRow in varBindTable:
                for name, val in varBindTableRow:
                    logging.info("%s = %s" % (name.prettyPrint(), val.prettyPrint()))
            return 0

    return 1

def snmpGetBulk(community_string, snmp_ip, snmp_port, non_rep, max_rep, cmdGen, oid):
    """ This function performs a SNMP get bulk command.
    """
    
    errorIndication, errorStatus, errorIndex, varBindTable = cmdGen.bulkCmd(
        cmdgen.CommunityData(community_string),
        cmdgen.UdpTransportTarget((snmp_ip, snmp_port)),
        non_rep, max_rep, oid, lookupNames=True, lookupValues=True)

    if errorIndication:
        logging.error(errorIndication)
    else:
        if errorStatus:
            logging.error("%s at %s" % (errorStatus.prettyPrint(),
                           errorIndex and varBinds[int(errorIndex)-1] 
                           or '?'))
        else:
            for varBindTableRow in varBindTable:
                for name, val in varBindTableRow:
                    logging.info("%s = %s" % (name.prettyPrint(), val.prettyPrint()))
            return 0, len(varBindTable) - 1

    return 1

if __name__ == "__main__":

    failFlag = False

    # Get the floating ip from the command line
    snmp_ip = sys.argv[1]

    # Set the logging level
    logging.basicConfig(level=logging.DEBUG)
#    debug.setLogger(debug.Debug('all'))

    # Generate the python MIBs
    cmdGen = mibTextToPy(MIB_PATH)

    # Test #1: Perform an SNMP Get Bulk command
    logging.info("Test 1: Perform an SNMP Get Bulk command")
    for i in range(len(OID) - 1):
        oid = (OID["wrsAlarmHistoryEntry"] + "." + str(i), )
        retVal, tableSize = snmpGetBulk(COMMUNITY_STRING, snmp_ip, SNMP_PORT, NON_REP, MAX_REP, cmdGen, *oid)
        if retVal == 1:
            logging.error("Test 1 FAILED")
            failFlag = True
            break

    # Test #2: Perform an SNMP Walk over the entire tree starting at the root
    logging.info("Test 2: Perform SNMP Walk")
    oid = (OID["wrsAlarmHistoryTable"], )
    retVal = snmpGetNext(COMMUNITY_STRING, snmp_ip, SNMP_PORT, cmdGen, *oid)
    if retVal == 1:
        logging.error("Test 2 FAILED")
        failFlag = True

    # Test #3: Perform an SNMP Get
    # Do individual snmpget requests to retrieve one alarm entry
    # The value can be from 1 to 2000 inclusive (potential)
    logging.info("Test 3: Perform SNMP Get")
    logging.debug("The size of the table is: %s" % str(tableSize))
    instanceno = str(randint(1,  tableSize))
    for item in OID:
        oid = (OID[item] + "." + instanceno, )
        retVal = snmpGet(COMMUNITY_STRING, snmp_ip, SNMP_PORT, cmdGen, *oid) 
        if retVal == 1:
            logging.error("Test 3 FAILED")
            failFlag = True
            break

    # Test #4: Perform a SNMP Walk in one entry
    # We should get a collection of related information on each run, 
    # i.e. AlarmIDs only, AlarmState only, etc.
    logging.info("Test 4: Perform a SNMP Walk in one entry")
    for i in range(len(OID) - 1):
        oid = (OID["wrsAlarmHistoryEntry"] + "." + str(i), )
        retVal = snmpGetNext(COMMUNITY_STRING, snmp_ip, SNMP_PORT, cmdGen, *oid)
        if retVal == 1:
            logging.error("Test 4 FAILED")
            failFlag = True
            break

    if failFlag == True:
        logging.critical("Test suite FAILED")
        sys.exit(1)
    else:
        logging.info("Test suite PASSED")
        sys.exit(0)
