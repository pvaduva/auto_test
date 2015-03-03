#!/usr/bin/env expect-lite

#HOST_IP=$HOST_IP HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD CPTNAME=$CPTNM

; finished test on numa:$NUMA_ID of compute:$CPTNAME

$NUMA_LIST_FILE=~/$CPTNAME.numas_ids
$MEM_AVAIL_FILE=~/$CPTNAME.free
$FREE_2M_FILE=~/$CPTNAME.free_2m
$USED_2M_FILE=~/$CPTNAME.used_2m
$FREE_1G_FILE=~/$CPTNAME.free_1g
$USED_1G_FILE=~/$CPTNAME.used_1g
>system host-memory-list $CPTNM | egrep '^\|\s*[0-9]+' | cut -d\| -f2 > $NUMA_LIST_FILE
>system host-memory-list $CPTNM | egrep '^\|\s*[0-9]+' | cut -d\| -f5 > $MEM_AVAIL_FILE
>system host-memory-list $CPTNM | egrep '^\|\s*[0-9]+' | cut -d\| -f12 > $FREE_2M_FILE
>system host-memory-list $CPTNM | egrep '^\|\s*[0-9]+' | cut -d\| -f13 > $USED_2M_FILE
>system host-memory-list $CPTNM | egrep '^\|\s*[0-9]+' | cut -d\| -f16 > $FREE_1G_FILE
>system host-memory-list $CPTNM | egrep '^\|\s*[0-9]+' | cut -d\| -f17 > $USED_1G_FILE

>wc -l $NUMA_LIST_FILE
+$NUMA_CNT=\n([0-9]+)
?if $NUMA_CNT <= 0 ? [
    ; no numa nodes!? something wrong terribly
    %DONE_COMPUTE
]
>shuf $NUMA_LIST_FILE

$IND_NUMA=1

[ $IND_NUMA <= $NUMA_CNT
    >tail -n+$IND_NUMA $NUMA_LIST_FILE | head -n1 | tr -d " \t" 
    +$NUMA_ID=\n([0-9]+)

    >tail -n+$IND_NUMA $MEM_AVAIL_FILE | head -n1 | tr -d " \t"
    +$FREE_TOTAL=\n([0-9]+)

    >tail -n+$IND_NUMA $FREE_2M_FILE | head -n1 | tr -d " \t"
    +$FREE_2M=\n([0-9]+|None)

    >tail -n+$IND_NUMA $USED_2M_FILE | head -n1 | tr -d " \t"
    +$USED_2M=\n([0-9]+|None)

    >tail -n+$IND_NUMA $FREE_1G_FILE | head -n1 | tr -d " \t"
    +$FREE_1G=\n([0-9]+|None)

    >tail -n+$IND_NUMA $USED_1G_FILE | head -n1 | tr -d " \t"
    +$USED_1G=\n([0-9]+|None)


    =$IND_NUMA + 1 

    ?if $NUMA_ID == __NO_STRING_CAPTURED__ ?%DONE_COMPUTE


    ; test on numa: $NUMA_ID of compute node: $CPTNAME
    #~fun_test_hugepage_on_compute_numa.inc HOST_IP=$HOST_IP HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD CPTNAME=$CPTNM NUMA_ID=$NUMA_ID
    ~fun_test_hugepage_on_compute_numa.inc HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD CPTNAME=$CPTNM NUMA_ID=$NUMA_ID FREE_TOTAL=$FREE_TOTAL FREE_2M=$FREE_2M USED_2M=$USED_2M FREE_1G=$FREE_1G USED_1G=$USED_1G
    
]

; finished test on numa:$NUMA_ID of compute:$CPTNAME
%DONE_COMPUTE

>rm -f $NUMA_LIST_FILE
>rm -f $MEM_AVAIL_FILE
>rm -f $FREE_2M_FILE
>rm -f $USED_2M_FILE
>rm -f $FREE_1G_FILE
>rm -f $USED_1G_FILE

