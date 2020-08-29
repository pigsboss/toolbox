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
else
    echo "TimeCap config file is missing."
    echo "Use default configuration."
    SRCNAME=$(basename $SRC)
    MAXDEPTH=7
fi
echo "Name: $SRCNAME"
echo "Maximum depth: $MAXDEPTH"
SNAR=$(readlink -f $DEST/$SRCNAME.snar)
if [ -f $SNAR ]; then
    echo "Found snapshot file $SNAR of incremental backups."
    LATEST=$(readlink -f $DEST/$SRCNAME-latest.tar)
    LASTDEPTH=$(basename -s .tar $LATEST|grep -o -E '[0-9]+')
    echo "Found previous backup $LATEST (depth: $LASTDEPTH)."
else
    LASTDEPTH=-1
fi
if [ $((LASTDEPTH+1)) -lt $MAXDEPTH ]; then
    CURDEPTH=$((LASTDEPTH+1))
    cd $SRC
    tar -c -g $SNAR -f $DEST/$SRCNAME-$CURDEPTH.tar ./
    ln -sf $DEST/$SRCNAME-$CURDEPTH.tar $DEST/$SRCNAME-latest.tar
else
    CURDEPTH=0
    cd $SRC
    tar -c -g $SNAR.new -f $DEST/$SRCNAME-$CURDEPTH.tar ./
    mv $SNAR.new $SNAR
    ln -sf $DEST/$SRCNAME-$CURDEPTH.tar $DEST/$SRCNAME-latest.tar
fi
echo "Created $CURDEPTH-depth backup $(readlink -f $DEST/$SRCNAME-latest.tar)."

