
;;;
Try to live-migrate the specified VM which is using local-storage.
This is expected to be rejected.

Required inputs:
    vmid=<uuid>             the uuid of the VM to test

Optional inputs:
    tenant_user=<user>      user name for tenant1, 'tenant1' by default
    tenant_passwd=<user>    user name for tenant1, 'tenant1' by default
    tenant2_user=<user>     user name for tenant2, 'tenant2' by default

Assumption:
    currently the user is 'admin'
;;;

@10
;get the hosting compute for VM:$vmid
>nova show $vmid
+$cur_hosting=.*OS-EXT-SRV-ATTR:host \s*\|\s* ([0-9a-z-]+) \s*\|

? $cur_hosting == __NO_STRING_CAPTURED__ ? [
    ;red ERROR: cannot find the hosting compute node of the VM:$vmid
    *FAIL
]
;current host is compute:$cur_hosting for VM:$vmid

;live-migrate the VM:$vmid
>nova live-migration $vmid

;expecting error messages, check if there's any message
;TODO: the feature is broken for now, do not test it
#
#+$errmsg=\n([^\s]+)
#
#? $errmsg == __NO_STRING_CAPTURED__ ? [
#    ;red ERROR: no error message found
#    *FAIL
#]

!sleep 6
;wait and check if hosting actually changed
$wait=0
$toatl=60
[ $wait < $total 
    !sleep 3
    >nova show $vmid
    +$new_hosting=.*OS-EXT-SRV-ATTR:host \s*\|\s* ([0-9a-z-]+) \s*\|

    ? $new_hosting == __NO_STRING_CAPTURED__ ? [
        ;red error: cannot find the hosting compute live-migrated to for the VM:$vmid
        *FAIL
    ]
    ? $new_hosting != $cur_hosting ? [
        ;red error: live-migratd! this is not expected!
        *FAIL
    ]
    =$wait + 3
]
;live-migration does not work, this is EXPECTED behavior

