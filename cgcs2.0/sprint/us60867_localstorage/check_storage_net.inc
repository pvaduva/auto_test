
;;;
Check the storage disks/files for the VM booted:

Required inputs:
    vmid=<uuid>         the uuid of the VM instance
    volume=<true|false> boot from volume or not

Optional inputs:

;;;

$volume=false

;get the hostname
>hostname
+$host=\s*(.*)\s*

;check if there is files for the VM:$vmid
? $volume == true ? [
    ;check if the volume exists on controller
    >sudo lvs 
    <.* 
    >>$host_passwd
    >sudo lvs 
    +$lvs=\s*(volume\-$vlmid)
    ? $lvs == __NO_STRING_CAPTURED__ ? [ 
        ;ERROR: volume is not on the controller for $vlmid? 
        ; The cinder volume is supposed to be hosted on the controller:$hostname
        *FAIL 
    ]   
    ;found volume for $vlmid on controller:$hostname
] :: [ 
    >ls -ld /opt/cgcs/nova/instances/$vmid/disk
    +$notfound=(No such file or directory)
    ? $notfound != __NO_STRING_CAPTURED__ ? [
        ;ERROR: no storage files found on $host:/opt/cgcs/nova/instances/$vmid
        *FAIL
    ]
]

;check if there a file for swap
>ls -ld /opt/cgcs/nova/instances/$vmid/disk.swap
+$notfound=(No such file or directory)
? $notfound != __NO_STRING_CAPTURED__ ? [
    ;ERROR: no storage file for swap disk found on $host:/opt/cgcs/nova/instances/$vmid
    *FAIL
]

;check if there a file for ephemera disk
>ls -ld /opt/cgcs/nova/instances/$vmid/disk.local
+$notfound=(No such file or directory)
? $notfound != __NO_STRING_CAPTURED__ ? [
    ;ERROR: no storage file for ephemera disk found on $host:/opt/cgcs/nova/instances/$vmid
    *FAIL
]

;all storage disks for VM:$vmid are correctly allocated

