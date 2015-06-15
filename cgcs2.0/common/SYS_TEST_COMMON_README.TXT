===== fail_show.inc
;;;
#
#    fail script - performs show commands to aid debugging
#    
#

To use:
*~fail_show.inc 


;;;
===== get_vm_of_type.inc
;;;
#
#    get vm of type: virtio, avp, dpdk
#        returns 'none' if desired_type not found

To use:
~get_vm_of_type.inc 

Options:
.    vm_name=<desired vm name>
.    desired_type=<virtio, avp, dpdk>

;;;
===== get_vm_type.inc
;;;
#
#    Gets VM type 
#        virtio, avp, dpdk
#    returns: $vm_type, $vm_uuid, $vm_data_ip
#
#

To use:
~get_vm_type.inc 

Options:
.    vm_name=<desired vm name>



;;;
===== lo_compute_to_vlm.inc
;;;
#
#    compute to vlm board mapping
#        For LARGE office only
#

To use:
~compute_to_vlm.inc 

Options:
.    compute=<desired vm name>


Returns: vlm board number $vlm_board

;;;
===== node_to_vlm_id.inc
;;;
#
#    Maps lab nodes to vlm targets
#        
#

To use:
~node_to_vlm.inc 

Options:
.    node=<desired vlm name>


Returns: vlm board number $vlm_id

;;;
===== reboot_node.inc
;;;
#
#    reboot node
#
#    options:
#        force=yes

To use:
~reboot_node.inc node=<name> [force=yes]

;;;
===== ssh_controller.inc
;;;
#
#    ssh to controller
#

To use:
~ssh_controller.inc IP=<ip> [PORT=<custom port>]

;;;
===== ssh_to_natbox.inc
;;;
#
#    ssh to vm with login via the NAT box
#    Use in real labs only
#

To use:
~ssh_to_nat_to_vm.inc 

Options:
.    vm_name=<desired vm name>
.    mgmt_net=<management net name>
.    FAIL=path/name_of_fail_script

NOTE:
set timeout to reasonable value before calling this script
assumes admin user

;;;
===== ssh_to_nat_to_vm.inc
;;;
#
#    ssh to vm with login via the NAT box
#    Use in real labs only
#

To use:
~ssh_to_nat_to_vm.inc 

Options:
.    vm_name=<desired vm name>
.    mgmt_net=<management net name>
.    FAIL=path/name_of_fail_script

NOTE:
set timeout to reasonable value before calling this script
assumes admin user

;;;
===== ssh_to_vm.inc
;;;
#    BROKEN: as of AVR, dev has stopped supporting this method, DO NOT USE
#
#    ssh to vm with login
#    uses ip netns (name space)
#

To use:
~ssh_to_vm.inc 

Options:
.    vm_name=<desired vm name>
.    mgmt_net=<management net name>
.    FAIL=path/name_of_fail_script

NOTE:
set timeout to reasonable value before calling this script
assumes admin user

;;;
===== swact_controllers.inc
;;;
#
#    swact controllers
#

To use:
~swact_controllers.inc IP=<ip> [PORT=<custom port>]

Options
.    force=yes        does a reboot -f on active controller
;;;
===== tcl_functions.inc
===== vlm_cmd.inc
;;;
#
#    vlm commands to targets
#        
#
To use:
~vlm_cmd.inc 

Options:
.    vlm_id=<target id>
.    cmd=<desired vm name>


Supported commands:
.    reserve
.    unreserve
.    poweroff
.    poweron
.    reboot

;;;
===== vlm_field.inc
;;;
#
#    Retrieves vlm target value
#        
#

To use:
~vlm_field.inc 

Options:
.    vlm_id=<desired vlm target ID>
.    vlm_field=<field to return>

Returns: $vlm_value

Note: to retrieve console info, must reserve vlm target first
;;;
===== wait_node_state.inc
;;;
#
#    wait for node to go to $state        <default=active>
#    
#

To use:
~wait_node_state.inc 

Options:
.    node=<name>
.    state=<desired state>        default:available
.    max=<60>                    default:60
;;;
===== wait_vm_active.inc
;;;
#
#    wait loop for vm to become active
#    

To use:
~wait_vm_active.inc 

Options:
.    vm_name=<desired vm name>
.    vm_state=<desired wait for state>    <default=ACTIVE>
.    quick=yes                            <default=no>

;;;
