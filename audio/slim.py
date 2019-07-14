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
        radio  (128kbps 44.1kHz VBR MP3).

Copyright: pigsboss@github
"""

import sys
import os
import hashlib
import signal
import pickle
import warnings
from mutagen.dsf import DSF
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from multiprocessing import cpu_count, Pool
from time import time
from os import path
from getopt import gnu_getopt
from subprocess import run, Popen, PIPE, DEVNULL
from tempfile import TemporaryDirectory

DEFAULT_CHECKSUM_PROG = 'sha224sum'
SAFE_PATH_CHARS = ' _'
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

## Reference:
##   https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
##   https://mutagen.readthedocs.io/en/latest/api/vcomment.html#mutagen._vorbis.VCommentDict
TAG_MAP = {
    'ID3': {
        'title'       : 'TIT2',
        'album'       : 'TALB',
        'albumartist' : 'TPE2',
        'artist'      : 'TPE1',
        'conducter'   : 'TPE3',
        'composer'    : 'TCOM',
        'tracknumber' : 'TRCK',
        'discnumber'  : 'TPOS',
        'date'        : 'TDRC',
        'isrc'        : 'TSRC',
        'encoded-by'  : 'TENC',
        'encoder'     : 'TSSE',
        'genre'       : 'TCON',
        'comment'     : 'COMM',
        'copyright'   : 'TCOP',
        'description' : 'TIT3'
    },
    'M4A': {
        'title'       : '\xa9nam',
        'album'       : '\xa9alb',
        'albumartist' : 'aART',
        'artist'      : '\xa9ART',
        'conducter'   : '----:com.apple.iTunes:CONDUCTOR',
        'composer'    : '\xa9wrt',
        'tracknumber' : 'trkn',
        'discnumber'  : 'disk',
        'date'        : '\xa9day',
        'isrc'        : '----:com.apple.iTunes:ISRC',
        'encoded-by'  : '\xa9too',
        'genre'       : '\xa9gen',
        'comment'     : '\xa9cmt',
        'copyright'   : 'cprt',
        'description' : 'desc'
    },
    'Vorbis': {
        'title'       : 'title',
        'album'       : 'album',
        'albumartist' : 'albumartist',
        'artist'      : 'artist',
        'conducter'   : 'conductor',
        'composer'    : 'composer',
        'tracknumber' : 'tracknumber',
        'discnumber'  : 'discnumber',
        'date'        : 'date',
        'isrc'        : 'isrc',
        'encoded-by'  : 'encoded-by',
        'encoder'     : 'encoder',
        'genre'       : 'genre',
        'comment'     : 'comment',
        'copyright'   : 'copyright',
        'description' : 'description'
    }
}

PRESETS = {
    'dxd':    {
        'max_sample_rate'     : 384000,
        'max_bits_per_sample' :     24,
        'format'              : 'FLAC',
        'extension'           : 'flac',
        'art_format'          :  'png',
        'art_resolution'      :     ''
    },
    'ldac':   {
        'max_sample_rate'     :  96000,
        'max_bits_per_sample' :     24,
        'format'              : 'FLAC',
        'extension'           : 'flac',
        'art_format'          :  'png',
        'art_resolution'      :  '800'
    },
    'cd':     {
        'max_sample_rate'     :  48000,
        'max_bits_per_sample' :     24,
        'format'              : 'FLAC',
        'extension'           : 'flac',
        'art_format'          :  'png',
        'art_resolution'      :  '800'
    },
    ## Reference: https://images.apple.com/itunes/mastered-for-itunes/docs/mastered_for_itunes.pdf
    'itunes': {
        'bitrate'             : 256000,
        'format'              :  'M4A',
        'extension'           :  'm4a',
        'art_format'          : 'jpeg',
        'art_resolution'      :  '640'
    },
    'radio':  {
        'max_sample_rate'     :  48000,
        'bitrate'             :    128, ## in kbits/s
        'format'              :  'MP3',
        'extension'           :  'mp3',
        'art_format'          : 'none'
    }
}

def add_cover_art(audio_file, picture_file):
    if audio_file.endswitch('.flac'):
        pass
    elif audio_file.endswitch('.m4a'):
        pass
    elif audio_file.endswitch('.mp3'):
        pass
    else:
        assert False, u'unsupported'

def get_tag(tags, key, scheme):
    return '\n'.join(tags[TAG_MAP[scheme][key]])

def get_albumartist(tags, scheme):
    try:
        a = get_tag(tags, 'albumartist', scheme)
    except KeyError:
        a = get_tag(tags, 'artist', scheme)
    return a

def get_artist(tags, scheme):
    try:
        a = get_tag(tags, 'artist', scheme)
    except KeyError:
        a = get_tag(tags, 'albumartist', scheme)
    return a

def get_tracknumber(tags, scheme):
    tn = get_tag(tags, 'tracknumber', scheme)
    if '/' in tn:
        tn, tt = tn.split('/')
    return int(tn)

def get_discnumber(tags, scheme):
    dn = get_tag(tags, 'discnumber', scheme)
    if '/' in dn:
        dn, dt = dn.split('/')
    return int(dn)

def get_source_file_checksum(audio_file):
    extname = path.splitext(audio_file)[1]
    if extname.lower() == '.flac':
        metadata = FLAC(audio_file)
        scheme = 'Vorbis'
    elif extname.lower() in ['.dsf', '.mp3']:
        metadata = FLAC(audio_file)
        scheme = 'ID3'
    elif extname.lower() == '.m4a':
        metadata = MP4(audio_file)
        scheme = 'M4A'
    else:
        raise TypeError(u'unsupported audio format {}.'.format(extname))
    for cmtline in metadata.tags[TAG_MAP[scheme]['comment']]:
        if 'Source Checksum Program: ' in cmtline:
            prog = cmtline.split(':')[1].strip()
        elif 'Source File Checksum: ' in cmtline:
            csum = cmtline.split(':')[1].strip()
    return {'program': prog, 'checksum': csum}

def set_source_file_checksum(audio_file, csum, program=DEFAULT_CHECKSUM_PROG):
    extname = path.splitext(audio_file)[1]
    if extname.lower() == '.flac':
        metadata = FLAC(audio_file)
        scheme = 'Vorbis'
    elif extname.lower() in ['.dsf', '.mp3']:
        metadata = FLAC(audio_file)
        scheme = 'ID3'
    elif extname.lower() == '.m4a':
        metadata = MP4(audio_file)
        scheme = 'M4A'
    else:
        raise TypeError(u'unsupported audio format {}.'.format(extname))
    if TAG_MAP[scheme]['comment'] in metadata.tags.keys():
        metadata.tags[TAG_MAP[scheme]['comment']] += [
            u'Source Checksum Program: {}'.format(program),
            u'Source File Checksum: {}'.format(csum)
        ]
    else:
        metadata.tags[TAG_MAP[scheme]['comment']]  = [
            u'Source Checksum Program: {}'.format(program),
            u'Source File Checksum: {}'.format(csum)
        ]
    metadata.save()
    return

def file_checksum(filepath, program=DEFAULT_CHECKSUM_PROG):
    """Calculate checksum of input file.
