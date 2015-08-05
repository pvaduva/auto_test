#!/usr/bin/env expect-lite

;;;
Perform the following operations on the specified VM instance:
    - suspend/resume
    - pause/unpause
    - live migrate
    - cold migrate
    - soft reboot
    - cold reboot 
    - stop/start 

Options
    reuired inputs:
        vmid=<vmid>             host name or ip address of the active controller
        ops=<suspend-resume|pause-unpause|live-migr|cold-migr|soft-reboot|cold-reboot|stop-start|migrates>        
                                operations to be performed on the VM
        password=<password>
Assumption:
    current user is 'admin'
;;;

$inc_path=../../common/el

$password=li69nux
$ops=all

#;clean up log entries
#;logon to VM: $vmid
#~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid
#>cp -f /var/log/user.log ./user.log.$(date +%Y%m%d-%H%M%S)
#>echo > /var/log/user.log

#;logout of the VM
#>exit
#>^C
#> hostname
#>exit
#>^C

? $ops != all ? [
    ? $ops != suspend-resume ? %SKIP_SUSPEND
] 

;suspend the vm
!sleep 1
>nova suspend "$vmid"
!sleep 3
;wait for the vm to be SUSPENDED 
~wait_vm_status.inc vmid=$vmid vm_state=suspended status=SUSPENDED power=4

;resume the vm
!sleep 1
>nova resume "$vmid"
!sleep 3
;wait for the vm to be RESUMED 
~wait_vm_status.inc vmid=$vmid

%SKIP_SUSPEND

? $ops != all ? [
    ? $ops != pause-unpause ? %SKIP_PAUSE
] 

;pause the vm
!sleep 1
>nova pause "$vmid"
!sleep 3
;wait for the vm to be PAUSED 
~wait_vm_status.inc vmid=$vmid vm_state=paused status=PAUSED power=3

;unpause the vm
!sleep 1
>nova unpause "$vmid"
!sleep 3
;wait for the vm to be UNPAUSED 
~wait_vm_status.inc vmid=$vmid

%SKIP_PAUSE

? $ops != all ? [
    ? $ops != live-migrate ? [
        ? $ops != migrate ? %SKIP_MIGRATE
    ]
] 

;live-migrate the vm
>nova live-migration "$vmid"
!sleep 1

#;wait vm starts to migrate
#~wait_vm_status.inc vmid=$vmid task_state=migrating status=MIGRATING

;wait for the vm to be READY 
~wait_vm_status.inc vmid=$vmid

%SKIP_LIVE_MIGRATION

? $ops != all ? [
    ? $ops != cold-migrate ? [
        ? $ops != migrate ? %SKIP_MIGRATE
    ]
] 

;wait for 60 seconds then 'migrate' 
!sleep 60

;cold migrate the vm
$_cnt=50
$_n=0
[ $_n < $_cnt 

    =$_n + 1
    ;try to cold-migrate $vmid the $_n time
    >nova migrate "$vmid"

    !sleep 3
    >nova show $vmid
    +$_power=\|\s* OS-EXT-STS:power_state \s*\|\s* ([0-9]+) \s*\|
    +$_task_state=\|\s* OS-EXT-STS:task_state \s*\|\s* ([^\s]+) \s*\|
    +$_vm_state=\|\s* OS-EXT-STS:vm_state \s*\|\s* ([^\s]+) \s*\|
    +$_status=\|\s* status\s*\|\s* ([^\s]+) \s*\|

    ? $_status == VERIFY_RESIZE ? %_DONE_COLD_MIGR
    ? $_task_state != - ? %_DONE_COLD_MIGR

    ;wait another 5 seconds and try again
    !sleep 3
]

%_DONE_COLD_MIGR

? $_n < $_cnt ? [
    ;wait for the vm to be VERIFY_RESIZE 
    ~wait_vm_status.inc vmid=$vmid vm_state=resized status=VERIFY_RESIZE power=1
    ;confirm the resizing
    >nova resize-confirm "$vmid"
    ;wait for the vm to be ready
    ~wait_vm_status.inc vmid=$vmid
] :: [
    ;warning, cannot cold migrate vm:$vmid
    ;*FAIL
]

%SKIP_MIGRATE

? $ops != all ? [
    ? $ops != soft-reboot ?[
        ? $ops != reboot ? %SKIP_REBOOT
    ]
] 

;soft reboot the vm
!sleep 1
>nova reboot "$vmid"
;wait for the vm to be in REBOOT
~wait_vm_status.inc vmid=$vmid vm_state=active status=REBOOT power=1
;wait for the vm to be ready
~wait_vm_status.inc vmid=$vmid

%SKIP_REBOOT

? $ops != all ? [
    ? $ops != hard-reboot ?[
        ? $ops != reboot ? %SKIP_REBOOT
    ]
] 

;cold reboot the vm
!sleep 1
>nova reboot --hard "$vmid"
;wait for the vm to be in HARD_REBOOT
~wait_vm_status.inc vmid=$vmid vm_state=active status=HARD_REBOOT power=1
;wait for the vm to be ready
~wait_vm_status.inc vmid=$vmid

%SKIP_HARD_REBOOT

? $ops != all ? [
    ? $ops != stop-start ? %SKIP_STOP
] 

;stop the vm
!sleep 1
>nova stop "$vmid"
;wait for the vm to be in SHUTOFF
~wait_vm_status.inc vmid=$vmid vm_state=stopped status=SHUTOFF power=4

;start the vm
!sleep 1
>nova start "$vmid"
;wait for the vm to be ready
~wait_vm_status.inc vmid=$vmid

%SKIP_STOP

~clean_heartbeating_events.inc password=$password

>source /etc/nova/openrc
;get the current system alarm list
>system alarm-list

$_limit_loglist=50
>system log-list -l $_limit_loglist

