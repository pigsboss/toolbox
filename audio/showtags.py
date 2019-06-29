#!/usr/bin/env python
import mutagen
import sys
metadata=mutagen.File(sys.argv[1])
print(metadata)
