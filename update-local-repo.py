#!/usr/bin/env python
"""Update local repository.

"""
import sys
from subprocess import check_output
from os import path

with open('server.sha1sum','r') as f:
    for line in f:
        checksum, fits = line.split()
        if path.exists(fits):
            checksum_local = check_output(["sha1sum", fits], shell=True).split()[0].lower()
            if checksum_local == checksum.lower():
                print "{:<120}: OK".format(fits)
            else:
                print "{:<120}: Conflict".format(fits)
        elif path.exists(fits+'.gz'):
            checksum_local = check_output(["gzip -d -c {}.gz|sha1sum -".format(fits)], shell=True).split()[0].lower()
            if checksum_local == checksum.lower():
                print "{:<120}: OK".format(fits+'.gz')
            else:
                print "{:<120}: Conflict".format(fits+'.gz')
        else:
            print "{<:120}: Miss".format(fits)
