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
#	compute to vlm board mapping
#		For LARGE office only
#

To use:
~compute_to_vlm.inc 

Options:
.	compute=<desired vm name>


Returns: vlm board number $vlm_board

;;;



$cc=$compute
=$cc/.+-(\d+)/\1/

#IP11-12
$comp0=21789
$comp1=21791

#cgts-grantley-01
$comp2=21766

#IP14-17
$comp3=22349
$comp4=22348
$comp5=22347
$comp6=21784

#HP380-1-4
$comp7=21768
$comp8=21769
$comp9=21770
$comp10=21771

#unallocated
$comp11=
$comp12=
$comp13=
$comp14=
$comp15=0000
$comp16=0000
$comp17=
$comp18=
$comp19=
$comp20=0000
$comp21=
$comp22=

#IP20-26
$comp23=18541
$comp24=18542
$comp25=18536
$comp26=18551
$comp27=22417
$comp28=22418
$comp29=21762
$comp28=

# deref array
$vlm_board=$comp$cc

; === compute:$compute vlm board:$vlm_board
