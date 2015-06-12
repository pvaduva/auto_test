# How to use this expect-lite file, Lines that begin with:
#	'>' send to remote host, implies "wait for prompt"
#	'<' _MUST_ be received from the remote host, or this config script will fail
#	# are comment lines, and have no effect
#	; are printable (in stdout) comments, and have no other effect
#	@ change the expect timeout value
#	! Embedded Expect commands
# For more info see: expect-lite.html
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

# set defaults
?if $max == $blank ? $_max=60 :: $_max=$max
?if $state == $blank? $state=available

; === wait for $node to come online
$compute=$node
$i=0

$c_state=none
[ $c_state != $state
	>system host-list
	<$compute
	+$c_state=(available|online|offline|failed|intest|disabled)

	!sleep 5
	+$i
	?if $i > $_max? %BREAK_ONLINE
]
%BREAK_ONLINE







