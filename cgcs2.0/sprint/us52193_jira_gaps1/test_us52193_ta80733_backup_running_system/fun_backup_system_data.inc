# #!/usr/bin/env expect-lite

;;;

Create a backup of the System Data

;;;

#HOST_IP=${HOST_IP} HOST_USER=${HOST_USER} HOST_PASSWD=${HOST_PASSWD}
#$HOST_IP=10.10.10.3
#$HOST_USER=wrsroot
#$HOST_PASSWD=li69nux
#$BACK_PATH=.

>echo "Start test Backup of System Data"

$BKNM=sysbk
$BKNM_SYS=$BKNM
$BKNM_IMG=$BKNM
=$BKNM_SYS + _system.tgz
=$BKNM_IMG + _images.tgz

; clear up the old backups
>sudo rm -rf /opt/backups/$BKNM_SYS /opt/backups/$BKNM_IMG
<assword|:\~\$
>>$HOST_PASSWD

; exute the system backup
@1500
>sudo config_controller --backup $BKNM
<assword|Performing backup
>>$HOST_PASSWD
<Backup complete|100%

; check if $BKNM_SYS generated
>cd /opt/backups; ls $BKNM_SYS
<$BKNM_SYS

; check if $BKNM_IMG generated
>cd /opt/backups; ls $BKNM_IMG
<$BKNM_IMG

; now exit from the remote host
>exit
>^C
<.*

; scp the logs from the remote host to $BACK_PATH
@300
>scp -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $HOST_USER@$HOST_IP:/opt/backups/$BKNM_SYS $BACK_PATH/
<assword:|$BKNM_SYS
>>$HOST_PASSWD

@300
>scp -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $HOST_USER@$HOST_IP:/opt/backups/$BKNM_IMG $BACK_PATH/
<assword:|$BKNM_IMG
>>$HOST_PASSWD


; ssh to the remote host
>ssh -o UserKnownHostsFIle=/dev/null -o StrictHostKeyChecking=no $HOST_USER@$HOST_IP
<assword|SYSTEM:|WARNING:
>>$HOST_PASSWD

; clear up the backup files on the remote host
>sudo rm -rf /opt/backups/$BKNM_SYS /opt/backups/$BKNM_IMG
<assword|SYSTEM:|WARNING:
>>$HOST_PASSWD

; change to admin
>export TMOUT=0
@20
>source /etc/nova/openrc

; done with backup of System Data

