
;;;
Check if guest-heartbeating is up

Required input:
    pass=<password>       password

Assumption:
;;;

#$cntlog1=/var/log/nfv-vim.log
$cntlog2=/var/log/guestAgent.log
#$cmptlog=/var/log/guestServer.log
#$vmlog=/var/log/user.log

$pass=li69nux

;change to root
>sudo su
>>$pass

;backup current file: $cntlog2
>cp -f $cntlog2 ./guestAgent.log-bk-`date +%Y%m%d-%H%M%S`
>cp -f $cntlog1 ./nfv-vim.log-bk-`date +%Y%m%d-%H%M%S`

;empty the current file: $cntlog2
>cat /dev/null > $cntlog2

;switch back to previous user
>exit
>^C
> hostname

