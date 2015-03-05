


#general vars
set DEBUG 0

#default value
set traffic "stop"

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
ixNet exec connectPort $PORTS
puts "connected to $PORTS"
after 1000
puts "check port link status"
set  all_ports [ixNet getList / vport]
for {set i 0} { $i < [expr [llength $all_ports] *2 ]} {incr i} {
   set all_ports_up 1
   foreach vp $all_ports {
       if {[ixNet getAttribute $vp -state] != "up"} {
           puts "$vp is down" 
           set all_ports_up 0
       } else {
          puts "$vp is Up"
       }
   }
   if $all_ports_up {
      break 
   } else {
      after 3000
   }
}
if $all_ports_up {
   puts "All ports are up"
} else {
   puts "some ports are still down"
   exit
}


if {$traffic == "start" } {
	puts "starting protocol"
	ixNet exec startAllProtocols
	puts "wait for all protocols to come up"
	after 1000
	#enable tracking
	tracking
	after 3000
	if { [ catch { ixNet exec apply [ixNet getRoot]traffic } error ] } {
		puts "ERROR: $error"
		puts "HINT: probably could not resolve ARP"
		exit 1
	}
	after 1000

	puts "starting traffic"
	#ixTclNet::StartTraffic
	ixNet exec start [ixNet getRoot]traffic
}
after 2000
if {$traffic == "stop"  || $traffic != "start" } {
	puts "stopping traffic"
	#ixTclNet::StopTraffic
	ixNet exec stop [ixNet getRoot]traffic
}
puts "ixia_traffic state:$traffic"
