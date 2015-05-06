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
#	reboot node
#
#	options:
#		force=yes

To use:
~reboot_node.inc node=<name> [force=yes]

;;;

# common include path
$inc_path=common

$admin_src_path=/etc/nova

?if $force == yes? $force_opt=-f :: $force_opt=


; === Become Admin
>source $admin_src_path/openrc 

; === identify active controller
>system sda-list | grep controller-services
+$act_controller=controller-services.*(controller-\d).*active


; === check node to be rebooted?
? $node==$act_controller ? [
	>echo "$pass" | sudo -S id
	<root
	@20
	; === rebooting active controller
	>sudo reboot $force_opt
	#<system is going down|Restarting system
	!sleep 5
	>>
	>>
	<Connection to.+closed|Write failed: Broken pipe
	>
	; wait for other active controller...
	>ping -c 20 $IP
	>
	~$inc_path/ssh_controller.inc 
	>
]::[
	; === log into node
	~$inc_path/ssh_controller.inc IP=$node PORT=
	; === reboot other node: $node
	#set up root access
	>echo "$pass" | sudo -S id
	<root
	@20
	>sudo reboot $force_opt
	<system is going down|Restarting system
	>>
	<Connection to.+closed
]
>
