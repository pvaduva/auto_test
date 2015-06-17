# How to use this expect-lite file, Lines that begin with:
#	'>' send to remote host, implies "wait for prompt"
#	'<' _MUST_ be received from the remote host, or this config script will fail
#	# are comment lines, and have no effect
#	; are printable (in stdout) comments, and have no other effect
#	@ change the expect timeout value
#	! Embedded Expect commands
# For more info see: expect-lite.html
;;;
#
#	fail script - performs show commands to aid debugging
#	
#

To use:
*~fail_show.inc 


;;;

        LOG.info("TEST FAILED: %s" % message)
        LOG.info("Show current system status")
        # showing a variety of commands, add as needed
        self.sysinv("alarm-list")
        self.sysinv("host-list")
        # show alarm-history from when test started
        action = 'alarm-history-list'
        params = ' -l 2000 -q start="%s"' % self.start_time
        self.sysinv(action, params=params)
        self.nova("flavor-list --extra")
        self.glance("image-list")
        self.neutron("net-list")
        self.nova("list --all-tenants")


;red === TEST FAILED:

; === Show current system status

>system host-list
>system alarm-list
>system alarm-history-list -l 25
>glance image-list
>cinder list
>neutron net-list
>nova flavor-list --extra
>nova list --all-tenants
>



