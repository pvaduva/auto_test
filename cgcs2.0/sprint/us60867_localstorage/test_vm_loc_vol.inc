
;;;
Lanuch a VM instance with:
    1 local-storage flavour (aggregate_instance_extra_specs:localstorage=true)
    2 boot from volume

and verify how its disks backed in the expecting way

Required inputs:
    vmname=<vmname>         the name of the VM instance

Optional inputs:
    flavor=<flavor>         flavor to use
    locstr=<true|false>     using local-storage or not (remote-storage)
    volume=<true|false>     boot from volume or not (from image)
    vlmname=<name>          name of the volume
    delvm=<true|false>      delete the VM instance after testing or not

;;;

$flavor=flv_local_storage-loc-es
$vmname=vm05loc_es_vlm
$delvm=false

;using flavor $flavor

;default values, will be overwritten by input arguments

~test_vm.inc flavor=$flavor locstr=true volume=true vlmname=vlm02_loc_es_vol vmname=$vmname delvm=$delvm

;end of test_vm_loc_vol.inc

