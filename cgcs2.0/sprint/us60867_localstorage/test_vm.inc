
;;;
Lanuch a VM instance with:
    1 specified flavor
    2 boot from image or volume

and verify how its disks backed in the expecting way

Required inputs:
    flavor=<flavor>         specified flavor
    locstr=<true|false>     whether the VM uses 'local-storage' feature
    volume=<true|false>     whether boot from image or volume
    vlmid=<volume-uuid>     ID of the volume to boot from
    imgid=<image-uuid>      ID of the image to boot from
    vlmname=<volume-name>   name of the volume to boot from
    vmname=<vmname>         the name of the VM instance
    delvm=<true|false>      delete the VM after testing with it, 'true' by default

Optional inputs:
    tenant_user=<user>      user name for tenant1, 'tenant1' by default
    tenant2_user=<user>     user name for tenant2, 'tenant2' by default

;;;

$flavor=flv_local_storage-net-es
$volume=true
$locstr=false

;get date to use as core of names
>date +%Y%m%d_%H%M%S
+$bsnm=([0-9]{8}_[0-9]{6})
? $bsnm == __NO_STRING_CAPTURED__ ? [
    >echo $RANDOM
    +$bsnm=1111_([0-9]+)
]
$vlmname=vlm_$bsnm
$vmname=vm_$bsnm
$delvm=true

;using flavor $flavor

;default values, will be overwritten by input arguments
$tenant_user=tenant1
$tenant2_user=tenant2

;before launch any instances, check the remote-storage location
>ls -l /opt/cgcs/nova/instances

;change user to tenant:$tenant_user
>source /home/wrsroot/openrc.$tenant_user

;get the keypair of tenant:$tenant_user
~get_keypair.inc
;ok, keypair=$keypair

;get the network IDs
~get_net_ids.inc
;ok, net1=$net1
;    net2=$net2
;    net3=$net3

;get the image id
~get_img.inc
;ok, image=$cgcs_img_id

;to boot from VOLUME or IMAGE ?
? $volume == true ? [
    ;boot from volume:$vlmname
    ;get the volume id
    ~get_vol.inc vlmname=$vlmname
    ;uuid=$vlmid for volume:$vlmname
] :: [
    ;will boot from image
]

;user data option
$userdata=--user-data /home/wrsroot/userdata/$tenant_user-avp1_userdata.txt

;launch VM:$vmname and get its uuid
@300
? $volume != true ? [
    ;boot from image:$cgcs_img_id
    >nova boot --poll --key_name=$keypair --flavor=$flavor $net1 $net2 $net3 $userdata --image $cgcs_img_id $vmname
    +$vmid=\|\s* id \s*\|\s* ([0-9a-f-]{32,36}) \s*\|
] :: [
    ;boot from volume:$vlmid
    >nova boot --poll --key_name=$keypair --flavor=$flavor $net1 $net2 $net3 $userdata --block_device_mapping vda=$vlmid:::0 $vmname
    +$vmid=\|\s* id \s*\|\s* ([0-9a-f-]{32,36}) \s*\|
]
? $vmid == __NO_STRING_CAPTURED__ ? [
    ;red ERROR: no instance uuid found for VM:$vmname, probably failed to launch VM
    >nova list
    *FAIL
] :: [
    ;uuid:$vmid of VM:$vmname
]

;wait the VM ready, maximum time 180 seconds
~wait_vm_status.inc vmid=$vmid timeout=180

;check storage disks for VM:$vmname, uuid:$vmid
? $locstr == false ? [
    ;check the storage disks allocated remotely 
    ~check_storage_net.inc volume=$volume vmid=$vmid
] :: [
    ;check the storage disks allocated locally 
    ~check_storage_loc.inc volume=$volume vmid=$vmid
]

? $delvm == true ? [
    ;delete VM instance
    >nova delete $vmid
    !sleep 15
]

;show the VMs list
>nova list

@10
>source /etc/nova/openrc

;end of test_vm.inc

