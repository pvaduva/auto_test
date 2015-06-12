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
#	vlm commands to targets
#		
#
To use:
~vlm_cmd.inc 

Options:
.	vlm_id=<target id>
.	cmd=<desired vm name>


Supported commands:
.	reserve
.	unreserve
.	poweroff
.	poweron
.	reboot

;;;

$vlm_tool=/folk/vlm/commandline/vlmTool



?if $cmd == reserve ? [
	>$vlm_tool reserve -t $vlm_id

]


?if $cmd == unreserve ? [
	>$vlm_tool unreserve -t $vlm_id

]

?if $cmd == poweroff ? [
	>$vlm_tool turnOff -t $vlm_id

]

?if $cmd == poweron ? [
	>$vlm_tool turnOn -t $vlm_id

]

?if $cmd == reboot ? [
	>$vlm_tool reboot -t $vlm_id

]



