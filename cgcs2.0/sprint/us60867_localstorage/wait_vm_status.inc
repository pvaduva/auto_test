
;;;
Wait the VM to be launched and behaviors correctly

Required inputs:
    vmid=<vmid>             the uuid of the VM
    timeout=<seconds>       maximum seconds to wait for the VM be ready

Optional inputs:
    $st_power               number indicating the power status
    $st_task_state          state of the task
    $st_vm_state            state of the VM instance
    $st_status              status of the VM instance

Assumption:
    the VM belongs to the current tenant
;;;

$wait=0
$timeout=200
$power=1
$task_state=-
$vm_state=active
$status=ACTIVE


#VMSTATE=resized STATUS=VERIFY_RESIZE

@10
;wait for the VM to be ready, timeout:$timeout
[ $wait <= $timeout
    >nova show $vmid
    +$st_power_state=\|\s* OS-EXT-STS:power_state \s*\|\s* ([0-9]+) \s*\|
    +$st_task_state=\|\s* OS-EXT-STS:task_state \s*\|\s* ([^\s]+) \s*\|
    +$st_vm_state=\|\s* OS-EXT-STS:vm_state \s*\|\s* ([^\s]+) \s*\|
    +$st_status=\|\s* status\s*\|\s* ([^\s]+) \s*\|

    ? $status == $st_status ? [
        ? $vm_state == $st_vm_state ?%DONE 
    ]

    ;try again after 10 seconds, toally waited:$wait
    !sleep 10
    =$wait + 10
]

? $wait > $timeout ? [
    ;ERROR: VM:$vmid not ready in $timeout seconds
    *FAIL
]

%DONE

;vm is in status: power:$st_power_state, task:$st_task_state, vm_state:$st_vm_state, status:$st_status


