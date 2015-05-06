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
#	get vm of type: virtio, avp, dpdk
#		returns 'none' if desired_type not found

To use:
~get_vm_of_type.inc 

Options:
.	vm_name=<desired vm name>
.	desired_type=<virtio, avp, dpdk>

;;;


?if $desired_type!=$blank? [

	; === get list of active existing VM
	>nova list --all-tenants | grep ACTIVE | awk '{print $4}' | paste -sd ' '
	+$vm_list=\n(.+)

	[ $vm=$vm_list
		>nova list --all-tenants | grep $vm | awk '{print $2}' | paste -sd ' '
		+$vm_uuid=([0-9a-f-]{36})
		; === get vm type
		~$inc_path/get_vm_type.inc vm_name=$vm
		?if $vm_type == $desired_type ?%BREAK_VM_WALK	
	]
	%BREAK_VM_WALK
	$vm_name=$vm


]::[
	$vm_type=none
]









