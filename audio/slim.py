#!/usr/bin/env python3
#coding=utf-8
"""SONY Music Library Manager.

Usage: slim.py action [options]

Actions:
  build
    Build SONY Music Library, generate metadata and checksums and extract album cover arts.
    Syntax: slim.py build -s SRC DEST
    SRC is path of SONY Music Library.

Options:
  -s  source (SONY Music Library) path.

Copyright: pigsboss@github
"""

import sys
import os
import hashlib
import signal
from multiprocessing import cpu_count, Pool
from time import time
from os import path
from getopt import gnu_getopt
from subprocess import run, Popen, PIPE, DEVNULL
from tempfile import TemporaryDirectory

DEFAULT_CHECKSUM_PROG = 'sha224sum'

def file_checksum(filepath, checksum_program=DEFAULT_CHECKSUM_PROG):
    """Calculate checksum of input file.
"""
    return run([checksum_program, '-b', filepath],
               check=True, stdout=PIPE, stderr=DEVNULL).stdout.decode().split()[0]

def audio_stream_checksum(audio_file, checksum_program=DEFAULT_CHECKSUM_PROG):
    """Calculate checksum of audio stream of input file.
"""
    with Popen(["ffmpeg", "-i", audio_file,
                "-vn",
                "-map_metadata", "-1",
                "-f", "aiff", "-"
    ], stdout=PIPE, stderr=DEVNULL) as p1:
        p2 = Popen([checksum_program, '-b', '-'], stdin=p1.stdout, stdout=PIPE, stderr=DEVNULL)
        return p2.communicate()[0].decode().split()[0]

def check_converter_args(*args):
    """Check audio format converter arguments.
"""
    infile  = args[0]
    outfile = args[1]
    if not path.isfile(infile):
        raise FileNotFoundError(u'{} not found.'.format(infile))
    if path.isfile(outfile):
        raise FileExistsError(u'{} already exists.'.format(outfile))
    outdir = path.abspath(path.split(outfile)[0])
    if not path.exists(outdir):
        os.makedirs(outdir)
    return infile, outfile, outdir

def dsd_to_aiff(infile, outfile, preset=''):
    arg = ['ffmpeg', '-i', infile]
    if preset.lower() in ['dxd', '384khz/24bit', '384/24', '354.8khz/24bit', '354.8/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=354800', '-c:a', 'pcm_s24be']
    elif preset.lower() in ['192khz/24bit', '192/24', '176.4khz/24bit', '176.4/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=176400', '-c:a', 'pcm_s24be']
    elif preset.lower() in ['hi-res', 'hires', '96khz/24bit', '96/24', '88.2khz/24bit', '88.2/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=88200',  '-c:a', 'pcm_s24be']
    elif preset.lower() in ['cd', '48khz/24bit', '48/24', '44.1khz/24bit', '44.1/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=44100',  '-c:a', 'pcm_s24be']
    arg += ['-f', 'aiff', outfile]
    run(arg, stdout=DEVNULL, stderr=DEVNULL, check=True)

def convert_to_caff(infile, outfile, data_format='LEF32@44100'):
    run(['afconvert', infile,
         '-d', data_format,
         '-f', 'caff',
         '--soundcheck-generate',
         '--src-complexity', 'bats',
         '-r', '127', outfile
    ], check=True)

def caff_to_m4a(infile, outfile, bitrate='256000'):
    run(['afconvert', infile,
         '-d', 'aac',
         '-f', 'm4af',
         '-u', 'pgcm', '2',
         '--soundcheck-read',
         '-b', bitrate,
         '-q', '127',
         '-s', '2', outfile
    ], check=True)

def tag_m4a(metadata_in, audio_in, cover_in, outfile):
    """Tag AAC audio file in m4a format.
"""
    run(['ffmpeg', '-i', metadata_in, '-i', audio_in,
         '-map', '1:a:0', '-c:a', 'copy', '-map_metadata', '0:g:0', outfile
    ], check=True, stdout=DEVNULL, stderr=DEVNULL)

