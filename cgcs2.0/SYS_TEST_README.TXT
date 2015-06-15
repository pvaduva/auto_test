===== test_8001_system_vm_ops.elt
;;;
#
#    system test - VM operations TC8001
#    
As part of the Test Improvements identified in Sprint 4: A recommendation was made to create new System Test 
which would cover 20 existing regression test cases (currently consuming 2h 45m of execution time). The new 
System Test would cover VM operations, including: booting, rebooting, live-migration, cold migration,  
passing cloud init data to VM, pause/resume, stop/resume.

Options
.    IP=<ip address/name of controller>
.    vm_type_list="virtio avp dpdk"
.    vm_name=<Specify when testing a single vm>
.    cloud=no            <default=yes>
.    with_traffic=yes    <default=no>

NOTE: requires NAT access for cloud init test
NOTE: required expect-lite 4.8.1

Assumptions
.    Lab is setup using lab_setup.sh, VMs are lauched with launch_instances.sh
.    Ixia lab file is pre-loaded (this could be improved to load a file later)


Version 1.0
;;;
===== test_system_alarm_history_measure.elt
;;;
#
#    sprint-2    Historical Alarm bench mark (trigger an even to create a lot alarm in the system)
#

Options:
.    num=<number of historical entries>

Assumptions:
.    System has been running for a while, and already has many alarms
;;;
===== test_system_compute_kill_kvms.elt
;;;
#
#    TC472    Kills KVM processes, and checks for VM recovery
#        Retest of Jira CGTS=1580
#
Options
.    compute=<compute>
;;;
===== test_system_compute_kill_procs.elt
;;;
#
#    TC698    Kill Major Process on a Compute node
#    TC697    Kill Critical Process on a Compute node
#
Options
.    compute=<compute>
.    severity=<critical|major>        default=major
;;;
===== test_system_launch_cinder_vm.elt
;;;
#
#    Part of TC1991    Recovery after DOS
#        Launches a cinder based VM

Automation assist script. TC still requires powering down storage nodes, and then power up

NOTE: may have to increase quotas to launch VM
;;;
===== test_system_launch_cinder_vm_time_measure.elt
;;;
#
#    Part of TCC1413    Measure VM Launch Times

#        Launches a cinder based VM, and times the launch

Automation assist script. TC still requires powering down storage nodes, and then power up

NOTE: may have to increase quotas to launch VM
;;;
===== test_system_live_migration_measure.elt
;;;
#
#    system test - VM live-migrate
#    


Options
.    IP=<ip address/name of controller>
.    vm_type_list="virtio avp dpdk"
.    vm_name=<Specify when testing a single vm>
.    with_traffic=yes    <default=no>

NOTE: requires NAT access for cloud init test
NOTE: required expect-lite 4.8.1

Assumptions
.    Lab is setup using lab_setup.sh, VMs are lauched with launch_instances.sh
.    Ixia lab file is pre-loaded (this could be improved to load a file later)


Version 1.0
;;;
===== test_system_lock_list_of_computes.elt
;;;
#
#    TC625 Lock/unlock a compute blade
#
Options
.    max=5        maximum number of lock/unlocks
.    compute_list=<list of computes to lock/unlock>
;;;
===== test_system_migrations_10x.elt
;;;
#
#    TC622    Run 10 cold/live migrations.

#
Options:
.    max=5        maximum migrations
.    vm_name_list=<list of vm names>
;;;
===== test_system_monitor_vms_doughnut.elt
;;;
#
#    system test monitor running VMs (via NAT box) and has doughnut in the middle
#
#    Automation Assist Script
#
#    Options:
#        vm_mon_number=5            Number of VMs to monitor
#        vm_ip_list=<list of VMs to monitor>
#

;;;
===== test_system_monitor_vms.elt
;;;
#
#    system test monitor running VMs (via NAT box) and swact controllers
#
#
#    Options:
#        vm_name=<desired vm name>

#

;;;
===== test_system_monitor_vms_on_compute_n_doughnut.elt
;;;
#
#    system test monitor running VMs (via NAT box) and has doughnut in the middle
#
#    Automation Assist Script
#
#    Options:
#        compute=<compute name>        compute to monitor VMs on
#        evac=yes                compute will be evacuted (by another script)
#

;;;
===== test_system_monitor_vms_reboot_vms.elt
;;;
#
#    system test monitor running VMs (via NAT box) and reboot VMs
#    TC651 Run 10 VM reboots and ensure automatic recovery
#

#    NOTE: running traffic will cause VMs to be too slow to log in, and test will fail

Options
.    max=5        Maximum times to reboot VMs
.    num_vms=10    Number of VMs to reboot

;;;
===== test_system_reboot_act_controller_check_vms.elt
;;;
#
#    TC514    Halt -f on active controller and confirm other controller takes activity; also then confirm can launch new
#
#    Options:
#        node=<desired node name to reboot>
#        tenant=<desired tenant>

NOTE: must increase quotas to start another VM

;;;
===== test_system_reboot_computes_with_vlm.elt
;;;
#
#    Reboots computes using VLM
#
Options
.    compute_list=<list of compute names>
;;;
===== test_system_reboot_node.elt
;;;
#
#    system test node reboot
#
#    Options:
#        node=<desired node name to reboot>

;;;
===== test_system_reboot_node_measure.elt
;;;
#
#    system test node reboot
#
#    Options:
#        node=<desired node name to reboot>

;;;
===== test_system_reboot_nodes.elt
;;;
#
#    system test node reboot
#
#    Options:
#        node_list=<list of nodes to reboot>
;;;
===== test_system_sample.elt
;;;
#
#    sample system test
#

;;;
===== test_system_snmpwalk.elt
;;;
#
#    system test to snmpwalk controller
#

;;;
===== test_system_swact_controllers_n_times.elt
;;;
#
#    TC560 Stress: Run 10 Controller swacts via cli
#
Options
.    max=10            number of times to swact
;;;
===== test_system_swact_time_measure.elt
;;;
#
#    TC911    Measure Controller SWACT Times
#
NOTE: uncontrolled SWACT will reboot the active controller!

Options:
.    type=controlled_swact        Uses swact command
.    type=uncontrolled_swact        Uses reboot -f on active controller
;;;
===== test_system_vlm_console.elt
;;;
#
#    sample system test - login into HW console
#

;;;
===== test_system_vlm_console_ironpass_net_boot.elt
;;;
#
#    sample system test - login into HW console
#
Options
.    node=<node to boot>        (e.g. hp380-1 ironpass-8 ts-r720-4)
;;;
===== test_system_vm_login.elt
;;;
#
#    system test log into VM
#
#
#    Options:
#        vm_name=<desired vm name>

#

;;;
===== test_system_vm_recovery_measure.elt
;;;
#
#    TC913    Measure VM Recovery Times
#

Options:
.    vm_name=<specific vm_name>
.    vm_type_list=avp                will pick the first available AVP

;;;
===== test_system_vm_traffic.elt
;;;
#
#    sample system test with VM and Ixia traffic
#
#    Uses existing VM
#
# Options:
#        IP=<name|ip of controller>
#        config_file=<name of Ixia config file>
#
#

;;;
