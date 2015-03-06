

#general vars
set DEBUG 0



# defaults

#set SessionFile "hp380_pv.ixncfg"
set SessionFile "hp380_L2_only.ixncfg"
set SessionFile "hp380_L2_only_2_str.ixncfg"

source ./ixia.stat.lib.tcl 
# read CLI arguments in form var=value
read_args




#####
regexp {\d+\.\d+} [package req IxTclNetwork] ver
catch {ixNet disconnect}

if { [ catch { ixNet connect $IxNetSvr -port $tcpPort -version $ver } error ] } {
	puts "ERROR: $error"
	exit 1
}
#################

if { [ catch {ixNet exec loadConfig [ixNet readFrom $SessionFile] } error ] } {
	puts "ERROR: File not found: $SessionFile"
	exit 1
} else {
	puts "loading config: $SessionFile"
}

set root [ixNet getRoot]

## swap port
ixNet setMultiAttribute $root/availableHardware \
                                                -offChassisHwM {}
ixNet commit
set chassis [ixNet add $root/availableHardware "chassis"]
ixNet setMultiAttribute $chassis \
                                                -hostname $chassis_ip \
                                                -cableLength 0 \
                                                -masterChassis {} \
                                                -sequenceId 1
ixNet commit

puts "assigning ports: $PORTS"
foreach port $PORTS vport [ixNet getList $root vport] {
                regexp {(\d+)/(\d+)} $port - slot pn
                ixNet setA $vport \
                       -connectedTo $chassis/card:$slot/port:$pn
}
if { [ catch {ixNet commit } error ] } { 
	puts "ERROR: $error"
	exit 1
} else {
	puts "ixia config loaded: $SessionFile"
}
