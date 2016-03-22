##!/usr/bin/env expect-lite

; options for creating a flavor
; TC1 create a flavor with 1 cpu, 128M memory? 
#$FLVNM1=flv_ta80733_1_mincpu_minmem
#$FLVID1=auto
#$FLVRAM1=128
#$FLVDISK1=0
#$FLVCPU1=1
#$ESPECTYPE=0-1

>echo "$FLVNM $FLVID $FLVRAM $FLVDISK $FLVCPU"

#>nova flavor-create $FLVNM $FLVID $FLVRAM $FLVDISK $FLVCPU | cut -d\| -f3 | grep $FLVNM | awk '{print $1}' | tr -d " "  
#<$FLVNM
#>nova flavor-create $FLVNM $FLVID $FLVRAM $FLVDISK $FLVCPU
#+$FLVUUID=\|\s*([a-f0-9-]{32,36})\s*\|\s*$FLVNM\s*\|
~fun_create_flavor.inc FLVNM=$FLVNM FLVRAM=$FLVRAM FLVDISK=$FLVDISK FLVCPU=$FLVCPU

; set the extra specs to flavor $FLVUUID
?if $ESPECTYPE == 0 ? [
    >nova flavor-key $FLVUUID set hw:cpu_policy=dedicated sw:wrs:guest:heartbeat=True hw:numa_node.0=0 hw:wrs:min_vcpus=1
]::[
    >nova flavor-key $FLVUUID set hw:cpu_policy=dedicated sw:wrs:guest:heartbeat=True hw:wrs:shared_vcpu=0 hw:wrs:min_vcpus=1
]
>nova flavor-show $FLVUUID

; create service instance
~fun_del_vm.inc $VMNM
>nova boot --key_name=$KEYPAIR --flavor=$FLVNM --nic net-id=$PUB_NET,vif-model=avp --nic net-id=$INT_NET,vif-model=e1000 --image=$IMAGE $VMNM
+$UUID=\|\s*id\s*\|\s*([a-f0-9-]{32,36})\s*\|

; perform operations on the instance
~fun_operation_instace.inc VMUUID=$UUID VMNM=$VMNM

; delete the vm $UUID
>nova delete $UUID

; delete the falvor $FLVUUID
>nova flavor-delete $FLVUUID

; again?
#>nova flavor-delete $FLVUUID

; done

