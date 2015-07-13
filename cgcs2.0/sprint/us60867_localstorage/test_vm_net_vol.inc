
;;;
Lanuch a VM instance with:
    1 network flavour (aggregate_instance_extra_specs:localstorage=false)
    2 boot from image

and verify how its disks backed in the expecting way

Required inputs:
    vmname=<vmname>         the name of the VM instance

Optional inputs:
    host_user=<user>        'wrsroot' by default
    host_passwd=<passwd>    'li69nux' by default
    tenant_user=<user>     user name for tenant1, 'tenant1' by default
    tenant_passwd=<passwd> password for tenanat1, 'tenant1' by default
    tenant2_user=<user>     user name for tenant2, 'tenant2' by default
    tenant2_passwd=<passwd> password for tenanat2, 'tenant2' by default
    flavor=<flavor>         flavor to use

;;;

$flavor=flv_local_storage-net-es
$vmname=vm01net_es

;using flavor $flavor

;default values, will be overwritten by input arguments
$host_user=wrsroot
$host_passwd=li69nux
$tenant_user=tenant1
$tenant_passwd=tenant1
$tenant2_user=tenant2
$tenant2_passwd=tenant2

~test_vm.inc flavor=$flavor locstr=false volume=true vlmname=vlm01_net_es_vol vmname=vm03_netesvol

;end of test_vm_net_vol.inc

