#!/bin/bash
usage="Convert video clip to GIF.
Usage: $(basename $0) [options] DEST
  -i input video clip file.
  -s (optional) resize, in W:H.
  -r (optional) frame rate.
  -b (optional) input video clip begins at position.
  -t (optional) limit input video clip to duration.
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
	b)
	    ssopt=("-ss" "${OPTARG}")
	    ;;
	t)
	    topt=("-t" "${OPTARG}")
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
ffmpeg -i "${inputfile}" ${ssopt[@]} ${topt[@]} -vf "scale=${size[0]}:${size[1]}:flags=lanczos,palettegen=stats_mode=full" palette.png
ffmpeg -i "${inputfile}" -i palette.png ${ssopt[@]} ${topt[@]} -lavfi "fps=${fps},scale=${size[0]}:${size[1]}:flags=lanczos [x]; [x][1:v] paletteuse=dither=sierra2_4a" "${dest}"
