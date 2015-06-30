#!/usr/bin/env expect-lite

#HOST_IP=$HOST_IP HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD CPTNAME=$CPTNM

;start to test on compute:$CPTNAME


;get the numa-node to test 

;reseet the $CPTNAME hugepage settings: #2M=1/2 of available, #1G=0
~fun_reset_hugepage_on_compute.inc CPTNAME=$CPTNM

$NUMA_ID=0

;test on numa: $NUMA_ID of compute node: $CPTNAME
~fun_test_hugepage_on_compute_numa.inc HOST_IP=$HOST_IP HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD CPTNAME=$CPTNM NUMA_ID=$NUMA_ID
    
;finished test on compute:$CPTNAME

%DONE_COMPUTE


