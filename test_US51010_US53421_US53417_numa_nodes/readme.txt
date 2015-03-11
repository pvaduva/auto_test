List of TCs:
TC1:  VM with hw:cpu_policy=dedicated flavor schedules only on host aggregate where dedicated_resources dedicated=false
TC2:  VM with hw:cpu_policy=shared schedules only on host aggregate where dedicated_resources dedicated=true
TC3:  Evacuated VM with hw:cpu_policy=shared reschedules only on host aggregate where dedicated_resources dedicated=false
TC4:  Evacuated VM with hw:cpu_policy=dedicated reschedule only on host aggregate where dedicated_resources dedicated=true
TC5:  Migrate (live) VM with hw:cpu_policy=dedicated  (migrates only to host meeting its flavor criteria)
TC6:  Migrate (live) VM with hw:cpu_policy=shared  (migrates only to host meeting its flavor criteria)
TC5:  Migrate (cold) VM with hw:cpu_policy=dedicated  (migrates only to host meeting its flavor criteria)
TC6:  Migrate (cold VM with hw:cpu_policy=shared  (migrates only to host meeting its flavor criteria)
TC7:  Resize VM with hw:cpu_policy=shared
TC8:  Resize VM with hw:cpu_policy=dedicated
TC9:  Pause/Resume VM with hw:cpu_policy=dedicated 
TC9:  Pause/Resume VM with hw:cpu_policy=shared
TC10: Instantiate a VM with a flavor of >64 vCPUs hw:cpu_policy=dedicated
TC10: Instantiate a VM with a flavor of >64 vCPUs hw:cpu_policy=shared
TC10: Resize a VM with flavor with >64 vCPUs hw:cpu_policy=shared
TC10: Resize a VM with flavor with >64 vCPUs hw:cpu_policy=dedicated
TC10: Migrate a VM with flavor with >64 vCPUs hw:cpu_policy=dedicated
TC10: Migrate a VM with flavor with >64 vCPUs hw:cpu_policy=shared
TC10: Evacuate a VM with a flavor with >64 vCPUs hw:cpu_policy=dedicated
TC10: Evacuate a VM with a flavor with >64 vCPUs hw:cpu_policy=shared 

TCs execution based on these prior steps:

Tue Mar 10 14:41:53 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-create dedicated.medium auto 2048 3 2
+--------------------------------------+------------------+-----------+------+-----------+------+-------+-------------+-----------+
| ID                                   | Name             | Memory_MB | Disk | Ephemeral | Swap | VCPUs | RXTX_Factor | Is_Public |
+--------------------------------------+------------------+-----------+------+-----------+------+-------+-------------+-----------+
| 7632b4a1-b98f-44f0-aa27-349124f3cb92 | dedicated.medium | 2048      | 3    | 0         |      | 2     | 1.0         | True      |
+--------------------------------------+------------------+-----------+------+-----------+------+-------+-------------+-----------+
Tue Mar 10 14:48:22 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-key dedicated.medium set hw:cpu_policy=dedicated
Tue Mar 10 14:48:32 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-key dedicated.medium set hw:mem_page_size=large
Tue Mar 10 14:48:34 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-key dedicated.medium set aggregate_instance_extra_specs:dedicated=true
Tue Mar 10 14:48:36 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-create shared.medium auto 2048 3 2
+--------------------------------------+---------------+-----------+------+-----------+------+-------+-------------+-----------+
| ID                                   | Name          | Memory_MB | Disk | Ephemeral | Swap | VCPUs | RXTX_Factor | Is_Public |
+--------------------------------------+---------------+-----------+------+-----------+------+-------+-------------+-----------+
| e7edf100-23f9-4302-96d6-538c80fa9baf | shared.medium | 2048      | 3    | 0         |      | 2     | 1.0         | True      |
+--------------------------------------+---------------+-----------+------+-----------+------+-------+-------------+-----------+
Tue Mar 10 14:48:43 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-key shared.medium set hw:cpu_policy=shared
Tue Mar 10 14:48:49 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-key shared.medium set hw:mem_page_size=any
Tue Mar 10 14:48:51 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova flavor-key shared.medium set aggregate_instance_extra_specs:dedicated=false
Tue Mar 10 14:48:53 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova aggregate-create dedicated_resources
+----+---------------------+-------------------+-------+----------+
| Id | Name                | Availability Zone | Hosts | Metadata |
+----+---------------------+-------------------+-------+----------+
| 5  | dedicated_resources | -                 |       |          |
+----+---------------------+-------------------+-------+----------+
Tue Mar 10 14:54:19 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova aggregate-set-metadata dedicated_resources dedicated=true
Metadata has been successfully updated for aggregate 5.
+----+---------------------+-------------------+-------+------------------+
| Id | Name                | Availability Zone | Hosts | Metadata         |
+----+---------------------+-------------------+-------+------------------+
| 5  | dedicated_resources | -                 |       | 'dedicated=true' |
+----+---------------------+-------------------+-------+------------------+
Tue Mar 10 14:54:24 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova aggregate-add-host dedicated_resources compute-0
Host compute-0 has been successfully added for aggregate 5 
+----+---------------------+-------------------+-------------+------------------+
| Id | Name                | Availability Zone | Hosts       | Metadata         |
+----+---------------------+-------------------+-------------+------------------+
| 5  | dedicated_resources | -                 | 'compute-0' | 'dedicated=true' |
+----+---------------------+-------------------+-------------+------------------+
Tue Mar 10 14:54:33 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova aggregate-create shared_resources
+----+------------------+-------------------+-------+----------+
| Id | Name             | Availability Zone | Hosts | Metadata |
+----+------------------+-------------------+-------+----------+
| 6  | shared_resources | -                 |       |          |
+----+------------------+-------------------+-------+----------+
Tue Mar 10 14:54:38 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ nova aggregate-set-metadata shared_resources dedicated=false
Metadata has been successfully updated for aggregate 6.
+----+------------------+-------------------+-------+-------------------+
| Id | Name             | Availability Zone | Hosts | Metadata          |
+----+------------------+-------------------+-------+-------------------+
| 6  | shared_resources | -                 |       | 'dedicated=false' |
+----+------------------+-------------------+-------+-------------------+
[wrsroot@controller-0 ~(keystone_admin)]$ nova aggregate-add-host shared_resources compute-1
Host compute-1 has been successfully added for aggregate 6 
+----+------------------+-------------------+-------------+-------------------+
| Id | Name             | Availability Zone | Hosts       | Metadata          |
+----+------------------+-------------------+-------------+-------------------+
| 6  | shared_resources | -                 | 'compute-1' | 'dedicated=false' |
+----+------------------+-------------------+-------------+-------------------+

Tue Mar 10 14:57:14 UTC 2015
[wrsroot@controller-0 ~(keystone_admin)]$ source ./openrc.tenant1
Tue Mar 10 14:57:27 UTC 2015
[wrsroot@controller-0 ~(keystone_tenant1)]$ cinder create --image-id c796fc90-2eef-4c0a-8c7b-24ae86e3f4f5 3
+---------------------+--------------------------------------+
|       Property      |                Value                 |
+---------------------+--------------------------------------+
|     attachments     |                  []                  |
|  availability_zone  |                 nova                 |
|       bootable      |                false                 |
|      created_at     |      2015-03-10T14:57:31.839584      |
| display_description |                 None                 |
|     display_name    |                 None                 |
|      encrypted      |                False                 |
|          id         | d02d2556-1339-4ea2-9394-1d17066be69d |
|       image_id      | c796fc90-2eef-4c0a-8c7b-24ae86e3f4f5 |
|       metadata      |                  {}                  |
|         size        |                  3                   |
|     snapshot_id     |                 None                 |
|     source_volid    |                 None                 |
|        status       |               creating               |
|     volume_type     |                 None                 |
+---------------------+--------------------------------------+
Tue Mar 10 14:57:32 UTC 2015
[wrsroot@controller-0 ~(keystone_tenant1)]$ cinder create --image-id c796fc90-2eef-4c0a-8c7b-24ae86e3f4f5 3
+---------------------+--------------------------------------+
|       Property      |                Value                 |
+---------------------+--------------------------------------+
|     attachments     |                  []                  |
|  availability_zone  |                 nova                 |
|       bootable      |                false                 |
|      created_at     |      2015-03-10T14:57:34.568566      |
| display_description |                 None                 |
|     display_name    |                 None                 |
|      encrypted      |                False                 |
|          id         | 82e0b853-b9d9-44f5-85f8-1449fdaf4e28 |
|       image_id      | c796fc90-2eef-4c0a-8c7b-24ae86e3f4f5 |
|       metadata      |                  {}                  |
|         size        |                  3                   |
|     snapshot_id     |                 None                 |
|     source_volid    |                 None                 |
|        status       |               creating               |
|     volume_type     |                 None                 |
+---------------------+--------------------------------------+
Tue Mar 10 15:00:21 UTC 2015
[wrsroot@controller-0 ~(keystone_tenant1)]$ nova boot --flavor=shared.medium --nic net-id=6ea8e663-851a-4be7-8529-950990300689,vif-model=avp --nic net-id=8579f060-7468-4874-a458-9db0dcc771b0,vif-model=avp --block_device_mapping vda=82e0b853-b9d9-44f5-85f8-1449fdaf4e28:::0 shared 
+--------------------------------------+------------------------------------------------------+
| Property                             | Value                                                |
+--------------------------------------+------------------------------------------------------+
| OS-DCF:diskConfig                    | MANUAL                                               |
| OS-EXT-AZ:availability_zone          | nova                                                 |
| OS-EXT-STS:power_state               | 0                                                    |
| OS-EXT-STS:task_state                | scheduling                                           |
| OS-EXT-STS:vm_state                  | building                                             |
| OS-SRV-USG:launched_at               | -                                                    |
| OS-SRV-USG:terminated_at             | -                                                    |
| accessIPv4                           |                                                      |
| accessIPv6                           |                                                      |
| adminPass                            | xM9dv3Yh9dwy                                         |
| config_drive                         |                                                      |
| created                              | 2015-03-10T15:00:59Z                                 |
| flavor                               | shared.medium (e7edf100-23f9-4302-96d6-538c80fa9baf) |
| hostId                               |                                                      |
| id                                   | 7a58c532-05b6-4a6e-a515-b02356e5530f                 |
| image                                | Attempt to boot from volume - no image supplied      |
| key_name                             | -                                                    |
| metadata                             | {}                                                   |
| name                                 | shared                                               |
| nics                                 |                                                      |
| os-extended-volumes:volumes_attached | [{"id": "82e0b853-b9d9-44f5-85f8-1449fdaf4e28"}]     |
| progress                             | 0                                                    |
| security_groups                      | default                                              |
| server_group                         |                                                      |
| status                               | BUILD                                                |
| tenant_id                            | 8b727a94cb82487b890edc045ddbd845                     |
| topology                             | node:0,  2048MB, pgsize:4K, vcpus:0,1, unallocated   |
| updated                              | 2015-03-10T15:01:00Z                                 |
| user_id                              | 5c6f05f6a58947888116660ef4bb5224                     |
| vcpus (min/cur/max)                  | [2, 2, 2]                                            |
+--------------------------------------+------------------------------------------------------+
Tue Mar 10 15:01:00 UTC 2015
[wrsroot@controller-0 ~(keystone_tenant1)]$ nova boot --flavor=dedicated.medium --nic net-id=6ea8e663-851a-4be7-8529-950990300689,vif-model=avp --nic net-id=8579f060-7468-4874-a458-9db0dcc771b0,vif-model=avp --block_device_mapping vda=d02d2556-1339-4ea2-9394-1d17066be69d:::0 dedicated
+--------------------------------------+---------------------------------------------------------+
| Property                             | Value                                                   |
+--------------------------------------+---------------------------------------------------------+
| OS-DCF:diskConfig                    | MANUAL                                                  |
| OS-EXT-AZ:availability_zone          | nova                                                    |
| OS-EXT-STS:power_state               | 0                                                       |
| OS-EXT-STS:task_state                | scheduling                                              |
| OS-EXT-STS:vm_state                  | building                                                |
| OS-SRV-USG:launched_at               | -                                                       |
| OS-SRV-USG:terminated_at             | -                                                       |
| accessIPv4                           |                                                         |
| accessIPv6                           |                                                         |
| adminPass                            | pw5QseSGj3Gu                                            |
| config_drive                         |                                                         |
| created                              | 2015-03-10T15:02:31Z                                    |
| flavor                               | dedicated.medium (7632b4a1-b98f-44f0-aa27-349124f3cb92) |
| hostId                               |                                                         |
| id                                   | 3d7e1110-505e-4b16-ba07-cc4966a025c4                    |
| image                                | Attempt to boot from volume - no image supplied         |
| key_name                             | -                                                       |
| metadata                             | {}                                                      |
| name                                 | dedicated                                               |
| nics                                 |                                                         |
| os-extended-volumes:volumes_attached | [{"id": "d02d2556-1339-4ea2-9394-1d17066be69d"}]        |
| progress                             | 0                                                       |
| security_groups                      | default                                                 |
| server_group                         |                                                         |
| status                               | BUILD                                                   |
| tenant_id                            | 8b727a94cb82487b890edc045ddbd845                        |
| topology                             | node:0,  2048MB, pgsize:4K, vcpus:0,1, unallocated      |
| updated                              | 2015-03-10T15:02:32Z                                    |
| user_id                              | 5c6f05f6a58947888116660ef4bb5224                        |
| vcpus (min/cur/max)                  | [2, 2, 2]                                               |
+--------------------------------------+---------------------------------------------------------+
