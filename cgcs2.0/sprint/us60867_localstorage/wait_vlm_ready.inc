
;;;
Wait node to reach the specified status

Required input:
    <vlmid>     uuid of the volume
Optional input:
    <status>    status to wait for

;;;

$status=available
$timeout=180

;wait for volume:$vlmid to be $status, timeout=$timeout

@6

$tm_wait=0
$tm_sleep=3

[ $tm_wait < $timeout 

    ;wait $tm_sleep and check the status of volume
    !sleep $tm_sleep

    =$tm_wait + $tm_sleep  

    >cinder show $vlmid
    +$id=.*id \s*\|\s* ([0-9a-f-]{32,36})
    +$cur_status=\s* status \s*\|\s* ([a-z]+) \s*\|

    ? $cur_status == $status ?%DONE 
]

? $tm_wait >= $timeout ? [
    ;timeout for waiting for the volume:$vlmid turn into status:$status
    ;fail the test case if required
    *FAIL
]

%DONE

;volume:$vlmid $status


