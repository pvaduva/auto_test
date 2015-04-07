
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
    ; wait for status to be $STATUS: $cnt

    @10
    ; cmd: cinder show $VOL_ID
    >cinder show $VOL_ID
    +$CUR_STATUS=\|[\s\t]*status[\s\t]*\|[\s\t]*([a-z]+)[\s\t]*\|
    ?if $CUR_STATUS == $STATUS ?%DONE
    ! sleep 3
]

?if $cnt >= $max ? [
    ; time out to wait for status to be $STATUS, tried $cnt times

    *FAIL
]

%DONE

