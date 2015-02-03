
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

; backup in-use cinder volumes

; done with backup in-use cinder volumes

; Create a volume snapshot
#>cinder snapshot-create --force True --display-name nvmsnapshot-$VOL_ID $VOL_ID
>cinder snapshot-create --force True $VOL_ID
+$SNP_ID=\|\s*id\s*\|\s*([a-z0-9-]{32,36})\s*\|

; Now there's a volume available for $VOL_ID

$max=120
$cnt=0
[ $cnt < $max
    =$cnt + 1
    >cinder snapshot-list --all-tenants
    #+$STATUS=\|\s*[a-z0-9-]{32,36}\s*\|\s*$VOL_ID\s*\|\s*([a-z]+)\s*\|
    +$STATUS=\|\s*$SNP_ID\s*\|\s*$VOL_ID\s*\|\s*([a-z]+)\s*\|
    ?if $STATUS == available ?%SNP_READY

    ; snapshot is not ready: $VOL_ID, wait and try again
    !sleep 6
]

?if $STATUS != available ? [
    ; cannot create snapshot, done
    %ALLDONE
]

%SNP_READY

>cinder snapshot-export $SNP_ID

$cnt=0
[ $cnt < $max
    =$cnt + 1
    !sleep 6

    >cinder snapshot-list --all-tenants
    +$STATUS=\|\s*$SNP_ID\s*\|\s*$VOL_ID\s*\|\s*([a-zA-Z0-9_-]+)\s*\|
    ?if $STATUS == available ?%EXPORT_READY
]

%EXPORT_READY

%backup file of the volume
>cd /opt/backups ; ls volume-$VOL_ID*
+$BK_FNM=\n(.*)

; scp the log file $BK_FNM from the remote host to $BACK_PATH
>exit
>^C
> date | true
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

%ALLDONE

