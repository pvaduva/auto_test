#!/usr/bin/python2.7

'''
Test server requirements:
  * smitools
  * pysnmp
  * pyasn1

System setup requirements:
  * ssh to machine
  * source /etc/nova/openrc
  * system snmp-comm-add -c test_community

System secondary requirements:
  * scp mibs off target each test or keep a static local copy
'''

# imports
from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.smi import builder
from pysnmp import debug
import os
import itertools
import time
import sys
from random import randint

# constants
COMMUNITY_STRING = "test_community"
#SNMP_IP = "128.224.150.189"
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

MIB_PATH = "mibs"
MIB_SRC = ["wrsEnterpriseReg.mib.txt", "wrsAlarmMib.mib.txt"]

# MIB to preload, MIB source file, MIB output file
MIB_SRCLIST = [["", "wrsEnterpriseReg.mib.txt", "WRS-ENTERPRISE-REG-MIB"],
               ["wrsEnterpriseReg.mib.txt", "wrsAlarmMib.mib.txt", "WRS-ALARM-MIB"]]

def mibTextToPy(mib_path):
    """ Convert mibs to a format that pysnmp can actually use. 
    """

    print "::: Setting MIB Path :::"
    cmdGen = cmdgen.CommandGenerator() 

    mibBuilder = builder.MibBuilder()
    mibBuilder = cmdGen.snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder 
    mibSources = mibBuilder.getMibSources() + (builder.DirMibSource(mib_path), )
    mibBuilder.setMibSources(*mibSources)
    print mibBuilder.getMibSources()

    if os.path.isdir(mib_path):
        for mib in MIB_SRCLIST:
            mib_preload = mib[0]
            mib_srcname = mib[1]
            mib_destname = mib[2]
            if not os.path.isfile(os.path.join(mib_path, mib_srcname)):
                print "FAILED: Required MIB %s is missing from path %s" % \
                      (mib_srcname, mib_path)
                return 1
            print "::: Converting MIB to py :::" 
            if mib_preload: 
		cmd = "smidump -k -p %s -f python %s | libsmi2pysnmp > %s" % \
		       (os.path.join(mib_path, mib_preload),
			os.path.join(mib_path, mib_srcname),
			os.path.join(mib_path, mib_destname) + ".py")
            else:
		cmd = "smidump -k -f python %s | libsmi2pysnmp > %s" % \
		       (os.path.join(mib_path, mib_srcname),
			os.path.join(mib_path, mib_destname) + ".py")
            print(cmd)
            os.system(cmd)
            print "::: Loading MIB :::" 
            mibBuilder.loadModules(mib_destname)
            print mib_destname
    else:
        print "FAILED: MIB directory %s is not present" % mib_path
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
        print(errorIndication)
    else:
        if errorStatus:
            print("%s at %s" % (errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex)-1] 
                                or '?'))
        else:
            for name, val in varBinds:
                print("%s = %s" % (name.prettyPrint(), val.prettyPrint()))
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
        print(errorIndication)
    else:
        if errorStatus:
            print("%s at %s" % (errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex)-1] 
                                or '?'))
        else:
            for varBindTableRow in varBindTable:
                for name, val in varBindTableRow:
                    print("%s = %s" % (name.prettyPrint(), val.prettyPrint()))
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
        print(errorIndication)
    else:
        if errorStatus:
            print("%s at %s" % (errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex)-1] 
                                or '?'))
        else:
            for varBindTableRow in varBindTable:
                for name, val in varBindTableRow:
                    print("%s = %s" % (name.prettyPrint(), val.prettyPrint()))
                    return 0

    return 1

if __name__ == "__main__":

    # Get the floating ip from the command line
    snmp_ip = sys.argv[1]

#    debug.setLogger(debug.Debug('all'))
    cmdGen = mibTextToPy(MIB_PATH)

    # Test #1: Perform an SNMP Get
    # Do individual snmpget requests to retrieve one alarm entry
    # The value can be from 1 to 2000 inclusive
    print ">>> Test 1: Perform SNMP Get"
    instanceno = str(randint(1, MAX_ALRM_TBL_SIZE))
    for item in OID:
        oid = (OID[item] + "." + instanceno, )
        retVal = snmpGet(COMMUNITY_STRING, snmp_ip, SNMP_PORT, cmdGen, *oid) 
        if retVal == 1:
            print "Test 1 FAILED"
            failFlag = True
            break
        
    # Test #2: Perform an SNMP Walk over the entire tree starting at the root
    print ">>> Test 2: Perform SNMP Walk" 
    oid = (OID["wrsAlarmHistoryTable"], )
    retVal = snmpGetNext(COMMUNITY_STRING, snmp_ip, SNMP_PORT, cmdGen, *oid)
    if retVal == 1:
        print "Test 2 FAILED"
        failFlag = True

    # Test #3: Perform a SNMP Walk in one entry
    # We should get a collection of related information on each run, 
    # i.e. AlarmIDs only, AlarmState only, etc.
    print ">>> Test #3: Perform a SNMP Walk in one entry"
    for i in range(len(OID) - 1):
        oid = (OID["wrsAlarmHistoryEntry"] + "." + str(i), )
        retVal = snmpGetNext(COMMUNITY_STRING, snmp_ip, SNMP_PORT, cmdGen, *oid)
        if retVal == 1:
            print "Test 3 FAILED"
            failFlag = True
            break

    # Test #4: Perform an SNMP Get Bulk command
    print ">>> Test #4: Perform an SNMP Get Bulk command"
    for i in range(len(OID) - 1):
        oid = (OID["wrsAlarmHistoryEntry"] + "." + str(i), )
        retVal = snmpGetBulk(COMMUNITY_STRING, snmp_ip, SNMP_PORT, NON_REP, MAX_REP, cmdGen, *oid)
        if retVal == 1:
            print "Test 4 FAILED"
            failFlag = True
            break

    if failFlag == True:
        sys.exit(1)
    else:
        sys.exit(0)
