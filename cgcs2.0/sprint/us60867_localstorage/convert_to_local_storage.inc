
;;;
Convert the compute node to 'local-storage' and check the expected results.

Required inputs:
    compute=<compute>       the compute node to covert

Optional inputs:
    host_user=<user>        'wrsroot' by default
    host_passwd=<passwd>    'li69nux' by default
;;;

;by default, work on compute-1, will be overwritten by caller
$compute=comptue-1

;lock the compute node: $compute and wait it's locked
~lock_wait.inc node=$compute status=locked 

;convert $compute to local-storage
~config_locst.inc compute=$compute host_user=$host_user host_passwd=$host_passwd

;unlock and wait $compute to be ready
~unlock_wait.inc node=$compute status=unlocked timeout=800

;check if successfully configured with local-storage on $compute
~verify_locst.inc node=$compute host_user=$host_user host_passwd=$host_passwd

;on compute:$compute
;lvg_id=$lvg_id
;pv_id=$pv_id

;end of convert_to_local_storage.inc

