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


?if $vlm_id == $blank? $vlm_id=18537

$vlm_tool=/folk/vlm/commandline/vlmTool 

?if $vlm_field != console? [
	>$vlm_tool getAttr all -t $vlm_id
	<$vlm_field
	+$vlm_value=:\s+(.+?)\n
]::[
	>$vlm_tool getAttr serial_port -t $vlm_id
	<Terminal Server IP
	+$_term_ip=:\s+(.+?)\n
	<Terminal Server Port
	+$_term_port=:\s+(.+?)\n
	?if $_term_port < 10? $_term_port=0$_term_port
	# return ip and port
	?if $_term_ip != TARGET_NOT_RESERVED_BY_USER? [
		$vlm_value=$_term_ip 20$_term_port
	]::[
		;red vlm target:$vlm_id not reserved by user
		$vlm_value=__NO_STRING_CAPTURED__
	]
]




## script testing lines

#>$vlm_tool -help
#>$vlm_tool getAttr -help

#>$vlm_tool getAttr serial_port -t $vlm_id

$vlm_field=IP Address

$vlm_id=21762
