#!/bin/bash
while getopts ":s:d:" arg; do
    case $arg in
	s)
	    backup_obj=${OPTARG}
	    ;;
	d)
	    backup_vol=${OPTARG}
	    ;;
	*)
	    exit 0
	    ;;
    esac
done
if mountpoint -q "${backup_vol}"; then
    echo "${backup_vol} is mounted."
else
    mount "$backup_vol"
    echo "$backup_vol is mounted."
fi
datetime=$(date +%Y%m%d-%H%M%S)
lv=$(basename ${backup_obj}).$datetime
vg=$(dirname ${backup_obj})
echo $lv
/sbin/lvcreate -L100g -n"${lv}" -s "${backup_obj}"
mkdir /mnt/${lv}
mount $vg/$lv -o ro /mnt/${lv}
tar -cpf $backup_vol/$(hostname).$lv.tar --xattrs-include="*.*" --numeric-owner --one-file-system -C /mnt/${lv} ./
umount /mnt/${lv}
rmdir /mnt/${lv}
/sbin/lvremove -f "${vg}/${lv}"