"""
    return run([program, '-b', filepath],
               check=True, stdout=PIPE, stderr=DEVNULL).stdout.decode().split()[0]

def audio_stream_checksum(audio_file, program=DEFAULT_CHECKSUM_PROG):
    """Calculate checksum of audio stream of input file.
"""
    with Popen(["ffmpeg", "-i", audio_file,
                "-vn",
                "-map_metadata", "-1",
                "-f", "aiff", "-"
    ], stdout=PIPE, stderr=DEVNULL) as p1:
        p2 = Popen([program, '-b', '-'], stdin=p1.stdout, stdout=PIPE, stderr=DEVNULL)
        return p2.communicate()[0].decode().split()[0]

def check_converter_args(*args):
    """Check audio format converter arguments.
"""
    infile  = path.normpath(path.abspath(args[0]))
    outfile = path.normpath(path.abspath(args[1]))
    if not path.isfile(infile):
        raise FileNotFoundError(u'{} not found.'.format(infile))
    outdir  = path.split(outfile)[0]
    if not path.exists(outdir):
        os.makedirs(outdir)
    return infile, outfile, outdir

def dsd_to_aiff(infile, outfile, preset=''):
    arg = ['ffmpeg', '-y', '-i', infile]
    if preset.lower() in ['dxd', '384khz/24bit', '384/24', '354.8khz/24bit', '354.8/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=354800', '-c:a', 'pcm_s24be']
    elif preset.lower() in ['192khz/24bit', '192/24', '176.4khz/24bit', '176.4/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=176400', '-c:a', 'pcm_s24be']
    elif preset.lower() in ['ldac', 'hi-res', 'hires', '96khz/24bit', '96/24', '88.2khz/24bit', '88.2/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=88200',  '-c:a', 'pcm_s24be']
    elif preset.lower() in ['cd', '48khz/24bit', '48/24', '44.1khz/24bit', '44.1/24']:
        arg += ['-af', 'aresample=resampler=soxr:precision=32:dither_method=triangular:osr=44100',  '-c:a', 'pcm_s24be']
    arg += ['-f', 'aiff', outfile]
    run(arg, stdout=DEVNULL, stderr=DEVNULL, check=True)
    return

def convert_to_caff(infile, outfile, data_format='LEF32@44100'):
    run(['afconvert', infile,
         '-d', data_format,
         '-f', 'caff',
         '--soundcheck-generate',
         '--src-complexity', 'bats',
         '-r', '127', outfile
    ], check=True)
    return

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
    return

def tag_m4a(metadata_in, audio_in, cover_in, outfile):
    """Tag AAC audio file in m4a format.
