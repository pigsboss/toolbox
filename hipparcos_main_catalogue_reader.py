#!/usr/bin/env python
import numpy as np
from subprocess import check_output

def get_num_lines(filename):
    return int(check_output('wc -l %s'%filename, shell=True).split()[0])

essential_entry=np.dtype([   # entry contains only essential fields
    ('HIP_No',  'uint64'),   # Hipparcos No. (identifier)
    ('RA',      'float64'),  # RA in degrees
    ('Dec',     'float64'),  # Dec in degrees
    ('Par',     'float64'),  # Parallax in mas
    ('RAPM',    'float64'),  # RA proper motion in mas/yr
    ('DecPM',   'float64'),  # Dec proper motion in mas/yr
    ('RA_E',    'float64'),  # RA standard error in mas
    ('Dec_E',   'float64'),  # Dec standard error in mas
    ('Par_E',   'float64'),  # Parallax standard error in mas
    ('RAPM_E',  'float64'),  # RA proper motion standard error in mas/yr
    ('DecPM_E', 'float64'),  # Dec proper motion standard error in mas/yr
    ('Vmag',    'float64')]) # V magnitude

def export_essential(text, binary):
    """Read all entries from text catalogue, extract essential fields from each entry,
and export to binary (NumPy) array.
"""
    fin     = open(text, 'r')
    nlines  = get_num_lines(text)
    entries = []
    t = 0
    for l in fin:
        fields = l.split('|')
        entry  = np.zeros(1, essential_entry)
        try:
            entry['HIP_No']  = int(fields[1])
            entry['RA']      = float(fields[8])
            entry['Dec']     = float(fields[9])
            entry['Par']     = float(fields[11])
            entry['RAPM']    = float(fields[12])
            entry['DecPM']   = float(fields[13])
            entry['RA_E']    = float(fields[14])
            entry['Dec_E']   = float(fields[15])
            entry['Par_E']   = float(fields[16])
            entry['RAPM_E']  = float(fields[17])
            entry['DecPM_E'] = float(fields[18])
            entry['Vmag']    = float(fields[5])
            entries         += [entry]
        except:
            t += 1
            print '%d entries ignored.'%t
    np.save(binary, np.array(entries))
