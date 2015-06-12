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
#	Maps lab nodes to vlm targets
#		
#

To use:
~node_to_vlm.inc 

Options:
.	node=<desired vlm name>


Returns: vlm board number $vlm_id

;;;


$nn=$node
#remove dashes
=$nn/[ -]//

$cc=$nn
#=$cc/.+?(\d+)/\1/
=$cc/([a-zA-Z]+)(\d+)/\2/


$node_type=$nn
=$node_type/([a-zA-Z]+)(\d+)/\1/


#IP1-4
$ironpass1=20519
$ironpass2=20520
$ironpass3=20521
$ironpass4=20522


#IP7-12
$ironpass7=21786
$ironpass8=21788
$ironpass9=21790
$ironpass10=21787
$ironpass11=21789
$ironpass12=21791


#IP14-17
$ironpass14=22349
$ironpass15=22348
$ironpass16=22347
$ironpass17=21784


#IP20-27
$ironpass20=18541
$ironpass21=18542
$ironpass22=18536
$ironpass23=18551
$ironpass24=22417
$ironpass25=22418
$ironpass26=21762
$ironpass27=18537


#HP380-1-4
$hp3801=21768
$hp3802=21769
$hp3803=21770
$hp3804=21771

#dell nodes 1-6
$tsr7201=22352
$tsr7202=22351
$tsr7203=21805
$tsr7204=21806
$tsr7205=21763
$tsr7206=21764




# deref array
?if $node_type == ironpass? $vlm_id=$ironpass$cc
?if $node_type == hp? $vlm_id=$hp$cc
?if $node_type == tsr? $vlm_id=$tsr$cc


; === node:$node vlm board:$vlm_id
