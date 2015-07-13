
;;;
Lock the node and wait it's been locked

Required input:
    <node>      name of the node
;;;

$node=compute-0

>system host-unlock $node

!sleep 6 
@6
>system host-show $node
+$st_admin=.*administrative \s*\|\s* (locked|unlocked)
+$st_avail=.*availability \s*\|\s* (available|online|offline|intest)

? $st_admin != unlocked ?[
    ;fail to unlock the node: $node

    ;check if it get-offline?
    ? $st_avail == offline ? [
        ;red the compute get offline, wait it get ONLINE again!
        ~wait_to_status.inc node=$node st_admin=locked st_avail=online st_operat=disabled timeout=$timeout fail_when_timeout=true
    ]

    >system host-unlock $node
    <.*
    !sleep 6
    >system host-show $node
    +$st_admin=.*administrative \s*\|\s* (locked|unlocked)
    +$st_avail=.*availability \s*\|\s* (available|online|offline|intest)

    ? $st_admin != unlocked ?[
        ;try to unlock $node again
        !sleep 3
        >system host-unlock $node
        +$st_admin=.*administrative \s*\|\s* (locked|unlocked)
        +$st_avail=.*availability \s*\|\s* (available|online|offline|intest)

        ? $st_admin != unlocked ?[
            ;still failed to unlock $node
            *FAIL
        ]
        ;OK, $node unlocked
    ]
]

;wait $node to be ready: "unlocked available enabled"
$timeout=800
~wait_to_status.inc node=$node st_admin=unlocked st_avail=available st_operat=enabled timeout=$timeout fail_when_timeout=true

;OK, $node now is unlocked and ready

