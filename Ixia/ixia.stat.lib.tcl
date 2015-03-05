
#general vars

set DEBUG 0
set VERSION "1.0"

# default values
set PORTS "3/15 3/16"
set IxNTclSvr 128.224.8.149:8009
set chassis_ip 128.224.151.109
regexp {(.*):(\d+)} $IxNTclSvr - IxNetSvr tcpPort


# used by psat_view
#set statList [list "Tx Frames" "Rx Frames" "Frames Delta" "Tx Frame Rate" "Rx Frame Rate"]

# statList for "Traffic Item Statistics"
set statList [list  "Traffic Item" "Tx Frames" "Rx Frames" "Frames Delta"  "Loss %" "Tx Frame Rate" "Rx Frame Rate"  "Tx L1 Rate pbs" "Rx L1 Rate bps" "Rx Bytes" "Tx Rate Bps" "Rx Rate Bps" "Tx Rate bps"  "Rx Rate bps" "Tx Rate kbps" "Rx Rate kpbs" "Tx Rate Mbps" "Rx Rate Mbps" "Latency avg ns" "Latency min ns" "Latency max ns" "First Time Stamp"  "Last Time Stamp"]


# common show help function
proc show_help { } {
	global argc argv argv0
	switch -glob $argv0 {
		"*start_stop*" {
			puts "$argv0 help"
			puts "  command starts or stops traffic"
			puts "  tclsh $argv0 traffic=<start|stop> \[tcpport=8010\] \[ixnetwork=ip_addr\]"
			puts "  e.g. tclsh $argv0 traffic=stop"
			puts " "
			puts " "
			puts " "
			puts " "
		}
		"*stats*" {
			puts "$argv0 help"
			puts "  command to clear or show stats"
			puts "   tclsh $argv0 stats=<clear|show> \[tcpport=8010\] \[ixnetwork=ip_addr\]"
			puts "   e.g. tclsh $argv0 stats=show"
			puts " "
			puts " "
			puts " "
		}
		"*config*" {
			puts "$argv0 help"
			puts "  command to load ixNetwork config"
			puts "  tclsh $argv0  config=<config_file> ports=\"<ports>\" \[tcpport=8010\] \[ixnetwork=ip_addr\]"
			puts "  e.g. tclsh $argv0  config=myconf.ixcfg ports=\"3/15 3/16\" "
			puts " "
			puts " "
			puts " "
		}
		"*stat.lib*" {
			puts "$argv0 help"
			puts "  library functions for ixia control scripts: load, start/stop, stats"
			puts "  This file is not to be exectued directly."
			puts "  "
			puts " "
			puts " "
			puts " "
		}
		
	}; # end switch
	puts "VERSION: $::VERSION\n"
	
	#puts "I need help!  $argv0"
	exit 1
}; # end proc


# show help if called directly
if { $argv0 == "ixia.stat.lib.tcl" } {
	show_help
	exit 1
}

proc read_args {  } {
	global  argc argv DEBUG
	#global config traffic stats tcpport ixnetwork
	#global SessionFile action tcpPort PORTS
	
	if { $argc >= 1  }  {
		# Walk thru additional args (should be cli constants)
		for { set x  0 } { $x < $argc} { incr x } {
			set optarg [ lindex $argv $x ]
			catch {set optargval [ lindex $argv [expr $x + 1]]}
			if { $optargval == "" } { 
				# no optargval, set to a sane value
				set optargval "--"
			}
			#puts "=====>$x|$optarg|$optargval|"
			# look for help & debug options which overide script options
			if { [catch { switch -glob -- $optarg {
				-h		-
				--help	{ show_help }
			} } \
			error ] } {
				puts "Warning: Bad input option: $error"
			}
			#general vars
			if [ regexp {.+=.*} $optarg ] {
				# detect and parse args in format "var=value"
				set user_var [string range $optarg 0 [expr [string first "=" $optarg] -1 ]]
				set user_value [string range $optarg [expr [string first "=" $optarg] +1 ] [string length $optarg]]
				if {$DEBUG} {puts "->$user_var $user_value"}
				# raise to global level
				#uplevel 1 set $user_var \"$user_value\"
				#set $user_var \"$user_value\"
				set $user_var $user_value
			}
		} ; # for loop
	}; #end if
	
	# process options
	if { [info exists config ] } { 
		set ::SessionFile $config
	}
	if { [info exists stats ] } { 
		set ::action $stats
	}
	if { [info exists tcpport ] } { 
		set ::tcpPort $tcpport
	}
	if { [info exists ports ] } { 
		set ::PORTS $ports
	}
	if { [info exists ixnetwork ] } { 
		set  ::IxNetSvr $ixnetwork
	}
	if { [info exists traffic ] } { 
		set  ::traffic $traffic
	}

}; # end proc


