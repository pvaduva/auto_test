# PySNMP SMI module. Autogenerated from smidump -f python WRS-ALARM-MIB
# by libsmi2pysnmp-0.1.3 at Tue Dec 16 08:43:48 2014,
# Python version sys.version_info(major=2, minor=7, micro=6, releaselevel='final', serial=0)

# Imports

( Integer, ObjectIdentifier, OctetString, ) = mibBuilder.importSymbols("ASN1", "Integer", "ObjectIdentifier", "OctetString")
( NamedValues, ) = mibBuilder.importSymbols("ASN1-ENUMERATION", "NamedValues")
( ConstraintsIntersection, ConstraintsUnion, SingleValueConstraint, ValueRangeConstraint, ValueSizeConstraint, ) = mibBuilder.importSymbols("ASN1-REFINEMENT", "ConstraintsIntersection", "ConstraintsUnion", "SingleValueConstraint", "ValueRangeConstraint", "ValueSizeConstraint")
( ModuleCompliance, NotificationGroup, ObjectGroup, ) = mibBuilder.importSymbols("SNMPv2-CONF", "ModuleCompliance", "NotificationGroup", "ObjectGroup")
( Bits, Integer32, ModuleIdentity, MibIdentifier, NotificationType, ObjectIdentity, MibScalar, MibTable, MibTableRow, MibTableColumn, TimeTicks, Unsigned32, ) = mibBuilder.importSymbols("SNMPv2-SMI", "Bits", "Integer32", "ModuleIdentity", "MibIdentifier", "NotificationType", "ObjectIdentity", "MibScalar", "MibTable", "MibTableRow", "MibTableColumn", "TimeTicks", "Unsigned32")
( DateAndTime, DisplayString, TextualConvention, ) = mibBuilder.importSymbols("SNMPv2-TC", "DateAndTime", "DisplayString", "TextualConvention")
( WrsBoolean, WrsUUID, wrsAlarms, ) = mibBuilder.importSymbols("WRS-ENTERPRISE-REG-MIB", "WrsBoolean", "WrsUUID", "wrsAlarms")

# Types

class WrsAlarmEntityInstanceId(TextualConvention, OctetString):
    displayHint = "255a"
    
class WrsAlarmEventType(Integer):
    subtypeSpec = Integer.subtypeSpec+SingleValueConstraint(2,6,7,9,5,8,3,1,10,0,4,)
    namedValues = NamedValues(("other", 0), ("communicationsAlarm", 1), ("timeDomainViolation", 10), ("qualityOfServiceAlarm", 2), ("processingErrorAlarm", 3), ("equipmentAlarm", 4), ("environmentalAlarm", 5), ("integrityViolation", 6), ("operationalViolation", 7), ("physicalViolation", 8), ("securityServiceOrMechanismViolation", 9), )
    
class WrsAlarmId(OctetString):
    subtypeSpec = OctetString.subtypeSpec+ValueSizeConstraint(0,7)
    
