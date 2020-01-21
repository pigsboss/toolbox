#!/usr/bin/env python3
#coding=utf-8
"""SLIM is a slim SONY Music Library Manager.

Usage: slim.py action [options]

Actions:

  build
    Build SONY Music Library, generate metadata and checksums and extract album cover arts.
    Syntax: slim.py build -s SRC DEST
    SRC is path of SONY Music Library.

  print
    print pre-built SONY Music Library from user specified database.
    Syntax: slim.py print PATH_TO_DB

  export
    Export SONY Music Library to specified audio format.

  update
    Re-scan filesystem and update SONY Music Library.

  sort[_cover_arts]
    Sort album cover arts by user specified key.

Options:
  -v  verbose.
  -s  source (SONY Music Library) path.
  -m  match, in [artist]/[album]/[discnumber.][tracknumber - ][title].
  -e  '[s]kip', '[o]verwrite' or '[u]pdate' if user specified output file already exists.
        skip       skip exporting.
        overwrite  overwrite existing file.
        update     skip if existing file has been exported from the same source.
  -p  audio format preset.
      Available presets (case-insensitive):
        dxd    (up to  384kHz/24bit FLAC).
        ldac   (up to   96kHz/24bit FLAC).
        cd     (up to   48kHz/24bit FLAC).
        itunes (256kbps 44.1kHz VBR AAC). 
        aac    (44.1kHz/48kHz VBR 5 AAC).
        opus   (44.1kHz/48kHz 128bps Opus).
        radio  (128kbps 44.1kHz VBR MP3).
  -b  bitrate, in kbps (overrides preset default bitrate).
  -k  key for sorting. Default: width.
  -r  sort in reverse order.
  -o  output.

Copyright: pigsboss@github
"""

import sys
import os
import hashlib
import signal
import pickle
import warnings
import csv
import shutil
import unicodedata
import numpy as np
from mutagen.mp3 import MP3
from mutagen.dsf import DSF
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.id3 import ID3, APIC, ID3TimeStamp, TextFrame, COMM
from mutagen.oggopus import OggOpus
from multiprocessing import cpu_count, Pool, Process, Queue
from time import time, sleep
from os import path
from getopt import gnu_getopt
from subprocess import run, Popen, PIPE, DEVNULL
from tempfile import TemporaryDirectory
from mpi4py import MPI

comm = MPI.COMM_WORLD

## Reference:
##   https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
##   https://mutagen.readthedocs.io/en/latest/api/vcomment.html#mutagen._vorbis.VCommentDict
TAG_MAP = {
    'ID3': {
        'grouping'      : 'TIT1',
        'title'         : 'TIT2',
        'subtitle'      : 'TIT3',
        'album'         : 'TALB',
        'discsubtitle'  : 'TSST',
        'artist'        : 'TPE1',
        'albumartist'   : 'TPE2',
        'conductor'     : 'TPE3',
        'remixer'       : 'TPE4',
        'composer'      : 'TCOM',
        'lyricist'      : 'TEXT',
        'publisher'     : 'TPUB',
        'tracknumber'   : 'TRCK',
        'discnumber'    : 'TPOS',
        'date'          : 'TDRC',
        'year'          : 'TYER',
        'isrc'          : 'TSRC',
        'encoded-by'    : 'TENC',
        'encoder'       : 'TSSE',
        'compilation'   : 'TCMP',
        'genre'         : 'TCON',
        'comment'       : 'COMM',
        'copyright'     : 'TCOP',
        'language'      : 'TLAN'
    },                  
    'MP4': {
        'grouping'      : '\xa9grp',
        'title'         : '\xa9nam',
        'subtitle'      : '----:com.apple.iTunes:SUBTITLE',
        'album'         : '\xa9alb',
        'discsubtitle'  : '----:com.apple.iTunes:DISCSUBTITLE',
        'albumartist'   : 'aART',
        'artist'        : '\xa9ART',
        'conductor'     : '----:com.apple.iTunes:CONDUCTOR',
        'remixer'       : '----:com.apple.iTunes:REMIXER',
        'composer'      : '\xa9wrt',
        'lyricist'      : '----:com.apple.iTunes:LYRICIST',
        'license'       : '----:com.apple.iTunes:LICENSE',
        'label'         : '----:com.apple.iTunes:LABEL',
        'tracknumber'   : 'trkn',
        'discnumber'    : 'disk',
        'year'          : '\xa9day',
        'isrc'          : '----:com.apple.iTunes:ISRC',
        'encoded-by'    : '\xa9too',
        'genre'         : '\xa9gen',
        'compilation'   : 'cpil',
        'comment'       : '\xa9cmt',
        'copyright'     : 'cprt',
        'language'      : '----:com.apple.iTunes:LANGUAGE',
        'description'   : 'desc'
    },                  
    'Vorbis': {
        'grouping'      : 'grouping',
        'title'         : 'title',
        'subtitle'      : 'subtitle',
        'album'         : 'album',
        'discsubtitle'  : 'discsubtitle',
        'albumartist'   : 'albumartist',
        'artist'        : 'artist',
        'conductor'     : 'conductor',
        'remixer'       : 'remixer',
        'composer'      : 'composer',
        'lyricist'      : 'lyricist',
        'performer'     : 'performer',
        'publisher'     : 'publisher',
        'label'         : 'label',
        'license'       : 'license',
        'tracknumber'   : 'tracknumber',
        'totaltracks'   : 'totaltracks',
        'tracktotal'    : 'tracktotal',
        'discnumber'    : 'discnumber',
        'totaldiscs'    : 'totaldiscs',
        'disctotal'     : 'disctotal',
        'date'          : 'date',
        'isrc'          : 'isrc',
        'encoded-by'    : 'encoded-by',
        'encoder'       : 'encoder',
        'genre'         : 'genre',
        'compilation'   : 'compilation',
        'comment'       : 'comment',
        'copyright'     : 'copyright',
        'language'      : 'language',
        'description'   : 'description'
    }
}

PRESETS = {
    'dxd':    {
        'max_sample_rate'     : 384000,
        'max_bits_per_sample' :     24,
        'format'              : 'FLAC',
        'extension'           : 'flac',
        'art_format'          :  'png',
        'art_resolution'      :   None
    },
    'ldac':   {
        'max_sample_rate'     :  96000,
        'max_bits_per_sample' :     24,
        'format'              : 'FLAC',
        'extension'           : 'flac',
        'art_format'          :  'png',
        'art_resolution'      :    800
    },
    'cd':     {
        'max_sample_rate'     :  48000,
        'max_bits_per_sample' :     24,
        'format'              : 'FLAC',
        'extension'           : 'flac',
        'art_format'          :  'png',
        'art_resolution'      :    800
    },
    ## Reference: https://images.apple.com/itunes/mastered-for-itunes/docs/mastered_for_itunes.pdf
    'itunes': {
        'bitrate'             : 256000,
        'format'              :  'M4A',
        'extension'           :  'm4a',
        'art_format'          : 'jpeg',
        'art_resolution'      :    640
    },
    'aac': {
        'max_sample_rate'     :  48000,
# variable bitrate (-vbr) mode: 1, 2, 3, 4, and 5. (Reference: http://wiki.hydrogenaud.io/index.php?title=Fraunhofer_FDK_AAC#Bitrate_Modes)
        'bitrate'             :      5,
        'format'              :  'M4A',
        'extension'           :  'm4a',
        'art_format'          : 'jpeg',
        'art_resolution'      :    640
    },
    'opus': {
        'max_sample_rate'     :  48000,
        'bitrate'             :    128, ## kbps
        'format'              :  'OGG',
        'extension'           :  'opus',
        'art_format'          : 'jpeg',
        'art_resolution'      :    640
    },
    'radio':  {
        'max_sample_rate'     :  48000,
        'bitrate'             :    128, ## kbps
        'format'              :  'MP3',
        'extension'           :  'mp3',
        'art_format'          : 'jpeg',
        'art_resolution'      :    200
    }
}