def tag_flac(metadata_in, audio_in, cover_in, outfile):
    """Tag FLAC audio file.
"""
    run(['ffmpeg', '-i', metadata_in, '-i', audio_in, '-i', cover_in,
         '-map', '1:a:0', '-map', '2:v:0',
         '-c:a', 'copy', '-c:v', 'png',
         '-metadata:s:v', 'title=\"Album cover\"',
         '-metadata:s:v', 'comment=\"Cover (front)\"',
         '-map_metadata', '0:g:0', outfile
    ], check=True, stdout=DEVNULL, stderr=DEVNULL)

def dsd_to_itunes(*args):
    """Convert DSD audio file to iTunes Plus AAC audio file.
"""
    infile, outfile, outdir = check_converter_args(*args)
    with TemporaryDirectory(dir=outdir) as tmpdir:
        aiff = path.join(tmpdir, 'a.aif')
        caff = path.join(tmpdir, 'a.caf')
        m4a  = path.join(tmpdir, 'a.m4a')
        dsd_to_aiff(infile, aiff)
        convert_to_caff(aiff, caff)
        caff_to_m4a(caff, m4a)
        tag_m4a(infile, m4a, None, outfile)

def dsd_to_flac(*args, preset='dxd', compression='-5'):
    infile, outfile, outdir = check_converter_args(*args)
    with TemporaryDirectory(dir=outdir) as tmpdir:
        aiff = path.join(tmpdir, 'a.aif')
        flac = path.join(tmpdir, 'a.flac')
        dsd_to_aiff(infile, outfile, preset=preset)
        run(['flac', compression, aiff, '-o', flac], check=True)
        

def flac_to_itunes(*args):
    """Convert FLAC audio file to iTunes Plus AAC audio file.
"""
    infile, outfile, outdir = check_converter_args(*args)
    with TemporaryDirectory(dir=outdir) as tmpdir:
        caff = path.join(tmpdir, 'a.caf')
        m4a  = path.join(tmpdir, 'a.m4a')
        convert_to_caff(infile, caff)
        caff_to_m4a(caff, m4a)
        tag_m4a(infile, m4a, None, outfile)

class audio_track(object):
    def __init__(self, filepath, checksum_program=DEFAULT_CHECKSUM_PROG, do_file_checksum=True, do_audio_stream_checksum=False):
        if not path.isfile(filepath):
            raise FileNotFoundError(u'Audio track file does not exist.'.format(filepath))
        albpath, filename = path.split(path.abspath(filepath))
        extname = path.splitext(filepath)[1]
        if extname.lower() in ['.dsd', '.dsf']:
            self.format = 'DSD'
        elif extname.lower() in ['.aiff', '.aif']:
            self.format = 'AIFF'
        elif extname.lower() in ['.flac']:
            self.format = 'FLAC'
        elif extname.lower() in ['.caf', '.caff']:
            self.format = 'CAFF'
        elif extname.lower() in ['.m4a']:
            self.format = 'M4A'
        else:
            raise TypeError(u'Audio format {} is not supported.'.format(extname))
        self.path = path.abspath(filepath)
        self.filename = filename
        self.parent = albpath
        artpath, albname = path.split(albpath)
        self.album = albname
        libroot, artname = path.split(artpath)
        self.artist = artname
        self.library = libroot
        self.id = hashlib.sha224(path.relpath(self.path, self.library).encode('utf-8')).hexdigest()
        self.parent_id = hashlib.sha224(path.relpath(self.parent, self.library).encode('utf-8')).hexdigest()
        self.checksum = {'program': checksum_program}
        if do_file_checksum:
            self.checksum['file'] = file_checksum(self.path, checksum_program=checksum_program)
        if do_audio_stream_checksum:
            self.checksum['audio'] = audio_stream_checksum(self.path, checksum_program=checksum_program)

    def transcode(self, filepath, preset=None):
        if preset.lower() in ['itunes', 'itunesplus']:
            if self.format == 'DSD':
                dsd_to_itunes(self.path, filepath)
            elif self.format == 'FLAC':
                flac_to_itunes(self.path, filepath)
            else:
                raise TypeError(u'Format not supported yet.')
    def ExtractCoverArt(self, filepath):
        run(['ffmpeg', '-i', self.path,
             '-an', '-c:v', 'png', filepath
        ], check=True, stdout=DEVNULL, stderr=DEVNULL)