proc tracking {}  {
                foreach ti [ixNet getList [ixNet getRoot]traffic trafficItem] {
                    set generate 0
                    foreach trk [ixNet getList $ti tracking] {
                        set trkBy [ixNet getA $trk -trackBy]
                        set add ""
                        foreach item "trackingenabled0 sourceDestPortPair0" {
                            puts "track by $item"
                            if ![regexp $trkBy $item]  {
                                lappend add $item
                            }
                        }
                        if { [string length $add] } {
                            set trkBy [concat $trkBy $add]
                            set generate 1
                            ixNet setA $trk -trackBy $trkBy
                        }
                    }
                    if { $generate } {
                        ixNet exec generate $ti
                    }
                }
      ixNet commit
}

proc psat_view {} {
    global statList
    #setup stats tracking for traffic item/dest port/src port
                foreach {view} [ixNet getList [ixNet getRoot]statistics view] {
                    if {[ixNet getAttribute $view -caption] == "PSAT1"} {
                        #torch and rebuild
                        ixNet remove $view
                        ixNet commit
                        break
                    }
                }
                
                set view [ixNet add [ixNet getRoot]/statistics view]
                ixNet setAttribute $view -caption "PSAT1"
                ixNet setAttribute $view -type layer23TrafficFlow
                ixNet setAttr $view -visible true

                after 5000 
                set view [ixNet remapIds $view]
                set view [lindex $view 0]
                ixNet commit

                # need to commit in order to build filter lists
                set availablePortFilterList [ixNet getList $view availablePortFilter]
                ixNet setAttr $view/layer23TrafficFlowFilter -portFilterIds $availablePortFilterList
                set availableTrafficItemList [ixNet getList $view availableTrafficItemFilter]
                ixNet setAttr $view/layer23TrafficFlowFilter -trafficItemFilterIds $availableTrafficItemList

                set availableStatList [ixNet getList $view statistic]
debug 1
                foreach statName $statList {
                    puts "looking for $statName"
                    foreach stat $availableStatList {
                        if [regexp $statName $stat] {
                          # statName was not found, continue
                           puts "enable $statName"
                          ixNet setAttribute $stat -enabled true
                          break
                        }
                    }
                }
                ixNet commit
                after 3000
                ixNet setAttr $view -enabled true
                ixNet setAttr $view -visible true
                ixNet commit
                ixNet setAttribute $view/page -pageSize 100
                return $view

}

proc collect_stats {view} {

            global statList  DEBUG
            #ixNet setAttribute $view -enabled true
#            ixNet setAttribute $view/page -pageSize 500
#            ixNet commit
            after 3000  
#            ixNet exec refresh $view
            after 1000  
	    
	proc print_col { title value } {
		set blank "                    "
		set blank_len [string length $blank]
		set ii $title
		set ii_len [string length $ii]
		set ii_blank [string range $blank 1 [expr $blank_len - $ii_len]]
		puts "$ii $ii_blank : $value"
	}; #end proc

    for {set page 1} {$page <= [ixNet getAttribute $view/page -totalPages]} {incr page} {
                ixNet setAttribute $view/page -currentPage $page
                ixNet commit
                after 1000 
                #set statsNames [concat [list "RX port            " "Traffic Name"] $statList]
                #puts "$statsNames"
		if {$DEBUG} {puts "sl=>$statList"}
		set rowlist3 [ixNet getAttribute $view/page -rowValues] 
		if {$DEBUG} {puts "raw==>$rowlist3 ZZZ [llength $rowlist3]"}
		set i 0
		set traffic_item_length [llength $rowlist3]
		while { $i < $traffic_item_length } {
			# un-encap list in list in list
			set rowlist2 [lindex $rowlist3 $i]
			set rowlist [lindex $rowlist2 0]
			if {$DEBUG} {puts "rl=>[llength $rowlist]|$rowlist "}
			puts "\n"
			foreach title $statList row $rowlist {
         			   #puts "$title=$row"
				   if { $row == "::ixNet::OK"} { 
				   	puts "No Stats to display"
					return
				   }
				   print_col $title $row
       			 }
			incr i
		}; #end while

      }; #end for
}; # end proc
