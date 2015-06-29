===== ./el/util/tcl_functions.inc
===== ./el/util/ssh_to_natbox.inc
;;;
#
#	ssh to vm with login via the NAT box
#	Use in real labs only
#

To use:
~ssh_to_nat_to_vm.inc 

Options:
.	vm_name=<desired vm name>
.	mgmt_net=<management net name>
.	FAIL=path/name_of_fail_script

NOTE:
set timeout to reasonable value before calling this script
assumes admin user

;;;
[1;34m    ~$inc_path/ssh_controller.inc user=cgcs IP=$natbox
[00m===== ./el/util/fail_interact.inc
;;;
#
#	fail script - pauses script, and drops to interact when test fails
#	
#

To use:
*~fail_interact.inc 


;;;
===== ./el/util/fail_show.inc
;;;
#
#	fail script - performs show commands to aid debugging
#	
#

To use:
*~fail_show.inc 


;;;
===== ./el/vm/ssh_to_vm.inc
;;;
#	BROKEN: as of AVR, dev has stopped supporting this method, DO NOT USE
#
#	ssh to vm with login
#	uses ip netns (name space)
#

To use:
~ssh_to_vm.inc 

Options:
.	vm_name=<desired vm name>
.	mgmt_net=<management net name>
.	FAIL=path/name_of_fail_script

NOTE:
set timeout to reasonable value before calling this script
assumes admin user

;;;
[1;34m    ?if $FAIL == $blank ? *~$inc_path/fail_show.inc :: ~$FAIL
[00m===== ./el/vm/get_vm_type.inc
;;;
#
#	Gets VM type 
#		virtio, avp, dpdk
#	returns: $vm_type, $vm_uuid, $vm_data_ip
#
#

To use:
~get_vm_type.inc 

Options:
.	vm_name=<desired vm name>



;;;
===== ./el/vm/ssh_to_nat_to_vm.inc
;;;
#
#	ssh to vm with login via the NAT box
#	Use in real labs only
#

To use:
~ssh_to_nat_to_vm.inc 

Options:
.	vm_name=<desired vm name>
.	mgmt_net=<management net name>
.	FAIL=path/name_of_fail_script

NOTE:
set timeout to reasonable value before calling this script
assumes admin user

;;;
[1;34m    ~$inc_path/ssh_controller.inc user=cgcs IP=$natbox
[00m[1;34m    ~$inc_path/ssh_controller.inc user=$vm_user pass=$vm_pass IP=$vm_ip
[00m===== ./el/vm/get_vm_of_type.inc
;;;
#
#	get vm of type: virtio, avp, dpdk
#		returns 'none' if desired_type not found

To use:
~get_vm_of_type.inc 

Options:
.	vm_name=<desired vm name>
.	desired_type=<virtio, avp, dpdk>

;;;
[1;34m    ~$inc_path/get_vm_type.inc vm_name=$vm
[00m===== ./el/vm/wait_vm_active.inc
;;;
#
#	wait loop for vm to become active
#	

To use:
~wait_vm_active.inc 

Options:
.	vm_name=<desired vm name>
.	vm_state=<desired wait for state>	<default=ACTIVE>
.	quick=yes							<default=no>

;;;
===== ./el/vlm/vlm_cmd.inc
;;;
#
#	vlm commands to targets
#		
#
To use:
~vlm_cmd.inc 

Options:
.	vlm_id=<target id>
.	cmd=<desired vm name>


Supported commands:
.	reserve
.	unreserve
.	poweroff
.	poweron
.	reboot

;;;
===== ./el/vlm/vlm_field.inc
;;;
#
#	Retrieves vlm target value
#		
#

To use:
~vlm_field.inc 

Options:
.	vlm_id=<desired vlm target ID>
.	vlm_field=<field to return>

Returns: $vlm_value

Note: to retrieve console info, must reserve vlm target first
;;;
===== ./el/vlm/node_to_vlm_id.inc
;;;
#
#	Maps lab nodes to vlm targets
#		
#

To use:
~node_to_vlm.inc 

Options:
.	node=<desired vlm name>


Returns: vlm board number $vlm_id

;;;
===== ./el/vlm/lo_compute_to_vlm.inc
;;;
#
#	compute to vlm board mapping
#		For LARGE office only
#

To use:
~compute_to_vlm.inc 

Options:
.	compute=<desired vm name>


Returns: vlm board number $vlm_board

;;;
===== ./el/node/ssh_node.inc
;;;
#
#	ssh to node
#

To use:
~ssh_controller.inc IP=<ip> [PORT=<custom port>]
~ssh_node.inc IP=<ip> [PORT=<custom port>]

;;;
===== ./el/node/reboot_node.inc
;;;
#
#	reboot node
#
#	options:
#		force=yes

To use:
~reboot_node.inc node=<name> [force=yes]

;;;
[1;34m    ~$inc_path/ssh_controller.inc 
[00m[1;34m    ~$inc_path/ssh_controller.inc IP=$node PORT=
[00m===== ./el/node/wait_node_state.inc
;;;
#
#	wait for node to go to $state		<default=active>
#	
#

To use:
~wait_node_state.inc 

Options:
.	node=<name>
.	state=<desired state>		default:available
.	max=<60>					default:60
;;;
===== ./el/node/ssh_controller.inc
;;;
#
#	ssh to node
#

To use:
~ssh_controller.inc IP=<ip> [PORT=<custom port>]
~ssh_node.inc IP=<ip> [PORT=<custom port>]

;;;
===== ./el/node/swact_controllers.inc
;;;
#
#	swact controllers
#

To use:
~swact_controllers.inc IP=<ip> [PORT=<custom port>]

Options
.	force=yes		does a reboot -f on active controller
;;;
[1;34m    ~$inc_path/ssh_controller.inc
[00m