class album(list):
    def __init__(self, albpath):
        self.path = path.abspath(albpath)
        artpath, albname = path.split(self.path)
        libroot, artname = path.split(artpath)
        self.artist = artname
        self.name = albname
        self.library = libroot
        self.parent = artpath
        self.id = hashlib.sha224(path.relpath(self.path, libroot).encode('utf-8')).hexdigest()
        self.parent_id = hashlib.sha224(path.relpath(self.parent, libroot).encode('utf-8')).hexdigest()
    def ExtractCoverArt(self, filepath):
        self[0].ExtractCoverArt(filepath)

class artist(list):
    def __init__(self, artpath):
        self.path = path.abspath(artpath)
        libroot, artname = path.split(self.path)
        self.library = libroot
        self.parent = libroot
        self.name = artname
        self.id = hashlib.sha224(path.relpath(self.path, libroot).encode('utf-8')).hexdigest()

class library(object):
    def __init__(self, libroot, outdir):
        self.path = path.abspath(libroot)
        if not path.exists(path.abspath(outdir)):
            os.makedirs(outdir)
        tracks = []
        self.albums = {}
        self.artists = {}
        result = run(['find', libroot,
                      '-type', 'f',
                      '-name', '*.flac', '-or', '-name', '*.dsf'
        ], check=True, stdout=PIPE, stderr=DEVNULL).stdout.decode().split('\n')
        for p in result:
            if path.isfile(p):
                albpath, trkname = path.split(path.abspath(p))
                artpath, albname = path.split(albpath)
                _, artname = path.split(artpath)
                if albpath not in self.albums:
                    a = album(albpath)
                    self.albums[a.id] = a
                if artpath not in self.artists:
                    a = artist(artpath)
                    self.artists[a.id] = a
                tracks.append(p)
        tic = time()
        sys.stdout.write(u'Calculating checksums......')
        sys.stdout.flush()
        with Pool(processes=cpu_count()//2) as pool:
            self.all_tracks = pool.map(audio_track, tracks)
        os.system('stty sane 2>/dev/null')
        sys.stdout.write(u'\rCalculating checksum......Finished. ({:.2f} seconds)\n'.format(time()-tic))
        sys.stdout.flush()
        checksum_save = path.join(path.abspath(outdir), '{}.txt'.format(DEFAULT_CHECKSUM_PROG))
        with open(checksum_save, 'w') as f:
            f.writelines(['{} {}\n'.format(t.id, t.checksum['file']) for t in self.all_tracks])
        print(u'Checksums saved to {}'.format(checksum_save))
        for t in self.all_tracks:
            self.albums[t.parent_id].append(t)
        artsdir = path.join(path.abspath(outdir), 'arts')
        if not path.exists(artsdir):
            os.makedirs(artsdir)
        tic = time()
        sys.stdout.write('Extracting album cover arts......')
        sys.stdout.flush()
        for a in self.albums:
            self.artists[self.albums[a].parent_id].append(self.albums[a])
            self.albums[a].ExtractCoverArt(path.join(artsdir, '{}.png'.format(self.albums[a].id)))
        sys.stdout.write(u'\rExtracting album cover arts......Finished. ({:.2f} seconds)\n'.format(time()-tic))
        sys.stdout.flush()


if __name__ == '__main__':
    action = sys.argv[1]
    opts, args = gnu_getopt(sys.argv[2:], 's:')
    if action.lower() in ['build']:
        for opt, val in opts:
            if opt == '-s':
                srcdir = path.abspath(val)
            else:
                assert False, 'unhandled option'
        outdir = args[0]
        l = library(srcdir, outdir)
        os.system('stty sane 2>/dev/null')
    elif action.lower() in ['help']:
        print(__doc__)
    else:
        assert False, 'unhandled action'
