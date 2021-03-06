# PySNMP SMI module. Autogenerated from smidump -f python WRS-ENTERPRISE-REG-MIB
# by libsmi2pysnmp-0.1.3 at Tue Dec 16 08:43:48 2014,
# Python version sys.version_info(major=2, minor=7, micro=6, releaselevel='final', serial=0)

# Imports

( Integer, ObjectIdentifier, OctetString, ) = mibBuilder.importSymbols("ASN1", "Integer", "ObjectIdentifier", "OctetString")
( NamedValues, ) = mibBuilder.importSymbols("ASN1-ENUMERATION", "NamedValues")
( ConstraintsIntersection, ConstraintsUnion, SingleValueConstraint, ValueRangeConstraint, ValueSizeConstraint, ) = mibBuilder.importSymbols("ASN1-REFINEMENT", "ConstraintsIntersection", "ConstraintsUnion", "SingleValueConstraint", "ValueRangeConstraint", "ValueSizeConstraint")
( Bits, Integer32, ModuleIdentity, MibIdentifier, TimeTicks, enterprises, ) = mibBuilder.importSymbols("SNMPv2-SMI", "Bits", "Integer32", "ModuleIdentity", "MibIdentifier", "TimeTicks", "enterprises")
( TextualConvention, ) = mibBuilder.importSymbols("SNMPv2-TC", "TextualConvention")

# Types

class WrsBoolean(Integer):
    subtypeSpec = Integer.subtypeSpec+SingleValueConstraint(1,0,)
    namedValues = NamedValues(("false", 0), ("true", 1), )
    
class WrsUUID(OctetString):
    subtypeSpec = OctetString.subtypeSpec+ValueSizeConstraint(0,36)
    

# Objects

wrs = ModuleIdentity((1, 3, 6, 1, 4, 1, 731)).setRevisions(("2014-07-10 00:00",))
if mibBuilder.loadTexts: wrs.setOrganization("Wind River Systems, Inc.")
if mibBuilder.loadTexts: wrs.setContactInfo("Wind River Systems, Inc.\n500 Wind River Way\nAlameda, CA 94501, USA\nContact: Wind River Systems Support\nE-mail : support@windriver.com\nPhone  : 510.748.4100")
if mibBuilder.loadTexts: wrs.setDescription("This module defines the Wind River Systems, Inc. Registration hierarchy.")
wrsCommon = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 1))
wrsAlarms = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 1, 1))
tms = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 2))
idb = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 2, 1))
rmonMib = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 2, 1, 1))
tmsGeneric = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 2, 2))
oemSwapi = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 2, 3))
oemProd = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 2, 4))
wrsTs = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 3))

# Augmentions

# Exports

# Module identity
mibBuilder.exportSymbols("WRS-ENTERPRISE-REG-MIB", PYSNMP_MODULE_ID=wrs)

# Types
mibBuilder.exportSymbols("WRS-ENTERPRISE-REG-MIB", WrsBoolean=WrsBoolean, WrsUUID=WrsUUID)

# Objects
mibBuilder.exportSymbols("WRS-ENTERPRISE-REG-MIB", wrs=wrs, wrsCommon=wrsCommon, wrsAlarms=wrsAlarms, tms=tms, idb=idb, rmonMib=rmonMib, tmsGeneric=tmsGeneric, oemSwapi=oemSwapi, oemProd=oemProd, wrsTs=wrsTs)