DEFAULT_CHECKSUM_PROG = 'sha224sum'
SAFE_PATH_CHARS = ' _'

def hostname():
    return run(['hostname','-f'], check=True, stdout=PIPE).stdout.decode().splitlines()[0]

def nwidechars(s):
    return sum(unicodedata.east_asian_width(x)=='W' for x in s)

def width(s):
    return len(s)+nwidechars(s)

def uljust(s, w):
    return s.ljust(w-nwidechars(s))

def wait_file(filepath, timeout=5.0):
    t   = 0.0
    dt  = 0.1
    tic = time()
    while (t < timeout) and (not path.isfile(filepath)):
        sleep(dt)
        t = time()-tic
    return path.isfile(filepath)

def load_tags(audio_file):
    """Load tags from audio file.

Reference:
http://age.hobba.nl/audio/mirroredpages/ogg-tagging.html

"""
    if audio_file.lower().endswith('.dsf'):
        audio = DSF(audio_file)
        scheme = 'ID3'
    elif audio_file.lower().endswith('.flac'):
        audio = FLAC(audio_file)
        scheme = 'Vorbis'
    elif audio_file.lower().endswith('.m4a'):
        audio = MP4(audio_file)
        scheme = 'MP4'
    elif audio_file.lower().endswith('.mp3'):
        audio = MP3(audio_file)
        scheme ='ID3'
    elif audio_file.lower().endswith('.opus'):
        audio = OggOpus(audio_file)
        scheme = 'Vorbis'
    else:
        raise TypeError(u'unsupported audio file format {}.'.format(audio_file))
    meta = {}
    if scheme == 'ID3':
        for k in TAG_MAP[scheme]:
            if TAG_MAP[scheme][k] in audio.keys():
                if k == 'date':
                    meta[k] = audio[TAG_MAP[scheme][k]][0].get_text()
                elif k == 'discnumber':
                    try:
                        meta[k], meta['totaldiscs'] = map(int, audio[TAG_MAP[scheme][k]][0].split('/'))
                    except ValueError:
                        meta[k] = int(audio[TAG_MAP[scheme][k]][0])
                        meta['totaldiscs'] = 0
                elif k == 'tracknumber':
                    try:
                        meta[k], meta['totaltracks'] = map(int, audio[TAG_MAP[scheme][k]][0].split('/'))
                    except ValueError:
                        meta[k] = int(audio[TAG_MAP[scheme][k]][0])
                        meta['totaltracks'] = 0
                elif k == 'year':
                    meta[k] = str(ID3TimeStamp(audio[TAG_MAP[scheme][k]][0]).year)
                    if 'date' not in meta:
                        meta['date'] = ID3TimeStamp(audio[TAG_MAP[scheme][k]][0]).get_text()
                elif k == 'compilation':
                    meta[k] = bool(int(audio[TAG_MAP[scheme][k]][0]))
                elif k == 'genre':
                    meta[k] = audio[TAG_MAP[scheme][k]].genres
                else:
                    meta[k] = audio[TAG_MAP[scheme][k]].text[0]
            if k == 'comment':
                meta[k] = []
                for kk in audio.keys():
                    if kk.lower().startswith('comm'):
                        meta[k] += audio[kk].text
    elif scheme == 'MP4':
        for k in TAG_MAP[scheme]:
            if TAG_MAP[scheme][k] in audio.keys():
                if k == 'date':
                    meta[k] = audio[TAG_MAP[scheme][k]][0]
                    meta['year'] = str(ID3TimeStamp(meta['date']).year)
                elif k == 'discnumber':
                    try:
                        meta[k], meta['totaldiscs'] = audio[TAG_MAP[scheme][k]][0]
                    except ValueError:
                        meta[k] = audio[TAG_MAP[scheme][k]][0]
                        meta['totaldiscs'] = 0
                elif k == 'tracknumber':
                    try:
                        meta[k], meta['totaltracks'] = audio[TAG_MAP[scheme][k]][0]
                    except ValueError:
                        meta[k] = audio[TAG_MAP[scheme][k]][0]
                        meta['totaltracks'] = 0
                elif k == 'year':
                    meta[k] = str(ID3TimeStamp(audio[TAG_MAP[scheme][k]][0]).year)
                    if 'date' not in meta:
                        meta['date'] = ID3TimeStamp(audio[TAG_MAP[scheme][k]][0]).get_text()
                elif k == 'compilation':
                    meta[k] = bool(int(audio[TAG_MAP[scheme][k]][0]))
                elif TAG_MAP[scheme][k].startswith('----'):
                    ## MP4 freeform keys start with '----' and only accept bytearray instead of str.
                    meta[k] = list(map(MP4FreeForm.decode, audio[TAG_MAP[scheme][k]]))
                else:
                    meta[k] = audio[TAG_MAP[scheme][k]][0]
    elif scheme == 'Vorbis':
        for k in TAG_MAP[scheme]:
            if TAG_MAP[scheme][k] in audio.keys():
                if k == 'date':
                    meta[k] = audio[TAG_MAP[scheme][k]][0]
                    meta['year'] = str(ID3TimeStamp(meta['date']).year)
                elif k == 'discnumber':
                    try:
                        meta[k], meta['totaldiscs'] = map(int, audio[TAG_MAP[scheme][k]][0].split('/'))
                    except ValueError:
                        meta[k] = int(audio[TAG_MAP[scheme][k]][0])
                        meta['totaldiscs'] = 0
                elif k == 'tracknumber':
                    try:
                        meta[k], meta['totaltracks'] = map(int, audio[TAG_MAP[scheme][k]][0].split('/'))
                    except ValueError:
                        meta[k] = int(audio[TAG_MAP[scheme][k]][0])
                        meta['totaltracks'] = 0
                elif k in ['totaldiscs', 'disctotal']:
                    meta['totaldiscs'] = int(audio[TAG_MAP[scheme][k]][0])
                elif k in ['totaltracks', 'tracktotal']:
                    meta['totaltracks'] = int(audio[TAG_MAP[scheme][k]][0])
                elif k == 'year':
                    meta[k] = str(ID3TimeStamp(audio[TAG_MAP[scheme][k]][0]).year)
                    if 'date' not in meta:
                        meta['date'] = ID3TimeStamp(audio[TAG_MAP[scheme][k]][0]).get_text()
                elif k == 'compilation':
                    meta[k] = False
                    if len(audio[TAG_MAP[scheme][k]][0]) > 0:
                        try:
                            meta[k] = bool(int(audio[TAG_MAP[scheme][k]][0]))
                        except ValueError:
                            meta[k] = True
                else:
                    meta[k] = audio[TAG_MAP[scheme][k]][0]
    return meta

