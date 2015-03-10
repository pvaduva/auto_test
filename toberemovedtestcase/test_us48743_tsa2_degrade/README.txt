This test was run manually using the November 17th load.  The data port
failures were done on the computes themselves via:

vshell port-list
vshell port-show <uuid>
sudo vconsole
port lock/unlock 0
port lock/unlock 0

In this case both links on compute-0 and compute-1 were link aggregated.  This
was also attempted with only compute-0 data link aggregated and compute-1 not
aggregated.  

Note, when failing both aggregated data link ports in virtualbox, it was not
possible to see the expected critical failure.  Due to this reason, vconsole
must be used when failing both ports otherwise migration will not be seen.
