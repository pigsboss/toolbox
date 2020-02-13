#!/usr/bin/env python3
#coding=utf-8
"""Estimate information entropy in bits of specified audio file.

Copyright: pigsboss@github
"""
import numpy as np
import soundfile as sf
import sys
from getopt import gnu_getopt
from os import path

def analyze_soundfile(filepath, bits=28):
    data, samplerate = sf.read(filepath, always_2d=True)
    nframes, nchans = data.shape
    dmin = np.min(data[:,0])
    dmax = np.max(data[:,0])
    x = np.int64((data[:,0]-dmin)/(dmax-dmin)*(2**bits-1)+0.5)
    cts = np.bincount(x)
    idx = np.nonzero(cts)
    pmf = cts[idx] / np.sum(cts)
    shs = -np.sum(pmf * np.log2(pmf))
    return {
        'path':filepath,
        'samplerate':samplerate,
        'nframes':nframes,
        'nchans':nchans,
        'shannons':shs
    }

def pprint(info_dict, display=True):
    if display:
        print("File path:          {}".format(info_dict['path']))
        print("Sample rate:        {:d} Hz".format(info_dict['samplerate']))
        print("Frames per channel: {:d}".format(info_dict['nframes']))
        print("Channels:           {:d}".format(info_dict['nchans']))
        print("Entropy bits:       {:.2f}".format(info_dict['shannons']))
    else:
        print("{}: {:d} channels * {:d} Hz * {:.2f} bits".format(
            info_dict['path'],
            info_dict['nchans'],
            info_dict['samplerate'],
            info_dict['shannons']
        ))

if __name__ == '__main__':
    opts, args = gnu_getopt(sys.argv[1:], 'hdb:')
    display = False
    bits = 28
    for opt, val in opts:
        if opt == '-h':
            print(__doc__)
            sys.exit()
        elif opt == '-d':
            display = True
        elif opt == '-b':
            bits = int(val)
    info = analyze_soundfile(path.abspath(path.normpath(path.realpath(args[0]))), bits=bits)
    pprint(info, display=display)
