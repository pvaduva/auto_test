
# HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD CPTNAME=$CPTNM NUMA_ID=$NUMA_ID FREE_TOTAL=$FREE_TOTAL FREE_2M=$FREE_2M USED_2M=$USED_2M FREE_1G=$FREE_1G USED_1G=$USED_1G

; get the current hugepage settings on $CPTNAME $NUMA_ID
>system host-memory-show $CPTNAME $NUMA_ID

; calculate 1G PAGE NUMBER 
>echo $(( $FREE_TOTAL / 2000 - 1 ))
+$n_1g=\n([0-9-]+)

?if $n_1g == $USED_1G ? [
    =$n_1g - 1
]
?if $n_1g < 0 ? [
    $n_1g=0
]

; calculate 2M PAGE NUMBER 
#>echo $(( ( $FREE_TOTAL - $n_1g * 512 ) / 2 ))
>echo $(( ( $FREE_TOTAL - $n_1g * 512 ) / 4 ))
+$n_2m=\n([0-9-]+)

?if $n_2m == $USED_2M ? [
    =$n_2m - 1
]

?if $n_2m < 0 ? [
    $n_2m=0
]

; check the PAGE NUMBERs of 2M and 1G
?if $n_1g == 0 ? [
    ; if both are zeros, skip the test
    ?if $n_2m == 0 ? %NUMA_DONE
]

$PERSONALITY=compute 

; lock the compute node: $CPTNAME
~fun_lock_wait.inc HOSTNAME=$CPTNAME PERSONALITY=$PERSONALITY

; test NEG1 : no <numa> <2m-hugepage-num> <1g-hugepage-num>
>system host-hugepage-update $CPTNAME
+$err=\n(system host-hugepage-update: error: too few arguments)

; test NEG2: no <2m-hugepage-num> <1g-hugepage-num>
>system host-hugepage-update $CPTNAME $NUMA_ID
+$err=\n(system host-hugepage-update: error: too few arguments)

; test NEG3: no <1g-hugepage-num>
>system host-hugepage-update $CPTNAME $NUMA_ID $n_2m
+$err=\n(system host-hugepage-update: error: too few arguments)

; test NEG4: too many input arguments
>system host-hugepage-update $CPTNAME $NUMA_ID $n_2m $n_1g 123
+$err=\n(system: error: unrecognized arguments: 123)

; test NEG5: invalid(negative) 2m-hugepage-num
>system host-hugepage-update $CPTNAME $NUMA_ID -1 $n_1g
+$err=\n(VM huge pages 2M must be greater than or equal to zero)

; test NEG6: invalid(non-integer) 1g-hugepage-num
>system host-hugepage-update $CPTNAME $NUMA_ID $n_2m 12f
+$err=\n(invalid literal for int\(\) with base 10:)

; test NEG7: invalid(non-integer) 2m-hugepage-num
>system host-hugepage-update $CPTNAME $NUMA_ID 12. $n_1g
+$err=\n(invalid literal for int\(\) with base 10:)

; test NEG8: invalid(too large) 2m-hugepage-num
>system host-hugepage-update $CPTNAME $NUMA_ID 123456789 $n_1g
+$err=\nNo available space for 2M huge page allocation, max 2M pages: ([0-9]+)

; test NEG9: invalid(too large) 1g-hugepage-num
>system host-hugepage-update $CPTNAME $NUMA_ID $n_2m 123456789
+$err=\nNo available space for 2M huge page allocation, max 2M pages: ([0-9]+)

; test NEG10: without changes
>system host-hugepage-update $CPTNAME $NUMA_ID 0 0 

#~fun_calc_pgnums.inc FREE_TOTAL=$FREE_TOTAL FREE_2M=$FREE_2M USED_2M=$USED_2M FREE_1G=$FREE_1G USED_1G=$USED_1G
>system host-hugepage-update $CPTNAME $NUMA_ID $n_2m $n_1g
+$cnfed_2m=\n\|\s* Configured \s*\|\s* ([0-9]+|None) \s*\|
+$cnfed_1g=\n\|\s* Configured \s*\|\s* ([0-9]+|None) \s*\|

>system host-unlock $CPTNAME
~fun_wait_till_states.inc HOSTNAME=$CPTNAME PERSONALITY=$PERSONALITY ADMINISTRATIVE=unlocked OPERATIONAL=enabled AVAILABILITY=available

#~fun_verfiy_result.inc CPTNAME=$CPTNAME NUMA_ID=$NUMA_ID FREE_TOTAL=$FREE_TOTAL FREE_2M=$FREE_2M USED_2M=$USED_2M FREE_1G=$FREE_1G USED_1G=$USED_1G

>system host-memory-show $CPTNAME $NUMA_ID 
# >system host-memory-show compute-1 0 | grep 'Configured' | cut -d\| -f2,3
+$cnfed_2m=\n\|\s* Configured \s*\|\s* ([0-9]+|None) \s*\|
?if $cnfed_2m == __NO_STRING_CAPTURED__ ? [
    $cnfed_2m=0
]
?if $cnfed_2m == None ? [
    $cnfed_2m=0
]

>system host-memory-show $CPTNAME $NUMA_ID | grep 'Configured' | tail -n1
+$cnfed_1g=\n\|\s* Configured \s*\|\s* ([0-9]+|None) \s*\|
?if $cnfed_1g == __NO_STRING_CAPTURED__ ? [
    $cnfed_1g=0
]
?if $cnfed_1g == None ? [
    $cnfed_1g=0
]

?if $cnfed_2m != $n_2m ? [
    ; the 2m-hugepage configured is not what specified, specified=$n_2m configured=$cnfed_2m 
    # 
]

?if $cnfed_1g != $n_1g ? [
    ; the 1g-hugepage configured is not what specified, specified=$n_1g configured=$cnfed_1g 
    # 
]

%NUMA_DONE