class WrsAlarmProbableCause(Integer):
    subtypeSpec = Integer.subtypeSpec+SingleValueConstraint(64,49,74,51,59,60,37,2,4,24,14,44,6,65,61,27,15,23,66,54,5,73,36,42,67,3,48,17,38,68,7,10,57,62,47,50,29,25,34,43,63,0,11,19,58,70,18,41,40,8,33,9,32,56,52,31,21,39,46,20,16,22,30,13,26,12,72,71,45,53,28,35,69,55,1,)
    namedValues = NamedValues(("nil", 0), ("adaptor-error", 1), ("cpu-cycles-limit-exceeded", 10), ("dataset-or-modem-error", 11), ("degraded-signal", 12), ("dte-dce-interface-error", 13), ("enclosure-door-open", 14), ("equipment-malfunction", 15), ("excessive-vibration", 16), ("file-error", 17), ("fire-detected", 18), ("flood-detected", 19), ("application-subsystem-failure", 2), ("framing-error", 20), ("heating-ventilation-cooling-system-problem", 21), ("humidity-unacceptable", 22), ("io-device-error", 23), ("input-device-error", 24), ("lan-error", 25), ("leak-detected", 26), ("local-node-transmission-error", 27), ("loss-of-frame", 28), ("loss-of-signal", 29), ("bandwidth-reduced", 3), ("material-supply-exhausted", 30), ("multiplexer-problem", 31), ("out-of-memory", 32), ("output-device-error", 33), ("performance-degraded", 34), ("power-problem", 35), ("processor-problem", 36), ("pump-failure", 37), ("queue-size-exceeded", 38), ("receive-failure", 39), ("call-establishment-error", 4), ("receiver-failure", 40), ("remote-node-transmission-error", 41), ("resource-at-or-nearing-capacity", 42), ("response-time-excessive", 43), ("retransmission-rate-excessive", 44), ("software-error", 45), ("software-program-abnormally-terminated", 46), ("software-program-error", 47), ("storage-capacity-problem", 48), ("temperature-unacceptable", 49), ("communication-protocol-error", 5), ("threshold-crossed", 50), ("timing-problem", 51), ("toxic-leak-detected", 52), ("transmit-failure", 53), ("transmitter-failure", 54), ("underlying-resource-unavailable", 55), ("version-mismatch", 56), ("duplicate-information", 57), ("information-missing", 58), ("information-modification-detected", 59), ("communication-subsystem-failure", 6), ("information-out-of-sequence", 60), ("unexpected-information", 61), ("denial-of-service", 62), ("out-of-service", 63), ("procedural-error", 64), ("unspecified-reason", 65), ("cable-tamper", 66), ("intrusion-detection", 67), ("authentication-failure", 68), ("breach-of-confidentiality", 69), ("configuration-or-customization-error", 7), ("non-repudiation-failure", 70), ("unauthorized-access-attempt", 71), ("delayed-information", 72), ("key-expired", 73), ("out-of-hours-activity", 74), ("congestion", 8), ("corrupt-data", 9), )
    
class WrsAlarmSeverity(Integer):
    subtypeSpec = Integer.subtypeSpec+SingleValueConstraint(3,1,4,0,2,)
    namedValues = NamedValues(("nil", 0), ("warning", 1), ("minor", 2), ("major", 3), ("critical", 4), )
    
class WrsAlarmState(Integer):
    subtypeSpec = Integer.subtypeSpec+SingleValueConstraint(1,0,2,)
    namedValues = NamedValues(("clear", 0), ("set", 1), ("msg", 2), )
    
class WrsAlarmText(TextualConvention, OctetString):
    displayHint = "255a"
    

# Objects

