# Copyright (c) 2013-2014 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import os
import subprocess
import re
import datetime
import time



def test_celiometer_benchmark():
   """Celiometer: Demonstrate stats can be display over a 1hr period

       Scenerio:
       1. Get statistic for avg.vswitch.port.transmit.util
       ceilometer sample-list -m avg.vswitch.port.transmit.util -l 60.
       2. Verify that statistic is displayed more than for one hour.
   """
   print("Get current time. Verify that system is running more than 60min")
   process = subprocess.Popen("uptime | egrep --color 'up.+(days|[0-9:]" \
              "{4,5})'", shell=True, stdout=subprocess.PIPE)
   stdout, stderr = process.communicate()
   if not stdout:
       sys.exit("Uptime is less than 60 minutes")

   list_of_sensors = ['hardware.ipmi.node.temperature',
                      'hardware.ipmi.node.outlet_temperature',
                      'hardware.ipmi.node.power',
                      'hardware.ipmi.node.airflow',
                      'hardware.ipmi.node.cups',
                      'hardware.ipmi.node.cpu_util',
                      'hardware.ipmi.node.mem_util',
                      'hardware.ipmi.node.io_util',
                      'hardware.ipmi.voltage',
                      'hardware.ipmi.fan',
                      'hardware.ipmi.temperature', 
                      'hardware.ipmi.current',
                      'compute.node.cpu.user.time',
                      'compute.node.cpu.iowait.time',
                      'compute.node.cpu.kernel.time',
                      'compute.node.cpu.user.time'] 

   for index in list_of_sensors:
       print("Get statistic for %s" % index)
       start_time = time.time()
       cmd = "ceilometer sample-list -m %s -l 60" % index
       print (cmd)
       os.system(cmd)
       end_time = time.time()
       elapsed_time = end_time - start_time
       print("elapsed time:  %s " % elapsed_time)

# Main function calls functions in order
def main():
    test_celiometer_benchmark()

# Program Starts Here!
main()

