
;;;
Lock the node and wait it's been locked

Required input:
    <node>      name of the node
;;;

$node=compute-0

>system host-lock $node

!sleep 6
@6
>system host-show $node
+$st_administrative=.*administrative \s*\|\s* (locked|unlocked)
+$st_availability=.*availability \s*\|\s* (available|online|offline|intest)

? $st_administrative != locked ?[
    ;fail to lock the node: $node
    ;try to force-lock
    > system host-lock -f $node
    ~wait_to_status.inc node=$node st_admin=locked st_avail=online st_operat=disabled timeout=120 fail_when_timeout=true forcelock=true
]

;node:$node should be locked
>system host-show $node

