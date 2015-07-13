
;;;
Convert the compute node to 'local-storage' and check the expected results.

Required input:
    <compute>       the name of the compute-node
    <host_user>     the user name to login to the compute-node
    <host_passwd>   the password for the user on the compute-node
Assumption:
    the compute node is already in 'unlocked       | enabled     | available' status
;;;

$compute=compute-1
$host_user=wrsroot
$host_passwd=li69nux

;check if lvg_id=$lvg_id, pv_id=$pv_id
>echo lvg_id=$lvg_id, pv_id=$pv_id

;check if compute:$compute is configured with local-storage

;check if 'nova-local' volume group is existing
;then get its UUID
>system host-lvg-list $compute
<.*
>system host-lvg-list $compute  | awk '{ if ($4 == "nova-local" && $6 == "provisioned") print $2}'
+$lvg_id=\s*([0-9a-f-]{32,36})\s*
? $lvg_id == __NO_STRING_CAPTURED__ ? [
    ;ERROR found: lvg 'nocal-local' is not ready on $compute
    *FAIL
]

;OK, the lvg exits on $compute, id:$lvg_id

;check if the physical-volume on $compute
>system host-pv-list $compute 
<.*
>system host-pv-list $compute  | awk '{ if ($14 == "nova-local" && $10 == "provisioned") print $2}'
+$pv_id=\s*([0-9a-f-]{32,36})\s*
? $pv_id == __NO_STRING_CAPTURED__ ? [
    ;ERROR: no physical-volume is set on $compute
    ;fail the whole test 
    *FAIL
]

;OK, the pv:$pv_id exists on $compute, id:$pv_id

;check whether $compute is in host-aggregate: local_storage_hosts
>nova aggregate-details local_storage_hosts
+$cmpt=\|\s* \'.*($compute).*\' \s*\|
? $cmpt == __NO_STRING_CAPTURED__ ? [
    ;ERROR: compute:$compute is NOT in local_storage_hosts, expecting it is in
    ;fail the whole test 
    *FAIL
]

;make sure $compute is in NOT in host-aggregate: remote_storage_hosts
>nova aggregate-details remote_storage_hosts
+$cmpt=\|\s* \'.*($compute).*\' \s*\|
? $cmpt != __NO_STRING_CAPTURED__ ? [
    ;ERROR: compute:$compute is in remote_storage_hosts, expecting it is NOT in
    ;fail the whole test 
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
? $vg == __NO_STRING_CAPTURED__ ? [
    ;ERROR: not existing
    ;fail the whole test
    *FAIL
]

;OK, the lvg 'nova-local' exits on compute:$compute

;check if the pvg exists
>sudo pvs
<.*
#<assword|SYSTEM:|WARNING:|
>>$host_passwd

>sudo pvs | awk '{print $2}'
+$vgpv=\s*(nova-local)\s*

? $vgpv == __NO_STRING_CAPTURED__ ? [
    ;ERROR: pv is not existing on compute:$compute
    ;fail the whole test
    *FAIL
]

;OK, the pv exists on compute:$compute

;get the lvs
>sudo lvs
<.*
>>$host_passwd
>sudo lvs

@20
;logout from the compute:$compute
>exit
>^C
>  date | true
<.*

>source /etc/nova/openrc
<.*

