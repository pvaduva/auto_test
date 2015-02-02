
;;;
    Wait the status of the specified cinder volume changed to STATUS (specified)
    input:
    VOL_ID      uuid of the cinder volume
    STATUS      status to be expected    
;;;

$max=120
$cnt=0
[ $cnt < $max
    =$cnt + 1
    @10
    >cinder list --all-tenants
    +$CUR_STATUS=\|\s* $VOL_ID \s*\|\s*([a-z]+)\s*\|
    ?if $CUR_STATUS == $STATUS ?%DONE
    ! sleep 3
]

?if $cnt >= $max ? [
    *FAIL
]

%DONE

