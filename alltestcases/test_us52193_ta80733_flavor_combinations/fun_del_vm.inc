

; delete server/vm with <name> specified

; required input arguments:
; <VMNM>=$VMNM

#| 0006bf5e-2c9f-4cc7-a9b6-5fe8698b0bf5 | ta80733_vm_1 | PAUSED  | -          | Paused      | public-net0=192.168.101.78; internal-net0=10.10.0.76, 10.10.1.76 |
# for test only
$VMNM=ta80733_vm_1

>nova list
+$UUID=\|\s*([0-9a-z-]{32,36})\s*\|\s*$VMNM\s*\|

[ $UUID != __NO_STRING_CAPTURED__
    >nova delete $UUID
    >nova list
    +$UUID=\|\s*([0-9a-z-]{32,36})\s*\|\s*$VMNM\s*\|
]


