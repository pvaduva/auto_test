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
#	wait loop for vm to become active
#	

To use:
~wait_vm_active.inc 

Options:
.	vm_name=<desired vm name>
.	vm_state=<desired wait for state>	<default=ACTIVE>


;;;


?if $vm_name!=$blank? [
	$_max=25
	$_i=0
	$vm_state=ACTIVE

	; === wait for  VM:$vm_name to become active
	$_vm_state=none
	[ $_vm_state != $vm_state
		>nova list --all-tenants | grep $vm_name
		<$vm_name
		+$_vm_state=(BUILD|ACTIVE|ERROR|REBOOT|PAUSED|SHUTOFF|SUSPENDED|MIGRATING|VERIFY_RESIZE|RESIZE|HARD_REBOOT)

		!sleep 5
		+$_i
		?if $_i > $_max? %BREAK_VM_RECOVER

	]
	%BREAK_VM_RECOVER
	>
]









