
;;;
    Wait the status of the specified cinder volume changed to STATUS (specified)
    input:
    HOSTNAME
    PERSONALITY
    #ADMINISTRATIVE
    #OPERATIONAL
    #AVAILABILITY
;;;

>system host-lock $HOSTNAME
<\|\s* task \s*\|\s* Locking \s*\||Avoiding 'lock' action on already 'locked' host

;;;
+----+--------------+-------------+----------------+-------------+--------------+
| id | hostname     | personality | administrative | operational | availability |
+----+--------------+-------------+----------------+-------------+--------------+
| 1  | controller-0 | controller  | unlocked       | enabled     | available    |
| 11 | controller-1 | controller  | unlocked       | enabled     | available    |
| 12 | storage-0    | storage     | unlocked       | enabled     | available    |
| 13 | storage-1    | storage     | unlocked       | enabled     | available    |
| 15 | compute-0    | compute     | locked         | disabled    | online       |
| 16 | compute-1    | compute     | unlocked       | enabled     | available    |
+----+--------------+-------------+----------------+-------------+--------------+
;;;

~fun_wait_till_states.inc HOSTNAME=$HOSTNAME PERSONALITY=$PERSONALITY ADMINISTRATIVE=locked OPERATIONAL=disabled AVAILABILITY=online


