
;;;
Wait the VM to be launched and behaviors correctly

Required inputs:
    vmid=<vmid>             the uuid of the VM
    status=<status>         status of the VM instance

Optional inputs:
    power=<power>           number indicating the power status
    task_state=<task>       state of the task
    vm_state=<vmstate>      state of the VM instance
    timeout=<seconds>       maximum seconds to wait for the VM be ready

Assumption:
    the VM was created by the current tenant
;;;

$timeout=200

$power=NONE
$task_state=NONE
$vm_state=NONE
$status=ACTIVE

$_wait=0
$_tm=5

@10
;wait for the VM to be in the expected status, timeout:$timeout
[ $_wait <= $timeout
    >nova show $vmid
    +$_power=\|\s* OS-EXT-STS:power_state \s*\|\s* ([0-9]+) \s*\|
    +$_task_state=\|\s* OS-EXT-STS:task_state \s*\|\s* ([^\s]+) \s*\|
    +$_vm_state=\|\s* OS-EXT-STS:vm_state \s*\|\s* ([^\s]+) \s*\|
    +$_status=\|\s* status\s*\|\s* ([^\s]+) \s*\|

    $_pass=1

    ? $_status != $status ? $_pass=0

    ? $vm_state != NONE ? [
        ? $_vm_state != $vm_state ? $_pass=0
    ]
    ? $power != NONE ? [
        ? $_power != $power ? $_pass=0
    ]
    ? $task_state != NONE ? [
        ? $_task_state != $task_state ? $_pass=0
    ] :: [ 
        ? $status == ACTIVE ? [
            ? $_task_state != - ? $_pass=0
        ]
    ]

    ? $_pass == 1 ? %DONE

    ;try again after $_tm seconds, toally waited:$_wait
    !sleep $_tm
    =$_wait + $_tm
]

? $_wait > $timeout ? [
    ;ERROR: VM:$vmid is not in expected status within $timeout seconds, 
    ;   expected status: power=$power, task_state=$task_state, vm_state=$vm_state, status=$status
    *FAIL
]

%DONE

;vm is in status: power:$_power, task:$_task_state, vm_state:$_vm_state, status:$_status


