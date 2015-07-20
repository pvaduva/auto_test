
;;;
    Test the VM voting on the specified VM

Required Option
    vmid=<uuid-of-vm>       uuid of the VM
    vmname=<name-of-vm>     name of the VM
    password=<password>     password for 'admin'
;;;

>source /etc/nova/openrc
$password=li69nux

;wait for the vm to be ready 
~wait_vm_status.inc vmid=$vmid

;make sure all the operation working
~vm_operations.inc vmid=$vmid
;done with TC1: Basic VM functionality with heartbeat flavor-key

!sleep 60
;make sure the heartbeating is working
~check_heartbeating_up.inc password=$password vmname=$vmname

;us57002_tc2: Pause/Suspend VM (suspend/resume)
;create vote-file to 'suspend'

;login to VM:$vmid VM name:$vmid
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

>rm -f /tmp/event_timeout  /tmp/vote_*
>touch /tmp/vote_no_to_suspend
>sync
>ls -l /tmp/vote_no_to_suspend
>exit
>^C
> hostname
>exit
>^C

!sleep 5
;attempt to suspend the vm, should be rejected
>nova suspend "$vmid"
!sleep 1

;check the vm should still be ACTIVE 
~wait_vm_status.inc vmid=$vmid

;check the events for action 'suspend'
~check_vm_voting_event.inc vmname=$vmname vmid=$vmid act=suspend


;logon the VM and remove the 'voting' file
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

>rm -f /tmp/vote_no_to_suspend /tmp/vote* 
>sync

;get off the VM and NATBOX
>sync
>exit
>^C
> hostname
>exit
>^C
> hostname


;end of tc2

;us57002_tc3: Stop/Start a VM

;create the voting-no file for action 'stop'
;logon the VM 
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

;create the file
>touch /tmp/vote_no_to_stop
>sync
>ls -l /tmp/vote_no_to_stop
>exit
>^C
> hostname

>exit
>^C
> hostname

!sleep 5
;attempt to stop the vm, should be rejected
>nova stop "$vmid"
!sleep 1
;the 'stop' request should be rejected
;the vm should be in ACTIVE
~wait_vm_status.inc vmid=$vmid
;the VM is active as expected

;check the voting events for 'stop' action
~check_vm_voting_event.inc vmname=$vmname vmid=$vmid act=stop

;cleanup

;logon the VM 
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

;remove voting file
>rm -rf /tmp/vote_no_to_stop /tmp/vote_*
>sync
>exit
>^C
> hostname

>exit
>^C
> hostname

;end of tc3

;us57002_tc4: Reboot a VM

;create the voting file for vote-no-to 'reboot'
;logon the VM  
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

;test voting 'no' to 'reboot'
>touch /tmp/vote_no_to_reboot
>sync
>ls -l /tmp/vote_no_to_reboot
>exit
>^C
> hostname

>exit
>^C
> hostname

!sleep 5
;attempt to reboot the vm, should be rejected
>nova reboot "$vmid"
!sleep 1
;the vm should be in ACTIVE
~wait_vm_status.inc vmid=$vmid
;the VM is active as expected

;check the voting events for 'reboot' action
~check_vm_voting_event.inc vmname=$vmname vmid=$vmid act=reboot

!sleep 1
;attempt to hard-reboot the vm, should be rejected
>nova reboot --hard "$vmid"
!sleep 1
;the vm should be in ACTIVE
~wait_vm_status.inc vmid=$vmid
;the VM is active as expected

;check the events
~check_vm_voting_event.inc vmname=$vmname vmid=$vmid act=reboot

;cleanup
;logon the VM 
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

;remove voting file
>rm -rf /tmp/vote_no_to_reboot /tmp/vote_*
>sync
>exit
>^C
> hostname

>exit
>^C
> hostname

;end of tc4 

;us57002_tc5: Migrate a VM

;logon to vm:$vmid
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid
;create 'vote' file to reject 'migrate'
>touch /tmp/vote_no_to_migrate
>sync
>ls -l /tmp/vote_no_to_migrate
>exit
>^C
> hostname

>exit
>^C
> hostname

!sleep 5
;attempt to live-migrate the vm, should be rejected
>nova live-migration "$vmid"
!sleep 1
;the vm should be in ACTIVE
~wait_vm_status.inc vmid=$vmid
;the VM is active as expected

;check the events
~check_vm_voting_event.inc vmname=$vmname vmid=$vmid act=migrate

!sleep 1
;attempt to cold migrate the vm, should be rejected
>nova migrate "$vmid"
!sleep 5
;the vm should be in ACTIVE
~wait_vm_status.inc vmid=$vmid
;the VM is active as expected

;check the events
~check_vm_voting_event.inc vmname=$vmname vmid=$vmid act=migrate

;clean the voting file
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

;remove 'no-vote' file for 'migrate'
>rm -rf /tmp/vote_no_to_migrate /tmp/vote_*
>sync
>exit
>^C
> hostname

>exit
>^C
> hostname

;end of tc5 

;us57002_tc6: Voting timeout

;logon to vm:$vmid
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid
;create 'voting' file 'event_timeout'
>touch /tmp/event_timeout
;create 'no-voting' file for 'suspend'
>touch /tmp/vote_no_to_suspend
>sync
>ls -l /tmp/event_timeout /tmp/vote_no_to_suspend
>exit
>^C
> hostname

>exit
>^C
> hostname

;make sure all the operation still working
~vm_operations.inc vmid=$vmid

;cleanup after test 'event_timeout'
~$inc_path/vm/ssh_to_nat_to_vm.inc vm_name=$vmid

;remove 'voting' file 'event_timeout'
>rm -f /tmp/event_timeout /tmp/vote_*

>exit
>^C
> hostname
>exit
>^C
> hostname

;end of tc6

