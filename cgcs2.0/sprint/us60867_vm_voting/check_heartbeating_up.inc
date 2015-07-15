
;;;
Check if guest-heartbeating is up

Required input:
    vmname=<name-of-vm>     name of the specified VM
    pass=<password>         password

Assumption:
    currently on VM
;;;

$cntlog1=/var/log/nfv-vim.log
#$cntlog2=/var/log/guestAgent.log
#$cmptlog=/var/log/guestServer.log
#$vmlog=/var/log/user.log

$pass=li69nux

$max=60
$_cnt=0
$_sleep=5

#Info : compute-1 30332b73-a180-4e2c-a5b0-c25541b918e4 is now heartbeating
;check on controller log: $cntlog1

[ $_cnt < $max 
    =$_cnt + 1
    >egrep "Guest-Services-(Disable callback for $vmname|Set callback for $vmnae)" $cntlog1 2>/dev/null | tail -n1
    +$_status=Guest-Services-(Disable|Set) callback for

    ? $_status == Set ? %_DONE

    !sleep $_sleep
]

%_DONE

? $_cnt >= 5 ? [
    ;the heartbeating is not up after $_cnt * $_sleep seconds 
    ;fail the test
    *FAIL
]

~clean_heartbeating_events.inc pass=$pass