def save_tags(meta, audio_file):
    """Save metadata to specified audio file.
"""
    if audio_file.lower().endswith('.dsf'):
        audio = DSF(audio_file)
        scheme = 'ID3'
    elif audio_file.lower().endswith('.flac'):
        audio = FLAC(audio_file)
        scheme = 'Vorbis'
    elif audio_file.lower().endswith('.m4a'):
        audio = MP4(audio_file)
        scheme = 'MP4'
    elif audio_file.lower().endswith('.mp3'):
        audio = MP3(audio_file)
        scheme ='ID3'
    elif audio_file.lower().endswith('.opus'):
        audio = OggOpus(audio_file)
        scheme = 'Vorbis'
    else:
        raise TypeError(u'unsupported audio file format {}.'.format(audio_file))
    if scheme == 'ID3':
        for k in meta:
            if k in TAG_MAP[scheme]:
                if k == 'date':
                    audio[TAG_MAP[scheme][k]] = TextFrame(encoding=3, text=[ID3TimeStamp(meta[k])])
                elif k == 'discnumber':
                    if meta['totaldiscs'] > 0:
                        audio[TAG_MAP[scheme][k]] = TextFrame(encoding=3, text=['{:d}/{:d}'.format(meta[k], meta['totaldiscs'])])
                    else:
                        audio[TAG_MAP[scheme][k]] = TextFrame(encoding=3, text=['{:d}'.format(meta[k])])
                elif k == 'tracknumber':
                    if meta['totaltracks'] > 0:
                        audio[TAG_MAP[scheme][k]] = TextFrame(encoding=3, text=['{:d}/{:d}'.format(meta[k], meta['totaltracks'])])
                    else:
                        audio[TAG_MAP[scheme][k]] = TextFrame(encoding=3, text=['{:d}'.format(meta[k])])
                elif k == 'compilation':
                    audio[TAG_MAP[scheme][k]] = TextFrame(encoding=3, text=[str(int(meta[k]))])
                else:
                    audio[TAG_MAP[scheme][k]] = TextFrame(encoding=3, text=[meta[k]])
    elif scheme == 'MP4':
        for k in meta:
            if k in TAG_MAP[scheme]:
                if k == 'discnumber':
                    audio[TAG_MAP[scheme][k]] = [(meta[k], meta['totaldiscs'])]
                elif k == 'tracknumber':
                    audio[TAG_MAP[scheme][k]] = [(meta[k], meta['totaltracks'])]
                elif k == 'compilation':
                    audio[TAG_MAP[scheme][k]] = int(meta[k])
                elif TAG_MAP[scheme][k].startswith('----'):
                    audio[TAG_MAP[scheme][k]] = list(map(lambda x:MP4FreeForm(x.encode('utf-8')), meta[k]))
                else:
                    audio[TAG_MAP[scheme][k]] = meta[k]
    elif scheme == 'Vorbis':
        for k in meta:
            if k in TAG_MAP[scheme]:
                if k in ['discnumber', 'tracknumber', 'totaldiscs', 'totaldracks', 'compilation']:
                    audio[TAG_MAP[scheme][k]] = '{:d}'.format(int(meta[k]))
                else:
                    audio[TAG_MAP[scheme][k]] = meta[k]
    audio.save()

def copy_tags(src, dest, keys=None):
    """Copy tags from source audio file to destined audio file.
"""
    meta = load_tags(src)
    try:
        tags = {k:meta[k] for k in keys}
    except TypeError:
        tags = meta
    save_tags(tags, dest)

def genpath(s):
    """Generate valid path from input string.
"""
    p = ''
    for x in s:
        if x.isalpha() or x.isdigit() or x in SAFE_PATH_CHARS:
            p+=x
        else:
            p+='_'
    return p.strip()

def add_cover_art(audio_file, picture_file):
    if audio_file.lower().endswith('.flac'):
        metadata = FLAC(audio_file)
        coverart = Picture()
        coverart.type = 3
        if picture_file.lower().endswith('.png'):
            mime = 'image/png'
        else:
            mime = 'image/jpeg'
        coverart.desc = 'front cover'
        with open(picture_file, 'rb') as f:
            coverart.date = f.read()
        metadata.add_picture(coverart)
    elif audio_file.endswith('.m4a'):
        metadata = MP4(audio_file)
        with open(picture_file, 'rb') as f:
            if picture_file.lower().endswith('.png'):
                metadata['covr'] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_PNG)]
            else:
                metadata['covr'] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]
    elif audio_file.endswith('.mp3'):
        metadata = ID3(audio_file)
        with open(picture_file, 'rb') as f:
            metadata['APIC'] = APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc=u'Cover',
                data=f.read()
            )
    else:
        assert False, 'unsupported audio file format.'
    metadata.save()

def get_source_file_checksum(audio_file):
    prog = None
    csum = None
    tags = load_tags(audio_file)
    if 'comment' in tags:
        cmts = tags['comment']
        if isinstance(cmts, list):
            cmts = '\n'.join(cmts)
        for cmt in cmts.splitlines():
            if cmt.lower().startswith('source checksum program:'):
                prog = cmt.split(':')[1].strip()
            elif cmt.lower().startswith('source file checksum:'):
                csum = cmt.split(':')[1].strip()
    return {'program': prog, 'checksum': csum}

def set_source_file_checksum(audio_file, csum, program=DEFAULT_CHECKSUM_PROG):
    if  audio_file.lower().endswith('.flac'):
        metadata = FLAC(audio_file)
        scheme = 'Vorbis'
    elif audio_file.lower().endswith('.opus'):
        metadata = OggOpus(audio_file)
        scheme = 'Vorbis'
    elif audio_file.lower().endswith('.dsf'):
        metadata = DSF(audio_file)
        scheme = 'ID3'
    elif audio_file.lower().endswith('.mp3'):
        metadata = MP3(audio_file)
        scheme = 'ID3'
    elif audio_file.lower().endswith('.m4a'):
        metadata = MP4(audio_file)
        scheme = 'MP4'
    else:
        raise TypeError(u'unsupported audio format {}.'.format(audio_file))
    if scheme=='ID3':
        if TAG_MAP[scheme]['comment'] in metadata.tags.keys():
            metadata.tags[TAG_MAP[scheme]['comment']] = COMM(encoding=3, text=['\n'.join([
                metadata.tags[TAG_MAP[scheme]['comment']][0],
                u'Source Checksum Program: {}'.format(program),
                u'Source File Checksum: {}'.format(csum)])])
        else:
            metadata.tags[TAG_MAP[scheme]['comment']] = COMM(encoding=3, text=['\n'.join([
                u'Source Checksum Program: {}'.format(program),
                u'Source File Checksum: {}'.format(csum)])])
    else:
        if TAG_MAP[scheme]['comment'] in metadata.tags.keys():
            if isinstance(metadata.tags[TAG_MAP[scheme]['comment']], str):
                cmt = '\n'.join([
                    metadata.tags[TAG_MAP[scheme]['comment']],
                    u'Source Checksum Program: {}'.format(program),
                    u'Source File Checksum: {}'.format(csum)
                ])
            elif isinstance(metadata.tags[TAG_MAP[scheme]['comment']], list):
                cmt = '\n'.join([
                    '\n'.join(metadata.tags[TAG_MAP[scheme]['comment']]),
                    u'Source Checksum Program: {}'.format(program),
                    u'Source File Checksum: {}'.format(csum)
                ])
            else:
                raise TypeError(u'target tag is neither str nor list.')
            metadata.tags[TAG_MAP[scheme]['comment']] = cmt
        else:
            metadata.tags[TAG_MAP[scheme]['comment']] = '\n'.join([
                u'Source Checksum Program: {}'.format(program),
                u'Source File Checksum: {}'.format(csum)])
    metadata.save()

