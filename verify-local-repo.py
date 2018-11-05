#!/usr/bin/env python
"""Verify local repository.

Syntax:
verify-local-repo.py server-checksum [checksum-algorithm] [output]
"""

import sys
from subprocess import check_output
from os import path

server_checksum_file = sys.argv[1]
try:
    checksum_algorithm = sys.argv[2]
except:
    checksum_algorithm = None
try:
    output_file = sys.argv[3]
except:
    output_file = 'local-repo-missing.txt'

with open(output_file, 'w') as g:
    with open(server_checksum_file, 'r') as f:
        for line in f:
            checksum, fits = line.split()
            if path.exists(fits):
                if checksum_algorithm is not None:
                    checksum_local = check_output(["{} {}".format(checksum_algorithm, fits)], shell=True).split()[0].lower()
                    if checksum_local == checksum.lower():
                        print "{:<120}: OK".format(fits)
                    else:
                        print "{:<120}: Conflict".format(fits)
                        g.write('{}  {}\n'.format(checksum, fits))
                else:
                    print "{:<120}: OK".format(fits)
            elif path.exists(fits+'.gz'):
                if checksum_algorithm is not None:
                    checksum_local = check_output(["gzip -d -c {}.gz|{} -".format(fits, checksum_algorithm)], shell=True).split()[0].lower()
                    if checksum_local == checksum.lower():
                        print "{:<120}: OK".format(fits+'.gz')
                    else:
                        print "{:<120}: Conflict".format(fits+'.gz')
                        g.write('{}  {}\n'.format(checksum, fits))
                else:
                    print "{:<120}: OK".format(fits+'.gz')
            else:
                print "{:<120}: Miss".format(fits)
                g.write('{}  {}\n'.format(checksum, fits))
