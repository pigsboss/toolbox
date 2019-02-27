#!/usr/bin/env python
"""dicmp
Dictionary Compare.

"""
import sys
from six import iteritems()
from os import path

def expand_path(s):
    l = []
    a, b = path.split(s)
    l.insert(0, b)
    while len(a)>0:
        s = a
        a, b = path.split(s)
        l.insert(0, b)
    return l

da = {}
with open(sys.argv[1], 'r') as f:
    for line in f:
        val, p = line.split()
        key = path.join(*tuple(expand_path(p)))
        da[key] = val.lower()

db = {}
with open(sys.argv[2], 'r') as f:
    for line in f:
        val, p = line.split()
        key = path.join(*tuple(expand_path(p)))
        db[key] = val.lower()

for key,val in iteritems(da):
    if db.has_key(key):
        if val != db[key]:
            print '{} in {}: {}'.format(key, sys.argv[1], da[key])
            print '{} in {}: {}'.format(key, sys.argv[2], db[key])

