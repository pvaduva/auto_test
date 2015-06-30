
;;;
Check the storage disks/files for the VM booted:

Required inputs:
    vmid=<uuid>         the uuid of the VM instance
    volume=<true|false> boot from volume or not

Optional inputs:
    vmuser=<vmuser>     user name to ssh onto VM, 'root' by default
    vmpasswd=<vmpasswd> password to ssh onto VM, 'root' by default
;;;

$volume=false
$vmuser=wrsroot
$vmpasswd=li69nux

;change back to admin
@30
>source /etc/nova/openrc

? $volume == true ? [
    >sudo lvs 
    >>$host_passwd
    >sudo lvs 
    +$lvs=\s*(volume\-$vlmid)
    ? $lvs == __NO_STRING_CAPTURED__ ? [ 
        ;red error: volume is not on the controller for $vlmid? volume=$volume
        *FAIL 
    ]   
    ;ok, found volume for $vlmid on controller:$hostname
]

!sleep 3
;get the hosting compute node of the VM:$vmid
>nova show $vmid

+$hostcpt=.*OS-EXT-SRV-ATTR:host \s*\|\s* ([0-9a-z-]+) \s*\|

? $hostcpt == __NO_STRING_CAPTURED__ ? [
    ;red failed to find the hosting compute of VM:$vmid
    *FAIL
]

;hosting compute is $hostcpt
>ssh -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $vmuser@$hostcpt
<assword|SYSTEM:|WARNING:
>>$vmpasswd

;check lvms on the hosting compute
>sudo lvs
>>$vmpasswd
>sudo lvs
+$vlm_root=\s*($vmid)_disk\s*
+$vlm_swap=\s*($vmid)_disk.swap\s*
+$vlm_ephemeral=\s*($vmid)_disk.local\s*

? $vlm_root == __NO_STRING_CAPTURED__ ? [
    ? $volume == false ? [
        ;red error: cannot find the backend for root disk
        *FAIL
    ] :: [
        ;ok, backed by cinder vlm
    ]
]
;found the backend for root disk: $vlm_root

? $vlm_swap == __NO_STRING_CAPTURED__ ? [
    ;red error: cannot find the backend for swap disk
    *FAIL
]
;find the backend for swap disk: $vlm_swap

? $vlm_ephemeral == __NO_STRING_CAPTURED__ ? [
    ;red error: cannot find the backend for ephemeral disk
    *FAIL
]
;found the backend for ephemeral disk: $vlm_ephemeral

;all storage disks for VM:$vmid are correctly located

@20
;logout from the compute:$compute
>exit
>^C
> date | true
<.*

>source /etc/nova/openrc
<.*

