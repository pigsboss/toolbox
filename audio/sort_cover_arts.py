#!/usr/bin/env python3
#coding=utf-8
"""Sort album cover arts by user specified key.

Usage:
    sort_cover_arts.py [options] target

Options:
    -h  print this help.
    -r  print sorted list by reversed order.
    -s  suffix of cover art filename. Default: .png.
    -k  sort by specified key. Default: width.
"""
import sys
import unicodedata
from getopt import gnu_getopt
from os import path
from subprocess import run, PIPE

def nwidechars(s):
    return sum(unicodedata.east_asian_width(x)=='W' for x in s)
def width(s):
    return len(s)+nwidechars(s)
def uljust(s, w):
    return s.ljust(w-nwidechars(s))

opts, args = gnu_getopt(sys.argv[1:], 'hs:k:r')
target  = args[0]
suffix  = '.png'
srtkey  = 'width'
reverse = False
for opt, val in opts:
    if opt == '-r':
        reverse = True
    elif opt == '-h':
        print(__doc__)
        sys.exit()
    elif opt == '-s':
        suffix = val
    elif opt == '-k':
        srtkey = val
    else:
        assert False, "unhandled option"

result = run(["find", target, "-type", "f", "-name", "*{}".format(suffix)], check=True, stdout=PIPE).stdout
albums = dict()
for p in result.decode().split('\n'):
    albpath, trkcovr = path.split(p)
    if path.exists(p):
        if albpath in albums:
            albums[albpath]['track_covers']+=[trkcovr]
        else:
            artpath, albname = path.split(albpath)
            _, artname = path.split(artpath)
            albums[albpath]={
                'track_covers':[trkcovr],
                'album_path':albpath,
                'artist':artname,
                'album_name':albname
            }
sys.stdout.write(u'Analysing cover arts......')
sys.stdout.flush()
for alb in albums:
    result = run(["identify", path.join(albums[alb]['album_path'], albums[alb]['track_covers'][0])], check=True, stdout=PIPE).stdout.decode()
    albums[alb]['cover'] = dict(zip(['format', 'geometry', 'page_geometry', 'depth', 'colorspace', 'filesize', 'user_time', 'elapsed_time'], result.split(suffix)[1].split()))
    albums[alb]['cover']['width'], albums[alb]['cover']['height'] = map(int, albums[alb]['cover']['geometry'].split('x'))
sys.stdout.write(u'\rAnalysing cover arts......Finished.\n')
alb_sorted = sorted(albums.keys(), key=lambda alb:albums[alb]['cover'][srtkey], reverse=reverse)
if reverse:
    print("Album cover arts sorted by {} (reversed):".format(srtkey))
else:
    print("Album cover arts sorted by {}:".format(srtkey))
artist_width = max([width(albums[alb]['artist']) for alb in alb_sorted])
albnam_width = max([width(albums[alb]['album_name']) for alb in alb_sorted])
for alb in alb_sorted:
    print(u'{} {} {}'.format(uljust(albums[alb]['artist'], artist_width+4), uljust(albums[alb]['album_name'], albnam_width+4), albums[alb]['cover'][srtkey]))