"""
    run(['ffmpeg', '-y', '-i', metadata_in, '-i', audio_in,
         '-map', '1:a:0', '-c:a', 'copy', '-map_metadata', '0:g:0', outfile
    ], check=True, stdout=DEVNULL, stderr=DEVNULL)
    return

def tag_flac(metadata_in, audio_in, cover_in, outfile):
    """Tag FLAC audio file.
"""
    run(['ffmpeg', '-y', '-i', metadata_in, '-i', audio_in, '-i', cover_in,
         '-map', '1:a:0', '-map', '2:v:0',
         '-c:a', 'copy', '-c:v', 'png',
         '-metadata:s:v', 'title=\"Album cover\"',
         '-metadata:s:v', 'comment=\"Cover (front)\"',
         '-map_metadata', '0:g:0', outfile
    ], check=True, stdout=DEVNULL, stderr=DEVNULL)
    return

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
    return

def dsd_to_flac(*args, preset='dxd', compression='-5'):
    infile, outfile, outdir = check_converter_args(*args)
    with TemporaryDirectory(dir=outdir) as tmpdir:
        aiff = path.join(tmpdir, 'a.aif')
        flac = path.join(tmpdir, 'a.flac')
        dsd_to_aiff(infile, outfile, preset=preset)
        run(['flac', compression, aiff, '-o', flac], check=True)
    return

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
    return

def find_tracks(srcdir):
    """Find all SONY Music tracks (*.flac and *.dsf).
"""
    result = run(['find', path.abspath(srcdir), '-type', 'f',
                  '-name', '*.flac', '-or', '-name', '*.dsf'
    ], check=True, stdout=PIPE, stderr=DEVNULL)
    tracks = []
    for p in result.stdout.decode().splitlines():
        if path.isfile(p):
            tracks.append(p)
    return tracks

def metadata_from_path(p):
    """Guess audio file metadata from its path.
"""
    m = {}
    parent, filename = path.split(path.normpath(path.abspath(p)))
    if ' - ' in filename:
        segs = path.splitext(filename)[0].split(' - ')
        tracknumber = segs[0]
        title = ' - '.join(segs[1:])
    elif ' ' in filename:
        segs = path.splitext(filename)[0].split()
        tracknumber = segs[0]
        title = ' '.join(segs[1:])
    else:
        title = path.splitext(filename)[0]
        m['tracknumber'] = None
        tracknumber = None
    if '.' in tracknumber:
        discnumber, tracknumber = tracknumber.split('.')
        m['discnumber'] = int(discnumber)
        m['tracknumber'] = int(tracknumber)
    if '/' in tracknumber:
        tracknumber, totaltracks = tracknumber.split('/')
        m['totaltracks'] = int(totaltracks)
        m['tracknumber'] = int(tracknumber)
    m['title'] = title
    artpath, albname = path.split(parent)
    _, artname = path.split(artpath)
    m['albumartist'] = artname
    m['album'] = albname
    return m

class AudioTrack(object):
    def __init__(self, filepath):
        ## examine path
        if not path.isfile(filepath):
            raise FileNotFoundError(u'Audio track file does not exist.'.format(filepath))
        self.source = path.normpath(path.abspath(filepath))
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
            return '{:d}.{:02d} - {}'.format(self.metadata['discnumber'], self.metadata['tracknumber'], genpath(self.metadata['title']))
        except ValueError:
            return '{:02d} - {}'.format(self.metadata['tracknumber'], genpath(self.metadata['title']))

    def GenParentPath(self):
        if not hasattr(self, 'metadata'):
            self.UpdateMetadata()
        return path.join(genpath(self.metadata['albumartist']), genpath(self.metadata['album']))

    def GenPath(self):
        return path.join(self.GenParentPath(), self.GenFilename())

    def UpdateFileChecksum(self, program=DEFAULT_CHECKSUM_PROG):
        self.file_checksum = {
            'program': program, 'checksum': file_checksum(self.source, program=program)}
        return self.file_checksum

    def UpdateAudioStreamChecksum(self, program=DEFAULT_CHECKSUM_PROG):
        self.audio_stream_checksum = {
            'program': program, 'checksum': audio_stream_checksum(self.source, program=program)}
        return self.audio_stream_checksum

    def UpdateMetadata(self):
        if self.format == 'DSD':
            scheme = 'ID3'
            metadata = DSF(self.source)
        elif self.format == 'FLAC':
            scheme = 'Vorbis'
            metadata = FLAC(self.source)
        else:
            assert False, 'unsupported format {}.'.format(self.formmat)
        self.metadata = {}
        self.metadata['albumartist'] = get_albumartist(metadata, scheme)
        self.metadata['tracknumber'] = get_tracknumber(metadata, scheme)
        self.metadata['artist']      = get_artist(metadata, scheme)
        self.metadata['album']       = get_tag(metadata, 'album', scheme)
        self.metadata['title']       = get_tag(metadata, 'title', scheme)
        try:
            self.metadata['discnumber'] = get_discnumber(metadata, scheme)
        except KeyError:
            self.metadata['discnumber'] = ''
        for key in ['conductor', 'composer', 'isrc', 'encoded-by', 'genre', 'comment', 'copyright', 'description']:
            try:
                self.metadata[key] = get_tag(metadata, key, scheme)
            except KeyError:
                self.metadata[key] = ''
        self.metadata['info'] = {
            'sample_rate'     : metadata.info.sample_rate,
            'bits_per_sample' : metadata.info.bits_per_sample,
            'channels'        : metadata.info.channels,
            'bitrate'         : metadata.info.bitrate,
            'length'          : metadata.info.length
        }
        return self.metadata

    def Export(self, filepath, preset, exists):
        """Export this audio track with specified preset.
