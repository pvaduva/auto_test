This is a test that was run manually on a virtualbox test environment with
daily build installed from Nov 17th, 2014.

This test could potentially be automated in the future using expect-lite.  It
contains commands to control the vswitch interfaces on the compute. Typically
this would be done via the virtualbox GUI, by disabling the 'Cable' in the Data
network interface.

One issue was noticed when this test was run.  That is CGTS-958 missing error
message if "system host-lock" fails or is rejected.  The live migration itself
was observed to work correctly.  


