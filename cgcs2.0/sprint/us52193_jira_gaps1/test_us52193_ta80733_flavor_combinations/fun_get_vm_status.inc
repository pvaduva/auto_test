##!/usr/bin/env expect-lite

; get the status of service/vm
; INPUT: VMUUID uuid of the service/vm


; get the status of a server
# for test only
$VMUUID=6ba5350b-aa2e-47a0-84ae-d59e1da4175a
>nova show $VMUUID
+$HOSTNAME=\|\s*[A-Za-z0-9-]+:hypervisor_hostname\s*\|\s*([A-Za-z0-9_-]+)\s*\|
+$POWER=\|\s*[A-Za-z0-9-]+:power_state\s*\|\s*([A-Za-z0-9_-]+)\s*\|
+$TASK_STATE=\|\s*[A-Za-z0-9-]+:task_state\s*\|\s*([A-Za-z0-9_-]+)\s*\|
+$TASK=\|\s*[A-Za-z0-9-]+:task_state\s*\|\s*([A-Za-z0-9_-]+)\s*\|
+$VM_STATE=\|\s*[A-Za-z0-9-]+:vm_state\s*\|\s*([A-Za-z0-9_-]+)\s*\|
+$STATUS=\|\s*status\s*\|\s*([A-Za-z0-9_-]+)\s*\|


;;;
+--------------------------------------+------------------------------------------------------------------------------------------------------------------------------+
| Property                             | Value                                                                                                                        |
+--------------------------------------+------------------------------------------------------------------------------------------------------------------------------+
| OS-DCF:diskConfig                    | MANUAL                                                                                                                       |
| OS-EXT-AZ:availability_zone          | nova                                                                                                                         |
| OS-EXT-SRV-ATTR:host                 | compute-0                                                                                                                    |
| OS-EXT-SRV-ATTR:hypervisor_hostname  | compute-0                                                                                                                    |
| OS-EXT-SRV-ATTR:instance_name        | instance-00000039                                                                                                            |
| OS-EXT-STS:power_state               | 1                                                                                                                            |
| OS-EXT-STS:task_state                | powering-off                                                                                                                 |
| OS-EXT-STS:vm_state                  | active                                                                                                                       |
| OS-SRV-USG:launched_at               | 2015-01-27T15:47:31.567139                                                                                                   |
| OS-SRV-USG:terminated_at             | -                                                                                                                            |
| accessIPv4                           |                                                                                                                              |
| accessIPv6                           |                                                                                                                              |
| config_drive                         |                                                                                                                              |
| created                              | 2015-01-27T15:47:24Z                                                                                                         |
| extended                             | {"cpuset": 4, "numanode": 0, "siblings_cpuset": null}                                                                        |
| flavor                               | flv_ta80733_1_mincpu_minmem (7fbe3461-8cd5-4884-97c3-55252fa7ef3c)                                                           |
| hostId                               | 36d531434577d130958123df4d45f6f75e0282ed8b7e226968fa413b                                                                     |
| id                                   | 6ba5350b-aa2e-47a0-84ae-d59e1da4175a                                                                                         |
| image                                | wrl5 (6c4f7f5e-adde-4dd2-8f95-53106f92edd1)                                                                                  |
| internal-net0 network                | 10.10.0.51, 10.10.1.51                                                                                                       |
| key_name                             | controller-0                                                                                                                 |
| metadata                             | {}                                                                                                                           |
| name                                 | ta80733_vm_1                                                                                                                 |
| nics                                 | {"nic1": {"vif_model": "avp", "port_id": "95afe2c2-4e94-47ec-a5e5-376ff9cc1dcd", "network": "public-net0", "mtu": 1500}}     |
|                                      | {"nic2": {"vif_model": "e1000", "port_id": "86b03bde-5947-4672-af12-06752e151d9c", "network": "internal-net0", "mtu": 1500}} |
| os-extended-volumes:volumes_attached | []                                                                                                                           |
| pinned                               | True                                                                                                                         |
| progress                             | 0                                                                                                                            |
| public-net0 network                  | 192.168.101.53                                                                                                               |
| server_group                         |                                                                                                                              |
| status                               | ACTIVE                                                                                                                       |
| tenant_id                            | 7e562e72f695499c84a93d04bcd7f752                                                                                             |
| updated                              | 2015-01-27T18:19:48Z                                                                                                         |
| user_id                              | 595a3d9d3bd64b56b7d5dd0b94695856                                                                                             |
| vcpus (min/cur/max)                  | [1, 1, 1]                                                                                                                    |
+--------------------------------------+------------------------------------------------------------------------------------------------------------------------------+
;;;


