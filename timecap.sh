#!/bin/bash
DATE=$(date +%Y%m%d-%H%M%S)
SRC=$(readlink -f $1)
DEST=$(readlink -f $2)
if [ ! -d $SRC ]; then
    echo "Invalid source directory: $SRC"
    exit 1
fi
if [ ! -d $DEST ]; then
    echo "Invalid destination directory: $DEST"
    exit 1
fi
CFGFILE=$SRC/.timecap
if [ -f $CFGFILE ]; then
    source $CFGFILE
    echo $MAXDEPTH
    echo $SRCNAME
else
    echo "TimeCap config file is missing."
    echo "Please create a config file ($CFGFILE) first."
    exit 1
fi
LATEST=$(readlink -f $DEST/$SRCNAME-latest.tar)
if [ -f $LATEST ]; then
    echo "Find previous backup $LATEST"
    

