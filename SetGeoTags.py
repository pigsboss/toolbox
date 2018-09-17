#!/usr/bin/env python
"""Insert GPS tags to the photo.

Syntax:
python SetGeoTags.py latitude longtitude altitude|"" filename

latitude  is a decimal number suffixed a letter 'S' or 'N'.
longitude is a decimal number suffixed a letter 'E' or 'W'.
altitude  is a decimal number or a null string "".

Requirements: piexif and PIL

Author: pigsboss@github
"""

from PIL import Image
from fractions import Fraction
import piexif
import sys

def float2rational(f):
    F = Fraction(f).limit_denominator()
    return (F.numerator, F.denominator)

def dd2dms(dd):
    mnt, sec = divmod(dd*3600.0, 60)
    deg, mnt = divmod(mnt, 60)
    return deg, mnt, sec

try:
    lat_str  = sys.argv[1]
    lon_str  = sys.argv[2]
    alt_str  = sys.argv[3]
    filename = sys.argv[4]
except:
    print __doc__
    raise StandardError("Syntax error.")

lon_ref = lon_str[-1]
lon_val = float(lon_str[:-1])
lat_ref = lat_str[-1]
lat_val = float(lat_str[:-1])
if len(alt_str) > 0:
    alt_ref = 0
    alt_val = float(alt_str)
else:
    alt_ref = None
    alt_val = None

d,m,s = dd2dms(lon_val)
lon_tuple = (float2rational(d), float2rational(m), float2rational(s))
d,m,s = dd2dms(lat_val)
lat_tuple = (float2rational(d), float2rational(m), float2rational(s))

exif_dict = piexif.load(filename)
gps_ifd = {
    piexif.GPSIFD.GPSVersionID: (2,0,0,0),
    piexif.GPSIFD.GPSLatitudeRef: lat_ref,
    piexif.GPSIFD.GPSLatitude: lat_tuple,
    piexif.GPSIFD.GPSLongitudeRef: lon_ref,
    piexif.GPSIFD.GPSLongitude: lon_tuple,
}
if alt_ref is not None:
    gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = alt_ref
    gps_ifd[piexif.GPSIFD.GPSAltitude] = float2rational(alt_val)

exif_dict["GPS"] = gps_ifd
exif_bytes = piexif.dump(exif_dict)
piexif.insert(exif_bytes, filename)
