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
~ssh_controller.inc IP=<ip> [PORT=<custom port>]

;;;

# common include path
$inc_path=common

$admin_src_path=/etc/nova

; === get floating IP
>/sbin/ip addr | grep secondary | grep eth0
+$float_ip=inet ([0-9.]+)/

; === Become Admin to swact
>source $admin_src_path/openrc 

; === identify active controller
>system sda-list | grep controller-services
+$act_controller=controller-services.*(controller-\d).*active

; === swact controllers
>system host-swact $act_controller
>
@30
>ping -c 30 -W 30 $float_ip
<icmp_[sr]eq=\d+ ttl=64
!sleep 30
>>
<Write failed
>
; === re-login to controller
~$inc_path/ssh_controller.inc
>
