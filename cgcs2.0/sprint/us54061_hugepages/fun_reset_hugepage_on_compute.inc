
# CPTNAME=$CPTNM NUMA_ID=$NUMA_ID

; get the current hugepage settings on $CPTNAME $NUMA_ID
; get 'Total' memory (MiB)

$NUMA_ID=0
; reset hugepage's setting on $CPTNAME node:$NUMA_ID
>system host-memory-show $CPTNAME $NUMA_ID
+$total=\|\s*Memory: Total \s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|
+$avaialble=\|\s*Available \s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|

; calculate 2M PAGE NUMBER of node:0
>echo $(( $avaialble / 4 - 1 ))
+$nd0_2m=\n([0-9-]+)


$NUMA_ID=1
; reset hugepage's setting on $CPTNAME node:$NUMA_ID
>system host-memory-show $CPTNAME $NUMA_ID
+$total=\|\s*Memory: Total \s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|
+$avaialble=\|\s*Available \s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|

; calculate 2M PAGE NUMBER of node:0
>echo $(( $avaialble / 4 - 1 ))
+$nd1_2m=\n([0-9-]+)

$PERSONALITY=compute 

; lock the compute node: $CPTNAME
~fun_lock_wait.inc HOSTNAME=$CPTNAME PERSONALITY=$PERSONALITY

$IND_NUMA=1

$to_set=$nd0_2m
[ $IND_NUMA <= 10
    =$IND_NUMA + 1

    ; clear the 1G hugepage setting on $CPTNAME : node 0
    >system host-hugepage-update $CPTNAME 0 -2M $to_set -1G 0
    +$status=(No available space for)

    ?if $status == __NO_STRING_CAPTURED__ ?%NODE0_DONE

    =$to_set / 2

]

%NODE0_DONE

$IND_NUMA=1

$to_set=$nd1_2m
[ $IND_NUMA <= 10
    =$IND_NUMA + 1

    ; clear the 1G hugepage setting on $CPTNAME : node 1
    >system host-hugepage-update $CPTNAME 1 -2M $to_set -1G 0
    +$status=(No available space for)

    ?if $status == __NO_STRING_CAPTURED__ ?%NODE1_DONE

    =$to_set / 2
]

%NODE1_DONE

>system host-unlock $CPTNAME

~fun_wait_till_states.inc HOSTNAME=$CPTNAME PERSONALITY=$PERSONALITY ADMINISTRATIVE=unlocked OPERATIONAL=enabled AVAILABILITY=available