def find_tracks(srcdir):
    """Find all SONY Music tracks (*.flac and *.dsf).
"""
    result = run([
        'find', path.abspath(srcdir), '-type', 'f',
        '-name', '*.flac', '-or', '-name', '*.dsf'
    ], check=True, stdout=PIPE, stderr=DEVNULL)
    tracks = []
    for p in result.stdout.decode().splitlines():
        if path.isfile(p):
            tracks.append(path.normpath(path.abspath(p)))
    return tracks

def gen_opus_tagopts(tags):
    """Generate opusenc metadata options.
"""
    opts = []
    for k in tags:
        if k in ['title', 'artist', 'album', 'tracknumber', 'date', 'genre']:
            opts += ['--{}'.format(k), '{}'.format(tags[k])]
        elif k == 'comment':
            opts += ['--comment', '{}={}'.format('comment', tags[k])]
        elif k in TAG_MAP['Vorbis']:
            opts += ['--comment', '{}={}'.format(k.upper(), tags[k])]
    return opts

def gen_flac_tagopts(tags):
    """Generate FLAC Tagging options.
"""
    opts = []
    for k in tags:
        if k in TAG_MAP['Vorbis']:
            if isinstance(tags[k], list):
                for opt in [['-T', '{}={}'.format(TAG_MAP['Vorbis'][k].upper(), v)] for v in tags[k]]:
                    opts += opt
            else:
                opts += ['-T', '{}={}'.format(TAG_MAP['Vorbis'][k].upper(), tags[k])]
    return opts

