

#general vars
set DEBUG 0

set action "show"

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

set root [ixNet getRoot]

set viewList [ixNet getList $root/statistics view]
if {$DEBUG} {puts "vl===>$viewList"}

#set view [lindex [ixNet getList $root/statistics view] end ]
# look for default "Traffic Item Statistics"
set view [lsearch -inline [ixNet getList $root/statistics view] *Traffic*]
if {$DEBUG} {puts "v===>$view"}

#set statList [get_header $view]

if {$action == "show" || $action != "clear"} {
	for {set i 0} {$i < 1} { incr i} {
	    puts "collecting stats"
	    collect_stats $view
	}
}

if {$action == "clear" } {
	puts "clearing stats"
	ixNet exec clearStats
}
