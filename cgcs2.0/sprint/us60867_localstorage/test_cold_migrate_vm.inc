
;;;
Try to cold migrate the specified VM which is using local-storage.
The expected results are depend on whether 2 or more local-storage nodes existing

Required inputs:
    vmid=<uuid>             the uuid of the VM to test
    cnt_computes=<n>        the number of compute-nodes
    loc_compute=<compute>   the compute configured with local-storage

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
    ;red error: cannot find the hosting compute node of the VM:$vmid
    *FAIL
]
;current host is compute:$cur_hosting for VM:$vmid

;attempt to code migrate, this is expected to fail with only 1 compute-node 
>system host-list | grep -v $loc_compute | awk '{ if ($6 == "compute") print $4}'
+$compute2=\n([^\s]+)
~convert_to_local_storage.inc compute=$compute2

;cold migrate the VM:$vmid
;waith for it get resized
>nova migrate $vmid
~wait_vm_status.inc vmid=$vmid timeout=400 vm_state=resized status=VERIFY_RESIZE

;resized OK
;confirm the resize and wait the compute be 'available'
>nova resize-confirm $vmid
~wait_vm_status.inc vmid=$vmid timeout=600 vm_state=active status=ACTIVE

;VM now is ACTIVE
;get the new hosting compute for VM:$vmid
>nova show $vmid
+$cur_hosting=.*OS-EXT-SRV-ATTR:host \s*\|\s* ([0-9a-z-]+) \s*\|

? $cur_hosting == __NO_STRING_CAPTURED__ ? [ 
    ;red error: cannot find the new hosting compute node of the VM:$vmid
    *FAIL
]
;current host is compute:$cur_hosting for VM:$vmid

;check storage of VM:$vmid after cold migration
~check_storage_loc.inc volume=$volume vmid=$vmid

;delete the VM:$vmid
>nova delete $vmid

;cold migration VM:$vmid succeeded

