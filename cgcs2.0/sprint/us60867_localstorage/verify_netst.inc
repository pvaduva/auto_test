
;;;
Verify the compute node is configured with 'remote/net storage' mode

Required inputs:
    compute=<compute>       the compute node to covert

Optional inputs:
    host_user=<user>        'wrsroot' by default
    host_passwd=<passwd>    'li69nux' by default

Assumption:
    the compute node is already in 'unlocked       | enabled     | available' status

;;;

;check if compute:$compute is converted ty remote/net stoarge

;default values, will be overwritten by caller's arguments
$compute=compute-1
$host_user=wrsroot
$host_passwd=li69nux

;lvg_id, pv_id should be already set
>echo lvg_id=$lvg_id, pv_id=$pv_id


;check if 'nova-local' volume group is existing
>system host-lvg-list $compute
<.*
>system host-lvg-list $compute  | awk '{ if ($4 == "nova-local") print $2}'
+$lvg_id=\s*([0-9a-f-]{32,36})\s*
? $lvg_id != __NO_STRING_CAPTURED__ ? [
    ;ERROR: lvg 'nocal-local' is on $compute, expecting it's NOT set
    *FAIL
]

;no 'nova-local' lvg set on the compute:$compute

;check if the physical-volume on $compute
>system host-pv-list $compute 
<.*
>system host-pv-list $compute  | awk '{ if ($14 == "nova-local" && $10 == "provisioned") print $2}'
+$pv_id=\s*([0-9a-f-]{32,36})\s*
? $pv_id != __NO_STRING_CAPTURED__ ? [
    ;ERROR: found physical-volume is set on $compute, expecting it's removed
    *FAIL
]

;no pv:$pv_id exists on $compute

;check whether $compute is in host-aggregate: local_storage_hosts
>nova aggregate-details local_storage_hosts
+$cmpt=\|\s* \'.*($compute).*\' \s*\|
? $cmpt != __NO_STRING_CAPTURED__ ? [
    ;ERROR: compute:$compute is in local_storage_hosts, expecting it is NOT in
    *FAIL
]

;make sure $compute is in in host-aggregate: remote_storage_hosts
>nova aggregate-details remote_storage_hosts
+$cmpt=\|\s* \'.*($compute).*\' \s*\|
? $cmpt == __NO_STRING_CAPTURED__ ? [
    ;ERROR: compute:$compute is NOT in remote_storage_hosts, expecting it is in
    *FAIL
]


;ssh onto compute:$compute, check if the lvg and pv exist
@120
>ssh -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $host_user@$compute
<assword|SYSTEM:|WARNING:
>>$host_passwd

@20
>sudo vgs
<.*
#<assword|SYSTEM:|WARNING:
>>$host_passwd
>sudo vgs | awk '{print $1}'
+$vg=\s*(nova-local)\s*

;check if the lvg 'nova-local' exits
? $vg != __NO_STRING_CAPTURED__ ? [
    ;ERROR: lvg 'nova-local' existing, expecting it's removed
    *FAIL
]

>sudo pvs | awk '{print $2}'
+$vgpv=\s*(nova-local)\s*

? $vgpv != __NO_STRING_CAPTURED__ ? [
    ;ERROR: pv is existing on compute:$compute, expecting it's removed already
    *FAIL
]

;OK, the pv exists on compute:$compute

;get the lvs
>sudo lvs
<.*
>>$host_passwd
>sudo lvs

;logout from the compute:$compute
>exit
>^C
>  date | true
<.*

>source /etc/nova/openrc
<.*

;end of verifying net-storage

