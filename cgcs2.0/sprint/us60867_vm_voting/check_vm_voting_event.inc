
;;;
Check if vm-voting is working as expected 

Required input:
    vmid=<uuid-of-vm>       uuid of the specified VM
    act=<operation-on-vm>   operation performed on the VM
                            currently only the following are supported:
                            suspend, pause, live-migrate, migrate, stop, reboot
    #pass=<password>         password

Assumption:
    currently on VM
;;;

$act=suspend
$pass=li69nux

$nfvvim=/var/log/nfv-vim.log
#$cntlog2=/var/log/guestAgent.log
#$cmptlog=/var/log/guestServer.log
#$vmlog=/var/log/user.log

!sleep 5
;check events/messages/logs after $act on VM:$vmid

;check the nfv-vim log on the controller

;check vote message: $_vote
>grep "Guest-Services-Vote for $vmname" $nfvvim 2>/dev/null
+$_act=action_type=(\w+)
? $_act == __NO_STRING_CAPTURED__ ? [
    ;cannot find vote message, "Guest-Services-Vote for $vmname", fail the test
    *FAIL
]

;check instance_uuid
>grep "Guest-Services action notify, instance_uuid=" $nfvvim 2>/dev/null
+$_instid=([0-9a-f-]{32,36})
? $_instid == __NO_STRING_CAPTURED__ ? [
    ;cannot find vote message, "Guest-Services action notify, instance_uuid=" fail the test
    *FAIL
]

;check if the requested act is rejected
>grep "Guest-Services-Vote for $vmname, vote=reject" $nfvvim 2>/dev/null
+$_rejected=vote=(reject)
? $_rejected == __NO_STRING_CAPTURED__ ? [
    ;cannot find vote message, Guest-Services-Vote for $vmname vote=$act fail the test
    *FAIL
]

;backup the log: $nfvvim
>sudo su
>>$pass

>cp $nfvvim ./nfv-vim.log-`date +%Y%m%d-%H%M%S`

;empty the log: $nfvvim
>cat /dev/null > $nfvvim

;restore the previous user
>exit
>^C
> whoami


