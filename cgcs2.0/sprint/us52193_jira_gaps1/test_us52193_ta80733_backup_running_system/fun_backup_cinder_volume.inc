# #!/usr/bin/env expect-lite

;;;

Create a backup of the Cinder Volume, including:
    1 Backing up 'Available Cinder Volumes'
    2 Backing up 'In-Use Cinder Volumes'
;;;

# HOST_IP=$HOST_IP HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD
#$HOST_IP=10.10.10.3
#$HOST_USER=wrsroot
#$HOST_PASSWD=li69nux
#$BACK_PATH=.

; "Start test Backup of Cinder Volumes"

; phase1 backup 'available cinder volumes'

$AVAILABLES=~/availabe.list
@20
>cinder list --all-tenants | tail -n+3 | grep 'available' | cut -d\| -f2 | awk '{print $1}' > $AVAILABLES

>wc -l $AVAILABLES
+$TOTAL=\n([0-9]+)
?if $TOTAL <= 0 ? [
    ; no available cinder volume to backup
    %PHASE1_DONE
]

$CURLN=1

[ $CURLN <= $TOTAL
    >tail -n+$CURLN $AVAILABLES | head -n1
    +$CV_ID=([a-z0-9-]{32,36})
    ?if $CV_ID == __NO_STRING_CAPTURED__ ?%PHASE1_DONE

    =$CURLN + 1 

    ; available cinder volume $CV_ID is not backup yet, do it now
    ~fun_backup_cinder_available_volume.inc HOST_IP=$HOST_IP HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD VOL_ID=$CV_ID
]
%PHASE1_DONE
>rm -rf $AVAILABLES

$INUSES=~/inuse.list
@20
>cinder list --all-tenants | tail -n+3 | grep 'in-use' | cut -d\| -f2 | awk '{print $1}' > $INUSES

>wc -l $INUSES
+$TOTAL=\n([0-9]+)
?if $TOTAL <= 0 ? [
    ; no in-use cinder volume to backup
    %PHASE2_DONE
]

; phase2 backup 'in-use cinder volumes'
$CURLN=1
[ $CURLN <= $TOTAL
    >tail -n+$CURLN $INUSES | head -n1
    +$CV_ID=([a-z0-9-]{32,36})
    ?if $CV_ID == __NO_STRING_CAPTURED__ ?%PHASE2_DONE

    =$CURLN + 1
    ; in-use cinder volume $CV_ID is not backup yet, do it now
    
    ~fun_backup_cinder_inuse_volume.inc HOST_IP=$HOST_IP HOST_USER=$HOST_USER HOST_PASSWD=$HOST_PASSWD VOL_ID=$CV_ID
]
%PHASE2_DONE
>rm -rf $INUSES

; all done with backup the cinder volumes

