
;;;
Convert the compute node to 'local-storage' and check the expected results.

Required input:
    <compute>       the name of the compute-node
;;;

$libdir=../../common

;check whether the compute node was already 
;  configured to support 'local storage'

$compute=compute-0

;check if compute:$compute already configured with local-storage
>system host-lvg-list $compute
+$lvg_name=.*\|\s* (nova-local)

? $lvg_name != nova-local ? [
    ;'nova-local' volume group is not existing

    ;created it
    >system host-lvg-add $compute nova-local
    !sleep 3
]

;then get its UUID
>system host-lvg-list $compute  
+$lvg_id=\s* ([0-9a-f-]{32,36}) \s*

? $lvg_id == __NO_STRING_CAPTURED__ ? [
    ;failed to create local volume group 'nova-cola' 
    *FAIL
]

;check if the physical-volume on $compute
>system host-pv-list $compute 
+$pv_id=\s* ([0-9a-f-]{32,36}) \s*

? $pv_id == __NO_STRING_CAPTURED__ ? [
    ;no physical-volume is set on $compute
    
    ;get the hard disk on $compute
    >system host-disk-list $compute
    +$disk_id=\s* ([0-9a-f-]{32,36}) \s*
    
    ? $disk_id == __NO_STRING_CAPTURED__ ? [
        ;FATAL: no available disk on $compute
        *FAIL
    ]::[
        ;add the disk: $disk_id to nova-local on $compute

        >system host-pv-add $compute nova-local $disk_id
        +$pv_id=\s* ([0-9a-f-]{32,36}) \s*

        ? $pv_id == __NO_STRING_CAPTURED__ ? [
            ;FATAL: failed to add physical-volume on $compute
            *FAIL
        ]
    ]
]::[
    ;There's already physical-volume on $compute
]

;volume-group created/existing, id: $lvg_id
;physical-volume created/existing, id: $pv_id


