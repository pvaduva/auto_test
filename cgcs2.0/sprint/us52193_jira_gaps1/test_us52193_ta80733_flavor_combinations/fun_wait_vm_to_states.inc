
; wait server/vm with <VMUUID> to be ready

; required input arguments:
; <VMUUID>
; <VMSTATE>
; <STATUS> 

$max=60
$cnt=0
[ $cnt < $max
    =$cnt + 1
    ~fun_get_vm_status.inc VMUUID=$VMUUID
    ?if $VM_STATE == $VMSTATE ? [
        ?if $STATUS == $STATUS ?%READY
    ]
    !sleep 3
]
%READY

?if $cnt >= $max ? [
    *FAIL
]