"""
        if not hasattr(self, 'file_checksum'):
            self.UpdateFileChecksum()
        if path.isfile(filepath):
            if exists.lower()[0] == 's':
                ## skip
                return
            elif exists.lower()[0] == 'u':
                ## update
                if self.file_checksum == get_source_file_checksum(filepath):
                    return
        if preset.lower() in ['dxd']:
            pass
        elif preset.lower() in ['ldac']:
            pass
        elif preset.lower() in ['cd']:
            pass
        elif preset.lower() in ['itunes']:
            if self.format == 'DSD':
                dsd_to_itunes(self.source, filepath)
            elif self.format == 'FLAC':
                flac_to_itunes(self.source, filepath)
            else:
                raise TypeError(u'Format not supported yet.')
            
        elif preset.lower() in ['radio']:
            pass
        else:
            raise TypeError(u'unsupported preset {}.'.format(preset))
        set_source_file_checksum(filepath, self.file_checksum['checksum'], program=self.file_checksum['program'])
        return

    def ExtractCoverArt(self, filepath):
        run(['ffmpeg', '-y', '-i', self.source,
             '-an', '-c:v', 'png', filepath
        ], check=True, stdout=DEVNULL, stderr=DEVNULL)
        

    def Print(self):
        print('    {:<20}: {:<80}'.format('Source',                self.source))
        print('    {:<20}: {:<80}'.format('Format',                self.format))
        print('    {:<20}: {:<80}'.format('Disc No.',              self.metadata['discnumber']))
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
        self[0].ExtractCoverArt(path.join(prefix, '{}.png'.format(self.id)))

class Library(object):
    """SONY Music Library.
"""
    def build(self, libroot, outdir):
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
        self.ExtractCoverArts()
        self.SaveChecksum()
        return

    def ImportTracks(self, tracks):
        """Import SONY Music tracks.
"""
        tic = time()
        new_tracks = []
        sys.stdout.write(u'Importing audio tracks......')
        sys.stdout.flush()
        with Pool(processes=cpu_count()//2) as pool:
            new_tracks = pool.map(AudioTrack, tracks)
##      for t in tracks:
##          new_tracks.append(AudioTrack(t))
        run(['stty', 'sane'], stdout=DEVNULL, stderr=DEVNULL)
        sys.stdout.write(u'\rImport audio tracks......Finished. ({:.2f} seconds)\n'.format(time()-tic))
        sys.stdout.flush()
        for t in new_tracks:
            if t.id not in self.tracks:
                self.tracks[t.id] = t
                if t.parent_id not in self.albums:
                    self.albums[t.parent_id] = Album(title=t.metadata['album'], artist=t.metadata['albumartist'])
                self.albums[t.parent_id].append(t)
        return

    def ExtractCoverArts(self):
        """Extract album cover arts.
