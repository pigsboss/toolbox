#!/usr/bin/env python
import mutagen
import sys
metadata=mutagen.File(sys.argv[1])
objdata=mutagen.File(sys.argv[2])
objdata.update(metadata)
objdata.save()
