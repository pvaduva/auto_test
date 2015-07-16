
;;;
Make sure the guest-heartbeating service is ready by checking
    logs files (maybe change when better ways are available)

Required input:
    vmname=<name-of-vm>     name of the specified VM
    password=<password>     password

Assumption:
    currently on VM
;;;

$_vimlog=/var/log/nfv-vim.log
#$_guest_agent_log=/var/log/guestAgent.log
#$_geust_server_log=/var/log/guestServer.log
#$_vm_instance_log=/var/log/user.log

$password=li69nux

$_max=60
$_cnt=0
$_sleep=5

;check on controller log: $_vimlog

[ $_cnt < $_max 
    =$_cnt + 1
    >egrep "Guest-Services-(Disable callback for $vmname|Set callback for $vmnae)" $_vimlog 2>/dev/null | tail -n1
    +$_status=Guest-Services-(Disable|Set) callback for

    ? $_status == Set ? %_DONE

    !sleep $_sleep
]

%_DONE

? $_cnt >= $_max ? [
    ;the heartbeating is not up after $_cnt * $_sleep seconds 
    ;fail the test
    *FAIL
]

~clean_heartbeating_events.inc password=$password