wrsAlarmMIB = ModuleIdentity((1, 3, 6, 1, 4, 1, 731, 1, 1, 1)).setRevisions(("2014-12-04 00:00","2014-07-10 00:00",))
if mibBuilder.loadTexts: wrsAlarmMIB.setOrganization("Wind River Systems, Inc.")
if mibBuilder.loadTexts: wrsAlarmMIB.setContactInfo("Wind River Systems, Inc.\n500 Wind River Way\nAlameda, CA 94501, USA\nContact : Wind River Systems Support\nE-mail: support@windriver.com\nPhone : 510.748.4100")
if mibBuilder.loadTexts: wrsAlarmMIB.setDescription("This module contains objects of the\nTitanium Server Alarm MIB, \nincluding notifications.")
wrsAlarmObjects = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1))
wrsTrapPrefix = ObjectIdentity((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0))
if mibBuilder.loadTexts: wrsTrapPrefix.setDescription("This OID represents the prefix branch for all WIND RIVER ITU Alarm Trap.\nThe last but one sub identifier in the OID of any Notification must have the value \nzero to facilitate v2<-->v1 conversion.")
wrsAlarmActiveTable = MibTable((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1))
if mibBuilder.loadTexts: wrsAlarmActiveTable.setDescription("This table contains information about active alarms.")
wrsAlarmActiveEntry = MibTableRow((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1)).setIndexNames((0, "WRS-ALARM-MIB", "wrsAlarmActiveIndex"))
if mibBuilder.loadTexts: wrsAlarmActiveEntry.setDescription("An active alarm entry")
wrsAlarmActiveIndex = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 1), Unsigned32().subtype(subtypeSpec=ValueRangeConstraint(1, 4294967295))).setMaxAccess("noaccess")
if mibBuilder.loadTexts: wrsAlarmActiveIndex.setDescription("The index of the Active Alarm in the Active Alarm Table.")
wrsAlarmActiveUuid = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 2), DisplayString()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveUuid.setDescription("An ID identifying the active alarm instance in the Active Alarm Table.")
wrsAlarmActiveAlarmId = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 3), WrsAlarmId()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveAlarmId.setDescription("An ID identifying the particular Alarm condition.\nTypically used as an index for looking up Alarm details \nin a System's Alarm Document.\n\nThis will be a structured ID, in order to allow grouping of \nAlarms into general categories and allow specific Alarms to \nbe independently added and numbered within the group.\n\ne.g.  <Alarm Group ID>.<Alarm Event ID>\n       where <Alarm Group ID> = 000 - 999\n             <Alarm Event ID> = 000 - 999\n\nNOTE: the { alarm-id, entity-instance-id } uniquely identifies an ACTIVE Alarm.  \ne.g. \n- an alarm is cleared based on the matching { alarm-id, entity-instance-id },\n- consecutive sets of an alarm with matching { alarm-id, entity-instance-id } \n  updates the fields of the single ACTIVE Alarm.  \n  E.g. updates severity for example.  ")
wrsAlarmActiveEntityInstanceId = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 4), WrsAlarmEntityInstanceId()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveEntityInstanceId.setDescription("This is a textual description of the resource under alarm. \n\nA '.' separated list of sub-entity-type=instance-value pairs,\nrepresenting the containment structure of the overall entity\ninstance.\n\nNote that this containment structure will be used for\nprocessing hierarchical clears.\n\ne.g\nsystem=ironpass1-4\nsystem=ironpass1-4 . host=compute-0\nsystem=ironpass1-4 . host=compute-0 . port=eth0\nsystem=ironpass1-4 . host=compute-0 . disk=/dev/sda\n\nsystem=ironpass1-4 . instance=vyatta_rtr_0\nsystem=ironpass1-4 . stack=vyatta_scaling_rtrs\n\nNOTE: the { alarm-id, entity-instance-id } uniquely identifies an ACTIVE Alarm.  \ne.g. \n- an alarm is cleared based on the matching { alarm-id, entity-instance-id },\n- consecutive sets of an alarm with matching { alarm-id, entity-instance-id } \n  updates the fields of the single ACTIVE Alarm.  \n  E.g. updates severity for example.")
wrsAlarmActiveDateAndTime = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 5), DateAndTime()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveDateAndTime.setDescription("Provided in this table as a convenience.  It is a copy of the Date and Time of the alarm.")
wrsAlarmActiveAlarmSeverity = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 6), WrsAlarmSeverity()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveAlarmSeverity.setDescription("The severity of the alarm.")
wrsAlarmActiveReasonText = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 7), WrsAlarmText()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveReasonText.setDescription("Represents the per active alarm instance additional text field.")
wrsAlarmActiveEventType = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 8), WrsAlarmEventType()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveEventType.setDescription("Represents the per active alarm instance event type values.")
wrsAlarmActiveProbableCause = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 9), WrsAlarmProbableCause()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveProbableCause.setDescription("Per active alarm instance ITU probable cause values.")
wrsAlarmActiveProposedRepairAction = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 10), WrsAlarmText()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveProposedRepairAction.setDescription("Represents more of the per active alarm instance additional text field.")
wrsAlarmActiveServiceAffecting = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 11), WrsBoolean()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveServiceAffecting.setDescription("This attribute indicates whether the alarm is service affecting or not.")
wrsAlarmActiveSuppressionAllowed = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 1, 1, 12), WrsBoolean()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmActiveSuppressionAllowed.setDescription("This attribute indicates whether the alarm can be manually suppressed or not.")
wrsAlarmHistoryTable = MibTable((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2))
if mibBuilder.loadTexts: wrsAlarmHistoryTable.setDescription("This table contains information about historical alarms.")
wrsAlarmHistoryEntry = MibTableRow((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1)).setIndexNames((0, "WRS-ALARM-MIB", "wrsAlarmHistoryIndex"))
if mibBuilder.loadTexts: wrsAlarmHistoryEntry.setDescription("A historical alarm entry")
wrsAlarmHistoryIndex = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 1), Unsigned32().subtype(subtypeSpec=ValueRangeConstraint(1, 4294967295))).setMaxAccess("noaccess")
if mibBuilder.loadTexts: wrsAlarmHistoryIndex.setDescription("The index of the historical alarm in the Historical Alarm Table.")
wrsAlarmHistoryUuid = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 2), DisplayString()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryUuid.setDescription("An ID identifying the historical alarm instance in the Historical Alarm Table.")
wrsAlarmHistoryAlarmId = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 3), WrsAlarmId()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryAlarmId.setDescription("An ID identifying the particular Alarm condition.\nTypically used as an index for looking up Alarm details \nin a System's Alarm Document.\n\nThis will be a structured ID, in order to allow grouping of \nAlarms into general categories and allow specific Alarms to \nbe independently added and numbered within the group.\n\ne.g.  <Alarm Group ID>.<Alarm Event ID>\n       where <Alarm Group ID> = 000 - 999\n             <Alarm Event ID> = 000 - 999 ")
wrsAlarmHistoryAlarmState = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 4), WrsAlarmState()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryAlarmState.setDescription("The state of the historical alarm.\n\nFor a CLEAR alarm history, many of the fields are not applicable and will be NULL value.\n The attributes that are applicable for a CLEAR alarm are:\n AlarmState, AlarmId, EntityInstanceId, Timestamp and ReasonText.\n \n For a Hierarchical CLEAR ALL alarm history, many of the fields are not applicable and will be NULL value.\n The attributes that are applicable for a CLEAR ALL alarm history are:\n AlarmState, EntityInstanceId, Timestamp and ReasonText.")
wrsAlarmHistoryEntityInstanceId = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 5), WrsAlarmEntityInstanceId()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryEntityInstanceId.setDescription("This is a textual description of the resource under alarm. \n\nA '.' separated list of sub-entity-type=instance-value pairs,\nrepresenting the containment structure of the overall entity\ninstance.\n\nNote that this containment structure will be used for\nprocessing hierarchical clears.\n\ne.g\nsystem=ironpass1-4\nsystem=ironpass1-4 . host=compute-0\nsystem=ironpass1-4 . host=compute-0 . port=eth0\nsystem=ironpass1-4 . host=compute-0 . disk=/dev/sda\n\nsystem=ironpass1-4 . instance=vyatta_rtr_0\nsystem=ironpass1-4 . stack=vyatta_scaling_rtrs")
wrsAlarmHistoryDateAndTime = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 6), DateAndTime()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryDateAndTime.setDescription("Provided in this table as a convenience.  It is the alarm last update Date and Time .")
wrsAlarmHistoryAlarmSeverity = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 7), WrsAlarmSeverity()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryAlarmSeverity.setDescription("The severity of the historical alarm.")
wrsAlarmHistoryReasonText = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 8), WrsAlarmText()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryReasonText.setDescription("Represents the per historical alarm instance additional text field.")
wrsAlarmHistoryEventType = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 9), WrsAlarmEventType()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryEventType.setDescription("Represents the per historical alarm instance event type values.")
wrsAlarmHistoryProbableCause = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 10), WrsAlarmProbableCause()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryProbableCause.setDescription("Per historical alarm instance ITU probable cause values.")
wrsAlarmHistoryProposedRepairAction = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 11), WrsAlarmText()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryProposedRepairAction.setDescription("Represents more of the per historical alarm instance additional text field.")
wrsAlarmHistoryServiceAffecting = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 12), WrsBoolean()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistoryServiceAffecting.setDescription("This attribute indicates whether the historical alarm is service affecting or not.")
wrsAlarmHistorySuppressionAllowed = MibTableColumn((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 2, 1, 13), WrsBoolean()).setMaxAccess("readonly")
if mibBuilder.loadTexts: wrsAlarmHistorySuppressionAllowed.setDescription("This attribute indicates whether the alarm can be manually suppressed or not.")
wrsAlarmConformance = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 2))
wrsAlarmCompliances = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 2, 1))
wrsAlarmGroups = MibIdentifier((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 2, 2))

