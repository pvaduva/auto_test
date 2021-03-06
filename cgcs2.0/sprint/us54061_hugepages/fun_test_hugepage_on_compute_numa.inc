
# HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD CPTNAME=$CPTNM NUMA_ID=$NUMA_ID

;get the current hugepage settings on $CPTNAME 

;get 'Total', 'Available' memory on numa:0
>system host-memory-show $CPTNAME 0
+$total0=\|\s*Memory:\s*Total\s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|
+$avaialble0=\|\s*Available\s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|

;get 'Total', 'Available' memory on numa:1
>system host-memory-show $CPTNAME 1
+$total1=\|\s*Memory:\s*Total\s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|
+$avaialble1=\|\s*Available\s*\(MiB\)\s*\|\s*([0-9]+|None)\s*\|

$avaialble=$avaialble0
? $avaialble1 < $avaialble ? [
    $avaialble=$avaialble1
]

;calculate 1G PAGE NUMBER will to be set
>echo $(( $avaialble / 2048 - 1 ))
+$n_1g=\n([0-9-]+)

? $n_1g == $confd_1g ? [
    ;$n_1g is same as current 1g-page-number, so use $n_1g - 1 instead
    =$n_1g - 1
]
? $n_1g < 0 ? [
    ; use 0 for 1g-page-number
    $n_1g=0
]

;will set #1G => $n_1g

;calculate 2M PAGE NUMBER 
>echo $(( $avaialble / 4 - 1 ))
+$n_2m=\n([0-9-]+)

? $n_2m == $USED_2M ? [
    ; $n_2m is the same as current 2m-page-number, so use $n_2m - 1 instead
    =$n_2m - 1
]

? $n_2m < 0 ? [
    $n_2m=0
]

;will set #2M => $n_2m

;check the PAGE NUMBERs of 2M and 1G
? $n_1g == 0 ? [
    ; if both are zeros, skip the test
    ? $n_2m == 0 ? %NUMA_DONE
]

$PERSONALITY=compute 

;lock the compute node: $CPTNAME
~fun_lock_wait.inc HOSTNAME=$CPTNAME PERSONALITY=$PERSONALITY

$IND_NUMA=1

[ $IND_NUMA <= 10
    =$IND_NUMA + 1

    >system host-hugepage-update $CPTNAME $NUMA_ID -2M $n_2m -1G $n_1g
    +$status=(No available space for|Processor does not support 1G huge pages)

    ? $status == __NO_STRING_CAPTURED__ ?%TO_UNLOCK

    ? $status == Processor does not support 1G huge pages ? [
        ;do not support 1G hugepage, try without #1G
        $n_1g=NotSupported
        >system host-hugepage-update $CPTNAME $NUMA_ID -2M $n_2m
        +$status=(No available space for)
        ? $status == __NO_STRING_CAPTURED__ ?%TO_UNLOCK
    ]

    ; too big: $status
    =$n_2m / 2
    =$n_1g / 2
    ; try to set with less numbers: #2M=$n_2m, #1G=$n_1g

    !sleep 5
]

%TO_UNLOCK

>system host-unlock $CPTNAME
~fun_wait_till_states.inc HOSTNAME=$CPTNAME PERSONALITY=$PERSONALITY ADMINISTRATIVE=unlocked OPERATIONAL=enabled AVAILABILITY=available

;get acutally set numbers for hugepage setting
>system host-memory-show $CPTNAME $NUMA_ID | grep '(2M)' -A2
+$cnfed_2m=\n\|\s*Total Pending\s*\|\s*([0-9]+|None)\s*\|
? $cnfed_2m == __NO_STRING_CAPTURED__ ? [
    $cnfed_2m=0
]
? $cnfed_2m == None ? [
    $cnfed_2m=0
]

? $cnfed_2m != $n_2m ? [
    ; the 2m-hugepage configured is not what specified, specified=$n_2m configured=$cnfed_2m 
    *FAIL
]

? $n_1g != NotSupported ? [
    >system host-memory-show $CPTNAME $NUMA_ID | grep '(1G)' -A2
    +$cnfed_1g=\n\|\s*Total Pending\s*\|\s*([0-9]+|None)\s*\|
    ? $cnfed_1g == __NO_STRING_CAPTURED__ ? [
        $cnfed_1g=0
    ]
    ? $cnfed_1g == None ? [
        $cnfed_1g=0
    ]
    ? $cnfed_1g != $n_1g ? [
        ; the 1g-hugepage configured is not what specified, specified=$n_1g configured=$cnfed_1g 
        *FAIL
    ]
]

$vmuser=wrsroot
$vmpasswd=li69nux
$hostcpt=$CPTNAME

>ssh -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $vmuser@$hostcpt
<assword|SYSTEM:|WARNING:
>>$vmpasswd

>sudo date
>>$vmpasswd
>sudo virsh freepages  0 --pagesize 2048
+$vrsh_2m=\s*2048KiB:\s*([0-9]+)

;check if #2m matches that in virsh
? $vrsh_2m != $cnfed_2m ? [
    ;does not match, fail the test case
    *FAIL
]

? $n_1g != NotSupported ? [
    ;check #1G matches setting in virsh
    >sudo virsh freepages  0 --pagesize 1048576
    +$vrsh_1g=\s*1048576KiB:\s*([0-9]+)
    ? $vrsh_1g != $cnfed_1g ? [
        ;does not match, fail the test case
        *FAIL
    ]
]

@20
;logout from the compute:$compute
>exit
>^C
> date | true
<.*

>source /etc/nova/openrc
<.*

; done with testing on $CPTNAME

%NUMA_DONE

