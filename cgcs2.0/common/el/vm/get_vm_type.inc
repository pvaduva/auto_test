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
#	Gets VM type 
#		virtio, avp, dpdk
#	returns: $vm_type, $vm_uuid, $vm_data_ip
#
#

To use:
~get_vm_type.inc 

Options:
.	vm_name=<desired vm name>



;;;

>nova list --all-tenants | grep $vm_name | awk '{print $2}' | paste -sd ' '
+$vm_uuid=([0-9a-f-]{36})

; === get nic type of VM
>nova show $vm_uuid | grep nic
+$vm_nic1= "wrs-if:vif_model": "(\w+)"
<$vm_nic1
+$vm_nic2= "wrs-if:vif_model": "(\w+)"
<$vm_nic2
+$vm_nic3= "wrs-if:vif_model": "(\w+)"

; === get vm data ip address
>nova show $vm_uuid | grep network | tail -1
+$vm_data_ip=\| ([0-9.:]{7,37})


?if $vm_nic2 == avp ? [
	; === nova flavor show $vm
	>nova show $vm_uuid | grep flavor
	+$oflavor_uuid=\(([0-9a-f-]{36})\)

	>nova flavor-show $oflavor_uuid | grep extra_specs
	+$hw_model=(hw:cpu_model)
	+$hw_model_type="(SandyBridge)"

	$vm_type=avp
	# work around for not finding SandyBridge
	?if $hw_model == hw:cpu_model ? $vm_type=dpdk
]

?if $vm_nic2 == virtio ? $vm_type=virtio

;purple === VM:$vm_name type is: $vm_type









