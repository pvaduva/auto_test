
;;;
    Wait the status of the specified cinder volume changed to STATUS (specified)
    input:
    HOSTNAME
    PERSONALITY
    ADMINISTRATIVE
    OPERATIONAL
    AVAILABILITY
;;;
;;;
+----+--------------+-------------+----------------+-------------+--------------+
| id | hostname     | personality | administrative | operational | availability |
+----+--------------+-------------+----------------+-------------+--------------+
| 1  | controller-0 | controller  | unlocked       | enabled     | available    |
| 2  | controller-1 | controller  | unlocked       | enabled     | available    |
| 3  | compute-0    | compute     | unlocked       | enabled     | available    |
| 4  | compute-1    | compute     | unlocked       | enabled     | available    |
+----+--------------+-------------+----------------+-------------+--------------+
;;;

$max=200
$cnt=0

[ $cnt < $max

    =$cnt + 1

    @10
    ; +$STATUS=\|\s*[0-9]+\s*\|\s* $HOSTNAME \s*\|\s* $PERSONALITY \s*\|\s* $ADMINISTRATIVE \s*\|\s* $OPERATIONAL \s*\|\s* ($AVAILABILITY) \s*\|

    >system host-list
    +$STATUS=\|\s*[0-9]+\s*\|\s* $HOSTNAME \s*\|\s* $PERSONALITY \s*\|\s* $ADMINISTRATIVE \s*\|\s* $OPERATIONAL \s*\|\s* ($AVAILABILITY) \s*\|

    ?if $STATUS == $AVAILABILITY ?%DONE

    ; $cnt : 
    ; node $HOSTNAME is not in status $AVAILABILITY yet, wait for 15 seconds and try again
    ! sleep 15
]

?if $cnt >= $max ? [

    ; node $HOSTNAME failed to get to status $STATUS in $max * 15 seconds 
    ; consider it as a FAIL

    *FAIL

]

; now node $HOSTNAME should be status $STATUS

%DONE