class AudioTrack(object):
    def __init__(self, filepath):
        ## examine path
        if not path.isfile(filepath):
            raise FileNotFoundError(u'Audio track file does not exist.'.format(filepath))
        self.source = path.normpath(path.abspath(filepath))
        self.file = {
            'size'  : path.getsize(self.source),
            'ctime' : path.getctime(self.source)
        }
        extname = path.splitext(self.source)[1]
        if extname.lower() in ['.dsf']:
            self.format = 'DSD'
        elif extname.lower() in ['.flac']:
            self.format = 'FLAC'
        else:
            raise TypeError(u'Audio format {} is not supported.'.format(extname))
        self.UpdateMetadata()
        self.UpdateFileChecksum()
        self.id        = hashlib.sha224('{}{}'.format(self.GenPath(), extname).encode('utf-8')).hexdigest()
        self.parent_id = hashlib.sha224(self.GenParentPath().encode('utf-8')).hexdigest()

    def GenFilename(self):
        if not hasattr(self, 'metadata'):
            self.UpdateMetadata()
        try:
            return '{:d}.{:02d} - {}'.format(
                self.metadata['discnumber'],
                self.metadata['tracknumber'],
                genpath(self.metadata['title'])
            )
        except KeyError:
            return '{:02d} - {}'.format(
                self.metadata['tracknumber'],
                genpath(self.metadata['title'])
            )

    def GenParentPath(self):
        if not hasattr(self, 'metadata'):
            self.UpdateMetadata()
        return path.join(
            genpath(self.metadata['albumartist']),
            genpath(self.metadata['album'])
        )

    def GenPath(self):
        return path.join(self.GenParentPath(), self.GenFilename())

    def UpdateFileChecksum(self, program=DEFAULT_CHECKSUM_PROG):
        self.file_checksum = {
            'program': program,
            'checksum': run([
                program, '-b', self.source
            ], check=True, stdout=PIPE, stderr=DEVNULL).stdout.decode().split()[0]
        }

    def UpdateMetadata(self):
        if self.format == 'DSD':
            scheme = 'ID3'
            metadata = DSF(self.source)
        elif self.format == 'FLAC':
            scheme = 'Vorbis'
            metadata = FLAC(self.source)
        else:
            assert False, 'unsupported format {}.'.format(self.formmat)
        self.metadata = load_tags(self.source)
        if 'albumartist' not in self.metadata:
            try:
                self.metadata['albumartist'] = self.metadata['artist']
            except KeyError:
                self.metadata['artist'] = self.metadata['performer']
                self.metadata['albumartist'] = self.metadata['performer']
        self.metadata['info'] = {
            'sample_rate'     : metadata.info.sample_rate,
            'bits_per_sample' : metadata.info.bits_per_sample,
            'channels'        : metadata.info.channels,
            'bitrate'         : metadata.info.bitrate,
            'length'          : metadata.info.length
        }
        return self.metadata

    def Export(self, filepath, preset, exists, bitrate):
        """Export this audio track with specified preset.
"""
        if not hasattr(self, 'file_checksum'):
            self.UpdateFileChecksum()
        if path.isfile(filepath):
            if exists.lower()[0] == 's':
                ## skip
                return filepath
            elif exists.lower()[0] == 'u':
                ## update
                if self.file_checksum == get_source_file_checksum(filepath):
                    return filepath
        coverart_path = path.join(path.split(filepath)[0], 'cover.{}'.format(PRESETS[preset]['art_format']))
        if preset.lower() in ['dxd', 'ldac', 'cd']:
            if self.format == 'DSD':
                ## dsf ------> aiff ------------> flac/opus
                ##     ffmpeg       flac/opusenc
                if self.metadata['info']['sample_rate'] > int(PRESETS[preset]['max_sample_rate']/48000+0.5)*44100*16:
                    sample_rate=int(PRESETS[preset]['max_sample_rate']/48000+0.5)*44100
                else:
                    sample_rate=int(self.metadata['info']['sample_rate']/44100/16+0.5)*44100
                ffmpeg = Popen([
                    'ffmpeg', '-y', '-i', self.source,
                    '-af', 'aresample=resampler=soxr:precision=28:dither_method=triangular:osr={:d},volume=+6dB'.format(sample_rate),
                    '-vn', '-map_metadata', '-1',
                    '-c:a', 'pcm_s24be',
                    '-f', 'aiff', '-'
                ], stdout=PIPE, stderr=DEVNULL)
                flac_enc = Popen([
                    'flac', '-', '-f',
                    '--picture', '3|image/png|Cover||{}'.format(coverart_path),
                    '--ignore-chunk-sizes', '--force-aiff-format',
                    *gen_flac_tagopts(self.metadata),
                    '-o', filepath
                ], stdin=ffmpeg.stdout, stderr=DEVNULL)
                flac_enc.communicate()
            else:
                q = int(self.metadata['info']['sample_rate']/44100+0.5)
                b = self.metadata['info']['sample_rate'] // q
                if q > PRESETS[preset]['max_sample_rate']//48000:
                    sample_rate = PRESETS[preset]['max_sample_rate']//48000*b
                    ## resample is required.
                    flac_dec = Popen([
                        'flac', self.source, '-d', '-c'
                    ], stdout=PIPE, stderr=DEVNULL)
                    ffmpeg = Popen([
                        'ffmpeg', '-i', '-',
                        '-af', 'aresample=resampler=soxr:precision=28:dither_method=triangular:osr={:d}'.format(sample_rate),
                        '-vn', '-map_metadata', '-1',
                        '-c:a', 'pcm_s24be',
                        '-f', 'aiff', '-'
                    ], stdin=flac_dec.stdout, stdout=PIPE, stderr=DEVNULL)
                    flac_enc = Popen([
                        'flac', '-', '-f',
                        '--picture', '3|image/png|Cover||{}'.format(path.join(path.split(filepath)[0], 'cover.png')),
                        '--ignore-chunk-sizes', '--force-aiff-format',
                        *gen_flac_tagopts(self.metadata),
                        '-o', filepath
                    ], stdin=ffmpeg.stdout, stdout=DEVNULL, stderr=DEVNULL)
                    flac_enc.communicate()
                else:
                    shutil.copyfile(self.source, filepath)
                    ## substitute cover art
                    audio = FLAC(filepath)
                    audio.clear_pictures()
                    audio.save()
                    add_cover_art(filepath, path.join(path.split(filepath)[0], 'cover.png'))
        elif preset.lower() in ['itunes']:
            with TemporaryDirectory(prefix=self.id, dir=path.split(filepath)[0]) as tmpdir:
                if self.format == 'DSD':
                    src = path.join(tmpdir, 'a.aiff')
                    run([
                        'ffmpeg', '-y', '-i', self.source,
                        '-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=352800,volume=+6dB',
                        '-c:a', 'pcm_s24be',
                        '-f', 'aiff', src
                    ], check=True, stdout=DEVNULL, stderr=DEVNULL)
                else:
                    src = self.source
                if not wait_file(src):
                    raise FileNotFoundError(u'{} (source) not found.'.format(src))
                caff = path.join(tmpdir, 'a.caf')
                run([
                    'afconvert', src,
                    '-d', 'LEF32@44100',
                    '-f', 'caff',
                    '--soundcheck-generate',
                    '--src-complexity', 'bats',
                    '-r', '127', caff
                ], check=True)
                if not wait_file(caff):
                    raise FileNotFoundError(u'{} (caff) not found.'.format(caff))
                run([
                    'afconvert', caff,
                    '-d', 'aac',
                    '-f', 'm4af',
                    '-u', 'pgcm', '2',
                    '--soundcheck-read',
                    '-b', '{:d}'.format(PRESETS[preset]['bitrate']),
                    '-q', '127',
                    '-s', '2', filepath
                ], check=True)
                if not wait_file(filepath):
                    raise FileNotFoundError(u'{} (m4a) not found.'.format(filepath))
            copy_tags(self.source, filepath)
            add_cover_art(filepath, path.join(
                path.split(filepath)[0],
                'cover.{}'.format(PRESETS[preset]['art_format'])
            ))
        elif preset.lower() in ['aac']:
            if bitrate is None:
                bitrate = str(PRESETS[preset]['bitrate'])
            qu = self.metadata['info']['sample_rate']//44100
            br = self.metadata['info']['sample_rate']//qu
            sr = br * min((PRESETS[preset]['max_sample_rate']//44100), qu)
            if self.format == 'DSD':
                gain = ',volume=+6dB'
            else:
                gain = ''
            run([
                'ffmpeg', '-y', '-i', self.source,
                '-af', 'aresample=resampler=soxr:precision=24:dither_method=triangular:osr={:d}{}'.format(sr, gain),
                '-vn', '-c:a', 'libfdk_aac', '-vbr', bitrate, filepath
            ], check=True, stdout=DEVNULL, stderr=DEVNULL)
            add_cover_art(filepath, path.join(
                path.split(filepath)[0],
                'cover.{}'.format(PRESETS[preset]['art_format'])
            ))
        elif preset.lower() in ['opus']:
            b = 48000 ## according to official opus codec RFC 6716 MDCT (modified discrete cosine transform)
                      ## layer of opus encoder always operates on 48kHz sampling rate.
            if bitrate is None:
                bitrate = str(PRESETS[preset]['bitrate'])
            if self.format == 'DSD':
                gain = ',volume=+6dB'
            else:
                gain = ''
            ffmpeg = Popen([
                'ffmpeg', '-y', '-i', self.source,
                '-af', 'aresample=resampler=soxr:precision=28:dither_method=triangular:osr={:d}{}'.format(b, gain),
                '-vn', '-map_metadata', '-1',
                '-c:a', 'pcm_s24le',
                '-f', 'wav', '-'
            ], stdout=PIPE, stderr=DEVNULL)
            opus_enc = Popen([
                'opusenc', '-',
                '--picture', '3||Cover||{}'.format(coverart_path),
                '--raw', '--raw-bits', '24', '--raw-rate', '{:d}'.format(b), '--raw-chan', '2',
                '--music', '--framesize', '60', '--comp', '10', '--vbr',
                '--bitrate', '{}k'.format(bitrate),
                *gen_opus_tagopts(self.metadata),
                filepath
            ], stdin=ffmpeg.stdout, stderr=DEVNULL)
            opus_enc.communicate()
        elif preset.lower() in ['radio']:
            if bitrate is None:
                bitrate = str(PRESETS[preset]['bitrate'])
            q = self.metadata['info']['sample_rate']//44100
            b = self.metadata['info']['sample_rate']//q
            if self.format == 'DSD':
                gain = ',volume=+6dB'
            else:
                gain = ''
            run([
                'ffmpeg', '-y', '-i', self.source,
                '-af', 'aresample=resampler=soxr:precision=24:dither_method=triangular:osr={:d}{}'.format(b, gain),
                '-vn', '-c:a', 'libmp3lame', '-b:a', '{}k'.format(bitrate), filepath
            ], check=True, stdout=DEVNULL, stderr=DEVNULL)
            add_cover_art(filepath, path.join(
                path.split(filepath)[0],
                'cover.{}'.format(PRESETS[preset]['art_format'])
            ))
        else:
            raise TypeError(u'unsupported preset {}.'.format(preset))
        if not wait_file(filepath):
            raise FileNotFoundError(u'{} not found.'.format(filepath))
        set_source_file_checksum(
            filepath,
            self.file_checksum['checksum'],
            program=self.file_checksum['program']
        )
        return filepath

    def ExtractCoverArt(self, filepath):
        run(['ffmpeg', '-y', '-i', self.source,
             '-an', '-c:v', 'png', filepath
        ], check=True, stdout=DEVNULL, stderr=DEVNULL)
        return filepath

    def Print(self):
        print('    {:<20}: {:<80}'.format('Source',                self.source))
        print('    {:<20}: {:<80}'.format('Format',                self.format))
        print('    {:<20}: {:<80}'.format('Track No.',             self.metadata['tracknumber']))
        print('    {:<20}: {:<80}'.format('Title',                 self.metadata['title']))
        print('    {:<20}: {:<80}'.format('Album',                 self.metadata['album']))
        print('    {:<20}: {:<80}'.format('Artist',                self.metadata['albumartist']))
        print('    {:<20}: {:<80}'.format('Genre',                 self.metadata['genre']))
        print('    {:<20}: {:.1f} kHz'.format('Sample rate', float(self.metadata['info']['sample_rate'])/1000.0))
        print('    {:<20}: {:<80}'.format('Bits per sample',       self.metadata['info']['bits_per_sample']))
        print('    {:<20}: {:<80}'.format('Channels',              self.metadata['info']['channels']))
        print('    {:<20}: {:.1f} kbits/s'.format('Bitrate', float(self.metadata['info']['bitrate'])/1000.0))
        return

class Album(list):
    def __init__(self, title=None, artist=None):
        self.title  = title
        self.artist = artist
        self.id     = hashlib.sha224(self.GenPath().encode('utf-8')).hexdigest()

    def GenPath(self):
        return path.join(genpath(self.artist), genpath(self.title))

    def ExtractCoverArt(self, prefix):
        self.cover_art_path = path.join(prefix, '{}.png'.format(self.id))
        if not wait_file(self[0].ExtractCoverArt(self.cover_art_path)):
            raise FileNotFoundError(u'cover art picture file not found.')
        return self.GetCoverArtInfo()

    def GetCoverArtInfo(self):
        result = run([
            'identify', self.cover_art_path
        ], check=True, stdout=PIPE).stdout.decode()
        info = dict(zip([
            'format',
            'geometry',
            'page_geometry',
            'depth',
            'colorspace',
            'filesize',
            'user_time',
            'elapsed_time'
        ], result.split('.png')[1].split()))
        info['width']  = int(info['geometry'].split('x')[0])
        info['height'] = int(info['geometry'].split('x')[1])
        self.cover_art_info = info
        return info

def __import_worker__(q_in, q_out):
    pack_in = q_in.get()
    while pack_in is not None:
        q_out.put(AudioTrack(pack_in))
        pack_in = q_in.get()

def __export_worker__(q_in, q_out):
    pack_in = q_in.get()
    while pack_in is not None:
        tobj, outfile, preset, exists, bitrate = pack_in
        q_out.put(tobj.Export(outfile, preset, exists, bitrate))
        pack_in = q_in.get()

def __extract_worker__(q_in, q_out):
    pack_in = q_in.get()
    while pack_in is not None:
        aobj, prefix = pack_in
        aobj.ExtractCoverArt(prefix)
        q_out.put(aobj)
        pack_in = q_in.get()

class Library(object):
    """SONY Music Library.
"""
    def Build(self, libroot, outdir):
        """Build SONY Music Library from source directory.
"""
        self.source = path.normpath(path.abspath(libroot))
        if path.exists(outdir):
            assert False, 'output directory already exists.'
        os.makedirs(outdir)
        ##
        ## initialize containers.
        tracks = find_tracks(self.source)
        self.tracks = {}
        self.albums = {}
        self.arts_path = path.join(outdir, 'arts')
        self.checksum_path = path.join(outdir, '{}.txt'.format(DEFAULT_CHECKSUM_PROG))
        self.ImportTracks(tracks)
        self.UpdateAlbums()
        self.ExtractCoverArts()
        print(u'{:d} audio tracks of {:d} album(s) loaded.'.format(len(self.tracks), len(self.albums)))
        return

    def ImportTracks(self, tracks):
        """Import SONY Music tracks.
"""
        tic = time()
        new_tracks = []
        q_file   = Queue()
        q_obj    = Queue()
        workers  = []
        nworkers = max(2, cpu_count())
        ntrks = len(tracks)
        for i in range(nworkers):
            proc = Process(target=__import_worker__, args=(q_file, q_obj))
            proc.start()
            workers.append(proc)
        sys.stdout.write(u'Importing audio tracks......')
        sys.stdout.flush()
        for t in tracks:
            q_file.put(t)
        i = 0
        while i < ntrks:
            tobj = q_obj.get()
            self.tracks[tobj.id] = tobj
            i += 1
            sys.stdout.write(u'\rImporting audio tracks......{:d}/{:d} ({:5.1f}%)'.format(i, ntrks, 100.0*i/ntrks))
            sys.stdout.flush()
        for i in range(nworkers):
            q_file.put(None)
        for proc in workers:
            proc.join()
        run(['stty', 'sane'], stdout=DEVNULL, stderr=DEVNULL)
        sys.stdout.write(u'\rImporting audio tracks......Finished. ({:.2f} seconds)\n'.format(time()-tic))
        sys.stdout.flush()
        for t in new_tracks:
            if t.id not in self.tracks:
                self.tracks[t.id] = t

    def UpdateAlbums(self):
        self.albums = {}
        tic = time()
        sys.stdout.write(u'Updating albums......')
        sys.stdout.flush()
        for t in self.tracks.values():
            if t.parent_id not in self.albums:
                self.albums[t.parent_id] = Album(title=t.metadata['album'], artist=t.metadata['albumartist'])
            self.albums[t.parent_id].append(t)
        sys.stdout.write(u'\rUpdating albums......Finished. ({:.2f} seconds)\n'.format(time()-tic))
    
    def ExtractCoverArts(self):
        """Extract album cover arts.
"""
        if not path.exists(self.arts_path):
            os.makedirs(self.arts_path)
        q_alb = Queue()
        q_pic = Queue()
        workers = []
        nworkers = cpu_count()
        nalbs = len(self.albums)
        for i in range(nworkers):
            proc = Process(target=__extract_worker__, args=(q_alb, q_pic))
            proc.start()
            workers.append(proc)
        for a in self.albums.values():
            q_alb.put((a, self.arts_path))
        tic = time()
        sys.stdout.write('Extracting album cover arts......')
        sys.stdout.flush()
        i = 0
        while i < nalbs:
            a = q_pic.get()
            self.albums[a.id] = a
            i += 1
            sys.stdout.write(u'\rExtracting album cover arts......{:d}/{:d} ({:5.1f}%)'.format(i, nalbs, 100.0*i/nalbs))
            sys.stdout.flush()
        sys.stdout.write(u'\rExtracting album cover arts......Finished. ({:.2f} seconds)\n'.format(time()-tic))
        sys.stdout.flush()
        run(['stty', 'sane'], stdout=DEVNULL, stderr=DEVNULL)
        for i in range(nworkers):
            q_alb.put(None)
        for proc in workers:
            proc.join()

    def SortCoverArts(self, sortkey, reverse=False):
        """Sort album cover arts.
"""
        if reverse:
            print("Album cover arts sorted by {} (reversed):".format(sortkey))
        else:
            print("Album cover arts sorted by {}:".format(sortkey))
        alb_sorted = sorted(self.albums.keys(), key=lambda alb:self.albums[alb].cover_art_info[sortkey], reverse=reverse)
        artist_width = max([width(self.albums[alb].artist) for alb in alb_sorted])
        albnam_width = max([width(self.albums[alb].title)  for alb in alb_sorted])
        for alb in alb_sorted:
            print(u'{} {} {}'.format(
                uljust(self.albums[alb].artist, artist_width+4),
                uljust(self.albums[alb].title, albnam_width+4),
                self.albums[alb].cover_art_info[sortkey]
            ))

    def Update(self):
        """Update pre-built SONY Music Library.
"""
        tracks = self.tracks
        self.tracks = {}
        for tid in tracks:
            if path.isfile(tracks[tid].source):
                self.tracks[tid] = tracks[tid]
        new_tracks = []
        src_tracks = {t.source:t.file for t in self.tracks.values()}
        for t in find_tracks(self.source):
            if t in src_tracks:
                if path.getctime(t) > src_tracks[t]['ctime'] or path.getsize(t) != src_tracks[t]['size']:
                    new_tracks.append(t)
            else:
                new_tracks.append(t)
        self.ImportTracks(new_tracks)
        self.UpdateAlbums()
        self.ExtractCoverArts()
        print(u'{:d} audio tracks of {:d} album(s) loaded.'.format(len(self.tracks), len(self.albums)))

    def Export(self, match=None, prefix=None, preset='dxd', exists='skip', verbose=False, bitrate=None):
        """Export matched tracks.
"""
        mpi_rank = comm.Get_rank()
        mpi_size = comm.Get_size()
        if match is None:
            artist_match = ''
            album_match = ''
            track_match = ''
        else:
            artist_match, album_match, track_match = match.split('/')
        if mpi_size == 1:
            ## non-mpi parallelism, but multiprocessing
            ## prepare albums
            nalbs = len(self.albums)
            i = 0
            tic = time()
            sys.stdout.write(u'Preparing album directories......')
            sys.stdout.flush()
            for a in self.albums.values():
                i+=1
                if artist_match in a.artist and album_match in a.title:
                    if not path.exists(path.join(prefix, a.GenPath())):
                        os.makedirs(path.join(prefix, a.GenPath()))
                    if PRESETS[preset]['art_resolution'] is None:
                        args = [
                            'convert',
                            path.join(self.arts_path, '{}.png'.format(a.id)),
                            path.join(prefix, a.GenPath(), 'cover.{}'.format(PRESETS[preset]['art_format']))
                        ]
                    else:
                        args = [
                            'convert',
                            path.join(self.arts_path, '{}.png'.format(a.id)),
                            '-resize', '{:d}x{:d}>'.format(PRESETS[preset]['art_resolution'], PRESETS[preset]['art_resolution']),
                            path.join(prefix, a.GenPath(), 'cover.{}'.format(PRESETS[preset]['art_format']))
                        ]
                    run(args, check=True, stdout=DEVNULL, stderr=DEVNULL)
                sys.stdout.write(u'\rPreparing album directories......{:d}/{:d} ({:5.1f}%)'.format(i, nalbs, 100.0*i/nalbs))
                sys.stdout.flush()
            sys.stdout.write(u'\rPreparing album directories......Finished. ({:.2f} seconds)\n'.format(time()-tic))
            sys.stdout.flush()
            ## export
            to_path  = []
            tracks   = []
            for t in self.tracks.values():
                if artist_match in t.metadata['albumartist'] and album_match in t.metadata['album'] and track_match in t.GenFilename():
                    tracks.append(t)
                    to_path.append(u'{}.{}'.format(path.join(prefix, t.GenPath()), PRESETS[preset]['extension']))
            q_obj    = Queue()
            q_out    = Queue()
            ntrks    = len(tracks)
            nworkers = max(2, cpu_count())
            workers  = []
            for i in range(nworkers):
                proc = Process(target=__export_worker__, args=(q_obj, q_out))
                proc.start()
                workers.append(proc)
            for i in range(ntrks):
                q_obj.put((tracks[i], to_path[i], preset, exists, bitrate))
            tic = time()
            i = 0
            sys.stdout.write(u'Exporting audio tracks......')
            sys.stdout.flush()
            while i < ntrks:
                outfile = q_out.get()
                i += 1
                sys.stdout.write(
                    u'\rExporting audio tracks......{:d}/{:d} ({:5.1f}%)'.format(
                        i, ntrks, 100.0*i/ntrks))
                sys.stdout.flush()
            for i in range(nworkers):
                q_obj.put(None)
            for proc in workers:
                proc.join()
            sys.stdout.write(u'\r\rExporting audio tracks......Finished. ({:.2f} seconds)\n'.format(time() - tic))
            sys.stdout.flush()
            run(['stty', 'sane'], stdout=DEVNULL, stderr=DEVNULL)
        else:
            ## mpi parallelism
            tic = time()
            if mpi_rank == 0:
                nalbs = len(self.albums)
                i = 0
                tic = time()
                sys.stdout.write(u'Preparing album directories......')
                sys.stdout.flush()
                for a in self.albums.values():
                    i+=1
                    if artist_match in a.artist and album_match in a.title:
                        if not path.exists(path.join(prefix, a.GenPath())):
                            os.makedirs(path.join(prefix, a.GenPath()))
                        if PRESETS[preset]['art_resolution'] is None:
                            args = [
                                'convert',
                                path.join(self.arts_path, '{}.png'.format(a.id)),
                                path.join(prefix, a.GenPath(), 'cover.{}'.format(PRESETS[preset]['art_format']))
                            ]
                        else:
                            args = [
                                'convert',
                                path.join(self.arts_path, '{}.png'.format(a.id)),
                                '-resize', '{:d}x{:d}>'.format(PRESETS[preset]['art_resolution'], PRESETS[preset]['art_resolution']),
                                path.join(prefix, a.GenPath(), 'cover.{}'.format(PRESETS[preset]['art_format']))
                            ]
                        run(args, check=True, stdout=DEVNULL, stderr=DEVNULL)
                    sys.stdout.write(u'\rPreparing album directories......{:d}/{:d} ({:5.1f}%)'.format(i, nalbs, 100.0*i/nalbs))
                    sys.stdout.flush()
                sys.stdout.write(u'\rPreparing album directories......Finished. ({:.2f} seconds)\n'.format(time()-tic))
                sys.stdout.flush()
                sleep(1.0)
                to_path  = []
                tracks   = []
                for t in self.tracks.values():
                    if artist_match in t.metadata['albumartist'] and album_match in t.metadata['album'] and track_match in t.GenFilename():
                        tracks.append(t)
                        to_path.append(u'{}.{}'.format(path.join(prefix, t.GenPath()), PRESETS[preset]['extension']))
            else:
                tracks  = None
                to_path = None
            tracks  = comm.bcast( tracks, root=0)
            to_path = comm.bcast(to_path, root=0)
            ntrks   = len(tracks)
            node    = hostname()
            node    = comm.gather(node, root=0)
            if mpi_rank == 0:
                for i in range(mpi_size):
                    sleep(.1)
                    print(u'Process {}/{} is ready on [{}].'.format(i+1, mpi_size, node[i]))
                print(u'All processes are ready.')
                itrks = list(map(len, [tracks[i::(mpi_size-1)] for i in range(mpi_size-1)]))
                t = np.zeros(mpi_size-1, dtype='int64')
                while np.sum(t)<ntrks:
                    sleep(.5)
                    for i in range(mpi_size-1):
                        sleep(.1)
                        if t[i]<itrks[i]:
                            msg = comm.recv(source=i+1, tag=11)
                            t[i] += 1
                        sys.stdout.write(u'\rExporting audio tracks......{:d}/{:d} ({:5.1f}%)'.format(int(np.sum(t)), ntrks, 100.0*np.sum(t)/ntrks))
                        sys.stdout.flush()
                sys.stdout.write(u'\rExporting audio tracks......Finished. ({:.2f} seconds)\n'.format(time() - tic))
                sys.stdout.flush()
                run(['stty', 'sane'], stdout=DEVNULL, stderr=DEVNULL)
            else:
                for i in range(mpi_rank-1, ntrks, mpi_size-1):
                    comm.send(tracks[i].Export(to_path[i], preset, exists, bitrate), dest=0, tag=11)
                    sleep(.1)

    def Print(self, match=None, verbose=False, output=''):
        """Print matched albums and audio tracks.
"""
        if match is None:
            artist_match = ''
            album_match = ''
            track_match = ''
        else:
            artist_match, album_match, track_match = match.split('/')
        try:
            ## print to csv file
            with open(output, 'w', newline='') as csvfile:
                fields = ['albumartist', 'album', 'tracknumber', 'artist', 'title', 'genre', 'composer', 'conductor']
                writer = csv.DictWriter(csvfile, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                for t in self.tracks.values():
                    if artist_match in t.metadata['albumartist'] and album_match in t.metadata['album'] and track_match in t.GenFilename():
                        writer.writerow(t.metadata)
        except IOError:
            ## print to stdout
            for a in self.albums.values():
                if artist_match in a.artist and album_match in a.title:
                    print(u'{}/{}:'.format(a.artist, a.title))
                    for t in a:
                        if track_match in t.GenFilename():
                            try:
                                print(u'  [{:<4}] {:d}.{:02d} - {}'.format(t.format, t.metadata['discnumber'], t.metadata['tracknumber'], t.metadata['title']))
                            except KeyError:
                                print(u'  [{:<4}] {:02d} - {}'.format(t.format, t.metadata['tracknumber'], t.metadata['title']))
                            if verbose:
                                t.Print()

def save_library(obj, to_path):
    with open(to_path, 'wb') as f:
        pickle.dump(obj, f)

def load_library(from_path):
    with open(from_path, 'rb') as f:
        return pickle.load(f)

def main():
    mpi_rank = comm.Get_rank()
    mpi_size = comm.Get_size()
    action = sys.argv[1]
    opts, args = gnu_getopt(sys.argv[2:], 'vrk:m:s:p:o:e:b:')
    verbose = False
    matched = None
    exists  = 'skip'
    output  = ''
    bitrate = None
    reverse = False
    sortkey = 'width'
    for opt, val in opts:
        if opt == '-s':
            srcdir = path.normpath(path.abspath(val))
        elif opt == '-v':
            verbose = True
        elif opt == '-p':
            preset = val
        elif opt == '-m':
            matched = val
        elif opt == '-o':
            output = val
        elif opt == '-e':
            exists = val
        elif opt == '-b':
            bitrate = val
        elif opt == '-k':
            sortkey = val
        elif opt == '-r':
            reverse = True
        else:
            assert False, 'unhandled option'
    if action.lower() in ['build']:
        if mpi_rank == 0:
            outdir = path.normpath(path.abspath(args[0]))
            l = Library()
            l.Build(srcdir, path.abspath(outdir))
            save_library(l, path.join(outdir, 'main.db'))
    elif action.lower() in ['help']:
        if mpi_rank == 0:
            print(__doc__)
    elif action.lower() in ['print']:
        if mpi_rank == 0:
            l = load_library(args[0])
            l.Print(match=matched, verbose=verbose, output=output)
    elif action.lower() in ['export']:
        if mpi_rank == 0:
            l = load_library(path.normpath(path.abspath(path.realpath(args[0]))))
        else:
            l = None
        l = comm.bcast(l, root=0)
        sleep(0.5)
        l.Export(
            match=matched,
            preset=preset,
            prefix=path.normpath(path.abspath(output)),
            exists=exists,
            verbose=verbose,
            bitrate=bitrate
        )
    elif action.lower() in ['update']:
        if mpi_rank == 0:
            l = load_library(args[0])
            l.Update()
            save_library(l, args[0])
    elif action.lower().startswith('sort'):
        if mpi_rank == 0:
            l = load_library(args[0])
            l.SortCoverArts(sortkey, reverse=reverse)
    else:
        assert False, 'unhandled action'

if __name__ == '__main__':
    main()

####    def audio_stream_checksum(audio_file, program=DEFAULT_CHECKSUM_PROG):
####        """Calculate checksum of audio stream of input file.
####    """
####        with Popen(["ffmpeg", "-i", audio_file,
####                    "-vn",
####                    "-map_metadata", "-1",
####                    "-f", "aiff", "-"
####        ], stdout=PIPE, stderr=DEVNULL) as p1:
####            p2 = Popen([program, '-b', '-'], stdin=p1.stdout, stdout=PIPE, stderr=DEVNULL)
####            return p2.communicate()[0].decode().split()[0]
####    
####    def tag_m4a(metadata_in, audio_in, cover_in, outfile):
####        """Tag AAC audio file in m4a format.
####    """
####        run(['ffmpeg', '-y', '-i', metadata_in, '-i', audio_in,
####             '-map', '1:a:0', '-c:a', 'copy', '-map_metadata', '0:g:0', outfile
####        ], check=True, stdout=DEVNULL, stderr=DEVNULL)
####        return
####    
####    def tag_flac(metadata_in, audio_in, cover_in, outfile):
####        """Tag FLAC audio file.
####    """
####        run(['ffmpeg', '-y', '-i', metadata_in, '-i', audio_in, '-i', cover_in,
####             '-map', '1:a:0', '-map', '2:v:0',
####             '-c:a', 'copy', '-c:v', 'png',
####             '-metadata:s:v', 'title=\"Album cover\"',
####             '-metadata:s:v', 'comment=\"Cover (front)\"',
####             '-map_metadata', '0:g:0', outfile
####        ], check=True, stdout=DEVNULL, stderr=DEVNULL)
####        return
####    
####    def metadata_from_path(p):
####        """Guess audio file metadata from its path.
####    """
####        m = {}
####        parent, filename = path.split(path.normpath(path.abspath(p)))
####        if ' - ' in filename:
####            segs = path.splitext(filename)[0].split(' - ')
####            tracknumber = segs[0]
####            title = ' - '.join(segs[1:])
####        elif ' ' in filename:
####            segs = path.splitext(filename)[0].split()
####            tracknumber = segs[0]
####            title = ' '.join(segs[1:])
####        else:
####            title = path.splitext(filename)[0]
####            m['tracknumber'] = None
####            tracknumber = None
####        if '.' in tracknumber:
####            discnumber, tracknumber = tracknumber.split('.')
####            m['discnumber'] = int(discnumber)
####            m['tracknumber'] = int(tracknumber)
####        if '/' in tracknumber:
####            tracknumber, totaltracks = tracknumber.split('/')
####            m['totaltracks'] = int(totaltracks)
####            m['tracknumber'] = int(tracknumber)
####        m['title'] = title
####        artpath, albname = path.split(parent)
####        _, artname = path.split(artpath)
####        m['albumartist'] = artname
####        m['album'] = albname
####        return m
####    def dsd_to_flac(*args, preset='dxd', compression='-5'):
####        infile, outfile, outdir = check_converter_args(*args)
####        with TemporaryDirectory(dir=outdir) as tmpdir:
####            aiff = path.join(tmpdir, 'a.aif')
####            flac = path.join(tmpdir, 'a.flac')
####            dsd_to_aiff(infile, outfile, preset=preset)
####            run(['flac', compression, aiff, '-o', flac], check=True)
####        return

