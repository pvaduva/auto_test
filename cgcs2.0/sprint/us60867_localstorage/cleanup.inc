
;;;
Cleanup after testing:
    1 delete VMs
    2 remove lvg
    3 convert compute to remote-storage
;;;

;cleanup the local-storage settings

;already converted $lc_cpt to remote-storage
#~convert_to_net_storage.inc compute=$lc_cpt

$compute2=NONE
? $compute2 != NONE ? [
    ;convert $compute2 to remote-storage
    ~convert_to_net_storage.inc compute=$compute2
]

;remove the file
>rm -rf $compute_list

? $debug != no ? [
    ;for debug only, remember to remove it
    ;go to interactive debug mode
    *INTERACT
]

;all VM lanuched should be already deleted

;end of cleanup

