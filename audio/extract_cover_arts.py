#!/usr/bin/env python3
#coding=utf-8
"""Extract album cover arts.

Usage:
    extract_cover_arts.py [options] SRC DEST

Options:
    -h print this help message.
    -v verbose.
    -o output filename. Default: cover.png.
    -i input audio file format(s). Default: all supported formats.
"""
from getopt import gnu_getopt
from subprocess import run, PIPE, DEVNULL
import sys, os
from os import path
opts, args = gnu_getopt(sys.argv[1:], 'hvo:i:')
verbose = False
outfile = 'cover.png'
formats = ['dsf', 'flac']
for opt, val in opts:
    if opt == '-h':
        print(__doc__)
        sys.exit()
    elif opt == '-v':
        verbose = True
    elif opt == '-o':
        outfile = val
    elif opt == '-i':
        formats = val.split(',')
    else:
        assert False, "unhandled option"
try:
    srcdir = args[0]
    outdir = args[1]
except IndexError:
    print(__doc__)
    sys.exit()

while not path.exists(srcdir):
    srcdir = input(u"{} does not exist. Please try again or press [Ctrl-c] to quit: ".format(srcdir))
while path.exists(outdir):
    outdir = input(u"{} already exists. Please try again or press [Ctrl-c] to quit: ".format(outdir))
os.makedirs(outdir)
args = ['find', srcdir, '-type', 'f']
for fmt in formats:
    args += ['-name', '*.{}'.format(fmt), '-or']
result = run(args[:-1], check=True, stdout=PIPE).stdout
albums = dict()
for trkpath in result.decode().split('\n'):
    if path.isfile(trkpath):
        albpath, trkfile = path.split(trkpath)
        if albpath in albums:
            albums[albpath] += [trkfile]
        else:
            albums[albpath]  = [trkfile]

for alb in albums:
    outpath = path.join(outdir, path.relpath(alb, srcdir))
    os.makedirs(outpath)
    trkpath = path.join(alb, albums[alb][0])
    if verbose:
        sys.stdout.write(u'  Extract from {}......'.format(trkpath))
        sys.stdout.flush()
    run(["ffmpeg", "-i", trkpath, "-an", "-c:v", "png", path.join(outpath, outfile)], stdout=DEVNULL, stderr=DEVNULL)
    if verbose:
        sys.stdout.write(u'\r  Extract from {}......OK\n'.format(trkpath))
        sys.stdout.flush()
