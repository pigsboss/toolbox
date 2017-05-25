#!/usr/bin/env python
import piexif
import sys
exif_dict = piexif.load(sys.argv[1])
for tag in exif_dict["GPS"]:
    print tag
    print(piexif.TAGS["GPS"][tag]["name"], exif_dict["GPS"][tag])
