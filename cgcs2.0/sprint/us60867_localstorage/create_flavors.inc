
;;;
Create flavors for testing 'local storage'.
Totally 9 flavors created:
3 without definition of key 'aggregate_instance_extra_specs'
3 with value of key 'aggregate_instance_extra_specs' set to 'false'
3 with value of key 'aggregate_instance_extra_specs' set to 'true'

nova flavor-create flv_local_storage    10001 512 1 3
nova flavor-create flv_local_storage-e --ephemeral 1 10002 512 1 3
nova flavor-create flv_local_storage-es --ephemeral 1 --swap 512 10003 512 1 3            

nova flavor-create flv_local_storage.net 20001 512 1 3
nova flavor-create flv_local_storage.net-e --ephemeral 1 20002 512 1 3
nova flavor-create flv_local_storage.net-es --ephemeral 1 --swap 512 20003 512 1 3            

nova flavor-create flv_local_storage.loc 30004 512 1 3
nova flavor-create flv_local_storage.loc-e --ephemeral 1 30005 512 1 3
nova flavor-create flv_local_storage.loc-es --ephemeral 1 --swap 512 30006 512 1 3

nova flavor-key flv_local_storage.net set aggregate_instance_extra_specs=false
nova flavor-key flv_local_storage.net-e set aggregate_instance_extra_specs=false
nova flavor-key flv_local_storage.net-es set aggregate_instance_extra_specs=false

nova flavor-key flv_local_storage.loc set aggregate_instance_extra_specs=true
nova flavor-key flv_local_storage.loc-e set aggregate_instance_extra_specs=true
nova flavor-key flv_local_storage.loc-es set aggregate_instance_extra_specs=true
;;;

$nvcp=1
~create_flavor.inc name=flv_local_storage id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=0 swap=0
~create_flavor.inc name=flv_local_storage-e id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=1 swap=0
~create_flavor.inc name=flv_local_storage-es id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=1 swap=512

~create_flavor.inc name=flv_local_storage-net id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=0 swap=0 
~create_flavor.inc name=flv_local_storage-net-e id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=1 swap=0
~create_flavor.inc name=flv_local_storage-net-es id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=1 swap=512

~create_flavor.inc name=flv_local_storage-loc id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=0 swap=0
~create_flavor.inc name=flv_local_storage-loc-e id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=1 swap=0
~create_flavor.inc name=flv_local_storage-loc-es id=auto ram=512 disk=1 vcpus=$nvcp ephemeral=1 swap=512

>nova flavor-key flv_local_storage-loc set aggregate_instance_extra_specs:localstorage=true

>nova flavor-key flv_local_storage-loc-e set aggregate_instance_extra_specs:localstorage=true

>nova flavor-key flv_local_storage-loc-es set aggregate_instance_extra_specs:localstorage=true

