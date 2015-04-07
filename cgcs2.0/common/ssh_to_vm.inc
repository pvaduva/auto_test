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
#	ssh to vm with login
#	uses ip netns (name space)
#

To use:
~ssh_to_vm.inc 

Options:
.	vm_name=<desired vm name>
.	mgmt_net=<management net name>
.	FAIL=path/name_of_fail_script

NOTE:
set timeout to reasonable value before calling this script
assumes admin user

;;;

# default vm name
$vm_name=tenant1-virtio1 

$cgcs=$vm_name
=$cgcs/.*(tenant).*/\1/

$mgmt_net=tenant1-mgmt-net
#$mgmt_net=public-net0

# cgcs credentials
$vm_user=root
$vm_pass=root

$ssh_opts= -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no -o ConnectTimeout=8 

$max_retry=5

# setup fail script
?if $FAIL == $blank ? *~$inc_path/fail_show.inc :: ~$FAIL


; === get mangement uuid
>neutron net-list
+$tenant1_mgmt_net_uuid=([0-9a-f-]{36}) \| $mgmt_net

; === get vm management address
>nova list --all-tenants
<$vm_name
+$vm_ip=$mgmt_net=([0-9.]{7,15})

; === get net host
>neutron dhcp-agent-list-hosting-net $tenant1_mgmt_net_uuid
+$vm_netns_host=(compute-\d+)

; === connect to net host
>ssh -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $vm_netns_host
<ssword:|WARNING:
>>$pass

; === set up sudo root access (to make it easier later in the interact session)
>echo "$pass" | sudo -S id
<root
>sudo su

>ip netns list
+$ns=\n(.*$tenant1_mgmt_net_uuid)


; === ping the VM
>ip netns exec $ns ping -c 2 $vm_ip
+$ping_result=(\d+ received| 0 received)

?if $ping_result != 0 received ? [

	; === connect to VM
	*/.*: /
	$i=0
	$response=refused
	[ $response != ssword
		>ip netns exec $ns ssh $ssh_opts $vm_user@$vm_ip
		+$response=(ssword|refused)
		!sleep 2
		+$i
		; --- retry $i
		?if $i > $max_retry ? [
			# exit while loop
			$response=ssword
			;red VM:$vm_ip sshd not responding, returning to controller
			>>^C
			>exit
			>exit
			*FAIL
			>
		]
	]
	#<ssword:
	>>$vm_pass
	# clear prompt
	*//
]::[
	;red VM $vm_name did not respond to ping, returning to controller
	>>^C
	>exit
	>exit
	*FAIL
	>
	
]
>











