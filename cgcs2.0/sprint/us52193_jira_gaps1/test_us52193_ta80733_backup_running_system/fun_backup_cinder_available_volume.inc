
;;;
    backup the specified cinder volume, which is in 'available' status

    #HOST_IP=${HOST_IP} HOST_USER=${HOST_USER} HOST_PASSWD=${HOST_PASSWD}

    input parameters required:
    $HOST_IP                e.g. 10.10.10.3
    $HOST_USER              e.g. wrsroot
    $HOST_PASSWD            e.g. li69nux
    $BACK_PATH              e.g. ./backupdir
    $VOL_ID                 uuid
;;;

; export the cinder volume $VOL_ID
; cmd: cinder export $VOL_ID
>cinder export $VOL_ID

; wait the volume is ready
~fun_wait_cvol_status.inc VOL_ID=$VOL_ID STATUS=available

; get backup file of the volume
>cd /opt/backups ; ls volume-$VOL_ID*
+$BK_FNM=\n(.*)

; scp the log file $BK_FNM from the remote host to $BACK_PATH
>exit
>^C
>  date | true
<.*

@1000
>scp -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $HOST_USER@$HOST_IP:/opt/backups/$BK_FNM $BACK_PATH/
<assword:|$$BK_FNM
>>$HOST_PASSWD


; re-connect to the remote host and clean up the backup files

; ssh to the remote host
>ssh -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $HOST_USER@$HOST_IP
<assword|SYSTEM:|WARNING:
>>$HOST_PASSWD

; clear up the backup files on the remote host
>sudo rm -rf /opt/backups/$BK_FNM
<assword|SYSTEM:|WARNING:
>>$HOST_PASSWD

; change to admin
>export TMOUT=0
@3
>source /etc/nova/openrc

; done with backup of System Data

