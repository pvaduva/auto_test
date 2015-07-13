
;;;
Wait node to reach the specified status

Required input:
    <node>      node name
    <st_admin>  expected 'administrative' status of the ndoe
    <st_avail>  expected 'availability' status of the ndoe
    <st_operat> expected 'operational' status of the ndoe

Optional input:
    <timeout>   default value is 180 seconds
    <fail_when_timeout> fail the whole test if timeout, default is false

;;;

$node=compute-0
$st_admin=unlocked
$st_avail=available
$st_operat=enabled
$timeout=180

@6

$tm_wait=1
$tm_sleep=3
$tm_force_lock=1

[ $tm_wait < $timeout 

    ;wait $tm_sleep and check the status of $node
    !sleep $tm_sleep

    =$tm_wait + 2

    >system host-show $node
    +$st_administrative=.*administrative \s*\|\s* (locked|unlocked)
    +$st_availability=.*availability  \s*\|\s* (available|online|offline|intest)
    +$st_operational=.*operational  \s*\|\s* (enabled|disabled)
    +$st_task=.*task\s*\|\s+([^\s]+\s*[A-Za-z]*)

    ? $st_admin == $st_administrative ? [
        ? $st_avail == $st_availability ? [
            ? $st_operat == $st_operational ?%DONE 
        ]
    ]

    ? $forcelock == true ? [
        =$tm_wait - 1
        ? $st_task == Force Locking ? [
            ;force locking, wait longer
            =$tm_force_lock + 1 
            ? $tm_force_lock > 10 ? [
                =$tm_wait + 1
                =$tm_force_lock - 10
            ]
        ]
    ]
]

? $tm_wait >= $timeout ? [
    ;timeout for waiting for the node:$node turn into status:$status
    ? $fail_when_timeout == true ?[
        ;fail the test case if required
        *FAIL
    ] 
]

%DONE

