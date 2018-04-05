#!/usr/bin/env python
"""Copy GeoTags from reference photos.

Syntax:
CopyGeoTags.py reference target [method]

reference - reference photo(s). Single file or directory.
target    - photo(s) that need GeoTags. Single file or directory.
method    - optional. Interpolation method, e.g., nearest, linear, cubic.

"""
SupportedFileExt = ['.jpg','.jpeg']
R = 6400.0e3
import piexif
import numpy as np
import sys
import os
from os import path
from fractions import Fraction
from datetime import datetime
from scipy.interpolate import interp1d

def float2rational(f):
    F = Fraction(f).limit_denominator()
    return (F.numerator, F.denominator)

def dd2dms(dd):
    mnt, sec = divmod(dd*3600.0, 60)
    deg, mnt = divmod(mnt, 60)
    return deg, mnt, sec

def exiftag2timestamp(exiftag):
    try:
        return (
            datetime.strptime(exiftag[0x9003],
                              r'%Y:%m:%d %H:%M:%S')-
            datetime.strptime("1970-01-01T00:00:00",
                              r'%Y-%m-%dT%H:%M:%S')
        ).total_seconds()
    except KeyError:
        return None

def geotag2xyzt(geotag):
    try:
        latref      = geotag[0x0001]
        lattuple    = geotag[0x0002]
        lonref      = geotag[0x0003]
        lontuple    = geotag[0x0004]
        altref      = geotag[0x0005]
        alttuple    = geotag[0x0006]
        HH,MM,SS    = geotag[0x0007]
        lat = np.deg2rad(
            lattuple[0][0]/   1.0/lattuple[0][1]+
            lattuple[1][0]/  60.0/lattuple[1][1]+
            lattuple[2][0]/3600.0/lattuple[2][1]
        )
        if latref == 'S':
            lat = 0 - lat
        lon = np.deg2rad(
            lontuple[0][0]/   1.0/lontuple[0][1]+
            lontuple[1][0]/  60.0/lontuple[1][1]+
            lontuple[2][0]/3600.0/lontuple[2][1]            
        )
        if lonref == 'W':
            lon = 0 - lon
        alt = alttuple[0]*1.0/alttuple[1]
        if altref == 1:
            alt = 0 - alt
        x = np.cos(lon)*np.cos(lat)*(R+alt)
        y = np.sin(lon)*np.cos(lat)*(R+alt)
        z = np.sin(lat)*(R+alt)
        t = HH[0]*3600.0/HH[1] + MM[0]*60.0/MM[1] + SS[0]*1.0/SS[1] + (
            datetime.strptime(geotag[0x001d],r'%Y:%m:%d')-datetime(1970,1,1,0,0,0)
        ).total_seconds()
        return x,y,z,t
    except KeyError:
        return None

try:
    method = sys.argv[3]
except IndexError:
    method = 'nearest'

ts = []
rs = []
if path.isdir(sys.argv[1]):
    for f in os.listdir(sys.argv[1]):
        if path.splitext(f)[1].lower() in SupportedFileExt:
            f = path.join(sys.argv[1],f)
            d = piexif.load(f)
            t = exiftag2timestamp(d['Exif'])
            r = geotag2xyzt(d['GPS'])
            if r is not None:
                ts.append(t)
                rs.append(r)
            else:
                print 'Missing datetime and/or GPS data in {}.'.format(f)
elif path.isfile(sys.argv[1]):
    f = sys.argv[1]
    d = piexif.load(f)
    t = exiftag2timestamp(d['Exif'])
    r = geotag2xyzt(d['GPS'])
    if r is not None:
        ts.append(t)
        rs.append(r)
    else:
        print 'Missing datetime and/or GPS data in {}.'.format(f)
if len(ts) == 0:
    raise StandardError('No reference found.')
elif len(ts) == 1:
    xfunc = lambda t:rs[0][0]
    yfunc = lambda t:rs[0][1]
    zfunc = lambda t:rs[0][2]
    tfunc = lambda t:t-(ts[0]-rs[0][3])
else:
    xfunc = interp1d(np.double(ts), np.double(rs)[:,0], kind=method, bounds_error=False, fill_value='extrapolate')
    yfunc = interp1d(np.double(ts), np.double(rs)[:,1], kind=method, bounds_error=False, fill_value='extrapolate')
    zfunc = interp1d(np.double(ts), np.double(rs)[:,2], kind=method, bounds_error=False, fill_value='extrapolate')
    ofunc = interp1d(np.double(ts), np.double(ts)-np.double(rs)[:,3], kind='nearest', bounds_error=False, fill_value='extrapolate')
    tfunc = lambda t:t-ofunc(t)
targets = []
if path.isdir(sys.argv[2]):
    for f in os.listdir(sys.argv[2]):
        if path.splitext(f)[1].lower() in SupportedFileExt:
            targets.append(path.join(sys.argv[2],f))
elif path.isfile(sys.argv[2]):
    targets.append(sys.argv[2])
for f in targets:
    d = piexif.load(f)
    t = exiftag2timestamp(d['Exif'])
    x = xfunc(t)
    y = yfunc(t)
    z = zfunc(t)
    utc = tfunc(t)
    r = float(sum((x**2.0,y**2.0,z**2.0))**0.5)
    alt = r-R
    lat = np.rad2deg(np.arcsin(z/r))
    lon = np.rad2deg(np.arctan2(y,x))
    if lat<0:
        latref = 'S'
        lat = abs(lat)
    else:
        latref = 'N'
    if lon<0:
        lonref = 'W'
        lon = abs(lon)
    else:
        lonref = 'E'
    if alt<0:
        altref = 1
        alt = abs(alt)
    else:
        altref = 0
    dd,mm,ss = dd2dms(lon)
    lontuple = (float2rational(dd),float2rational(mm),float2rational(ss))
    dd,mm,ss = dd2dms(lat)
    lattuple = (float2rational(dd),float2rational(mm),float2rational(ss))
    alttuple = float2rational(alt)
    dt = datetime.fromtimestamp(utc)
    timetuple = ((dt.hour,1),(dt.minute,1),(dt.second*1000+dt.microsecond/1000,1000))
    datestr   = datetime(dt.year,dt.month,dt.day).strftime(r'%Y:%m:%d')
    gps_ifd = {
        piexif.GPSIFD.GPSVersionID: (2,0,0,0),
        piexif.GPSIFD.GPSLatitudeRef: latref,
        piexif.GPSIFD.GPSLatitude: lattuple,
        piexif.GPSIFD.GPSLongitudeRef: lonref,
        piexif.GPSIFD.GPSLongitude: lontuple,
        piexif.GPSIFD.GPSAltitudeRef: altref,
        piexif.GPSIFD.GPSAltitude: alttuple,
        piexif.GPSIFD.GPSTimeStamp: timetuple,
        piexif.GPSIFD.GPSDateStamp: datestr,
    }
    d['GPS'] = gps_ifd
    piexif.insert(piexif.dump(d), f)
