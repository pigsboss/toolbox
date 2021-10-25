#!/bin/bash
usage="Convert video clip to GIF.
Usage: $(basename $0) [options] DEST
  -i input video clip file.
  -s (optional) resize, in W:H.
  -r (optional) frame rate.
"
while getopts ":hi:o:s:r:" opt; do
    case "${opt}" in
	h)
	    echo "${usage}"
	    exit
	    ;;
	i)
	    inputfile="${OPTARG}"
	    ;;
	s)
	    IFS=':' read -r -a size <<< "${OPTARG}"
	    ;;
	r)
	    fps="${OPTARG}"
	    ;;
	\?)
	    echo "${opt} is not recognized."
	    echo "${usage}"
	    exit
	    ;;
    esac
done
shift $((OPTIND -1))
dest=$@
ffmpeg -i "${inputfile}" -vf "scale=${size[0]}:${size[1]}:flags=lanczos,palettegen=stats_mode=full" palette.png
ffmpeg -i "${inputfile}" -i palette.png -lavfi "fps=${fps},scale=${size[0]}:${size[1]}:flags=lanczos [x]; [x][1:v] paletteuse=dither=sierra2_4a" "${dest}"
