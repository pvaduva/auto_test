
;;;
Create a flavor and handling errors.

Required inputs:

  name=<name>               Name of the new flavor
  ram=<size_ram>            Memory size in MB
  disk=<size_disk>          Disk size in GB
  vcpus=<vcpus>             Number of vcpus

Optional inputs:
  id=<id>                   Unique ID (integer or UUID) for the new flavor. If
                            specifying 'auto', a UUID will be generated as id
  ephemeral_opt=<ephemeral> empheral disk size in GB, 0 indicating no epheral disk
  swap_opt=<swap>           swap disk size in GB, 0 indicating no swap disk
;;;

$id=auto
$ephemeral_opt=
>echo $ephemeral
+$ephemeral=\n([0-9]+)
? $ephemeral != __NO_STRING_CAPTURED__ ? [
    ? $ephemeral != 0 ? [
        $ephemeral_opt= --ephemeral $ephemeral 
    ]
]

$swap_opt=
>echo $swap
+$swap=\n([0-9]+)
? $swap != __NO_STRING_CAPTURED__ ? [
    ? $swap != 0 ? [
        $swap_opt= --swap $swap 
    ]
]

>nova flavor-create $name $id $ram $disk $vcpus $swap_opt $ephemeral_opt
+$ret=\n(ERROR)

? $ret != __NO_STRING_CAPTURED__ ? [
    ;yellow flavor with name/id of $name/$id is already exists
    ;try to delete the existing flavor

    ?$id != auto ? [

        ;delete flavor by id: $id 
        >nova flavor-delete $id
    ]::[

        ;delete flavor by name: $name 
        >nova flavor-delete $name
    ]

    ;then try to create again after 3 seconds
    !sleep 3
    >nova flavor-create $name $id $ram $disk $vcpus $swap_opt $ephemeral_opt
    +$ret=\n(ERROR)

    ? $ret != __NO_STRING_CAPTURED__ ? [
        ;red ERROR, cannot create flavor even after removing existing flavor with same
        ;   name/id
        ;red fail the whole test
        *FAIL
    ]
]
;finished to create flavor $name

