# How to use this expect-lite file, Lines that begin with:
#	'>' send to remote host, implies "wait for prompt"
#	'<' _MUST_ be received from the remote host, or this config script will fail
#	# are comment lines, and have no effect
#	; are printable (in stdout) comments, and have no other effect
#	@ change the expect timeout value
#	! Embedded Expect commands
# For more info see: expect-lite.html
;;;
#
#	swact controllers
#

To use:
~swact_controllers.inc IP=<ip> [PORT=<custom port>]

Options
.	force=yes		does a reboot -f on active controller
;;;


# common include path
$inc_path=common

$admin_src_path=/etc/nova


# minimum number of controllers
$min_controllers=2

# number of times to check for active controller
$_max=50

; === get floating IP
>/sbin/ip addr | grep secondary | grep eth0
+$float_ip=inet ([0-9.]+)/

; === Become Admin to swact
>source $admin_src_path/openrc 

; === identify active controller
>system sda-list | grep controller-services
+$act_controller=controller-services.*(controller-\d).*active

$_i=1
[ $act_controller == __NO_STRING_CAPTURED__
	; === waiting for system services: $_i
	>system sda-list | grep controller-services
	+$act_controller=controller-services.*(controller-\d).*active
	!sleep 5
	+$_i
]

?if $force != yes? [
	!sleep 5
	$_result=1
	$_i=1
	[ $_result != 0
		; === swact controllers, trying: $_i
		>system host-swact $act_controller
		>echo $?
		+$_result=\n(\d)
		!sleep 5
		+$_i
	]
	>
	@30
	>ping -c 30 -W 30 $float_ip
	<icmp_[sr]eq=\d+ ttl=6\d
	!sleep 30

	>>
	<Write failed
	>
]::[
	; === wait for second controller to be available
	>system sda-list | grep controller-services | egrep 'active|standby'
	>system sda-list | grep controller-services | egrep 'active|standby' | wc -l
	+$num_of_controllers=\n(\d)
	$i=0
	[ $num_of_controllers < $min_controllers
		>source $admin_src_path/openrc 
		>system sda-list | grep controller-services | egrep 'active|standby' | wc -l
		+$num_of_controllers=\n(\d)
		!sleep 5
		+$i
		?if $i > $_max ? %STOP_WAIT
	]
	%STOP_WAIT
	
	
	; === set up sudo root access (to make it easier later in the interact session)
	>echo "$pass" | sudo -S id
	<root
	; === fail active controller	
	@3
	>
	>sudo reboot -f
	>
	# disconnect ssh session
	>>~.
	<Connection to .* closed
	>
	@30
	>ping -c 30 -W 30 $float_ip
	<icmp_[sr]eq=\d+ ttl=6\d
	!sleep 30
	>>

]
; === re-login to controller
~$inc_path/ssh_controller.inc

>
