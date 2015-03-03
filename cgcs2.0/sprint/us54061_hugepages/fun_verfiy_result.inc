
#CPTNAME=$CPTNAME NUMA_ID=$NUMA_ID FREE_TOTAL=$FREE_TOTAL FREE_2M=$FREE_2M USED_2M=$USED_2M FREE_1G=$FREE_1G USED_1G=$USED_1G

>ssh -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no  compute-0
<assword|SYSTEM:|WARNING:
>>$HOST_PASSWD


>sudo virsh freepages --all
<assword|.*
>>$HOST_PASSWD
+$n0_2mpgs=2048KiB:\s*([0-9]+)
+$n0_1gpgs=1048576KiB:\s*([0-9]+)


>sudo virsh freepages --all | tail -n+5
+$n1_2m=2048KiB:\s*([0-9]+)
+$n1_1gpgs=1048576KiB:\s*([0-9]+)

