#!/bin/bash
DEFAULT_DEST=/home/svn/backups
SVNROOT=/home/svn/repos
DATE=$(date +%Y%m%d_%H%M%S)
#DATE=$(date +%Y%m%d)
COMPRESSOR='gzip'
COMPFORMAT='gz'
if [ -z $1 ]
then
    DEST=$DEFAULT_DEST
else
    DEST=$1
fi
echo Dump svn repositories to $DEST:
echo -------------------------------
cd $SVNROOT
echo svn root directory is $(pwd).
for REPOS in $(ls)
do
    if [ -d $REPOS ]
    then
	echo Verifying svn repository $REPOS...
	if svnadmin verify -q $REPOS
	then
	    echo Dumping svn repository $REPOS...
	    LATESTDUMP=$DEST/$REPOS-$DATE.dump.$COMPFORMAT
	    svnadmin dump -q $REPOS | $COMPRESSOR -c > $LATESTDUMP
	    if [ -f $DEST/$REPOS-latest.dump.$COMPFORMAT ]; then
		echo Compressing previous dump...
		LASTDUMP=$(readlink $DEST/$REPOS-latest.dump.$COMPFORMAT)
		xdelta3 -q -s $LATESTDUMP $LASTDUMP $LASTDUMP.vcdiff
		rm $LASTDUMP
	    fi
	    ln -sf $LATESTDUMP $DEST/$REPOS-latest.dump.$COMPFORMAT
	    echo Archiving svn repository database $REPOS...
	    LATESTDB=$DEST/$REPOS-$DATE.db.tar.$COMPFORMAT
	    tar cf - $REPOS | $COMPRESSOR -c > $LATESTDB
	    if [ -f $DEST/$REPOS-latest.db.tar.$COMPFORMAT ]; then
		echo Compressing previous database...
		LASTDB=$(readlink $DEST/$REPOS-latest.db.tar.$COMPFORMAT)
		xdelta3 -q -s $LATESTDB $LASTDB $LASTDB.vcdiff
		rm $LASTDB
	    fi
	    ln -sf $LATESTDB $DEST/$REPOS-latest.db.tar.$COMPFORMAT
	else
	    echo $REPOS is not a valid repository.
	fi
    fi
done
