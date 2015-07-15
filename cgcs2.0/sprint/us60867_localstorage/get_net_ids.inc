
;;;
Get the IDs of networks: management, user-net0 and internal

Required inputs:
    vmname=<vmname>         the name of the VM instance

Optional inputs:
    host_user=<user>        'wrsroot' by default
    host_passwd=<passwd>    'li69nux' by default
    flavor=<flavor>         flavor to use

;;;

$tenant=tenant1
;change user to tenant:$tenant
>source /home/wrsroot/openrc.$tenant

;get the network IDs
>neutron net-list
+$mgmt_netid=\s* ([0-9a-f-]{32,36}) \s*\|\s* $tenant-mgmt-net \s*\|
+$net0_netid=\s* ([0-9a-f-]{32,36}) \s*\|\s* $tenant-net0 \s*\|
+$int0_netid=\s* ([0-9a-f-]{32,36}) \s*\|\s* internal0-net0 \s*\|

? $mgmt_netid == __NO_STRING_CAPTURED__ ? [
    ;WARNING: failed to get uuid of $tenant-mgmt for tenant:$tenant
    $net1=
] :: [
    ;uuid of $tenant-mgmt-net is $mgmt_netid
    $net1=--nic net-id=$mgmt_netid,vif-model=virtio
]

? $net0_netid == __NO_STRING_CAPTURED__ ? [
    ;WARNING: failed to get uuid of $tenant-net0 for tenant:$tenant
    $net2=
] :: [
    ;uuid of $tenant-net0 is $net0_netid
    $net2=--nic net-id=$net0_netid,vif-model=avp
]

? $int0_netid == __NO_STRING_CAPTURED__ ? [
    ;WARNING: failed to get uuid of $tenant-mgmt for tenant:$tenant
    $net3=
] :: [
    ;uuid of internal0-net0 is $int0_netid
    $net3=--nic net-id=$int0_netid,vif-model=avp
]

;net1:$net1, net2:$net2, net3:$net3

