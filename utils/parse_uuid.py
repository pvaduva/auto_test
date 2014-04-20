#!/usr/bin/python3

from collections import deque
import os
import sys
import re
import time 
from optparse import OptionParser

"""
 Usage comments/Help
"""
usage = "usage: %prog [options]"
opt_parser = OptionParser(usage=usage)
opt_parser.add_option('-f', "--log_file", dest='log_file',
                  help="Supply the file name to be processed")

(options, args) = opt_parser.parse_args()

if options.log_file is  None:
    log_file = '/tmp/novalist.log'
else: log_file = options.log_file

# opening the perser config file and dump it to a 
f = open(log_file, 'r')
lines = f.readlines()
f.close()

uuids=list()

'''
Find UUIDs of all the VMs
'''
for l in lines:
    r = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
    found = re.search(r,l)
    if found is not None:
        #sys.stdout.write(found.group(0)+'\n')
        uuids.append(found.group(0))

# Exit if the there is nothing in the list so WASSP doesn't get confused
if len(uuids) <= 0:
    print ("{\"X\":\"[]\"}")
    exit(0)

''' Make an array that resambles this formate
# CALLPARSER PRINT: {"X":"[{'vm':'0'},{'vm':'1'},{'vm':'1'},{'vm':'2'},{'vm':'3'},{'vm':'4'},{'vm':'5'}]"
'''
def makeWasspArray2():
    out = open('/tmp/wassp.out','w')
    str1 = ("{\"X\":\"[")
    out.write(str1)
    varOut = (str1)
    while uuids:
        str1 = ("{'uuid':'"+uuids.pop(0)+"'}")
        out.write(str1)
        varOut = varOut + (str1)
        # Write a comma if it is not the last item in list
        if ( len(uuids) > 0 ):
            out.write(",")
            varOut = varOut + (",")
        else:
            # close the list
            str1 = ("]\"}")
            out.write(str1)
            varOut = varOut + (str1)
            break
    out.close()
    return varOut

print (makeWasspArray2())

exit(0)



