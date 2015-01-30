##!/usr/bin/env expect-lite

; perform maintenance oprerations on a server (vm instance)

; VMUUID should be passed in

; get the status of a server
#$VMUUID=6ba5350b-aa2e-47a0-84ae-d59e1da4175a

~fun_get_vm_status.inc VMUUID=$VMUUID

; make sure the service/vm is ready
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=active STATUS=ACTIVE

; A1 pause/unpause the server/vm
; A1 step1: pause the server/vm
>nova pause $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=paused STATUS=PAUSED

; A1 step2: unpause the server/vm $VMUUID
>nova unpause $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=active STATUS=ACTIVE

; end of A1 pause/unpause the server/vm $VMUUID


; A2 suspend/resume the server/vm $VMUUID
; A2 step1: suspend the server/vm $VMUUID
>nova suspend $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=suspended STATUS=SUSPENDED

; A2 step2: resume the server/vm $VMUUID
>nova resume $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=active STATUS=ACTIVE
; end of A2 suspend/resume the server/vm $VMUUID

; A3 stop/start the server/vm $VMUUID
; A3 step1: stop the server
>nova stop $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=stopped STATUS=SHUTOFF
; A3 step2: start the service/vm $VMUUID
>nova start $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=active STATUS=ACTIVE
; end of A3 stop/start the server/vm $VMUUID

; A4 migrate server/vm $VMUUID
; A4 step1, migrate the server

>nova migrate $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=resized STATUS=VERIFY_RESIZE

; confirm resize
>nova resize-confirm $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=active STATUS=ACTIVE

; end of A4 migrate server/vm $VMUUID

; A5 live-migration server/vm $VMUUID
; A5 step1, live-migration the server
>nova live-migration $VMUUID
~fun_wait_vm_to_states.inc VMUUID=$VMUUID VMSTATE=active STATUS=ACTIVE

; end of A5 live-migration server/vm $VMUUID



