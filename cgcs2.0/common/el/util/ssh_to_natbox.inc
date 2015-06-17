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
#	ssh to vm with login via the NAT box
#	Use in real labs only
#

To use:
~ssh_to_nat_to_vm.inc 

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

$mgmt_net=mgmt-net
#$mgmt_net=public-net0

#nat box credentials
$natuser=cgcs
$natpass=li69nux

# cgcs credentials
$vm_user=root
$vm_pass=root
$natbox=128.224.150.11

$ssh_opts= -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no -o ConnectTimeout=8 

$max_retry=5

$ping=ping





; === connect to nat box
~$inc_path/ssh_controller.inc user=cgcs IP=$natbox

>hostname
>















