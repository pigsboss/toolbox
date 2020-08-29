#!/bin/bash
LV=$1
PV=$2
SIZE=$3
CMD=$4
LVNAME=$(basename $LV)
SVNAME="$LVNAME"_backup
echo "creating snapshot volume..."
lvcreate -L$SIZE -n $SVNAME -s $LV $PV
if [ ! -d /mnt/lvsnapshots/$SVNAME ]; then
    mkdir -p /mnt/lvsnapshots/$SVNAME
fi
sleep 3
echo "mounting snapshot volume..."
mount /dev/vg/$SVNAME -o ro /mnt/lvsnapshots/$SVNAME
sleep 3
echo "executing post-snap command..."
eval $4
sleep 3
echo "unmounting snapshot volume..."
umount /dev/vg/$SVNAME
sleep 3
echo "removing snapshot volume..."
lvremove -f /dev/vg/$SVNAME
