#!/usr/bin/env python2

import sys
import os
from os import path
TOP_DIR = '/sys/bus/acpi/drivers/battery'
if path.isdir(TOP_DIR):
    full = {}
    now = {}
    for d in os.listdir(TOP_DIR):
        if path.isdir(path.join(TOP_DIR,d)):
            for b in os.listdir(path.join(TOP_DIR,d,'power_supply')):
                with open(path.join(TOP_DIR,d,'power_supply',b,'energy_full')) as f:
                    full[b] = eval(f.readline())
                with open(path.join(TOP_DIR,d,'power_supply',b,'energy_now')) as f:
                    now[b] = eval(f.readline())
                print '%s: %d/%d = %0.2f%%'%(b,now[b],full[b],now[b]*100.0/full[b])
else:
    print "System platform is not supported."
    sys.exit()

full_t = 0.0
now_t = 0.0
for b in full:
    full_t += full[b]
for b in now:
    now_t += now[b]
print 'Total: %d/%d = %0.2f%%'%(now_t,full_t,now_t*100.0/full_t)
