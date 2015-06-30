;;;
Convert the compute node to 'remote storage'

Required inputs:
    compute=<compute>       the compute node to covert

Optional inputs:
    host_user=<user>        'wrsroot' by default
    host_passwd=<passwd>    'li69nux' by default

;;;

$compute=compute-1

;get the 'nova-local' lvg on compute:$compute
>system host-lvg-list $compute
+$lvg_id=\s* ([0-9a-f-]{32,36}) \s*\|\s* nova-local \s*\|
? $lvg_id == __NO_STRING_CAPTURED__ ? [
    ;no 'nova-local' lvg on the compute:$compute
    ;done
] :: [
    ;the lvg exists on compute:$compute
    ;delete it
    >system host-lvg-delete $compute nova-local
    <.

    ;wait and check if it's in 'deleting' status
    !sleep 6
    >system host-lvg-list $compute
    +$status=\s* [0-9a-f-]{32,36} \s*\|\s* nova-local \s*\|\s* ([^\s]+) \s*\|
    ? $status != removing ? [
        ;ERROR: failed to delete the lvg:$lvg_id on compute:$compute
        ; fail the whole test
        *FAIL
    ]
]


;the lvg on compute:$compute is removed

