##!/usr/bin/env expect-lite

; options for creating a flavor
; TC1 create a flavor with 1 cpu, 128M memory? 
#$FLVNM1=flv_ta80733_1_mincpu_minmem
#$FLVID1=auto
#$FLVRAM1=128
#$FLVDISK1=0
#$FLVCPU1=1

>echo "$FLVNM $FLVID $FLVRAM $FLVDISK $FLVCPU"

#>nova flavor-create $FLVNM $FLVID $FLVRAM $FLVDISK $FLVCPU | cut -d\| -f3 | grep $FLVNM | awk '{print $1}' | tr -d " "  
#<$FLVNM
#>nova flavor-create $FLVNM $FLVID $FLVRAM $FLVDISK $FLVCPU
#+$FLVUUID=\|\s*([a-f0-9-]{32,36})\s*\|\s*$FLVNM\s*\|
~fun_create_flavor.inc FLVNM=$FLVNM FLVRAM=$FLVRAM FLVDISK=$FLVDISK FLVCPU=$FLVCPU

#; get extra specs
#~fun_get_extra_specs.inc FLVID=$FLVUUID
#>shuf -i 2000-66000 -n 1
#+$RD=\n([0-9]+)
#?if $RD > 4300 ? [
#    $DDTD_CPUS=True
#]::[
#    $DDTD_CPUS=False
#]

#>shuf -i 2000-66000 -n 1
#+$RD=\n([0-9]+)
#?if $RD > 4300 ? [
#    $GST_HREARTBEAT=True
#]::[
#    $GST_HREARTBEAT=False
#]

; set the extra specs to flavor $FLVUUID
#>nova flavor-key $FLVUUID set hw:cpu_policy=dedicated sw:wrs:guest:heartbeat=$GST_HREARTBEAT
#>nova flavor-show $FLVUUID

; create service instance
@6
#$VMNM=ta80733_vm_1
~fun_del_vm.inc $VMNM
>nova boot --key_name=$KEYPAIR --flavor=$FLVNM --nic net-id=$PUB_NET,vif-model=avp --nic net-id=$INT_NET,vif-model=e1000 --image=$IMAGE $VMNM
+$UUID=\|\s*id\s*\|\s*([a-f0-9-]{32,36})\s*\|
@3

; perform operations on the instance
~fun_operation_instace.inc VMUUID=$UUID VMNM=$VMNM

; delete the vm $UUID
>nova delete $UUID

; delete the falvor $FLVUUID
>nova flavor-delete $FLVUUID

#; again?
#>nova flavor-delete $FLVUUID

; done

