
;;;
Convert the specified compute node to 'remote-storage' mode

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

;convert $compute to net-storage
~config_netst.inc compute=$compute host_user=$host_user host_passwd=$host_passwd

;unlock and wait $compute to be ready
~unlock_wait.inc node=$compute status=unlocked timeout=800

;check if successfully configured with local-storage on $compute
~verify_netst.inc node=$compute host_user=$host_user host_passwd=$host_passwd

;end of convert_to_net_storage.inc

