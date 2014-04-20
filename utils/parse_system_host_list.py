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
opt_parser.add_option('-l', "--log_file", dest='log_file',
                  help="Supply the file name to be processed")
opt_parser.add_option('-v', "--wassp_var", dest='wassp_var',
                  help="Wassp var to output")
opt_parser.add_option('-d', "--wassp_dict_id", dest='wassp_dict_id',
                  help="Wassp var to output")
opt_parser.add_option('-f', "--lookfor", dest='lookfor',
                  help="Regex to look for: example:  '[\s|]*([0-9]+)[\s|]*([a-zA-Z0-9-]+).*'")

(options, args) = opt_parser.parse_args()

if options.log_file is  None:
    log_file = '/tmp/system-host-list.log'
else: log_file = options.log_file

if options.wassp_var:
    wassp_var = options.wassp_var
else: wassp_var = 'X'

if options.wassp_dict_id:
    wassp_dict_id = options.wassp_dict_id
else: wassp_dict_id = 'item'

if options.lookfor:
    lookfor = options.lookfor
else: lookfor = '[\s|]*([0-9]+)[\s|]*([a-zA-Z0-9-]+).*'

# opening the perser config file and dump it to a 
f = open(log_file, 'r')
lines = f.readlines()
f.close()

holder=list()

'''
Find host of all the VMs
'''
for l in lines:
    r = re.compile(lookfor)
    found = re.match(r,l)
    if found is not None:
        #sys.stdout.write(found.group(2)+'\n')
        holder.append(found.group(2))

# print ("length of holder %s" % len(holder))
# Exit if the there is nothing in the list so WASSP doesn't get confused
if len(holder) <= 0:
    print ("{\"" + wassp_var + "\":\"[]\"}")
    exit(0)

''' Make an array that resambles this format
CALLPARSER PRINT: {"X":"[{'vm':'0'},{'vm':'1'},{'vm':'1'},{'vm':'2'},{'vm':'3'},{'vm':'4'},{'vm':'5'}]"
'''
def makeWasspArray2():
    out = open('/tmp/wassp.out','w')
    str1 = ("{\"" + wassp_var + "\":\"[")
    out.write(str1)
    varOut = (str1)
    while holder:
        str1 = ("{'" + wassp_dict_id + "':'"+holder.pop(0)+"'}")
        out.write(str1)
        varOut = varOut + (str1)
        # Write a comma if it is not the last item in list
        if ( len(holder) > 0 ):
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