# Augmentions

# Notifications

wrsAlarmCritical = NotificationType((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0, 1)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmId"), ("WRS-ALARM-MIB", "wrsAlarmActiveProbableCause"), ("WRS-ALARM-MIB", "wrsAlarmActiveEventType"), ("WRS-ALARM-MIB", "wrsAlarmActiveProposedRepairAction"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmSeverity"), ("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ("WRS-ALARM-MIB", "wrsAlarmActiveSuppressionAllowed"), ("WRS-ALARM-MIB", "wrsAlarmActiveServiceAffecting"), ) )
if mibBuilder.loadTexts: wrsAlarmCritical.setDescription("This notification indicates that an alarm of 'Critical' severity\nhas been raised on the system.\nThe varbinds include details of the alarm.")
wrsAlarmMajor = NotificationType((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0, 2)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmId"), ("WRS-ALARM-MIB", "wrsAlarmActiveProbableCause"), ("WRS-ALARM-MIB", "wrsAlarmActiveEventType"), ("WRS-ALARM-MIB", "wrsAlarmActiveProposedRepairAction"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmSeverity"), ("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ("WRS-ALARM-MIB", "wrsAlarmActiveSuppressionAllowed"), ("WRS-ALARM-MIB", "wrsAlarmActiveServiceAffecting"), ) )
if mibBuilder.loadTexts: wrsAlarmMajor.setDescription("This notification indicates that an alarm of 'Major' severity\nhas been raised on the system.\nThe varbinds include details of the alarm.")
wrsAlarmMinor = NotificationType((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0, 3)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmId"), ("WRS-ALARM-MIB", "wrsAlarmActiveProbableCause"), ("WRS-ALARM-MIB", "wrsAlarmActiveEventType"), ("WRS-ALARM-MIB", "wrsAlarmActiveProposedRepairAction"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmSeverity"), ("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ("WRS-ALARM-MIB", "wrsAlarmActiveSuppressionAllowed"), ("WRS-ALARM-MIB", "wrsAlarmActiveServiceAffecting"), ) )
if mibBuilder.loadTexts: wrsAlarmMinor.setDescription("This notification indicates that an alarm of 'Minor' severity\nhas been raised on the system.\nThe varbinds include details of the alarm.")
wrsAlarmWarning = NotificationType((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0, 4)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmId"), ("WRS-ALARM-MIB", "wrsAlarmActiveProbableCause"), ("WRS-ALARM-MIB", "wrsAlarmActiveEventType"), ("WRS-ALARM-MIB", "wrsAlarmActiveProposedRepairAction"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmSeverity"), ("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ("WRS-ALARM-MIB", "wrsAlarmActiveSuppressionAllowed"), ("WRS-ALARM-MIB", "wrsAlarmActiveServiceAffecting"), ) )
if mibBuilder.loadTexts: wrsAlarmWarning.setDescription("This notification indicates that an alarm of 'Warning' severity\nhas been raised on the system.\nThe varbinds include details of the alarm.")
wrsAlarmMessage = NotificationType((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0, 5)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmId"), ("WRS-ALARM-MIB", "wrsAlarmActiveProbableCause"), ("WRS-ALARM-MIB", "wrsAlarmActiveEventType"), ("WRS-ALARM-MIB", "wrsAlarmActiveProposedRepairAction"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmSeverity"), ("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ("WRS-ALARM-MIB", "wrsAlarmActiveSuppressionAllowed"), ("WRS-ALARM-MIB", "wrsAlarmActiveServiceAffecting"), ) )
if mibBuilder.loadTexts: wrsAlarmMessage.setDescription("This notification indicates that a stateless message alarm\nevent has occurred on the system.\nThe varbinds include details of the alarm.")
wrsAlarmClear = NotificationType((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0, 9)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmId"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ) )
if mibBuilder.loadTexts: wrsAlarmClear.setDescription("This notification indicates that a previously\nreported alarm have been cleared.\nThe previously reported alarm is identified by the\n{ AlarmId, EntityInstanceId } tuple.")
wrsAlarmHierarchicalClear = NotificationType((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 1, 0, 99)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ) )
if mibBuilder.loadTexts: wrsAlarmHierarchicalClear.setDescription("This notification indicates that one or more previously\nreported alarms have been cleared.\nThe previously reported alarms are identified by the \nEntityInstanceId attribute.\nALL alarms against EntityInstanceId and all of its children\nhave been cleared.")

# Groups

wrsAlarmNotificationsGroup = NotificationGroup((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 2, 2, 1)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmMessage"), ("WRS-ALARM-MIB", "wrsAlarmMajor"), ("WRS-ALARM-MIB", "wrsAlarmWarning"), ("WRS-ALARM-MIB", "wrsAlarmMinor"), ("WRS-ALARM-MIB", "wrsAlarmCritical"), ("WRS-ALARM-MIB", "wrsAlarmHierarchicalClear"), ("WRS-ALARM-MIB", "wrsAlarmClear"), ) )
if mibBuilder.loadTexts: wrsAlarmNotificationsGroup.setDescription("Wind River alarm notification group.")
wrsAlarmGroup = ObjectGroup((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 2, 2, 2)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmActiveAlarmId"), ("WRS-ALARM-MIB", "wrsAlarmActiveAlarmSeverity"), ("WRS-ALARM-MIB", "wrsAlarmActiveEntityInstanceId"), ("WRS-ALARM-MIB", "wrsAlarmActiveDateAndTime"), ("WRS-ALARM-MIB", "wrsAlarmActiveUuid"), ("WRS-ALARM-MIB", "wrsAlarmActiveProbableCause"), ("WRS-ALARM-MIB", "wrsAlarmActiveEventType"), ("WRS-ALARM-MIB", "wrsAlarmActiveProposedRepairAction"), ("WRS-ALARM-MIB", "wrsAlarmActiveReasonText"), ("WRS-ALARM-MIB", "wrsAlarmActiveSuppressionAllowed"), ("WRS-ALARM-MIB", "wrsAlarmActiveServiceAffecting"), ) )
if mibBuilder.loadTexts: wrsAlarmGroup.setDescription("Wind River alarm group.")

# Compliances

wrsAlarmCompliance = ModuleCompliance((1, 3, 6, 1, 4, 1, 731, 1, 1, 1, 2, 1, 1)).setObjects(*(("WRS-ALARM-MIB", "wrsAlarmGroup"), ) )
if mibBuilder.loadTexts: wrsAlarmCompliance.setDescription("The compliance statement for entities which implement\nthe Wind River Alarm MIB.")

# Exports

# Module identity
mibBuilder.exportSymbols("WRS-ALARM-MIB", PYSNMP_MODULE_ID=wrsAlarmMIB)

# Types
mibBuilder.exportSymbols("WRS-ALARM-MIB", WrsAlarmEntityInstanceId=WrsAlarmEntityInstanceId, WrsAlarmEventType=WrsAlarmEventType, WrsAlarmId=WrsAlarmId, WrsAlarmProbableCause=WrsAlarmProbableCause, WrsAlarmSeverity=WrsAlarmSeverity, WrsAlarmState=WrsAlarmState, WrsAlarmText=WrsAlarmText)

# Objects
mibBuilder.exportSymbols("WRS-ALARM-MIB", wrsAlarmMIB=wrsAlarmMIB, wrsAlarmObjects=wrsAlarmObjects, wrsTrapPrefix=wrsTrapPrefix, wrsAlarmActiveTable=wrsAlarmActiveTable, wrsAlarmActiveEntry=wrsAlarmActiveEntry, wrsAlarmActiveIndex=wrsAlarmActiveIndex, wrsAlarmActiveUuid=wrsAlarmActiveUuid, wrsAlarmActiveAlarmId=wrsAlarmActiveAlarmId, wrsAlarmActiveEntityInstanceId=wrsAlarmActiveEntityInstanceId, wrsAlarmActiveDateAndTime=wrsAlarmActiveDateAndTime, wrsAlarmActiveAlarmSeverity=wrsAlarmActiveAlarmSeverity, wrsAlarmActiveReasonText=wrsAlarmActiveReasonText, wrsAlarmActiveEventType=wrsAlarmActiveEventType, wrsAlarmActiveProbableCause=wrsAlarmActiveProbableCause, wrsAlarmActiveProposedRepairAction=wrsAlarmActiveProposedRepairAction, wrsAlarmActiveServiceAffecting=wrsAlarmActiveServiceAffecting, wrsAlarmActiveSuppressionAllowed=wrsAlarmActiveSuppressionAllowed, wrsAlarmHistoryTable=wrsAlarmHistoryTable, wrsAlarmHistoryEntry=wrsAlarmHistoryEntry, wrsAlarmHistoryIndex=wrsAlarmHistoryIndex, wrsAlarmHistoryUuid=wrsAlarmHistoryUuid, wrsAlarmHistoryAlarmId=wrsAlarmHistoryAlarmId, wrsAlarmHistoryAlarmState=wrsAlarmHistoryAlarmState, wrsAlarmHistoryEntityInstanceId=wrsAlarmHistoryEntityInstanceId, wrsAlarmHistoryDateAndTime=wrsAlarmHistoryDateAndTime, wrsAlarmHistoryAlarmSeverity=wrsAlarmHistoryAlarmSeverity, wrsAlarmHistoryReasonText=wrsAlarmHistoryReasonText, wrsAlarmHistoryEventType=wrsAlarmHistoryEventType, wrsAlarmHistoryProbableCause=wrsAlarmHistoryProbableCause, wrsAlarmHistoryProposedRepairAction=wrsAlarmHistoryProposedRepairAction, wrsAlarmHistoryServiceAffecting=wrsAlarmHistoryServiceAffecting, wrsAlarmHistorySuppressionAllowed=wrsAlarmHistorySuppressionAllowed, wrsAlarmConformance=wrsAlarmConformance, wrsAlarmCompliances=wrsAlarmCompliances, wrsAlarmGroups=wrsAlarmGroups)

# Notifications
mibBuilder.exportSymbols("WRS-ALARM-MIB", wrsAlarmCritical=wrsAlarmCritical, wrsAlarmMajor=wrsAlarmMajor, wrsAlarmMinor=wrsAlarmMinor, wrsAlarmWarning=wrsAlarmWarning, wrsAlarmMessage=wrsAlarmMessage, wrsAlarmClear=wrsAlarmClear, wrsAlarmHierarchicalClear=wrsAlarmHierarchicalClear)

# Groups
mibBuilder.exportSymbols("WRS-ALARM-MIB", wrsAlarmNotificationsGroup=wrsAlarmNotificationsGroup, wrsAlarmGroup=wrsAlarmGroup)

# Compliances
mibBuilder.exportSymbols("WRS-ALARM-MIB", wrsAlarmCompliance=wrsAlarmCompliance)
