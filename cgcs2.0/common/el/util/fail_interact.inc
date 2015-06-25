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
#	fail script - pauses script, and drops to interact when test fails
#	
#

To use:
*~fail_interact.inc 


;;;


;red === TEST FAILED:

; === show previous executed lines of script
>>
# Calls expect-lite internal function (like ESC -9) to show lines of main script
# show last 9 lines, in bufstack 1 (main script)
!_el_buffer_show -9 1

; === Drop to Interact

*INTERACT
>