"""
        if not path.exists(self.arts_path):
            os.makedirs(self.arts_path)
        tic = time()
        sys.stdout.write('Extracting album cover arts......')
        sys.stdout.flush()
        with Pool(processes=cpu_count()//2) as pool:
            pool.starmap(Album.ExtractCoverArt, zip(self.albums.values(), [self.arts_path]*len(self.albums)))
        run(['stty', 'sane'], stdout=DEVNULL, stderr=DEVNULL)
        sys.stdout.write(u'\rExtracting album cover arts......Finished. ({:.2f} seconds)\n'.format(time()-tic))
        sys.stdout.flush()
        return

    def SaveChecksum(self):
        """Save checksums of tracks to specified path.
"""
        with open(self.checksum_path, 'w') as f:
            f.writelines(['{} {}\n'.format(t.id, t.file_checksum['checksum']) for t in self.tracks.values()])
            print(u'Checksums saved to {}'.format(self.checksum_path))
        return

    def Update(self):
        """Update pre-built SONY Music Library.
"""
        tracks = find_tracks(self.source_path)
        return

    def Export(self, match=None, prefix=None, preset='dxd', exists='skip'):
        """Export matched tracks.
"""
        if match is None:
            artist_match = ''
            album_match = ''
            track_match = ''
        else:
            artist_match, album_match, track_match = match.split('/')
        ## prepare albums
        for a in self.albums.values():
            if artist_match in a.artist and album_match in a.title:
                if not path.exists(path.join(prefix, a.GenPath())):
                    os.makedirs(path.join(prefix, a.GenPath()))
                try:
                    args = [
                        'convert',
                        path.join(self.arts_path, '{}.png'.format(a.id)),
                        '-resize', '{:d}px\\>'.format(PRESETS[preset]['art_resolution']),
                        path.join(prefix, a.GenPath(), 'cover.{}'.format(PRESETS[preset]['art_format']))
                    ]
                except ValueError:
                    args = [
                        'convert',
                        path.join(self.arts_path, '{}.png'.format(a.id)),
                        path.join(prefix, a.GenPath(), 'cover.{}'.format(PRESETS[preset]['art_format']))
                    ]
                run(args, check=True, stdout=DEVNULL, stderr=DEVNULL)
        for t in self.tracks.values():
            if artist_match in t.metadata['albumartist'] and album_match in t.metadata['album'] and track_match in t.GenFilename():
                t.Export(u'{}.{}'.format(path.join(prefix, t.GenPath()), PRESETS[preset]['extension']), preset, exists)
        return

    def Print(self, match=None, verbose=False):
        """Print matched albums and audio tracks.
"""
        if match is None:
            artist_match = ''
            album_match = ''
            track_match = ''
        else:
            artist_match, album_match, track_match = match.split('/')
        for a in self.albums.values():
            if artist_match in a.artist and album_match in a.title:
                print(u'{}/{}:'.format(a.artist, a.title))
                for t in a:
                    if track_match in t.GenFilename():
                        try:
                            print(u'  [{:<4}] {:d}.{:02d} - {}'.format(t.format, t.metadata['discnumber'], t.metadata['tracknumber'], t.metadata['title']))
                        except ValueError:
                            print(u'  [{:<4}] {:02d} - {}'.format(t.format, t.metadata['tracknumber'], t.metadata['title']))
                        if verbose:
                            t.Print()
        return

def save_library(obj, to_path):
    with open(to_path, 'wb') as f:
        pickle.dump(obj, f)
    return

def load_library(from_path):
    with open(from_path, 'rb') as f:
        return pickle.load(f)

def main():
    action = sys.argv[1]
    opts, args = gnu_getopt(sys.argv[2:], 'vm:s:p:o:e:')
    verbose = False
    matched = None
    exists  = 'skip'
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
        else:
            assert False, 'unhandled option'
    if action.lower() in ['build']:
        outdir = path.normpath(path.abspath(args[0]))
        l = Library()
        l.build(srcdir, path.abspath(outdir))
        save_library(l, path.join(outdir, 'main.db'))
    elif action.lower() in ['help']:
        print(__doc__)
    elif action.lower() in ['print']:
        l = load_library(args[0])
        l.Print(match=matched, verbose=verbose)
    elif action.lower() in ['export']:
        l = load_library(args[0])
        l.Export(match=matched, preset=preset, prefix=path.normpath(path.abspath(output)), exists=exists)
    else:
        assert False, 'unhandled action'
    return

if __name__ == '__main__':
    main()
