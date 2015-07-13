
;;;
Lanuch a VM instance with:
    1 locastorage flavour (aggregate_instance_extra_specs:localstorage=true)
    2 boot from image

and verify how its disks backed in the expecting way

Required inputs:
    vmname=<vmname>         the name of the VM instance

Optional inputs:
    tenant_user=<user>     user name for tenant1, 'tenant1' by default
    tenant_passwd=<passwd> password for tenanat1, 'tenant1' by default
    flavor=<flavor>         flavor to use

;;;

$flavor=flv_local_storage-loc-es
$vmname=vm04loc_es

;using flavor $flavor

;default values, will be overwritten by input arguments
$tenant_user=tenant1
$tenant_passwd=tenant1

;before launch any instances, check the remote-storage location
>ls -l /opt/cgcs/nova/instances

;change user to tenant:$tenant_user
>source /home/wrsroot/openrc.$tenant_user

~test_vm.inc flavor=$flavor volume=false locstr=true vmname=$vmname

;end of test_vm_net_img.inc

