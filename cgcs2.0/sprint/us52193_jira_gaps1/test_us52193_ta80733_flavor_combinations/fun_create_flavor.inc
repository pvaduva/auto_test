

; create flavor with <name> specified, remove the flavors with the name if any existing

; required input arguments:
; <FLVNM>
; <FLVRAM>
; <FLVDISK>
; <FLVCPU>

>nova flavor-list
+$FLVUUID=\|\s*([a-f0-9-]{32,36})\s*\|\s*$FLVNM\s*\|

[ $FLVUUID != __NO_STRING_CAPTURED__
    >nova flavor-delete $FLVUUID
    >nova flavor-list
    +$FLVUUID=\|\s*([a-f0-9-]{32,36})\s*\|\s*$FLVNM\s*\|
]

>nova flavor-create $FLVNM auto $FLVRAM $FLVDISK $FLVCPU
+$FLVUUID=\|\s*([a-f0-9-]{32,36})\s*\|\s*$FLVNM\s*\|
?if $FLVUUID == __NO_STRING_CAPTURED__ ? [
    *TERM    
]

