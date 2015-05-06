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
#	ssh to controller
#

To use:
~ssh_controller.inc IP=<ip> [PORT=<custom port>]

;;;


$IP=10.10.10.3
$user=wrsroot
$pass=li69nux

$admin_src_path=/etc/nova

# support custom port support
$ssh_opts= -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no -o ConnectTimeout=20 
?if $PORT != $blank ? $ssh_opts=$ssh_opts -p $PORT 


; === connecting to $IP

@20
>ssh -X $ssh_opts $user@$IP
<ssword:|Last login:
>>$pass

>export TMOUT=0

?if $user == wrsroot? [
	@3
	; === set up sudo root access (to make it easier later in the interact session)
	>echo "$pass" | sudo -S id
	<root

	; === show source admin credentials
	>source $admin_src_path/openrc 

	; === show version
	>cat /etc/build.info
	>
]

