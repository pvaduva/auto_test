
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

$max=120
$cnt=0
[ $cnt < $max
    =$cnt + 1
    @10
    >system host-list
    ; +$STATUS=\|\s*[0-9]+\s*\|\s* $HOSTNAME \s*\|\s* $PERSONALITY \s*\|\s* $ADMINISTRATIVE \s*\|\s* $OPERATIONAL \s*\|\s* ($AVAILABILITY) \s*\|
    +$STATUS=\|\s*[0-9]+\s*\|\s* $HOSTNAME \s*\|\s* $PERSONALITY \s*\|\s* $ADMINISTRATIVE \s*\|\s* $OPERATIONAL \s*\|\s* ($AVAILABILITY) \s*\|
    ?if $STATUS == $AVAILABILITY ?%DONE
    ! sleep 15
]

?if $cnt >= $max ? [
    ; consider it as a FAIL
    *FAIL
]

%DONE

